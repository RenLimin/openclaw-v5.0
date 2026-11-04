# DESIGN-OUTLINE — 会话/超时故障自动恢复可靠性加固 v1.0

- 状态：**待 Rex 评审**
- 日期：2026-11-04
- 作者：Jerry 🦞
- 层级：L2 基础设施（跨 error_handler / gateway-safety / session-recovery / model-scheduling）
- 关联事故：2026-11-03 本会话（`agent:main:dashboard:4bd7e100`）`FailoverError: LLM request timed out.` 未自动救回
- 前置：P0 止血已交付（commit `b120892`：增量游标检测 + cron 2h→15m）

---

## 1. 背景与根因（已用证据确认）

2026-11-03 23:08–23:47，主工作会话两次 LLM 请求超时（model-scheduling 把所有
fallback 节点试遍仍超时），任务中断且未被自动恢复。排查确认四道防线各有缺口：

| # | 防线 | 缺口 | P0/P1 |
|---|---|---|---|
| 1 | 日志事件检测 | 30min 时间窗口 vs 2h cron，滑窗事件永久漏报 | **P0 已修** |
| 2 | guarded 重启 | guard 因 in-flight compaction 正确阻断（rc=1）后**无补偿重试**，拦完即放弃 | P1-a |
| 3 | 会话级重试 | 硬编码只盯 `agent:main:main`；要求 `status=failed`（turn 超时后会话仍 `running`）；要求 current-task active | P1-b |
| 4 | 故障对症 | `FailoverError` 是上游端点问题、gateway 进程健康，却一律重启 gateway，不对症；且**无任何机制重发 turn 续跑任务** | P1-c |

另有一处放大器：

| # | 问题 | 现象 |
|---|---|---|
| 5 | 巡检器自身超时 | 19:24 / 21:26 两次 error-scan 子进程被慢端点拖死（929s / 672s，no output），检测停摆 | P1-d |

**关键事实（不可违背的现状）**

- `FailoverError` 时 gateway 进程存活（cron/exec/日志正常），重启进程**不能**恢复
  某个会话中断的 turn。
- 当前**不存在**"自动重发一条用户消息到 dashboard 会话续跑"的已验证通路；
  `check_and_retry.wake_session()` 用的是
  `openclaw agent --agent main --session-key <key> --message ...`。
- compaction 进行中**绝不可**重启（2026-10-27 自杀式重启事故立的护栏，必须保留）。

---

## 2. 目标 / 非目标

### 目标

1. guard 因瞬时关键工作阻断重启后，能在工作结束、且故障仍在时**安全补一次**恢复动作。
2. 会话级恢复覆盖**真实在跑任务的会话**（不只是写死的 main），并能识别
   "turn 超时但会话非 failed"这一形态。
3. 对 `FailoverError` **对症处置**：先探测上游/切 fallback，重启只作为最后手段。
4. 巡检器在慢端点下不再整进程超时停摆（外部探测严格超时、隔离、降级）。
5. 所有自动动作幂等、有界（次数/间隔）、可审计、可人工接管，杜绝风暴与自杀式重启。

### 非目标（本期不做）

- 不做"重放用户原始消息"式的全自动 turn 续跑（风险高，可能重复副作用；
  仅做"安全重启发话/通知"，是否真续跑由人或显式授权开关决定，默认**只通知不代跑**）。
- 不接泛微/企微等外部系统回写。
- 不改 model-scheduling 的路由核心算法，只读取其健康信号/调用既有切换能力。
- 不做跨主机编排。

---

## 3. 方案大纲（4 个改动点）

### P1-a 挂起式安全重启补偿（gateway-safety + error_handler）

- `safe_restart.sh` rc=1（hard block，compaction in-flight）时，扫描器不再"记完即弃"，
  而是写一条 `pending-recovery` 记录：
  `~/.openclaw/state/pending-recovery.json`（含原因、时间戳、触发证据 hash、attempt 计数）。
- 后续每轮扫描：若存在 pending 且
  (a) guard 放行（rc=0）、(b) 原始故障信号仍在/复现、(c) 在最长等待 TTL 内、
  (d) 未超补偿次数，
  则执行一次 guarded 重启并清除 pending；否则保留等待，超 TTL 转人工通知。
- **去抖**：同一故障证据只挂一条；compaction 结束后最多补 1 次，绝不连续重启。
- rc=2（indeterminate）维持现状，不纳入自动补偿。

### P1-b 会话级恢复接对（session-recovery）

`check_and_retry.py` 三处纠偏：

1. **会话枚举去硬编码**：不再只看 `agent:main:main`，改为枚举"有未完成任务归属的
   活跃会话"。会话与任务的归属从 task_tracker 记录的 `session_key` 取
   （需在 start 时落 session_key，见下方"数据模型增量"）。
2. **识别 turn 超时形态**：会话 `running` 但最近一次 turn/run 以
   `LLM request timed out` / `FailoverError` 终态、且超过静默阈值（如 ≥10min 无新输出）
   才判"卡住"，避免误判正常长任务。判定数据源：gateway 日志增量（复用 P0 游标）
   + sessions 状态，二者交叉确认。
3. **放宽 current-task 门槛**：以"会话绑定的任务"为准，而非只认全局单个 current-task；
   无任务的会话超时只通知、不自动动作。

**默认安全档**：检测到卡住 → 先记录 + 通知 Rex（含会话、任务、最后断点、建议命令）；
自动"重启发话"由显式开关 `--auto-wake` 控制，默认关闭。保留 MAX_RETRIES=2、
最小间隔 5min、blocked 首次通知等既有护栏。

### P1-c FailoverError 对症处置（model-scheduling × error_handler）

- 检出 `llm_timeout` 时，不再第一步就重启 gateway，处置顺序改为：
  1. 调用 model-scheduling 健康探测（复用/增强 `health_check.py`，**严格短超时**），
     判断是"全端点不可用"还是"单端点慢"。
  2. 全端点连续 N 次失败 → 建议/（在授权下）切 fallback 模型，并通知；
     单次/瞬时 → 只记录不动作。
  3. 仅当**同时**存在 gateway 进程级异常（`openclaw status` 不健康）时才走
     P1-a 的 guarded 重启。端点问题 + 进程健康 => **不重启**。
- 处置决策与证据写入 `error-scan-latest.json` 的 fixes，便于审计"为什么没/有重启"。

### P1-d 巡检器自身超时隔离（error_handler）

- 所有外部网络探测收敛为统一的短超时（建议连接 3s / 总 8s），逐项 try/except 隔离，
  单端点慢不阻塞其余扫描，更不拖垮主进程。
- 主流程对每个 scan_* 设独立预算并 catch 超时，失败的单项标记
  `scanner_item_timeout`，其余结果正常产出。
- 评审点：昨晚 672s/929s 的具体卡点需在 DETAIL 阶段用计时日志确认（疑似串行
  provider 探测 + 缺超时），不凭猜测改。

---

## 4. 数据模型增量（最小）

- task_tracker start 增加可选 `session_key` 字段（向后兼容，缺省为空）。
- 新增 `~/.openclaw/state/pending-recovery.json`（运行态，不入库不入 git）。
- 复用 P0 `memory/error-scan-cursor.json` 供会话卡住判定读增量日志。
- 不改任何业务库；新增字段一律可选、幂等迁移。

---

## 5. 模块影响面

| 组件 | 文件（预期） | 改动性质 |
|---|---|---|
| gateway-safety | `scripts/safe_restart.sh`（仅可能加结构化 rc 输出）、新增 pending 小模块 | 增量 |
| error_handler | `scan_errors.py`（处置顺序、分项超时、pending 联动） | 增量 |
| session-recovery | `check_and_retry.py`、`task_tracker.py`（session_key） | 增量 |
| model-scheduling | `scripts/health_check.py`（增强/严格超时，不改路由） | 增量 |
| 测试 | 各组件 `tests/` 新增，纯函数优先，真实临时文件/日志 fixture | 新增 |

红线：不删既有 guard 判定；不提高自动重启/自动代跑的激进程度；不引入第三方依赖、
凭据、网络外呼（健康探测仅访问已配置的模型端点，属既有行为）。

---

## 6. 验收标准（黄金用例，DETAIL 固化）

1. **补偿重启**：构造 pending + compaction 结束 + 故障仍在 → 恰好补 1 次 guarded 重启；
   guard 仍 block 时不重启、不计数风暴；超 TTL → 人工通知。
2. **卡住识别**：会话 running 但 turn FailoverError 且静默超阈值 → 判卡住并通知；
   正常长任务（持续有输出）→ 不误判。
3. **对症不重启**：注入（fixture）FailoverError + 进程健康 + 端点全挂 →
   只切 fallback/通知，**不重启**；进程不健康才重启。
4. **巡检隔离**：某探测端点 hang → 该项标 item_timeout、主扫描 exit=0 且其余结果完整，
   总耗时有上界。
5. **幂等有界**：同一证据连跑 3 轮，重启/通知/重启发话次数稳定不增长。
6. **回归**：P0 的 19 个单测 + 新增测试全绿；现有 session-recovery / gateway-safety
   测试零破坏。全部结果真实执行，不虚构。

---

## 7. 分期与工时

| Phase | 内容 | 估时 |
|---|---|---|
| P1-1 | P1-d 巡检分项超时隔离（最独立、先止血检测稳定性） | 0.5 人日 |
| P1-2 | P1-c FailoverError 对症 + 健康探测增强 | 1 人日 |
| P1-3 | P1-a pending 补偿重启 | 1 人日 |
| P1-4 | P1-b 会话卡住识别 + task session_key（默认只通知） | 1.5 人日 |
| 合计 | 含缓冲 | 约 4–4.5 人日 |

每 Phase 独立可交付、可回滚；自动"重启发话/切 fallback"的激进开关默认关闭，
需要时由 Rex 显式打开。

---

## 8. 待 Rex 拍板的决策点

1. **自动代跑档位**：卡住时默认"只通知不自动重启发话"，是否同意？
   （我推荐默认保守；自动重启发话有重复副作用风险。）
2. **自动切 fallback**：端点连续失败时，是"仅建议"还是"自动切换 + 通知"？
   （我推荐先仅建议，把切换也做成显式开关。）
3. **Phase 顺序/范围**：是否按 P1-1→P1-4 全做，还是先挑 P1-d + P1-c？
