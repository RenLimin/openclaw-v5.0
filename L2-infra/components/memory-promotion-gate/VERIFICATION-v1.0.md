# VERIFICATION v1.0 — memory-promotion-gate

日期：2026-11-27 · Lane C（重跑）
验收口径（PRD §4）：`promoted > 0` 且 `candidates_with_recalls > 0`；幂等 diff 为空；测试全绿。

## 1. 机器门禁：pytest
```
python3 -m pytest L2-infra/components/memory-promotion-gate/tests -q
=> 17 passed
```
覆盖：候选解析、跨日累积、指纹稳定性、评分权重/门槛、风险分级正负例、
dry-run 不写盘、apply→再 apply 幂等、无 recalls fail-closed、MEMORY.md 缺失报错。

## 2. 真实运行（工作区 /Users/bangcle/.openclaw/workspace，82 天 dreaming 报告）

| 步骤 | 命令 | 结果 |
|---|---|---|
| dry-run | `--workspace $PWD --dry-run --probe-limit 8` | `candidates_raw=7499 candidates_unique=6626 with_recalls=6 would_promote=33 pending_review_high_risk=316`，exit 0，**MEMORY.md 零变化** |
| apply #1 | `--workspace $PWD --apply --probe-limit 8` | exit 0，新增 **33** 条带 `<!-- dream-promoted: <fp> -->` 标记段落（diff +69 行） |
| apply #2 | 同上再跑 | exit 0，`applied: 0`，**diff = 0 行**（幂等成立） |

真实 recalls 证据（memory_search 命中）：
- `Assistant: 删除 0，失败 0` → recalls=4，score=0.8168
- `reference_data 表设计: variance_reason...` 等跨日复现条目 → score=0.3269（days_seen 驱动）

## 3. fail-closed 验证
`--no-probe` 或 store 中无信号时 `--apply` 返回 exit 2 且不写 MEMORY.md（测试 test_fail_closed 覆盖）。

## 4. 已知限制（遗留）
1. recall 探测受 `--probe-limit` 限流（本次 8/6626），未探测条目按跨日频次评分；
   生产可配合定时任务放大 limit，或对全量候选做「关键词 → memory_search」批量探测。
2. `--json` 模式下 human 摘要与 JSON 可能同时输出（stdout 混排），自动化消费请只取最后一个 JSON 对象。
3. MEMORY.md 采用追加式，不参与 L1 consolidation 的 supersede/merge；长期需人工或后续组件治理重复主题。
4. 本机 82 天报告里大量候选为历史会话噪音（reset/寒暄），已由 NOISE_PATTERNS 拦截，未计入晋升。
5. 本组件**不写回 L1 召回存储**；L1 自身死锁（daily/grounded 信号未产生）仍存在，需 L1 上游修复或后续单独排查 admissionPolicy。
