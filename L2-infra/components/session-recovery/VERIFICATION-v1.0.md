# session-recovery — 测试方案 (VERIFICATION)

> 版本: v1.0 · 日期: 2026-09-28

## 测试范围

- 任务登记
- 断点续跑
- 自动重试

## 测试用例

| # | 场景 | 输入 | 预期结果 |
|---|---|---|---|
| TC01 | 任务登记 | 任务信息 | current-task.md |
| TC02 | 断点续跑 | 中断任务 | 从断点恢复 |
| TC03 | 自动重试 | 失败任务 | 自动重试 |

## 实测结果

- start: ✅
- current: ✅
- check_and_retry: ✅
- cron_retry: ✅
