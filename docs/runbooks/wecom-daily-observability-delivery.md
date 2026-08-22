# 每日观测摘要 → 企业微信投递

> **状态**：⏸ 阻塞中 —— 缺 Agent mode 凭据
> **授权**：Rex 2026-08-22 明确要求（ADR-008 §6 授权项 2/2）
> **相关**：`EXP-20260822-005`（cron delivery 污染 status）· ADR-004（可观测性）

## 1. 为什么还没做

cron 投递走 **Agent outbound** 路径，插件 README §Notes 明确要求：

> Cron jobs use the **Agent outbound** path — Agent mode
> (`corpId` / `corpSecret` / `agentId`) must be configured.

当前配置只有 **Bot mode**：

| 字段 | 状态 |
|---|---|
| `channels.wecom.botId` | ✅ 已配 |
| `channels.wecom.secret` | ✅ 已配 |
| `channels.wecom.agent.corpId` | ❌ **缺** |
| `channels.wecom.agent.corpSecret` | ❌ **缺** |
| `channels.wecom.agent.agentId` | ❌ **缺**（主动推送必需）|

Bot mode 只能**被动响应**（有人 @ 机器人才回）。cron 是**主动推送**，必须走 Agent。

## 2. Rex 需要提供的三样

从企业微信管理后台 → 应用管理 → 自建应用：

| 字段 | 位置 | 说明 |
|---|---|---|
| **CorpID** | 我的企业 → 企业信息 | 形如 `ww1234567890abcdef` |
| **CorpSecret** | 应用详情页 | 应用的 Secret |
| **AgentId** | 应用详情页 | 数字，形如 `1000002` |

配置命令（**由 Rex 执行**，我不接触凭据明文）：

```bash
openclaw config set channels.wecom.agent.corpId <YOUR_CORP_ID>
openclaw config set channels.wecom.agent.corpSecret <YOUR_CORP_SECRET>
openclaw config set channels.wecom.agent.agentId <YOUR_AGENT_ID>
```

> 💡 更安全的做法：用 SecretRef 指向文件，而非明文写进 `openclaw.json`。
> 参见 ADR-005 凭据管理 + `scripts/credentials.sh`。

## 3. 另外两个前置条件

### 3.1 可信 IP 白名单

企业微信要求调用方 IP 在应用的**可信 IP 列表**内，否则 API 调用被拒。

两个选择：
- 把本机公网 IP 加进企业微信后台的可信 IP
- 或配固定出口代理：`channels.wecom.network.egressProxyUrl`

代理优先级（README §183）：
```
channels.wecom.network.egressProxyUrl
  > OPENCLAW_WECOM_EGRESS_PROXY_URL
  > WECOM_EGRESS_PROXY_URL
  > HTTPS_PROXY > ALL_PROXY > HTTP_PROXY
```

### 3.2 投递目标

`delivery.to` 支持的格式（README §486）：

| 格式 | 含义 | 例 |
|---|---|---|
| `party:<id>` | 部门全员 | `party:1`（根部门=全公司）|
| `dept:<id>` | 同上别名 | `dept:5` |
| `tag:<id>` | 标签组 | `tag:Ops` |
| `user:<id>` | 指定个人 | `user:zhangsan` |
| `group:<id>` | 外部群 | `group:wr123abc` |
| `chat:<id>` | 群聊别名 | `chat:wc456def` |
| 纯数字 | 自动判为部门 | `1` → `party:1` |
| `wr…` / `wc…` | 自动判为群聊 | `wr123` → chatid |
| 其他字符串 | 自动判为用户 | `zhangsan` → touser |

**建议**：观测摘要是给 Rex 自己看的运维数据，用 `user:<Rex的企微账号>` 而非
`party:1`（别给全公司发系统日志）。

## 4. 凭据补齐后的执行步骤

### 4.1 更新 cron job

```bash
# 注意子命令是 edit，不是 update（已实测确认）
openclaw cron edit aadc3416-5c72-4333-ad4f-6ef0402db0cc \
  --announce --channel wecom --to "user:<REX_USERID>"
```

或用 automations 工具：

```json5
{
  action: "update",
  jobId: "aadc3416-5c72-4333-ad4f-6ef0402db0cc",
  patch: {
    delivery: {
      mode: "announce",
      channel: "wecom",
      to: "user:<REX_USERID>",
    },
    description: "L2 可观测性: 每日 9:00 CST 生成 agent 观测摘要，投递到企业微信。",
  },
}
```

### 4.2 保留 `failureAlert: false`？

**建议改为启用**。当初关掉是因为无 channel 时投递必然失败、告警全是噪音。
现在有真实投递通道了，投递失败**应该**被知道：

```json5
{ failureAlert: { mode: "announce", channel: "wecom", to: "user:<REX_USERID>", after: 2 } }
```

`after: 2` 避免单次网络抖动就告警。

### 4.3 验证（必做，别只看配置）

```bash
# 1. 手动触发，看真实投递结果
openclaw cron run aadc3416-5c72-4333-ad4f-6ef0402db0cc --force

# 2. 查投递状态 —— 关键是 lastDeliveryStatus
openclaw cron show aadc3416-5c72-4333-ad4f-6ef0402db0cc | grep -iE "lastRunStatus|lastDeliveryStatus"
```

**判读**（依据 EXP-20260822-005）：

| `lastRunStatus` | `lastDeliveryStatus` | 含义 |
|---|---|---|
| `ok` | `ok` | ✅ 真成功 |
| `ok` | `failed` | ⚠️ 脚本跑了但没发出去 —— 查可信 IP |
| `error` | `not-requested` | ❌ 脚本本身失败 |

> **别只看 `lastRunStatus: ok` 就认为成功** —— 这正是 EXP-005 的坑：
> status 混合了「执行结果」与「投递结果」。

### 4.4 配置变更后

```bash
bash scripts/config.sh audit      # 应全绿
bash scripts/config.sh snapshot   # 快照入库
bash scripts/scan_secrets.sh      # 确认 corpSecret 未泄漏
```

## 5. 已完成的准备工作

凭据一到位就能直接接上，脱敏防线已提前加固：

- `snapshot_config.py` 的 `SECRET_KEYS` 已覆盖
  `corpsecret` / `appsecret` / `botsecret` / `encodingaeskey` / `egressproxyurl` / `proxyurl`
- `scan_secrets.sh` 已加对应扫描模式，双向测试通过（真值命中、`<REDACTED>` 不误报）
- **本仓库是 public**，所以这层防护是硬要求，不是可选项

## 6. 相关

- 插件 README：`~/.openclaw/npm/projects/wecom-wecom-openclaw-plugin-18f843d908/node_modules/@wecom/wecom-openclaw-plugin/README.md`
- `EXP-20260822-005`：cron delivery 污染 job 状态 + 6 个 CLI 陷阱
- ADR-004 可观测性 · ADR-005 凭据管理 · ADR-007 配置管理
