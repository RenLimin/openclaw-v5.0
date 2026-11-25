# Known Issues — model-scheduling

> 只记录，不修复。供后续排期与主会话修改参考。
> 建立：2026-11-24 · 状态：待 Rex 主会话处理
> 复现命令均相对本组件目录（`/Users/bangcle/.openclaw/workspace/L2-infra/components/model-scheduling`）。

---

## KI-01 缺少跨会话并发错峰机制（高）

**现象**：多个 agent 会话同时运行时，模型请求同时打向 provider，无任何全局限速/排队。

**证据**（2026-11-24 实测）：
```bash
for k in 错峰 限流 并发 concurrency semaphore throttle stagger jitter 排队 queue RPM TPM 429 backoff 重试间隔; do
  printf '%-12s %s\n' "$k" "$(grep -ril "$k" scripts/ config/ *.md 2>/dev/null | wc -l | tr -d ' ')"
done
```
命中：`错峰` / `concurrency` / `semaphore` / `throttle` / `stagger` / `jitter` / `排队` / `queue` / `RPM` / `TPM` / `backoff` / `重试间隔` **全部 0**。
（`限流` 6、`并发` 6、`429` 12 属**被动错误分类**文本，非主动调度逻辑。）

**现状边界**：
- `scripts/proxy.py` 唯一并发原语是 `_embedding_lock`（`asyncio.Lock`，仅覆盖 embedding），**chat 请求无闸门**；
- `config/config.yaml` **无任何并发/速率配置项**（只有 host/port、热更新、健康反馈 TTL）；
- 已有的是「路由 + 配额识别 + 故障转移」，**没有错峰**。

**易混淆项（不算缺口）**：
- `classify_429()`（`scripts/proxy.py`）区分「账号配额耗尽」vs「突发限流」——**被动响应**，不改变发送节奏；
- `runtime_feedback`：连续 3 次网络失败标记 unreachable（TTL 3600s）——**故障隔离**，非错峰。

**建议方向（未实施）**：在 proxy 层加全局信号量 + 请求间隔 jitter + RPM/TPM 上限；作用于跨会话，而非单会话内。

---

## KI-02 突发限流的就地重试会放大并发（中）

**现象**：429 + `RequestBurstTooFast` 时选择「不隔离 provider、就地退让重试」。理由是「隔离 provider 反而扩大故障」——该判断在**低并发**下成立，在**多会话高并发**下相反：重试即叠加压力。

**证据**：`scripts/proxy.py` 429 分支注释（`# 429+RequestBurstTooFast → 不标记（突发限流,短暂退让即可,隔离 provider 反而扩大故障）`）。

**建议**：与 KI-01 一并评估，重试策略需感知当前全局并发度；高并发时应改为延迟/排队，而非立即重试。

---

## 附：2026-11-24 两次会话中断的归因（**不属于**本组件）

| 报错 | 真实归属 |
|---|---|
| `Context is too large and auto-compaction could not recover this turn` | 上下文管理（`L2-infra/components/context-management`），与错峰无关 |
| `restart recovery claim changed before agent adoption` | OpenClaw 本体重启恢复竞态（`/opt/homebrew/lib/node_modules/openclaw`），不在本仓库 |

> 结论：这两条**不应**作为 model-scheduling 的修复依据；真正的调度缺口是 KI-01 / KI-02。
