---
type: convention
status: active
date: 2026-08-22
owner: Rex + Jerry
---

# Commit 与配置变更约定

> 目的：**任何变更都可追溯、可回滚、不丢失**。
> 触发本约定的事故：2026-08-21 `agents.defaults.compaction.model` 被自身后续操作静默覆盖丢失，
> 因配置不在版本控制中，只能靠 `openclaw.json.bak*` 轮转备份逆向追查。

## 1. Commit 规范（Conventional Commits）

### 1.1 格式

```
<type>(<scope>): <简短描述>

<可选正文：为什么这么改、依据、验证方式>
```

- **描述用中文**，术语/命令/文件名/标识符保持英文
- 首行 ≤ 72 字符，不加句号
- 正文说明**依据与验证**，不是重复描述改了什么

### 1.2 type 取值

| type | 用途 | 示例 |
|---|---|---|
| `feat` | 新增能力/组件 | `feat(persistence): L2 持久化适配 — 核心实现` |
| `fix` | 修正错误配置/代码/结论 | `fix: 校准 4 个模型的 contextWindow` |
| `docs` | 文档、ADR、EXP 卡片 | `docs(exp): EXP-004 contextWindow 实测法` |
| `chore` | 版本控制维护、清理 | `chore: 从版本控制移除业务运行日志` |
| `refactor` | 不改行为的结构调整 | `refactor(observability): 拆分数据源适配层` |
| `test` | 测试相关 | `test(persistence): 补迁移回滚用例` |

### 1.3 scope 取值

L2 组件名（`observability` / `credentials` / `persistence` / `context` / `config`）、
文档类型（`adr` / `exp` / `arch`），或省略（跨模块变更）。

### 1.4 强制要求

- ✅ **一个逻辑变更 = 一个 commit**。配置修正 + 卡片沉淀可以同一个 commit（它们是一件事）
- ✅ **结论被推翻时用 `fix:` 显式记录**，不要静默改掉旧结论。旧卡片标 `superseded_by`，新卡片写 `supersedes`
- ❌ 不写 `update`、`wip`、`修改一下` 这类无信息量的描述
- ❌ 不把多个不相关变更塞进一个 commit

## 2. 配置变更约定（`~/.openclaw/openclaw.json`）

### 2.1 问题

配置文件在 `~/.openclaw/`，**不在** workspace git 仓库内。后果：

- 无 diff 记录 → 谁改的、改了什么、为什么，全靠记忆
- 无回滚点 → 只能依赖 OpenClaw 的 `openclaw.json.bak{,.1..4}` 轮转（只保留 5 份，会被冲掉）
- **多轮操作会静默互相覆盖**（2026-08-21 事故的直接原因）

### 2.2 标准流程

任何配置变更**必须**四步走：

```bash
# 1. dry-run 验证
openclaw config patch --file /tmp/change.json5 --dry-run

# 2. 应用
openclaw config patch --file /tmp/change.json5

# 3. 读回确认（不要相信 "Applied N updates" 的输出）
openclaw config get <改动的路径>
openclaw config validate

# 4. 快照入库
python3 scripts/snapshot_config.py && git add config-snapshots/ && git commit
```

**第 3 步是重点**：2026-08-21 的事故中 `Applied 3 config update(s)` 正常返回，
但后续操作把它覆盖了。**只有读回才算验证**。

### 2.3 配置快照

`scripts/snapshot_config.py` 把配置**脱敏后**导出到 `config-snapshots/openclaw.json`，纳入 git。

- 脱敏：所有 `apiKey` / `token` / `secret` / `password` 字段值替换为 `<REDACTED>`
- 保留：模型声明、contextWindow、compaction 策略、工具策略、plugin 配置结构
- 目的：**配置变更可 diff、可追溯、可回滚**；凭据仍只在 `~/.openclaw/secrets/`（600）

```bash
python3 scripts/snapshot_config.py            # 写入 config-snapshots/
python3 scripts/snapshot_config.py --check    # 仅检查是否有未快照的变更（供 hook 用）
python3 scripts/snapshot_config.py --diff     # 显示当前配置与上次快照的差异
```

### 2.4 不可逆操作仍需确认

配置改动虽然可回滚，但以下情况**先问 Rex**：

- 删除 provider / plugin / 已有模型声明
- 改动 `tools.*` 策略（影响 agent 能力边界）
- 改动 secrets provider 引用路径
- 任何涉及对外副作用的配置（webhook、delivery target）

## 3. 提交前检查清单

```
□ dry-run 通过
□ 应用后读回确认（openclaw config get / validate）
□ 配置快照已更新（scripts/snapshot_config.py）
□ 结论有依据（实测数据 / 官方一手来源 / 文档引用）
□ 推翻旧结论时已标注 supersedes / superseded_by
□ commit message 符合 §1 规范
□ 无凭据泄漏（git diff 里搜一遍 key/token/secret）
```

## 4. 相关

- 资产清单自动更新：`.git/hooks/pre-commit`（见 `scripts/install-hooks.sh`）
- 凭据管理：`ADR-202608-005`、`scripts/credentials.sh`
- 配置踩坑：`EXP-20260821-003`（配置被覆盖）、`EXP-20260822-004`（实测优于文档）

## 5. 变更历史

- 2026-08-22: 创建。起因是 compaction 配置静默丢失事故 + Rex 要求统一 commit 规则
