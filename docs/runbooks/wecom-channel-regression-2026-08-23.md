# 企业微信渠道回归测试报告

| 项 | 值 |
|---|---|
| 测试时间 | 2026-08-23 00:41~00:45 CST |
| 触发原因 | gateway 重启后验证 channel 完整性 + 停用 openclaw-weixin 的副作用检查 |
| 插件 | `@wecom/wecom-openclaw-plugin@2026.5.7` |
| 宿主 | `openclaw@2026.7.2-beta.7` |
| 账号 | `wecom default`（企业微信），Bot mode / WebSocket |
| 结论 | **对话能力完整可用；主动投递受协议限制不可用（非配置问题）** |

---

## 1. 测试矩阵

| # | 用例 | 方法 | 结果 | 证据 |
|---|---|---|---|---|
| T1 | channel 加载 | `channels status --channel wecom` | ✅ | `enabled, configured, **running**` |
| T2 | WS 连接 + 鉴权 | gateway 日志 | ✅ | `00:41:10 WebSocket connected` → `Authentication successful` |
| T3 | weixin 停用副作用 | 日志检索 | ✅ | 重启后时段 `channel-runtime` 报错 **0** 次 |
| T4 | 权限策略读回 | 配置读取 | ✅ | `dmPolicy=pairing`, `ownerAllowFrom=["wecom:1313"]` |
| T5 | pairing 状态 | `pairing list wecom` | ✅ | `No pending` — 已批准且持久 |
| T6 | 会话可寻址性 | `conversations_list` | ✅ | `conv_02b0c774…` / `target: user:1313` **跨重启存活** |
| T7 | **主动投递** | `conversations_send` 实发 | ❌ | `errcode=93006, errmsg=invalid chatid` |
| T8 | 入站回调 | 日志计数 | ✅ | `aibot_msg_callback` 累计 2 次 |
| T9 | 流式回复 | streamId 序列 | ✅ | `finish=false`(增量) → `finish=true`(收尾) |
| T10 | 消息路由 | dynamic-routing 日志 | ✅ | `matchedBy=default, agentId=main` |
| T11 | 出站回复（应答） | `Reply ack received` | ✅ | 累计 4 次成功 ack |

**通过 10 / 11。唯一失败项 T7 为平台协议限制，非配置缺陷。**

---

## 2. 关键发现

### 2.1 `running` ≠ 之前的 `configured`

重启前状态是 `configured`，重启后为 **`running`**。说明：

- 停用 `openclaw-weixin` 消除了插件加载阶段的连带干扰
- WeCom channel 现在是真正的运行态，不只是"配置存在"

> 插件 README 有专节 `Channel 显示 "OK" 但未连接` —— 印证 `OK`/`configured`
> 不足以判定可用，必须看 `running` + WS 鉴权日志。

### 2.2 T7 失败：主动投递受协议限制（第二次实测确认）

```
2026-08-23T00:42:17 WARN: Reply ack error:
  errcode=93006, errmsg=invalid chatid
```

**重启不改变此结论**（首次实测于 2026-08-22 23:16，见 EXP-006）。

根因：aibot 单聊回调 body 无 `chatid` 字段，仅有 `from.userid` 与
单条消息级、会过期的 `response_url`。`aibot_send_biz_msg` 需合法 `chatid` → 必然 93006。

**能力边界**：

| 方向 | 可用性 |
|---|---|
| 入站（用户 → Jerry） | ✅ |
| 出站**应答**（回复当条消息） | ✅ 含流式 |
| 出站**主动**（cron / 告警 / 广播） | ❌ 需 Agent mode |

### 2.3 会话地址跨重启持久，且 target 被规范化

```
重启前: target = wecom:1313
重启后: target = user:1313      ← 规范化为标准前缀形式
conversationRef 不变: conv_02b0c7742a357cf0c31e93a47bdf5d58
```

`conversationRef` 稳定，可安全用于长期引用。

### 2.4 群聊策略未配置（当前无群聊场景）

```
groupPolicy      = null
groupAllowFrom   = null
```

插件默认 `groupPolicy: open`（README L428 附近）。**当前未在任何群中使用，
故无实测数据**。若将来入群，需先确认此项——`open` 意味着任意群可触发。

> **未实测的不写成结论**：本次无群聊入站样本，群聊能力状态为「未验证」，
> 不是「可用」也不是「不可用」。

---

## 3. 权限策略现状（可审计快照）

| 配置项 | 值 | 含义 |
|---|---|---|
| `dmPolicy` | `pairing` | 陌生发送者首条消息仅生成待批请求，**不建会话** |
| `allowFrom` | `[]` | 空 —— 依赖 pairing 逐个批准，非白名单模式 |
| `groupPolicy` | `null` | 未显式配置，插件默认 `open` |
| `groupAllowFrom` | `null` | 未配置 |
| `commands.ownerAllowFrom` | `["wecom:1313"]` | 由 `pairing approve` **自动写入** |

⚠️ **`dmPolicy: pairing` 的静默特性**：未批准时 `conversations_list` 返回空数组，
表象等同于"用户没发消息"。排查顺序应为 **先查 gateway 日志，再查 conversations_list**。

⚠️ `pairing approve` 会自动修改 `commands.ownerAllowFrom`。该值含成员归属标识，
公开仓库需脱敏 —— 已于 2026-08-22 修复 `snapshot_config.py` 列表元素脱敏漏洞（EXP-006 §同期修复）。

---

## 4. 诊断方法（可复用）

日志位置 **不在** `~/.openclaw/logs/`（那里只有 watchdog / restart）：

```bash
plutil -p ~/Library/LaunchAgents/ai.openclaw.gateway.plist | grep StandardOutPath
# => ~/Library/Logs/openclaw/gateway.log
```

分环节验证，避免"配置错了"这类笼统判断：

```bash
L=~/Library/Logs/openclaw/gateway.log
grep '\[wecom\]' "$L" | grep -E "Authenticated|Authentication successful"  # 凭据有效？
grep -c 'aibot_msg_callback' "$L"                                          # 入站到达？
grep -c 'Reply ack received' "$L"                                          # 应答成功？
grep 'aibot_send_msg' "$L" | grep -oE 'errcode=[0-9]+|errmsg=[a-z ]+'      # 主动发失败？
grep -oE 'streamId=[a-z_0-9]+, finish=(true|false)' "$L" | tail            # 流式工作？
```

**四层分离**：鉴权 / 入站 / 应答 / 主动发。本次正是靠这个矩阵定位到
"只有第 4 层失败"，从而排除配置问题。

---

## 5. 结论与建议

### 可用（无需动作）

企业微信对话能力**完整**：入站、应答、流式、路由、pairing 权限控制全部工作正常。
Rex 可直接在企微中与 Jerry 对话、下达指令（已配为 command owner）。

### 不可用（已接受，不建设）

主动投递需 Agent mode（自建应用）：

```
corpId / corpSecret（自建应用的，≠ Bot Secret）/ agentId / token / encodingAESKey
+ 回调 URL 公网可达（gateway 默认 127.0.0.1:18789，需内网穿透）
```

**决定暂不建设**：需企业微信管理员权限 + 通讯录读取权限 + 开公网入口，
收益仅"每日摘要自动推送"，而摘要已落盘 `memory/` 与 `logs/observability/`。
扩大攻击面换取边际便利，不划算。

### 未验证（不写成结论）

- **群聊能力**：无入站样本。入群前需先确认 `groupPolicy`（默认 `open`）。
- **个人微信主动推送**：`openclaw-weixin` 因宿主 breaking change 无法加载（EXP-007），
  源码显示理论可行但**未经实测**。

### 相关配置状态

`每日观测摘要` cron 已回滚为 `delivery.mode=none` + `failureAlert=false`，
不会产生每日失败告警。

---

## 6. 相关文档

- [EXP-20260822-006](../knowledge-base/by-category/project-experience/correct/EXP-20260822-006-wecom-aibot-cannot-push-proactively.md) — aibot 无法主动推送（根因分析）
- [EXP-20260823-007](../knowledge-base/by-category/project-experience/correct/EXP-20260823-007-plugin-declares-compat-but-imports-missing-sdk-subpath.md) — openclaw-weixin 加载失败
- [ADR-202608-008](../knowledge-base/by-category/project-experience/adr/ADR-202608-008-tool-policy-governance.md) — 工具策略三态模型
- 官方文档：https://docs.openclaw.ai/channels/wecom/
