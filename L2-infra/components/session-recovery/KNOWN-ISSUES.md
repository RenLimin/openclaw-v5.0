# session-recovery — 已知限制与上游跟踪

> 记录「本组件/服务端无法清除、根因在浏览器或上游」的问题，避免重复建设与误报。
> 规则：能复用/上游已修的不自造；浏览器端状态不在沙箱可写范围。

---

## KI-20261110-01 · Control UI 侧边栏黄三角「消息需要关注」（浏览器 Outbox 留尸）

**现象**
会话左侧出现黄色三角标记（`session-row-badge--attention`），悬停提示
「你的消息未发送 / messageNeedsAttention」。服务端全部正常时标记仍在。

**数据来源（已定位，非服务端）**
- 标记条件：Control UI 前端 `outboxAttentionCountForSession(sessionKey) > 0`。
- 数据源：**浏览器 localStorage 的待发箱(Stored Chat Outbox)**，key 前缀
  `openclaw.control.outbox*`；由
  `outbox-store-projection` → `createStoredChatOutboxReader()` 读取。
- 计入 attention 的消息 `sendState` ∈ {`failed`, `unconfirmed`, `held`}。
- 服务端对应表（核对均干净，**不是**同一数据源）：
  `context_engine_turn_outbox`（0 行）、`delivery_queue_entries`（全 completed）、
  `memory/tasks.db`（active=0）。

**为什么会留**
发送在客户端侧失败（如 provider HTTP 503 / 断连）后，浏览器把消息保守地留在
outbox 等待人工确认（防重复投递）；服务端随后恢复、会话继续，但该失败记录
不被自动清除 → 「服务端已恢复、浏览器 outbox 留尸」。

**处置（在打开 Dashboard 的浏览器里，沙箱够不到）**
1. 打开 Outbox（待发箱）面板，或 Cmd+K 搜 `Outbox`。
2. 对卡住消息：**Discard（丢弃）** 立即消标；或确认未送达后 **Retry（重试）**。
3. 兜底：硬刷新（Cmd+Shift+R）；仍在则 DevTools → Application → Local Storage，
   仅删 key 含 `openclaw.control.outbox` 的项（勿清全站数据，恐伤其他草稿）。

**上游跟踪**
- Issue：openclaw/openclaw **#151986** [Bug, P1, 🦞 diamond]
  “failed send persists as immortal client-side retry … fires stale action on retry”。
- 已合入修复（v2026.9.8 起）：普通失败发送已提供 **Discard** 控件
  （PR #152188 / #155653 相关）。本机 2026.9.8 已具备，故优先用 UI Discard。
- 上游**未竟**：placement-owned 失败发送仍缺 Discard（#151986 保持 open 即因此窄口）。
- 相关假标修复：#166124（清发送进行中的 false attention，已 closed）。
- 结论：**不重复上报、不在服务端自造清理器**；待上游补齐 placement-owned 收口。
  若本机复现时连 Discard 都不可用，再向 #151986 补充复现信息。

<!-- observed: 2026-11-10 | status: active -->
<!-- project: github.com/RenLimin/openclaw-v5.0 -->
