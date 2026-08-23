---
type: experience
id: EXP-20260822-005
date: 2026-08-22
title: cron delivery 失败会污染 job 状态 — 无 channel 环境须设 delivery.mode=none
layers: [L1, L2]                # L1 OpenClaw cron 契约；L2 可观测性组件
stage: manage
severity: medium               # 任务实际成功，但状态误报 error，掩盖真实故障
category: correct
tags: [openclaw, cron, automations, delivery, channel, observability]
status: active
supersedes: null
superseded_by: null
---

# [EXP-20260822-005] cron 任务「成功却报 error」：delivery 失败污染 job 状态

## 1. 背景

L2 可观测性组件的「每日观测摘要」cron（`0 9 * * *` @ Asia/Shanghai，`sessionTarget: isolated`）
连续多日 `lastRunStatus: error`，但产物（`memory/YYYY-MM-DD.md` 摘要、
`logs/observability/*.jsonl`）**每次都正常生成**。

环境：OpenClaw 2026.7.2-beta.7，本机**零 channel 配置**（只用 webchat，非可投递 channel）。

## 2. 问题

### 2.1 症状

```
openclaw cron list --all
→ 每日观测摘要 ... Status: error
     Delivery: announce -> last (last -> no route, will fail-closed: Channel...)
```

但 `openclaw cron runs --id <jobId>` 里每条 `summary` 都是成功的：

```
status = error
deliveryStatus = not-delivered
summary = "✅ 已完成。每日观测摘要已写入 memory/2026-08-22.md，原始数据也已生成。"
```

### 2.2 根因

`status: error` **不是任务执行失败，是投递失败**。链条：

1. job 的 `delivery.channel = "last"`（默认行为：投到"上次用过的 channel"）
2. 本机 `openclaw channels list --all` → **全部 `not installed, not configured, disabled`**
3. 投递解析失败：
   ```
   Channel is required (no configured channels detected).
   Run openclaw channels add to configure one...
   ```
4. **投递失败被计入 job 整体 status** → `error`，且触发 failure alert（同样投递失败，二次噪音）

### 2.3 为什么危险

任务实际成功却常态化报 `error`，会**训练人忽略这个状态位**。真正的执行失败发生时无法区分。
可观测性组件自己不可观测 —— 这是最讽刺的失败模式。

## 3. 方案

### 3.1 修复

产物直接落盘（写 `memory/` 与 `logs/`）的 job **不需要投递**，显式关闭：

```bash
openclaw cron edit <jobId> \
  --no-deliver \          # delivery.mode = none
  --no-failure-alert \    # 关闭告警，避免二次投递噪音
  --clear-channel \       # 清掉 channel: "last"
  --description "...delivery=none（本机无 channel，结果直接写 memory/）..."
```

等价配置：
```json
{ "delivery": { "mode": "none", "bestEffort": true }, "failureAlert": false }
```

### 3.2 验证

```bash
openclaw cron run <jobId>          # 手动触发
sleep 45
openclaw cron runs --id <jobId>    # 看最新 entry
```

修复前后对比：

| 字段 | 修复前 | 修复后 |
|---|---|---|
| `status` | `error` | **`ok`** |
| `deliveryStatus` | `not-delivered` | **`not-requested`** |
| `consecutiveErrors` | 累积 | **0** |
| 产物 | 正常 | 正常（未变） |

`not-requested` 是关键信号：**主动不投递** ≠ 投递失败。

## 4. CLI 陷阱（实测）

1. **`openclaw cron` 无 `update` 子命令，是 `edit`**。`cron update` 会报错。
2. **`cron runs` 必须带 `--id`**：`openclaw cron runs --id <jobId>`，位置参数会报
   `Missing required option "--id <id>"`。
3. **`cron logs` 不存在**。运行历史只有 `cron runs`。
4. **`cron runs` 的 JSON 顶层键是 `entries`**，不是 `runs`/`items`。
   ```bash
   openclaw cron runs --id <jobId> | python3 -c "
   import json,sys
   for e in json.load(sys.stdin)['entries']:
       print(e['tsIso'], e['status'], e['deliveryStatus'], str(e['summary'])[:120])
   "
   ```
5. **`automations` 工具的 `patch.failureAlert` 只接受 object**，传 `false` 报
   `must be object`。要关闭得用 CLI `--no-failure-alert`。
6. **`cron run` 是异步入队**，返回 `{ok, enqueued, runId}` 后需等待（本例 16~30s），
   再查 `cron runs` 看结果。

## 5. 教训

**规则**（可推广）：

1. **cron job 的 `status` 混合了「执行结果」与「投递结果」**。排查前先看 `deliveryStatus`
   和 `summary` 区分二者，不要被 `error` 直接误导。
2. **产物落盘型 job 必须 `delivery.mode = none`**。默认的 `channel: "last"` 在无 channel
   环境必然失败。`isolated` target 尤其容易踩 —— 它没有"上次的 channel"上下文。
3. **同时关 `failureAlert`**。告警本身也走投递，投递坏了告警也发不出，只是徒增噪音记录。
4. **常态化的假 error 比没有监控更糟**。它让状态位失去信号价值。发现 job 长期 error 但产物
   正常时，优先怀疑投递配置，并**修到 `ok`** 而不是"知道它其实没事"。
5. **休眠不影响补跑**。本机 9:00 处于休眠，cron 在 09:03 唤醒后补跑成功 —— 说明调度器有
   catch-up 行为，休眠不是漏跑原因。

**监控点**：
- ⚠️ 未来若配置了真实 channel（Feishu/WeCom 等），需重新评估是否要打开投递
- ⚠️ 新建 cron job 时，若产物落盘则**默认加 `--no-deliver`**，不要等它报错
- ⚠️ **`--no-deliver` 阻止不了 agent 主动调 `message`**（见 §6.2）—— WeCom 已上线，
  落盘型 job 若要确保静默，需在提示词或 `payload.toolsAllow` 里限制

**升级判断**：
- [x] 涉及 L1 契约（cron/automations 投递语义）
- [x] 影响 L2 组件（可观测性）
- [ ] 多模块对齐
- **决定**：保持经验卡片。属配置操作范式与故障识别，非架构决策。

## 6. 相关

- **组件**：`scripts/observability/agent_observer.py`（ADR-202608-004）
- **job**：`每日观测摘要` id `aadc3416-5c72-4333-ad4f-6ef0402db0cc`
- **约定**：`docs/conventions/commit-and-config.md`（同样强调"读回才算验证"）
- **相关卡片**：`EXP-20260822-004`（同日：不要相信推断，去实测）

## 6.1 环境变更（2026-08-22 12:03）

WeCom channel 已由 Rex 配置并启用（`openclaw channels list --all` → `installed, configured, enabled`）。

**本卡片的结论仍然成立**，但适用前提变了：

| 项 | 状态 |
|---|---|
| 根因分析（status 混合执行与投递结果） | ✅ 仍然正确，与 channel 有无无关 |
| 「产物落盘型 job 应设 delivery.mode=none」 | ✅ 仍然推荐 —— 写文件的任务本就不需要投递 |
| 「本机零 channel，投递必然失败」 | ⚠️ **已过期** —— 现有 WeCom 可投递 |
| 6 个 CLI 陷阱 | ✅ 仍然有效 |

**未改动现有 cron 配置**：`delivery.mode=none` 对落盘型任务依然是正确选择。
若要把每日观测摘要投到 WeCom，需 Rex 明确要求（涉及对外发送）。

## 6.2 ⚠️ 重要修正（2026-08-23）：`--no-deliver` 不等于"不会外发"

本卡片隐含假设「设了 `delivery.mode=none` 任务结果就不会外发」。
**官方文档明确否定了这个推断**（`cli/cron.md:97` / `cron-jobs.md:331`）：

> `--no-deliver` disables that fallback **but does not remove the agent's
> `message` tool** when a chat route is available.

即：

| 机制 | `delivery.mode=none` 能否阻止 |
|---|---|
| 自动投递（announce/webhook） | ✅ 能阻止 |
| **agent 主动调 `message` 工具** | ❌ **阻止不了** |

**为何现在才重要**：卡片创建时本机零 channel，`message` 工具无路可走，
两者区别不可观测。**WeCom 上线后（见 §6.1）差异变得真实** ——
落盘型 job 的 agent 仍可主动往 WeCom 发消息，`delivery.mode=none` 管不了。

**确保不外发需两层**：

1. `delivery.mode=none` —— 关自动投递
2. **job 提示词里显式要求不调 `message`**，或给 job 限制工具集（`payload.toolsAllow`）

当前三个 cron job 均为落盘型，提示词未显式禁止 `message`。
**属潜在风险而非已发生事故**（实测未见主动投递），已记入监控点。

> 教训：卡片的结论依赖环境前提时，**前提变了要回头重评**。
> “本机零 channel” 这类前提应在卡片里显式标注，而非隐含在结论里。

## 7. 变更历史

- 2026-08-22: 创建（cron delivery 污染 status 的识别与修复 + 6 个 CLI 陷阱）
- 2026-08-22 12:03: 补 §6.1 —— WeCom channel 已配置，标注哪些结论过期、哪些仍成立
- 2026-08-23: 补 §6.2 —— 官方文档明确 `--no-deliver` **不移除 `message` 工具**，
  WeCom 上线后落盘型 job 仍可主动外发；监控点新增一条
