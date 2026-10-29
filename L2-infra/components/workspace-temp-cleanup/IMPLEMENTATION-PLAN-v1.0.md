# workspace-temp-cleanup — 开发计划 (IMPLEMENTATION-PLAN)

> INFRA-CLN-001 · v1.0 · 2026-10-29

| Phase | 内容 | 工时 | 出口 |
|---|---|---|---|
| P1 | clean-engine：scanner/judger/reporter/executor + Candidate 模型 | 0.5d | dry-run/list 正确 |
| P2 | CLI `tempcleanctl`：4 子命令 + 退出码 + verify 自检 | 0.3d | 契约测试通过 |
| P3 | 测试：8 用例 + 黄金基准，真实 trash | 0.4d | pytest 全绿 |
| P4 | cron 注册（03:30 isolated）+ announce + verify 随扫描 | 0.3d | cron runs ok |
| P5 | 验收 7 步法 + 架构文档状态转已上线 | 0.2d | 交付 |

合计约 1.7d。P1-P3 本轮连续完成；P4 涉及 cron/config 变更，按规约先 inspect 再 merge，单独确认。
