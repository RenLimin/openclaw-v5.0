---
type: experience
id: EXP-20260822-006
date: 2026-08-22
title: WeCom aibot 单聊只能应答不能主动推送（93006）
category: correct
layers: [L1, L2]
tags: [wecom, channel, cron, delivery, proactive-messaging, platform-limit]
related: [EXP-20260822-005, ADR-202608-004]
---

# WeCom aibot 单聊无法主动投递（errcode 93006）

## 场景

给 cron「每日观测摘要」配 WeCom 投递。已装官方插件、`botId` + `secret` 配好、
WS 鉴权成功、能正常收发对话，但 cron 主动推送始终失败。

## 结论（实测）

**智能机器人（aibot / Bot mode）能"应答"，不能"主动推"1:1 私聊。**

| 环节 | 结果 |
|---|---|
| WS 连接 + 鉴权 | ✅ `Authentication successful` |
| 入站回调 | ✅ `aibot_msg_callback` 正常 |
| **回复**当前消息 | ✅ `Reply ack received` |
| **主动**发送 | ❌ `errcode=93006, errmsg=invalid chatid` |

## 根因

aibot 单聊回调 body 的真实字段：

```json
{"msgid":"...", "aibotid":"...", "chattype":"single",
 "from":{"userid":"1313"}, "response_url":"...", "text":{...}}
```

**没有 `chatid`**（群聊才有）。可用的只有：

- `from.userid` —— 通讯录 ID，但 Bot 无通讯录读取权限，不能用于 `aibot_send_biz_msg` 寻址
- `response_url` —— **单条消息级、会过期**，只能回复当条消息

主动发送需调 `aibot_send_biz_msg`，该接口要合法 `chatid` → 拿不到 → 93006。

插件源码 `dist/index.js` 有印证性注释：

> 按 sessionKey 精确取回「原始大小写」的 chatId / chatType …
> 小写后的 chatId 调用企业微信 `aibot_send_biz_msg` 会报 invalid chatid

说明这条路径确实依赖 chatid；单聊场景 `getSessionChatInfo()` 返回 `undefined`。

## 文档误读警示 ★

插件 README 的两句话容易被读反：

| 原文 | 正确理解 | 易犯的误读 |
|---|---|---|
| L278 "Bot WebSocket available → send via WS" | 描述**出站优先级**（Bot 优先、Agent 兜底） | ❌ "Bot 能主动发任意目标" |
| L282 "**Agent-only** accounts can still send proactive messages" | Agent **补** Bot 的短板 | ❌ 反推"Bot-only 也能主动发" |

**教训：README 的「支持主动消息」是模式级笼统描述，不等于每种模式支持每种目标类型。
必须实测。** 本次两轮结论互相矛盾，都是先下判断后验证；实际拿到 93006 日志只需 5 分钟。

## 另一个前置陷阱：`dmPolicy: pairing` 静默扣留首条消息

`dmPolicy: pairing`（插件默认 `open`，本机配为 `pairing`）下，陌生发送者首条消息
**只生成待批请求，不建立会话**：

```
[wecom] Pairing request created for sender=1313
```

此时 `conversations_list(channel=wecom)` 返回 **空数组** —— 看起来像"用户没发消息"，
实际消息已到达。**排查顺序应是先看 gateway 日志，再看 conversations_list。**

批准：

```bash
openclaw pairing list wecom              # 拿 CODE
openclaw pairing approve wecom <CODE>
```

⚠️ `openclaw pairing list`（不带 channel 名）会报
"No chat DM pairing channels are configured" —— 因为 wecom 是 plugin channel，**必须带 channel 参数**。

⚠️ 批准会**自动写入** `commands.ownerAllowFrom`（若原为空）：

```
Command owner configured wecom:1313 (commands.ownerAllowFrom was empty)
```

这是一次配置变更，公开仓库需确认快照已脱敏（见 §同期修复）。

## 正确的诊断方法

日志在 `~/Library/Logs/openclaw/gateway.log`（**不在** `~/.openclaw/logs/`，
后者只有 watchdog / restart）。位置来自 launchd：

```bash
plutil -p ~/Library/LaunchAgents/ai.openclaw.gateway.plist | grep StandardOutPath
```

分环节验证，避免"配置错了"的笼统结论：

```bash
L=~/Library/Logs/openclaw/gateway.log
grep '\[wecom\]' "$L" | grep -E "Authenticated|Authentication successful"  # 凭据有效？
grep -c 'aibot_msg_callback' "$L"                                         # 入站到了？
grep 'Reply ack received' "$L"                                            # 回复成功？
grep 'aibot_send_msg' "$L" | grep -oE 'errcode=[0-9]+|errmsg=[a-z ]+'     # 主动发失败？
```

## 要主动投递需 Agent mode（成本评估）

需 5 项凭据 + 1 个基础设施条件：

```
corpId / corpSecret（自建应用的，≠ Bot Secret）/ agentId / token / encodingAESKey
+ 回调 URL 公网可达（gateway 默认 127.0.0.1:18789，需内网穿透）
```

**权衡（本项目决定暂不做）**：需企业微信管理员权限 + 通讯录读取权限 + 开公网入口，
而收益仅为"每日摘要自动推送"——摘要本已落盘 `memory/` 与 `logs/observability/`。
**扩大攻击面换取边际便利，不划算。** 待出现真实主动告警需求再一并建设。

## 收尾：失败配置必须回滚

实测失败后应立即恢复，否则每天定时失败一次并触发告警：

```bash
openclaw cron edit <jobId> --no-failure-alert
# delivery 改回 mode=none（automations update patch: delivery.mode=none, channel/to 置 null）
```

读回确认 `delivery.mode=none` + `failureAlert=false`。

## 与 EXP-005 的联动（第二次验证）

`lastRunStatus: ok` 但 `lastDeliveryStatus: not-delivered`。
**只看 `lastRunStatus` 会误判为成功。** 必须分开看两个字段 —— 这是 EXP-005 的教训，本次再次生效。

## 同期修复：快照脱敏漏列表元素

`snapshot_config.py` 的 `redact()` 原逻辑：

```python
if is_secret_key(k) and not isinstance(v, (dict, list)):   # ← list 被跳过
```

敏感键的值若为**列表**则完全不脱敏。`ownerAllowFrom: ["wecom:1313"]` 正好命中，
成员归属标识进入公开仓库快照。已修为逐元素脱敏，并补 8 个字段
（`ownerallowfrom`/`allowfrom`/`groupallowfrom`/`userid`/`openid`/`toparty`/`totag`/`touser`）。

**这是 `SECRET_KEYS` 第三次同类遗漏**（前两次：`botId`、WeCom Agent 字段），
印证 ADR-007 P4「新 provider 凭据字段名未被覆盖 → 泄漏」是持续性风险，
不是一次性任务。回归验证：`contextWindow` / `maxTokens` 等容量参数未被误脱敏。

## 参考

- 官方 WeCom 文档：https://docs.openclaw.ai/channels/wecom/
  —— 只含 3 条安装命令，**明确声明凭据/连接模式属外部插件**，OpenClaw 侧不要求 Corp ID
- 插件 README：`~/.openclaw/npm/projects/wecom-wecom-openclaw-plugin-*/node_modules/@wecom/wecom-openclaw-plugin/README.md`
- 错误码查询：https://open.work.weixin.qq.com/devtool/query?e=93006
