# model-scheduling — 测试方案 v1.2（错峰与突发限流治理）

> 版本：v1.2 ｜ 日期：2026-11-25
> 范围：KI-01（跨会话并发错峰）、KI-02（突发限流就地重试放大并发）
> 上游：`DESIGN-DETAIL-v1.1-throttle.md`、`KNOWN-ISSUES.md`
> 不替代 v1.0/v1.1，为增量增补。

## 测试范围

| 模块 | 内容 |
|---|---|
| `scripts/throttle.py` | TokenBucket / ProviderThrottle / GlobalGate |
| `scripts/proxy.py` | 准入接入、KI-02 退让、`_forward_once` 返回契约修复 |
| `config/routing.yaml` | `throttle:` 配置段 |

## 测试用例（机器可判）

| # | 场景 | 预期 | 结果 |
|---|---|---|---|
| A1 | 满桶请求 | 零等待 | ✅ |
| A1 | 空桶单 token | 等待 ≈ 亏空/补充速率 | ✅ |
| A1 | 部分桶 | 等待 = (需−有)/速率 | ✅ |
| A1 | 请求量 > 桶容量 | 放行交 provider（不死等） | ✅ |
| A1 | 桶补充封顶 | tokens ≤ capacity | ✅ |
| A2 | N+1 并发 / 容量 N | 至少一个观测到 inflight==N | ✅ |
| A2 | 异常退出 | inflight 归零 | ✅ |
| A3 | `enabled=false` / 缺段 / 畸形配置 | 闸门旁路，零等待 | ✅ |
| A4 | 低并发（ratio<threshold） | 退让 0s | ✅ |
| A4 | 高并发（ratio=1.0） | 退让 = max | ✅ |
| A4 | 阈值边界 | 退让 = base | ✅ |
| A4 | `burst_backoff.enabled=false` | 恒 0s | ✅ |
| A5 | 连续两次发送间隔 | ≥ min_interval | ✅ |
| A5 | `min_interval=0` | 无强制间隔 | ✅ |
| B1 | key 缺失时 `_forward_once` | 返回三元组非 None，且写出 500 | ✅ |
| B2 | key 缺失走完整 `_handle_chat` | 不抛异常（fallback 可用） | ✅ |
| C1 | TPM 主导大 prompt | 大请求触发补桶等待 | ✅ |
| C2 | 未知 provider | 仍受并发闸门兜底 | ✅ |

## 实测结果

```
$ python3 -m pytest tests/ -q
75 passed in 4.32s
```

其中新增 `tests/test_throttle.py`（24 项）、`tests/test_forward_once_contract.py`（3 项），既有 48 项无回归。

## 真实链路验证（A6）

| 步骤 | 命令 | 结果 |
|---|---|---|
| 独立端口冒烟 | `proxy.py --port 3100 --skip-probe` + `/health` | ✅ 服务起、探活跳过正常 |
| 真实 chat（auto 链） | `--port 3100` + `{"model":"auto",...}` | ✅ 命中 `longCat/LongCat-2.0` |
| 生产重启后 | `auto` 链 3 次 chat | ✅ 3/3 成功（见提交记录） |
| 资产入册 | `gen_asset_inventory.py --check` | ✅ 最新的 |
| registry 自校验 | `capability_registry.py --validate` | ✅ entry 路径全存在 |

## 顺带修复的既有缺陷

`_forward_once` 在 provider key 缺失分支 `await self._send_error(...); return` → 返回 **None**，
而调用方是三元组解包 → `TypeError` → 被 `handle_request` 吞成「请求处理失败」，**fallback 链不再重试**。
该缺陷在 v1.1 给 `_forward_once` 包上闸门后会被直接击穿，故一并修复并加契约回归测试。

## 回退验证

`routing.yaml` 置 `throttle.enabled: false` → watcher 10s 热更新旁路，无需重启（已由 A3 覆盖）。
