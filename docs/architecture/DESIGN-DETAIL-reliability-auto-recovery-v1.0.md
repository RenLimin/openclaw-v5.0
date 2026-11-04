# DESIGN-DETAIL — 故障自动恢复可靠性加固 v1.0

- 状态：**OUTLINE 已由 Rex 通过（2026-11-04）；DETAIL 待评审后按 Phase 编码**

> **实现状态变更（2026-11-04，Rex 授权"同意按建议执行"后直接落地，P1 四项全部交付并推送）：**
>
> | 项 | Commit | 交付内容 |
> |---|---|---|
> | P1-d 分项超时隔离 | `31b8273` | `run_scan_items` 守护线程+预算45s，cron/provider/plugin/context 四项并发隔离，曾 929s→现 5–6s |
> | P1-c FailoverError 对症 | `457f379` | 新增 `endpoint_probe.py` 探三端点；进程不健康才重启，全端点连续2轮不可达仅建议切 fallback，瞬时只观察 |
> | P1-a 挂起补偿重启 | `b3a6f63` | 新增 `recovery_pending.py`（TTL30min/最多补1次/evidence去抖）；guard rc=1 阻断后压缩结束且故障仍在恰好补1次 |
> | P1-b 会话卡住识别 | `d1afbde` | 新增 `stall_detect.py` 跨轮状态机+独立游标；绑任务卡住→通知，无绑定仅记录，默认不代跑，`--auto-wake` 显式开启 |
>
> **测试**：error_handler 35、gateway-safety 7、model-scheduling 7、session-recovery 88 passed（新增均绿）。
> session-recovery 仅剩 **7 个改造前已存在的既有红账**（基线钉死，非本次引入），建议另行专项收口。
> P0 见 `b120892`（增量游标 + 15min 周期）。此段为事后状态指针，正文不回改，保审计链。
- 作者：Jerry 🦞 · 关联：`DESIGN-OUTLINE-reliability-auto-recovery-v1.0.md`、P0 commit `b120892`
- 范围：L2 跨 error_handler / gateway-safety / session-recovery / model-scheduling
- 已定策略：**卡住默认只通知不自动代跑**；**切 fallback 仅建议 + 显式开关**；按 **P1-d→c→a→b** 推进

---

## 0. 现状锚点（均来自源码实测）

`L2-infra/scripts/error_handler/scan_errors.py` main（约 1024–1042）串行调用：

```
scan_cron_errors()
scan_llm_timeouts(new_log_lines)        # P0 纯函数
scan_compaction_failures(new_log_lines) # P0 纯函数
scan_provider_health()                  # = config_full_chain + asset + zombie + temp + openclaw status
scan_plugin_channel_health()
scan_context_overflow()
```

- `run_cmd(cmd, timeout=15)`：subprocess 有超时；网络探测 `urllib.urlopen(timeout=3/5)` 有超时。
- 但**主流程对每个 scan_* 没有独立 wall-clock 预算、没有异常隔离**：单项内部多次串行
  run_cmd/urlopen 的耗时会累加（2026-11-03 19:24=929s、21:26=672s 两次 no-output
  子进程超时即此形态），且任一 scan_* 抛异常会让整轮结果丢失。
- `auto_fix()`：`llm_timeout` → 一律 `safe_restart.sh`（timeout=120）；不区分端点问题
  与进程问题；rc=1（guard 硬阻断）后记 "not restarted" 即弃，无补偿。
- `check_and_retry.py`：会话 key 写死 `agent:main:main`；要求 current-task active；
  wake 用 `openclaw agent --agent main --session-key <k> --message ...`。
- model-scheduling `health_check.py` 仅 32 行，单一 HTTP 200 探测，无多端点/无聚合。

---

## 1. P1-d：巡检分项超时隔离（Phase 1，0.5 人日）

### 1.1 新增分项执行器（stdlib，无第三方依赖）

在 scan_errors.py 新增：

```python
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

SCAN_ITEM_BUDGET_SEC = 45          # 每个扫描项 wall-clock 硬预算
SCAN_ITEM_FAIL = "scanner_item_timeout"

def run_scan_item(name, fn, *, budget=SCAN_ITEM_BUDGET_SEC):
    """在有界时间内运行一个 scan_*，异常/超时隔离，不影响其它项。

    返回 (errors, item_errors)：
      - 正常：(fn(), [])
      - 超时：([], [{type: SCAN_ITEM_FAIL, name, detail: budget exceeded}])
      - 异常：([], [{type: scanner_item_error, name, detail: str(exc)}])
    用守护线程执行：超时后主线程直接返回，底层线程为 daemon，不阻塞进程退出
    （Python 无法强杀线程；网络/subprocess 调用自身已有 timeout，会自行收尾）。
    """
```

### 1.2 main 改造

6 个扫描项统一经 `run_scan_item` 执行（线程池 max_workers=3，**顺序无关的可并行**：
cron/provider/plugin 互相独立；依赖日志的两个纯函数保留同步直接调用——它们零IO极快）。
收集各自 item_errors 并入 all_errors。这样：

- 单项 hang 最多 45s 即被放弃并标记，主扫描一定产出、exit=0；
- 整轮 wall-clock 有上界（纯函数项忽略 + 3 批并发 ≈ 最多约 2×45s + 余量）。

### 1.3 契约与测试

- 纯函数、无副作用；item_errors 的 type 固定，供签名去重与审计。
- 测试（`tests/test_scan_isolation.py`）：
  1. 正常项原样返回；
  2. `time.sleep` 超预算 → 标 SCAN_ITEM_FAIL、不抛出；
  3. 项内 raise → 标 scanner_item_error、其余项照常；
  4. 三个慢项并发，总耗时 < 串行和（证明并行 + 预算生效）。

---

## 2. P1-c：FailoverError 对症处置（Phase 2，1 人日）

### 2.1 处置顺序（改写 auto_fix 中 timeout_errors 分支）

```
1) gateway 进程健康？ run_cmd("openclaw status", timeout=15)
2) 端点健康？       聚合探测（见 2.2），严格短超时
3) 决策：
   - 进程不健康                     → 走 P1-a guarded 重启
   - 进程健康 + 端点连续 N 次失败   → 仅建议切 fallback（fix: model_fallback_suggested）
   - 进程健康 + 单次/瞬时           → 只记录，不动作
```

**默认不自动切 fallback**；fix 里给出可直接执行的建议命令；自动切换仅在
`--enable-auto-fallback` 显式开关下执行（本期可只实现建议，开关留接口）。

### 2.2 model-scheduling 健康探测增强

`health_check.py` 增 `probe_endpoints(timeout=(3,8)) -> dict`：从 model-scheduling
配置读取已注册端点，逐个 `urllib` 短超时探测，返回
`{endpoint: {ok, latency_ms, error}}`，**单端点失败不影响其它**；CLI 保持向后兼容。
不新增依赖、不改路由算法、不读凭据明文（复用现有配置加载）。

### 2.3 测试

- 纯函数/本地 HTTP fixture（stdlib `http.server`）：全挂 / 部分挂 / 全通三态；
- auto_fix 决策表四行（进程×端点）断言"进程健康+端点挂 ⇒ fixes 中**无** restart"。

---

## 3. P1-a：挂起式安全重启补偿（Phase 3，1 人日）

### 3.1 新增 pending 模块 `recovery_pending.py`（stdlib）

状态文件 `~/.openclaw/state/pending-recovery.json`（运行态，不入库）：

```json
{"reason":"llm_timeout","evidence_hash":"<sha1 of triggering log lines>",
 "created_at":"...","attempts":0,"last_guard_rc":1}
```

接口：`load() / upsert(reason, evidence) / get() / clear() / touch(rc)`。
`evidence_hash` 去抖——同一故障证据只挂一条。

### 3.2 联动逻辑（auto_fix）

- guarded 重启 rc=1（hard block）→ `upsert` 挂起，fix result 记 "pending until guard clears"。
- 每轮扫描若存在 pending：
  guard rc=0 **且** 原始证据对应故障在最近增量日志复现/仍未恢复 **且** attempts<1 **且**
  未超 TTL（默认 30min）→ 执行一次 guarded 重启，成功则 clear、attempts+=1。
- guard 仍 rc=1 → 保留等待；超 TTL 或 attempts 超限 → 转人工通知 fix 并 clear。
- **同一证据最多补 1 次重启**，绝不连续重启；rc=2（不确定）不自动补偿。

### 3.3 测试

用临时 STATE_DIR + stub guard（rc=1→rc=0）：block 后放行恰好补 1 次；持续 block 不
计数；TTL 超时转人工；同证据 upsert 去重。

---

## 4. P1-b：会话卡住识别（Phase 4，1.5 人日，默认只通知）

### 4.1 task_tracker 增 session_key（向后兼容）

`start` 增可选 `--session-key`，落任务卡；缺省空。旧任务读取不受影响。

### 4.2 卡住判定（check_and_retry 改造）

- 去硬编码：枚举"绑定了未完成任务的会话"（从任务卡 session_key 取，而非只 main）。
- 形态识别：会话 `running` **且** P0 增量日志中该会话最近 turn 以
  `LLM request timed out`/`FailoverError` 终态 **且** 静默 ≥ STALL_SILENT_MIN（默认 10min）
  → 判 stalled。日志 + sessions 状态交叉确认；持续有输出的正常长任务不判。
- 无任务绑定的会话超时：仅记录。
- **动作默认只通知**：产出含会话/任务/最后断点/建议命令的通知；自动重启发话仅在
  `--auto-wake` 下执行（保留 MAX_RETRIES=2、最小间隔 5min、blocked 首次通知）。

### 4.3 测试

fixture 增量日志：running+FailoverError+静默超时 ⇒ stalled 且只通知（无 wake 子进程）；
running+持续输出 ⇒ 不判；`--auto-wake` 才触发 wake 且计数有界。

---

## 5. 事务边界 / 风险

- 所有新增状态文件在 `~/.openclaw/state` 或 `memory/`，git 已忽略；写操作幂等。
- 线程方案不能强杀线程：依赖被调网络/subprocess 自身超时收尾，daemon 不阻塞退出。
- 不删 guard 判定、不提高自动重启/代跑激进度、无第三方依赖/凭据/新外呼
  （健康探测仅访问已配置模型端点，属既有行为范畴）。

## 6. 验收（承接 OUTLINE §6）

每 Phase：新增单测真实跑全绿；最后跨组件回归 P0 19 测试零破坏；7 步法收尾
（含幂等连跑 3 轮、调用点 grep、结果真实执行）。

## 7. Phase / 工时

| Phase | 内容 | 工时 |
|---|---|---|
| P1-1 | P1-d 分项隔离 | 0.5d |
| P1-2 | P1-c 对症 + health_check 增强 | 1d |
| P1-3 | P1-a pending 补偿 | 1d |
| P1-4 | P1-b 卡住识别（只通知） | 1.5d |
