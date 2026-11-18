# context-guardian（修复版）

上下文保护插件 v6：主动监控上下文压力、自动触发 `/compact`、对超大工具结果做实时微压缩。

**与上游 v5.1.1 的唯一实质差异**：结果改写从 `after_tool_call` 迁到 `tool_result_persist`。

## 为什么必须修

上游 v5 把微压缩写在 `after_tool_call`：

- host 对该钩子按 **Observe** 语义处理（`runVoidHook`，fire-and-forget，返回值不回读）
- 且 `emitToolResultOutput` 在钩子**之前**已执行
- 于是 `event.result = compactedResult` 永远丢弃 → 插件日志有 `Micro-compacted`，transcript 里却从不出现截断

实测证据（2026-11-17/18 gateway.log）：`Micro-compacted` 16 条、`Large result after compaction` 1900+ 条，但全部停在 ~8014 chars（插件自身 8000 告警值），说明改写从未生效。

另有一处配置缺陷：非 bundled 插件未声明 `hooks.allowConversationAccess=true`，导致 `before_prompt_build` 被门禁阻断（压力基线永不更新）。

## 修复

| 项 | v5（上游） | v6（本组件） |
|---|---|---|
| 结果改写钩子 | `after_tool_call`（no-op） | `tool_result_persist`（host 回读 `{ message }`） |
| 会话状态 | 无上限 Map | 有界 LRU（200） |
| 阈值 | warn=12500（可触发，host cap=32000） | warn=base×2.5，默认 7500 < 32000 |
| 授权 | 缺 `allowConversationAccess` | 随 entry 声明 |

## 加载方式

通过 `plugins.load.paths` 显式选中本目录，以**最高优先级** shadow 掉 clawhub 安装的 v5.1.1 副本（同 id 只保留最高优先级 manifest）。因此 `openclaw plugins update` 不会覆盖本修复。

## 验证

```bash
node --test tests/test_core.js     # 17 用例
grep "Persist-compressed" ~/Library/Logs/openclaw/gateway.log | tail
grep "ContextGuardian] v6 loaded" ~/Library/Logs/openclaw/gateway.log | tail -1
```

文档：PRD-v1.0 / DESIGN-OUTLINE-v1.0 / DESIGN-DETAIL-v1.0 / OPERATIONS-v1.0 / VERIFICATION-v1.0
