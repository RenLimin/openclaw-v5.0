# L2 配置管理组件 — 设计

> **状态**: ✅ 已上线 (2026-08-22) — ADR-007 已实现,快照 + 四步流程 + 漂移检测
> **ADR**: [ADR-202608-007](../../../knowledge-base/by-category/project-experience/adr/ADR-202608-007-config-management.md)
> **层级**: L2 基础设施层
> **创建**: 2026-08-22

## 1. 问题定义

L1（OpenClaw）已提供完整的配置读写能力：`openclaw config get/patch/validate`、
schema 校验、`.bak` 轮转备份、SecretRef 解析。**本组件不重新实现这些**。

真实缺口是**治理**层面的四个问题，都有已发生的事故背书：

| # | 问题 | 已发生的事故 | 代价 |
|---|---|---|---|
| P1 | **变更不可追溯** | 2026-08-21 `compaction.model` 被自身后续操作静默覆盖 | 只能靠 `.bak*`（仅 5 份轮转）逆向追查 |
| P2 | **"应用成功"≠"生效"** | 同上 —— `Applied 3 config update(s)` 正常返回后被覆盖 | 误报成功，事故延迟发现 |
| P3 | **能力声明靠推断** | `minimax-m3` 误设 512000（引用直连 API 的限制）、`ark-code-latest` 误设 262144 | 浪费容量 / 真实溢出 |
| P4 | **配置漂移无人发现** | `.git/hooks/` 不入版本控制，clone 后 hook 静默丢失 | 保护机制失效而无感 |

**核心洞察**：配置管理的难点不在"怎么改"，而在**"改完怎么确认真的改了，以及以后怎么发现它被改回去"**。

## 2. 设计原则

1. **不重新实现 L1**。只做 L1 之上的治理封装，严禁绕过 `openclaw config` 走裸文件写入。
2. **可追溯优于可回滚**。`.bak` 提供回滚，但不回答"谁改的、为什么"。快照入 git 补上这一半。
3. **验证必须读回**。任何写入后强制 read-back 比对，不信命令返回值。
4. **凭据零外泄**。快照脱敏用精确字段名匹配，凭据本体只留在 `~/.openclaw/secrets/`（600）。
5. **漂移可检测**。所有"应该保持一致"的东西（hook、快照）都要有 `--check` 模式供 CI/hook 调用。

## 3. 组件构成

```
配置管理组件
├── 变更流程规范        docs/conventions/commit-and-config.md
├── 配置快照            scripts/snapshot_config.py       → config-snapshots/
├── 能力实测            scripts/probe_context_window.py
├── hook 漂移检测        scripts/install-hooks.sh --check
└── 统一入口            scripts/config.sh                 ← 本次新增
```

### 3.1 变更流程（对应 P2）

四步，缺一不可：

```bash
openclaw config patch --file <patch> --dry-run   # 1. 验证
openclaw config patch --file <patch>             # 2. 应用
openclaw config get <path> && openclaw config validate   # 3. 读回确认 ★
bash scripts/config.sh snapshot                  # 4. 快照入库
```

第 3 步是 P1/P2 事故的直接教训：**只有读回才算验证**。

### 3.2 配置快照（对应 P1）

`scripts/snapshot_config.py` 把 `~/.openclaw/openclaw.json` 脱敏后导出到
`config-snapshots/openclaw.json`，纳入 git。

**脱敏策略**（关键设计）：用**精确字段名**匹配，不用子串。

```python
SECRET_KEYS = {"apikey", "token", "secret", "password", "credential", ...}
KEEP_KEYS   = {"maxtokens", "keeprecenttokens", "maxtokensfield", ...}
```

> ⚠️ **踩过的坑**：首版用子串匹配（`"token" in key`），把 `maxTokens`、
> `keepRecentTokens` 全脱敏成 `<REDACTED>` —— 而这些正是最需要 diff 的容量参数，
> 等于毁掉了快照的价值。**必须精确匹配 + 显式白名单。**

实测结果：仅 3 处真凭据被脱敏，所有 `contextWindow` / `maxTokens` / compaction 策略完整保留。

### 3.3 能力实测（对应 P3）

`scripts/probe_context_window.py` — 二分探边界，实测模型真实 `contextWindow`。

**为什么必须实测**（三类文档失效模式）：

| 失效模式 | 案例 |
|---|---|
| 文档描述的是直连 API，非转售通道 | MiniMax 直连拒绝 >512000，但 ARK 通道支持 1M |
| 启用条件不适用于转售通道 | 智谱要求 `glm-5.3[1m]` 后缀，ARK 端点无需 |
| 官方 CLI 查不到尝鲜/别名模型 | `arkcli models get glm-5.3` 返回 `{ok:false}` |

**关键区分**：`context_window`（输入+输出总和）≠ `max_input_token_length`（输入侧上限）。
OpenClaw 的 `contextWindow` 用于判断历史容量，**应对齐 max_input**。
`ark-code-latest` 就是因为忽略这点而误设 262144（真值 229376）。

### 3.4 漂移检测（对应 P4）

| 对象 | 检测命令 | 失效后果 |
|---|---|---|
| git hooks | `bash scripts/install-hooks.sh --check` | 资产清单/快照提醒失效 |
| 配置快照 | `python3 scripts/snapshot_config.py --check` | 变更无记录 |

两者都接入 `.git/hooks/pre-commit`，提交时自动提醒（**不阻塞**——保护机制不该妨碍工作）。

### 3.5 统一入口

`scripts/config.sh` 把上述操作收敛为一致的动词，对齐 `credentials.sh` 的范式：

```bash
bash scripts/config.sh audit      # 全面审计：快照一致性 + hook 漂移 + 配置校验 + 凭据引用
bash scripts/config.sh snapshot   # 快照入库
bash scripts/config.sh diff       # 当前配置 vs 上次快照
bash scripts/config.sh apply <f>  # 四步流程：dry-run → apply → 读回 → 快照
bash scripts/config.sh probe <m>  # 实测模型 contextWindow
```

`apply` 子命令把四步流程**固化成代码**，杜绝人为跳过第 3 步。

## 4. 契约（提供给 L3）

L3 不直接读 `~/.openclaw/openclaw.json`。稳定接口：

| 接口 | 形式 | 稳定性 |
|---|---|---|
| 配置审计 | `scripts/config.sh audit`，退出码 0=健康 / 1=有问题 | 稳定 |
| 配置快照 | `config-snapshots/openclaw.json`（脱敏，可安全读取） | 稳定 |
| 变更流程 | `scripts/config.sh apply <patch-file>` | 稳定 |

**不承诺**：`~/.openclaw/openclaw.json` 的内部结构（属 L1，会随 OpenClaw 升级变化）。

## 5. 验证

```bash
bash scripts/config.sh audit          # 期望：全绿，退出码 0
python3 scripts/snapshot_config.py --check
bash scripts/install-hooks.sh --check
openclaw config validate
```

**已验证事项**：
- ✅ 脱敏正确性：3 处凭据脱敏，容量参数完整保留（`git show HEAD:config-snapshots/openclaw.json`）
- ✅ 推送前凭据扫描：`ark-*`/`sk-*`/`ghp_`/`tvly-*`/`Bearer`/`BEGIN` 全无命中
- ✅ hook 一致性：`install-hooks.sh --check` 通过
- ✅ 实测脚本：glm-5.3 边界定位到 1,048,568 通过 / 1,048,618 拒绝

## 6. 监控点

- ⚠️ OpenClaw 升级后 `openclaw config` 子命令行为可能变化 → 重跑 `config.sh audit`
- ⚠️ 新增 provider/plugin 时确认其凭据字段名被 `SECRET_KEYS` 覆盖，否则会泄漏进快照
- ⚠️ 新增模型时**先 probe 再声明 ctx**，不要照抄兄弟模型
- ⚠️ `config-snapshots/` 与实际配置长期不一致 → 说明有人绕过流程直接改文件

## 7. 未来演进

| 阶段 | 内容 | 触发条件 |
|---|---|---|
| 阶段 1（当前） | 快照 + 审计 + 实测 + 漂移检测 | — |
| 阶段 2 | 配置变更审批流（patch 走 PR review） | 多人协作 |
| 阶段 3 | 多环境配置（dev/prod profile 分离） | 出现第二套部署 |

## 8. 相关

- **ADR**: [ADR-202608-007](../../../knowledge-base/by-category/project-experience/adr/ADR-202608-007-config-management.md)
- **约定**: [commit-and-config.md](../../../conventions/commit-and-config.md)
- **经验卡片**: `EXP-20260821-003`（配置被覆盖）、`EXP-20260822-004`（实测优于文档）
- **同层组件**: 凭据管理（ADR-005）、持久化（ADR-006）、可观测性（ADR-004）
