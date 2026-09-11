# L2 配置治理组件 (config) — 设计

> **状态**: 已上线（2026-08-21 创建，持续演进）
> **层级**: L2 基础设施层
> **组件类**: 配置变更治理
> **ADR**: ADR-202608-007（配置管理）

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 组件类 | 配置变更治理 |
| 状态 | ✅ 已建设 |
| 设计依据 | 2026-08-21 `compaction.model` 被覆盖丢失事故 |

## 2. 职责

为 OpenClaw 核心配置（`~/.openclaw/openclaw.json`）提供**变更治理**能力：

1. **快照/审计** — 脱敏快照入库，变更可追溯
2. **漂移检测** — 当前配置 vs 上次快照的 diff
3. **安全写入** — 统一写入通道，dry-run → apply → 读回 → 自动回退
4. **凭据泄漏扫描** — 推送前检测 staged 内容中的凭据
5. **资产清单** — 自动生成系统资产全景（插件/技能/agent/cron/凭据）
6. **Hook 管理** — git hooks 安装与漂移检测

## 3. 核心设计

### 3.1 模块架构

```
config/
├── config.sh                  ← 统一 CLI 入口（audit/snapshot/diff/apply/probe/scan）
├── config_safe_write.sh       ← 统一安全写入通道（5 步保护）
├── snapshot_config.py         ← 脱敏快照生成器（双道防线脱敏）
├── gen_asset_inventory.py     ← 系统资产清单生成器
├── install-hooks.sh           ← git hooks 安装/漂移检测
├── git-hooks/
│   └── pre-commit             ← pre-commit hook（资产清单+快照+知识库校验）
└── tests/
    ├── conftest.py
    └── test_smoke.py
```

### 3.2 四步变更流程（核心价值链）

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ [1/4]    │    │ [2/4]    │    │ [3/4]    │    │ [4/4]    │
│ dry-run  │ →  │ apply    │ →  │ 读回确认  │ →  │ 快照入库  │
│ 预检     │    │ 应用     │    │ 逐键验证  │    │ 保存回退点│
└──────────┘    └──────────┘    └──────────┘    └──────────┘
      │                │               │                │
      └─ 失败中止      │               │                │
                       └─ 失败自动回退到最新 .bak        │
                                       └─ 失败自动回退   │
                                                       └─ 完成
```

**设计要点**：
- 任何步骤失败 → 自动回退到最新备份
- 读回验证逐键检查（最多 20 条叶子路径）
- 回退点带时间戳，支持精确回退到任意变更前

### 3.3 安全写入通道（config_safe_write.sh）

独立于 `config.sh apply` 的**更严格**写入通道，供其他组件调用：

| 步骤 | 保护机制 |
|---|---|
| [1/5] | 保存回退点（带时间戳） |
| [2/5] | dry-run 预检 |
| [3/5] | 写入 + validate |
| [4/5] | 深层读回验证 |
| [5/5] | 失败自动回退 |

**约束**：所有自定义资产对 `openclaw.json` 的写入**必须**经过此脚本，禁止直接调用 `openclaw config patch/set`。

### 3.4 双道防线脱敏

`snapshot_config.py` 采用两层脱敏策略：

```
第一道：key 名精确匹配
  ├─ SECRET_KEYS 集合（apikey/token/secret/password/botid/corpid/...）
  ├─ 后缀/子串兜底（*_API_KEY / *ClientSecret / *AesKey）
  └─ KEEP_KEYS 白名单（maxTokens/keepRecentTokens 等容量参数保留原值）

第二道：值形态兜底
  ├─ URL 内嵌 user:pass@
  ├─ 已知凭据前缀（sk-/ghp-/xoxb-/eyJ...）
  ├─ 纯 hex 长串（≥32 字符）
  └─ 长 opaque 串（≥32 字符，同时含数字+字母）
  
并行命中即脱敏；SecretRef 间接引用与占位符放行。
```

### 3.5 审计检查项

`config.sh audit` 覆盖 7 个维度：

| # | 检查项 | 说明 |
|---|---|---|
| 1 | 配置文件存在性与权限 | 权限非 600 警告 |
| 2 | schema 校验 | `openclaw config validate` |
| 3 | 快照一致性 | 当前配置 vs 快照 diff |
| 4 | hook 漂移 | 已安装 hooks 与 canonical 版本对比 |
| 5 | 凭据引用完整性 | SecretRef 文件是否存在 + 权限 |
| 6 | 模型 contextWindow 声明 | 列出所有模型的 ctx 声明 |
| 7 | 凭据泄漏扫描 | staged 改动中检测凭据（有 staged 时触发） |

### 3.6 pre-commit Hook 行为

```
pre-commit
  ├─ 1. 重生成资产清单 → 有变化自动 git add
  ├─ 2. 检查配置快照 → 仅提醒（不阻塞）
  └─ 3. 知识库 schema 校验 → 阻塞性错误拒绝提交
```

## 4. 接口与用法

```bash
# 统一 CLI
bash L2-infra/components/config/config.sh audit             # 全面审计
bash L2-infra/components/config/config.sh snapshot          # 脱敏快照入库
bash L2-infra/components/config/config.sh diff              # 当前 vs 快照
bash L2-infra/components/config/config.sh apply <file>      # 四步变更流程
bash L2-infra/components/config/config.sh probe <model> <n> # 实测 contextWindow
bash L2-infra/components/config/config.sh scan              # 凭据泄漏扫描

# 安全写入通道
bash L2-infra/components/config/config_safe_write.sh '<json-patch>'
bash L2-infra/components/config/config_safe_write.sh --file patch.json5

# 资产清单
python3 L2-infra/components/config/gen_asset_inventory.py            # 写入文件
python3 L2-infra/components/config/gen_asset_inventory.py --check    # 漂移检查
python3 L2-infra/components/config/gen_asset_inventory.py --stdout   # 标准输出

# Hook 管理
bash L2-infra/components/config/install-hooks.sh          # 安装 hooks
bash L2-infra/components/config/install-hooks.sh --check  # 漂移检测
```

## 5. 依赖

| 依赖 | 用途 |
|---|---|
| `openclaw` CLI | `config validate` / `config patch` / `config get` / `backup` |
| Python 3 | snapshot_config.py / gen_asset_inventory.py |
| `git` | pre-commit hook / 资产清单仓库信息 |

## 6. 设计约束

1. **快照不含凭据值** — 双道防线脱敏，凭据本体只存 `~/.openclaw/secrets/`
2. **快照入库可追溯** — `config-snapshots/` 纳入 git，每次变更有 diff
3. **写入必须读回** — 杜绝"写了但没生效"的静默失败
4. **失败自动回退** — 校验/读回失败 → 自动恢复到最新备份
5. **资产清单只读** — `gen_asset_inventory.py` 不修改任何系统状态
6. **幂等** — 快照/清单重复生成结果不变（时间戳除外）

## 7. 演进方向

| 方向 | 优先级 | 触发条件 |
|---|---|---|
| 配置变更通知 | 中 | apply 成功后 wecom 通知 |
| 自动快照 cron | 中 | 定时检测未快照变更并自动入库 |
| 配置 schema 版本管理 | 低 | 多环境（dev/staging/prod）配置对齐 |
| 凭据轮换提醒 | 低 | SecretRef 文件 age 追踪 |

## 8. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-08-21 | 首版：四步变更流程 + 快照入库（compaction.model 事故驱动） |
| 2026-08-22 | 安全写入通道 + 凭据引用完整性检查 |
| 2026-08-23 | 值形态兜底脱敏（review 发现 key 名匹配漏网 6/7） |
| 2026-08-24 | 资产清单生成器 + pre-commit hook 集成 |
| 2026-08-25 | hook 漂移检测 + audit 命令 7 维审计 |
