# model-scheduling 设计细则 v1.1 —— 跨会话错峰与突发限流治理

> 版本：v1.1 ｜ 日期：2026-11-25 ｜ 状态：已实施
> 上游：`DESIGN.md`、`DESIGN-DETAIL-v1.0.md`（本文为增量，不替代 v1.0）
> 解决：`KNOWN-ISSUES.md` 的 KI-01（高）、KI-02（中）
> 复现命令均相对组件目录 `L2-infra/components/model-scheduling`。

---

## 1. 问题定义

### 1.1 KI-01 缺少跨会话并发错峰机制（高）

多 agent 会话同时运行时，chat 请求无任何全局限速/排队，直接打向 provider。
现状边界（已实测）：

- `scripts/proxy.py` 唯一并发原语是 `_embedding_lock`（`asyncio.Lock`，仅覆盖 embedding）；**chat 无闸门**；
- `config/providers.yaml` 已有 `rate_limit.{requests_per_minute, tokens_per_minute}`（per provider），**但没有任何代码读取它**——配置存在、逻辑缺失；
- `config/config.yaml` 无并发/速率配置项。

易混淆项（不算缺口）：`classify_429()` 是被动错误分类；`runtime_feedback` 是故障隔离。二者都不改变发送节奏。

### 1.2 KI-02 突发限流就地继续会放大并发（中）

429 + `RequestBurstTooFast` 分支选择「不标记 provider、继续 fallback」。
低并发下成立；多会话高并发下相反——每次继续都叠加一个新请求。

---

## 2. 业界最佳实践（调研来源）

| 来源 | 要点 |
|---|---|
| Alibaba Cloud Model Studio《Best practices for handling rate limiting》<br>https://www.alibabacloud.com/help/en/model-studio/rate-limiting-best-practices | 完整流水线：`估算输入 tokens → 双重准入(RPM & TPM) → 并发锁 → 流量整形 → 发送 → 结算输出 tokens`。**平滑等待放在并发锁内**，避免等待结束后在出口重新扎堆。 |
| LiteLLM 官方文档《Budgets, Rate Limits》<br>https://docs.litellm.ai/docs/proxy/users | 计数器跨实例需集中（Redis 滑动窗口）；本机单实例等价于进程内计数。区分 RPM（硬限制，精确）与 TPM（尽力而为，可能略超）。 |
| LiteLLM《Proxy - Load Balancing》<br>https://docs.litellm.ai/docs/proxy/load_balancing | 超限在**到达 provider 之前**以 `429` 阻断；路由策略含 `least-busy`。 |
| Spheron《LLM API Rate Limits for AI Agents》<br>https://www.spheron.network/blog/llm-rate-limits-for-ai-agents-guaranteed-concurrency-for-too | 「RPM/TPM 是速率而非并发上限」——突发可在分钟均值健康时已超限。必须用并发闸门补齐。 |
| callsphere《Semaphores and Rate Limiting》<br>https://callsphere.ai/blog/semaphores-rate-limiting-controlling-concurrent-llm-api-requests | 信号量（并发）与限速器（吞吐）**两者都需要**；经验值 `max_concurrent ≈ rate_limit / 平均延迟秒`。 |

**共识**：单一手段不足。最小可行集 = ① per-provider RPM 令牌桶 ② per-provider TPM 令牌桶 ③ 全局并发信号量 ④ 平滑间隔 + jitter ⑤ 突发时感知并发度决定退让。

---

## 3. 方案取舍

| 方案 | 结论 | 理由 |
|---|---|---|
| 固定窗口计数 | ❌ | 窗口边界可突发 2 倍；业界一致用令牌桶 |
| 仅 RPM 桶 | ❌ | 大 prompt 场景 TPM 先耗尽（Zuplo/Spheron 实证） |
| 全局单桶（不分 provider） | ❌ | provider 各自独立配额，混算会误伤健康 provider |
| Redis 集中计数 | ❌ 本期不做 | 单实例部署，进程内计数已满足；引入 Redis 增运维面 |
| 新配置文件 `throttle.yaml` | ❌ | watcher 只检查已缓存文件，需额外加载与注册，改动面大 |
| **复用 `routing.yaml` 新增 `throttle:` 段 + 复用 `providers.yaml.rate_limit`** | ✅ | 两文件均已在热更新缓存中，零 watcher 改动；per-provider 参数已有出处 |

**放置位置**：准入与整形放在 `_handle_chat` 的**转发尝试外层**（`await gate(...)` 包住 `_forward_once`），而非 `_forward_once` 内部——因为 fallback 会换 provider，每次尝试都应独立准入。

---

## 4. 设计

### 4.1 新增 `scripts/throttle.py`

```
TokenBucket(capacity, refill_per_second)
  ├─ tokens / last_refill
  ├─ time_until_ready(amount, now) -> float   # 不足时返回需等待秒数，不扣减
  └─ consume(amount, now)                      # 扣减（调用前应已等待）

ProviderThrottle
  ├─ rpm_bucket / tpm_bucket   # 由 providers.yaml rate_limit 构建
  └─ refresh(provider_conf)    # 热更新后重建桶（保留当前 tokens，取 min）

GlobalGate
  ├─ _sem: asyncio.Semaphore(max_concurrent_chat)
  ├─ _inflight: int            # 自有计数（不依赖 Semaphore 私有值）
  ├─ _last_send_mono: float    # 平滑用单调时钟
  ├─ inflight_ratio() -> float
  ├─ burst_backoff_seconds() -> float   # KI-02：inflight 高于阈值才退让
  └─ async gate(provider_id, est_tokens)  # async context manager
```

`gate()` 内部顺序严格对齐业界流水线：

1. **双重准入**：`wait = max(rpm.time_until_ready(1), tpm.time_until_ready(est))`；`await sleep(wait)` 后消费。
2. **并发锁**：`async with self._sem`，进入即 `self._inflight += 1`。
3. **平滑 + jitter**：距上次发送不足 `min_interval` 则补足，并加 `uniform(0, min_interval*jitter_ratio)` 抖动。
4. **yield**（执行真正转发）；`finally` 中 `_inflight -= 1`。

> 锁内做平滑是刻意的（Alibaba 文档明确：锁外等待会在出口重新扎堆）。

### 4.2 配置（`config/routing.yaml` 新增段）

```yaml
throttle:
  enabled: true
  max_concurrent_chat: 16        # 全局并发闸门
  min_interval_seconds: 0.2      # 平滑最小发送间隔
  jitter_ratio: 0.25             # 抖动比例（均匀分布）
  burst_backoff:                # KI-02
    enabled: true
    inflight_ratio_threshold: 0.7
    base_seconds: 1.0
    max_seconds: 10.0
```

**失败开放（fail-open）**：`throttle.enabled` 缺省/`false`、或配置解析失败 → 闸门整体旁路，行为退回 v1.0。宁可暂时无保护，不可因新代码阻断生产。

### 4.3 接入点（`scripts/proxy.py`）

- `ProxyHandler.__init__`：构建 `GlobalGate`（读 `routing.yaml` 的 `throttle` 段）。
- `_handle_chat`：fallback 循环内，每次尝试改为
  `async with self.gate.gate(provider_id, est): success, ... = await self._forward_once(...)`
- 429 突发分支（KI-02）：`kind == "ratelimit"` 时调 `self.gate.burst_backoff_seconds()`，
  非 0 则 `await asyncio.sleep(d)` 再继续下一模型，日志显式记录退让时长与当前 inflight。
- **不动** `_forward_once` 内部、不动 embeddings 现有 `_embedding_lock`（两者独立）。

### 4.4 热更新

`providers.yaml` / `routing.yaml` 变更经既有 watcher 生效；`_handle_chat` 每次尝试都取当前配置重建/刷新对应 provider 的桶，无需重启。

---

## 5. 验收标准（机器可判）

| # | 标准 | 判定方式 |
|---|---|---|
| A1 | 令牌桶数学正确：满桶即时通过；空桶等待 ≈ 亏空/补充速率 | `tests/test_throttle.py` |
| A2 | 并发闸门封顶：N+1 个并发请求必有 1 个等待 | 同上（确定性时序） |
| A3 | fail-open：`enabled=false` 时 `gate()` 不产生任何等待 | 同上 |
| A4 | KI-02：inflight 低于阈值退让 0s，高于阈值退让 ∈ [base, max] | 同上 |
| A5 | 平滑间隔生效：连续两次发送间隔 ≥ min_interval | 同上 |
| A6 | 真实请求端到端不受影响 | 重启后 `auto` 链 3 次 chat 成功 |
| A7 | 资产入册 | `gen_asset_inventory.py --check` 通过、registry 自校验通过 |

---

## 6. 回退方案

1. 一键：`routing.yaml` 置 `throttle.enabled: false` → 热更新 10s 内旁路（无需重启）。
2. 彻底：还原 `proxy.py` 接入点；`throttle.py` 保留（不被调用即无副作用）。
