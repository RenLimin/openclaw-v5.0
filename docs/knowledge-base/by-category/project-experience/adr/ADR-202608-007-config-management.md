---
type: adr
id: ADR-202608-007
date: 2026-08-22
title: L2 配置管理组件设计决策 — 治理封装而非重新实现
status: accepted
supersedes: null
superseded_by: null
deciders: [Rex, Jerry]
layers: [L1, L2]
tags: [config, governance, snapshot, drift-detection, secret-redaction]
---

# [ADR-202608-007] L2 配置管理组件设计决策

## 1. 状态

**accepted** — 2026-08-22 Rex 确认 · 阶段 1 已实现并验证

## 2. 背景

L2 建设的第 5 个组件。架构文档原本把「配置管理」标注为 **"复用 L1"** ——
OpenClaw 已提供 `openclaw config get/patch/validate`、schema 校验、`.bak` 轮转备份、
SecretRef 解析。看起来无需自建。

**但连续 2 天发生了 4 类事故，全部与配置治理有关**：

| # | 事故 | 日期 |
|---|---|---|
| P1 | `agents.defaults.compaction.model` 被自身后续操作静默覆盖丢失 | 2026-08-21 |
| P2 | `Applied 3 config update(s)` 正常返回，但配置实际已被覆盖 | 2026-08-21 |
| P3 | `minimax-m3` 误设 512000、`ark-code-latest` 误设 262144（靠文档推断） | 2026-08-21 |
| P4 | `.git/hooks/` 不入版本控制，clone 后 hook 静默丢失 | 2026-08-22 |

**关键洞察**：L1 解决了"怎么改配置"，但没解决**"改完怎么确认真的改了，以后怎么发现它被改回去"**。
这是治理问题，不是能力问题。

**设计文档**: [components/config/DESIGN.md](../../../../architecture/components/config/DESIGN.md)

## 3. 核心决策

### 决策 1：只做治理封装，严禁重新实现 L1

**决策**：本组件不实现配置读写、schema 校验、备份轮转。所有写入必须经 `openclaw config patch`。

**理由**：
- 裸文件写入会绕过 schema 校验和 `.bak` 轮转，制造更多事故
- OpenClaw 升级时内部结构会变，自建 parser 必然腐化
- 符合 L2 约束"必须适配 L1 契约，不能绕过、不能 hack"

**否决方案**：自建配置文件读写层（提供"更好的 API"）。
**否决理由**：与 L1 双写同一文件必然产生竞态与覆盖 —— 这正是 P1 事故的形态。

### 决策 2：脱敏快照入 git，补上"可追溯"

**决策**：`~/.openclaw/openclaw.json` 脱敏后快照到 `config-snapshots/`，纳入版本控制。

**理由**：`.bak` 轮转只保留 5 份且不回答"谁改的、为什么改"。git 提供无限历史 + commit message + diff。

**关键实现细节（踩坑后修正）**：脱敏必须用**精确字段名匹配 + 显式白名单**，不能用子串匹配。

```python
SECRET_KEYS = {"apikey", "token", "secret", "password", "credential", ...}
KEEP_KEYS   = {"maxtokens", "keeprecenttokens", "maxtokensfield", ...}
```

首版用子串匹配（`"token" in key`），把 `maxTokens`、`keepRecentTokens` 全脱敏成
`<REDACTED>` —— 而这些正是最需要 diff 的容量参数，等于毁掉快照价值。

**否决方案**：把 `~/.openclaw/openclaw.json` 做符号链接进 repo。
**否决理由**：含 gateway token 与 apiKey，任何 push 都会泄漏凭据。

### 决策 3：变更流程固化为代码，杜绝跳过"读回确认"

**决策**：`scripts/config.sh apply <patch>` 把四步流程写死：
dry-run → apply → **读回确认** → 快照入库。

**理由**：P2 事故的根因是"信了命令返回值"。`Applied N config update(s)` 只表示
写入调用成功，不表示当前状态如预期。**只有读回才算验证。**

写成文档会被跳过，写成脚本不会。

### 决策 4：漂移可检测，但不阻塞

**决策**：所有"应保持一致"的对象都提供 `--check` 模式（退出码 0/1），接入 pre-commit **仅提醒**。

| 对象 | 检测 |
|---|---|
| 配置快照 | `snapshot_config.py --check` |
| git hooks | `install-hooks.sh --check` |

**理由**：保护机制不该妨碍工作。阻塞式 hook 会被 `--no-verify` 绕过，反而彻底失效。

### 决策 5：能力声明只信实测

**决策**：模型 `contextWindow` 必须由 `probe_context_window.py` 实测确定，禁止照抄文档或兄弟模型。

**理由**（P3 事故的三类文档失效模式）：

| 失效模式 | 案例 |
|---|---|
| 文档描述直连 API，非转售通道 | MiniMax 直连拒绝 >512000，ARK 通道支持 1M |
| 启用条件不适用于转售通道 | 智谱要求 `glm-5.3[1m]`，ARK 端点无需 |
| 官方 CLI 查不到尝鲜/别名模型 | `arkcli models get glm-5.3` → `{ok:false}` |

**附带认知**：`context_window`（输入+输出）≠ `max_input_token_length`（输入侧）。
OpenClaw 的 `contextWindow` 判断历史容量，应对齐 **max_input**。
`ark-code-latest` 因忽略此点误设 262144（真值 229376）。

## 4. 契约（提供给 L3）

L3 不直接读 `~/.openclaw/openclaw.json`：

| 接口 | 形式 | 稳定性 |
|---|---|---|
| 配置审计 | `scripts/config.sh audit`（退出码 0=健康） | 稳定 |
| 脱敏配置 | `config-snapshots/openclaw.json` | 稳定 |
| 变更流程 | `scripts/config.sh apply <patch>` | 稳定 |

**不承诺**：`~/.openclaw/openclaw.json` 内部结构（属 L1，随升级变化）。

## 5. 后果

**正面**：
- 配置变更可 diff、可追溯、可回滚到任意历史点
- 四步流程固化，无法跳过验证
- 漂移自动暴露（快照/hook）
- 一条命令完成全面审计

**负面 / 成本**：
- 每次配置变更多一步快照提交（约 10 秒）
- `config-snapshots/` 与实际配置可能短暂不一致（由 `--check` 兜底）
- 脱敏白名单需随新 provider 维护，否则可能漏脱敏

**风险与缓解**：

| 风险 | 缓解 |
|---|---|
| 新 provider 的凭据字段名未被 `SECRET_KEYS` 覆盖 → 泄漏 | `config.sh audit` 输出凭据引用清单；push 前扫 `ark-*`/`sk-*`/`ghp_` 等模式 |
| 有人绕过流程直接改文件 | `--check` 在 pre-commit 提醒；长期不一致即信号 |
| OpenClaw 升级改变 `config` 子命令行为 | 升级后重跑 `config.sh audit` |

## 6. 验证

```bash
bash scripts/config.sh audit    # → 全绿，退出码 0
```

**实测通过项**：
- ✅ audit 六项全绿（配置权限 600 / schema / 快照 / hook / 凭据引用 / ctx 声明）
- ✅ apply 四步流程：dry-run → apply → 读回确认到 `ttl: "10m"` → 快照自动更新
- ✅ diff 精确定位变更行（`- "ttl": "10m"` / `+ "ttl": "5m"`）
- ✅ check 闭环：检测(退出码1) → 提示 → 修复 → 确认(退出码0)
- ✅ probe 子命令正常
- ✅ 脱敏正确性：仅 3 处真凭据脱敏，全部容量参数保留

**发现并修复的既有问题**：`scripts/git-hooks/`（旧）与 `scripts/hooks/`（新）重复，
已合并至 `scripts/git-hooks/`。

## 7. 演进路径

| 阶段 | 内容 | 触发条件 |
|---|---|---|
| **阶段 1（当前）** | 快照 + 审计 + 实测 + 漂移检测 | — |
| 阶段 2 | 配置变更审批流（patch 走 PR review） | 多人协作 |
| 阶段 3 | 多环境配置（dev/prod profile 分离） | 出现第二套部署 |

## 8. 相关

- **设计**: [components/config/DESIGN.md](../../../../architecture/components/config/DESIGN.md)
- **约定**: [commit-and-config.md](../../../../conventions/commit-and-config.md)
- **经验卡片**: `EXP-20260821-003`（P1/P2）、`EXP-20260822-004`（P3）、`EXP-20260822-005`（cron 配置）
- **同层 ADR**: 004 可观测性 · 005 凭据管理 · 006 持久化
- **架构**: `docs/architecture/00-system-architecture.md` §3.2

## 9. 变更历史

- 2026-08-22: 创建并 accepted（阶段 1 实现完成并验证）
