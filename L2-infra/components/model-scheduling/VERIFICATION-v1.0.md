# model-scheduling — 测试方案 (VERIFICATION)

> 版本: v1.0 · 日期: 2026-09-28

## 测试范围

- 模型路由
- 健康探测
- 用量获取
- 多级 fallback

## 测试用例

| # | 场景 | 输入 | 预期结果 |
|---|---|---|---|
| TC01 | 模型路由 | 4 种任务类型 | 正确路由 |
| TC02 | 健康探测 | 所有模型 | 状态正确 |
| TC03 | 用量获取 | provider API | 用量数据 |
| TC04 |  fallback | 主模型不可用 | 自动切换 |

## 实测结果

- router: ✅
- health_check: ✅
- fetch_usage: ✅
- fallback: ✅
- 827 req / 115 err (13.9%): ✅
