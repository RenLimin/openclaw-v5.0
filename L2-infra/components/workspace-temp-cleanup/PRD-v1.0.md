# workspace-temp-cleanup — 产品需求文档 (PRD)

> 组件：workspace-temp-cleanup (L2) · 编码：INFRA-CLN-001
> 版本：v1.0 · 日期：2026-10-29
> 状态：📐 待审核（架构文档 v5.7 已登记规划态）

## 1. 概述

**业务目标**：让 workspace 内所有临时/中间产物**可识别、可清理、不污染 git**，由系统级定期清理机制统一兜底，避免磁盘堆积与 git 状态污染。

**背景**：2026-10-29 审计发现 `analysis_output/` 等临时产物无 TTL、无 gitignore、无清理机制；会话清理（session_cleanup）只清会话不清文件。

## 2. 功能清单

| # | 功能 | 优先级 | 说明 |
|---|---|---|---|
| F1 | 临时区识别 | P0 | 按 §7.4.5 约定识别临时路径：`analysis_output/`、`scripts/tmp/`、`tmp/`、`scratch/`、`*-tmp/`、`*.tmp` |
| F2 | 登记清单解析 | P0 | 解析 `.openclaw-temp.json`（path / kind / ttl_days / created / source_task），TTL 按 kind 有默认值 |
| F3 | 扫描与判定 | P0 | 扫描候选路径 → 按 TTL（默认中间数据 7 天 / 台账报表 30 天）判定是否过期 |
| F4 | dry-run 报告 | P0 | 默认输出报告：路径 / 大小 / 过期天数 / 处置动作；**不实际删除** |
| F5 | 实际清理 | P0 | `--yes` 才实删；**只用 `/usr/bin/trash`**，不用 `rm`；只删"已标记"路径 |
| F6 | cron 集成 | P1 | 注册为 cron isolated 任务（每日 02:00 与会话清理错峰），默认 dry-run |
| F7 | 通知 | P1 | 有实际删除动作时 announce 到 WeCom（沿用巡检通知口径） |
| F8 | gitignore 联动 | P1 | 保证临时区已在 `.gitignore`（`analysis_output/` 等），防污染 git 状态 |

## 3. 验收标准

1. dry-run 与实删路径一致：**未标记的路径一律不删**（可注入伪装文件验证）
2. 删除走 trash，可从废纸篓恢复；不用 rm（grep 代码确认无 rm 调用）
3. TTL 判定正确：`created + ttl_days` 边界日期的文件处置正确（当天不删、次日删）
4. `.openclaw-temp.json` 解析：缺字段用 kind 默认值；非法 JSON 报错不静默
5. cron 注册后 runs 状态 ok；实删动作触发通知
6. 幂等：同一状态连跑 3 次，结果一致（无重复删除、无遗漏）

## 4. 用户故事

- 作为系统管理员，我希望 AI 产生的台账/中间 JSON 30 天后自动进废纸篓，不再手动清理。
- 作为 AI Agent，我希望大文件落盘后登记 TTL，系统定期替我清理，不污染 git。
- 作为审计者，我希望看到每次清理前有 dry-run 报告，删除可追溯、可恢复。

## 5. 边界（不做）

- ❌ 不清理未标记路径（即使很旧）——安全优先
- ❌ 不处理会话/subagent 清理（归 session_cleanup）
- ❌ 不提供"永久删除"（只 trash，人工清空废纸篓）
- ❌ 不自动修改 `.openclaw-temp.json`（登记是写方职责，组件只读）

## 6. 风险与对策

| 风险 | 对策 |
|---|---|
| 误删正式交付物 | 未标记不删 + 双确认（dry-run 先行 + --yes 才删） |
| 正在使用的文件被删 | TTL 由登记方设置；台账类 30 天足够长；删除前可加 mtime 双重校验 |
| trash 命令缺失 | 启动自检：`/usr/bin/trash` 不可用则 abort，绝不 fallback rm |
