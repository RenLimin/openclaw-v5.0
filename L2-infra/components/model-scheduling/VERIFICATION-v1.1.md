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

---

## v1.2 增补（2026-11-10）

**背景**: 带图大上下文请求（~360k tokens）回退链结构性为空 + 429 语义混为一谈 + 流式中断静默（详见 CHANGELOG 2026-11-10 条目）。

**新增测试**: `tests/test_fallback_resilience.py`（22 项）

| 测试类 | 覆盖点 | 数量 |
|---|---|---|
| `TestClassify429` | 429 错误码分类（quota vs ratelimit） | 6 |
| `TestWriteProviderHealth` | exhausted 首次标记/时间戳冻结/新建 provider/大小写 | 4 |
| `TestMultimodalChainHasLargeCtxFallback` | multimodal 大 ctx 链含 longCat、能力过滤不放宽 | 4 |
| `TestStreamInterruptionNotSilent` | 流式无 finish 标志/连接中断 → 报 502 | 3 |
| `TestClassifyTaskMedia` | 带图但文本意图明确时不误判 multimodal | 5 |

**全量测试**: 44 passed（原 22 + 新增 22）

**端到端验证**:
- 真实请求 chat ✅ / multimodal 带图 ✅ / coding 跳过 exhausted cp1 ✅
- multimodal 360k、900k 链均含 longCat（修复前为空 → 结构性故障）
- 探活 429 正确分类：cp1 配额耗尽 → exhausted（非 degraded）
- proxy 重启加载新代码，`/health` 正常

---

## v1.3 增补（2026-11-12）

**背景**: 长回合流式输出被 proxy `total=120` 超时砍断 → gateway 收到半截 tool call → 报 `Provider returned an incomplete or malformed tool call`（8 次失败，均 360-430s 长回合）。详见 CHANGELOG 2026-11-12 条目。

**新增测试**: `tests/test_stream_timeout.py`（4 项）

| 测试类 | 覆盖点 | 数量 |
|---|---|---|
| `TestStreamTimeoutConfig` | 流式无 total 上限 / sock_read=120 / 非流式 total=300 / 无 finish 报 502 | 4 |

**全量测试**: 48 passed（原 44 + 新增 4）

**端到端验证**:
- proxy 重启（pid 50126→6087），探活 2/4 healthy
- 11:54 重启后 0 次新流式中断（修复前 11:34-11:46 共 3 次）
- 真实请求 chat ✅ / coding ✅，均路由 longCat（路由链修复后）
