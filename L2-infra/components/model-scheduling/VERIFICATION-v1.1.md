# model-scheduling — 测试方案 (VERIFICATION)

> 版本: v1.1 · 日期: 2026-11-08
> 变更: 新增 exhausted 修复回归测试（13 项），详见文末「v1.1 增补」

## 测试范围

- 模型路由
- 健康探测
- 用量获取
- 多级 fallback
- exhausted 状态处理（v1.1 新增）

## 测试用例

| # | 场景 | 输入 | 预期结果 |
|---|---|---|---|
| TC01 | 模型路由 | 4 种任务类型 | 正确路由 |
| TC02 | 健康探测 | 所有模型 | 状态正确 |
| TC03 | 用量获取 | provider API | 用量数据 |
| TC04 | fallback | 主模型不可用 | 自动切换 |
| TC05 | exhausted TTL 内 | 30min 前标记 | `unreachable`（跳过路由） |
| TC06 | exhausted 超 TTL | 2h 前标记 | `unknown`（重新试探） |
| TC07 | exhausted 无时间戳 | 无 last_checked | `unreachable`（保守跳过） |
| TC08 | unreachable TTL 内 | 30min 前标记 | `unreachable`（原有逻辑保留） |
| TC09 | unreachable 超 TTL | 2h 前标记 | `unknown`（原有逻辑保留） |
| TC10 | healthy 状态 | healthy | `healthy`（不受影响） |
| TC11 | 首次 402 标记 | 无 status | 写入 `last_checked` |
| TC12 | 重复 402 标记 | 已 exhausted | `last_checked` 不变 |
| TC13 | 探活状态不变 | exhausted → exhausted | 保留原 `last_checked` |
| TC14 | 探活状态变化 | exhausted → healthy | 刷新 `last_checked` |
| TC15 | 探活首次标记 | 无 last_checked | 写入 now |

## 实测结果

- router: ✅
- health_check: ✅
- fetch_usage: ✅
- fallback: ✅
- 827 req / 115 err (13.9%): ✅

## v1.1 增补（2026-11-08）

**背景**: deepseek 余额耗尽后系统反复撞 402、永久卡死。根因是 exhausted 状态的 TTL 自愈逻辑被 3 处覆盖（详见 CHANGELOG 2026-11-08 条目）。

**新增测试**: `tests/test_proxy_exhausted.py`（13 项）

| 测试类 | 覆盖点 | 数量 |
|---|---|---|
| `TestGetProviderHealthExhausted` | exhausted/unreachable 的 TTL 分支 | 7 |
| `TestMarkExhaustedNoRefresh` | 402 重复标记不刷新时间戳 | 3 |
| `TestStartupProbeNoReset` | 探活状态不变不刷新时间戳 | 3 |

**全量测试**: 22 passed（原 9 + 新增 13）

**验证方式**: 不触网、不依赖真实 usage.json（monkeypatch 注入），可重复执行。
