# context-guardian 修复版 — 设计大纲 (DESIGN-OUTLINE)

## 1. 目标

把工具结果微压缩从 host 不回读的 `after_tool_call` 迁移到 host 唯一回读的 `tool_result_persist`，使压缩**真实写入 transcript**；同时修正阈值与授权，恢复压力监控链路。

## 2. 整体架构

```
┌─ host (OpenClaw 2026.9.8) ────────────────────────────────────────┐
│ 工具执行                                                      │
│   ├─ before_tool_call   ← 插件改写 params（exec 限流）        │
│   ├─ emitToolResultOutput（先落结果，插件已无权改写）          │
│   ├─ after_tool_call    ← 插件仅观测（不做改写）              │
│   └─ persistToolResult  ← tool_result_persist ★唯一改写点     │
│        └─ runToolResultPersist(...)?.message ?? message       │
│             └─ appendMessageAndCacheTranscriptSeq(...)        │
└───────────────────────────────────────────────────────────────┘
```

## 3. 模块划分

| 模块 | 职责 | 文件 |
|---|---|---|
| 核心逻辑 | 分类、阈值、截断、压力估算（纯函数，零依赖） | `core.js` |
| 插件注册 | hook 注册、配置读取、会话状态、日志 | `index.js` |
| 测试 | 17 黄金用例 | `tests/test_core.js` |
| 元数据 | manifest | `openclaw.plugin.json` / `package.json` |

## 4. 关键设计决策

| # | 决策 | 理由 |
|---|---|---|
| D1 | 改写点选 `tool_result_persist` | host 用 `result.message ?? message` 写 transcript，是唯一被消费的改写 |
| D2 | `after_tool_call` 降级为纯观测 | 保留压力统计能力，但不再做任何 result 赋值（避免误导） |
| D3 | 默认 `microCompactMaxChars=3000` | warn=7500 必须 < host 持久化 cap（当前 32000）；critical=3000 积极压缩 |
| D4 | 会话状态有界 LRU（200） | v5 的 Map 无清理，长跑泄漏 |
| D5 | 通过 `plugins.load.paths` shadow 上游 | config-selected 优先级最高，`plugins update` 不覆盖修复 |
| D6 | 逻辑与注册分离 | `core.js` 可 node:test 单测，无需起 host |

## 5. 风险与回滚

| 风险 | 缓解 |
|---|---|
| 插件加载失败导致保护失效 | 加载失败有 `plugin(s) failed to initialize` 日志；可 `plugins disable context-guardian` 回退 |
| 压缩过度丢信息 | EDIT/PRESERVE 永不压缩；low 压力不压缩；提示语告知重试方法 |
| 与上游 v5 行为差异 | 仅改写点与阈值变化，配置键名兼容 |
| 回滚 | 从 `plugins.load.paths` 移除本目录即可恢复上游 v5.1.1 |

## 6. 验证策略

1. 单元：`node --test tests/test_core.js`（17 用例）
2. 加载：日志 `v6 loaded ... rewrite=tool_result_persist`
3. 授权：新代际无 `blocked because non-bundled`
4. 基线：日志出现 `session=...turn=...`
5. E2E：构造超大结果 → 日志 `Persist-compressed` + transcript 文本含标记
