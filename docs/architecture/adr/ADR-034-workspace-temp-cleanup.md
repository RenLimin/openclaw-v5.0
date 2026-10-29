# ADR-034：Workspace 临时资产标记与系统级定期清理

> 状态：accepted
> 日期：2026-10-29
> 决策人：Rex
> 组件：workspace-temp-cleanup（L2，INFRA-CLN-001）

## 背景

2026-10-29 审计华夏银行信用卡中心交付查询时发现：

1. **临时产物无人管**：`analysis_output/` 等查询输出物无 TTL、无 gitignore、无清理机制，会长期堆积并污染 git 状态。
2. **现有清理不覆盖文件**：会话生命周期管理（session_cleanup，每日 02:00）只清会话/subagent，不清 workspace 文件；4 个 cron job 也无文件清理。
3. **按目录盲删危险**：临时件与正式交付物可能混放，纯按目录名/时间删除有误删风险。

## 决策

在 **L2 基础设施层** 建设 `workspace-temp-cleanup`（INFRA-CLN-001），确立"标记优先、AI 系统级定期清理"机制：

### 1. 统一临时区与标记（架构 §7.4.5）
- 临时区：`analysis_output/`、`scripts/tmp/`、`tmp/`、`scratch/`，命名约定 `*-tmp/`、`*.tmp`
- 双标记：目录命名约定 + 仓库根 `.openclaw-temp.json` 显式登记（path/kind/ttl_days/created/source_task）

### 2. fail-closed 清理
- **未标记路径一律不删**（即使很旧）
- 删除只走 `/usr/bin/trash`，禁止 rm/rmtree/os.remove；trash 不可用则中止
- 默认 dry-run，`clean --yes` 才实删
- 过期判定：`age = today - max(created, mtime)`，`age > ttl_days`（TTL 当天不删）；默认 TTL：intermediate 7 天 / ledger 30 天

### 3. 系统级调度
- cron isolated 每日 **03:30**（与 02:00 会话清理错峰）执行 `clean --yes`
- 有实删动作 announce WeCom（1313），无删除静默
- `verify` 自检接入错误扫描（每 30m），失败报 `tempclean_verify_failed`

### 4. 正式交付物边界
- 查询输出物/台账等工作产物按临时件处理，不进 git（`.gitignore` 覆盖 `analysis_output/`），本地按 TTL 定期清除
- 真正的正式交付物不进临时区，直接 commit

## 后果

- 临时资产可识别、可追溯、可恢复（废纸篓）、定期清除；git 状态不再被临时件污染。
- 写方（AI/脚本）承担登记责任，组件只读登记、fail-closed，避免误删。
- 代价：写大文件需落临时区/登记，多一步约定。
