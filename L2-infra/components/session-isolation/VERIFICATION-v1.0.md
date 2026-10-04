# session-isolation — 测试方案 (VERIFICATION)

> 版本: v1.0 · 日期: 2026-09-28

## 测试范围

- Task Protocol
- State Protocol
- Event Protocol

## 测试用例

| # | 场景 | 输入 | 预期结果 |
|---|---|---|---|
| TC01 | Task 创建 | 任务定义 | Task 文件生成 |
| TC02 | State 写入 | 状态数据 | 命名空间隔离 |
| TC03 | Event 记录 | 事件 | 审计日志 |

## 实测结果

- Task Protocol: ✅
- State Protocol: ✅
- Event Protocol: ✅
- 6 tests: ✅
