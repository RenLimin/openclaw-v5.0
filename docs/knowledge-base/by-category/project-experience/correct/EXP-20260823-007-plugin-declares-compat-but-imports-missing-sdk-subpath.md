---
type: experience
id: EXP-20260823-007
date: 2026-08-23
title: 第三方 channel 插件声明兼容却 import 不存在的 SDK 入口
category: correct
layers: [L1, L2]
stage: manage
tags: [plugin, channel, compatibility, peer-dependency, weixin, third-party]
status: active
related: [EXP-20260822-006, ADR-202608-008]
---

# 插件声明兼容 ≠ 实际可加载（`plugin-sdk/channel-runtime` 缺失）

## 现象

装 `@tencent-weixin/openclaw-weixin@2.4.6`（个人微信 channel）、扫码登录成功、
重启 gateway 后，channel 状态报错：

```
openclaw-weixin 054b1c52e357-im-bot: enabled, configured,
error: Package subpath './plugin-sdk/channel-runtime' is not defined by "exports"
       in .../@tencent-weixin/openclaw-weixin/node_modules/openclaw/package.json
       imported from .../dist/src/messaging/process-message.js
stopped, health:not-running
```

`stopped` + `health:not-running` = **加载阶段即失败**，不是配置问题。

## 根因

插件 import `openclaw/plugin-sdk/channel-runtime`，该子路径**在宿主的 `exports` 中不存在**。

| 对象 | 版本 | `exports` 数 | 含 `./plugin-sdk/channel-runtime` |
|---|---|---|---|
| 宿主 openclaw | 2026.7.2-beta.7 | 302 | ❌ |
| 插件内嵌 openclaw | 2026.7.2-beta.7 | 302 | ❌ |
| openclaw 最新 | 2026.8.1-beta.2 | 314 | ❌ |

只存在名字相近的 `./plugin-sdk/channel-runtime-context`。

**关键矛盾**：插件声明 `peerDependencies: { openclaw: ">=2026.5.12" }`，
宿主 `2026.7.2-beta.7` **满足**该约束，且 `2.4.6` 是 `latest` —— 但实际加载失败。

> **`peerDependencies` 只是版本区间声明，不校验实际 import 的子路径是否存在。**
> Node.js ESM `exports` 字段是白名单：未列出的子路径一律拒绝，无论文件是否存在。

## 排查要点

**① 版本号相同不代表没问题。** 第一直觉是"插件带了旧的 openclaw 副本"，
实测两边都是 `2026.7.2-beta.7` —— 内嵌副本不是原因。

**② 升级宿主修不了。** 先验证目标版本是否补了该入口，再决定是否升级：

```bash
cd /tmp && npm pack openclaw@<版本> --silent | tail -1 \
  | xargs -I{} tar -xzOf {} package/package.json \
  | python3 -c "import json,sys; ex=json.load(sys.stdin).get('exports',{}); \
      print(len(ex), './plugin-sdk/channel-runtime' in ex)"
```

**③ 降级前先查旧版 import，不要盲试。** 每次试装都要重启 gateway，成本高。
只读探测（`npm pack` + `tar -xzO`，不安装）：

```bash
for V in 2.4.5 2.4.4 2.4.3 2.3.1; do
  F=$(npm pack @tencent-weixin/openclaw-weixin@$V --silent 2>/dev/null | tail -1)
  tar -xzOf "$F" | grep -aoE "openclaw/plugin-sdk/[a-z-]+" | sort -u
done
```

**本次结果：2.4.5 / 2.4.4 / 2.4.3 / 2.3.1 全部 import `channel-runtime`
→ 降级无效**，不必尝试。

## 处置：停用，不改 node_modules ★

**不要**修改插件 `dist/` 里的 import 路径。理由：

- 下次 `plugins install` / 升级会覆盖，修复不可持久
- 修补第三方发布产物，不可追溯、不可审计
- 违反最小变更与可回滚原则

正确动作：

```bash
openclaw config set plugins.entries.openclaw-weixin.enabled false
openclaw config get plugins.entries.openclaw-weixin   # 读回确认
# 重启 gateway 生效
```

然后向插件方报 issue（可复现信息已齐全：插件版本 / 宿主版本 / 报错子路径 /
失败文件 `dist/src/messaging/process-message.js` / 已验证最新宿主同样缺失 /
四个旧版同样 import）。

## 附带发现

**① 扫码登录会创建额外账号。** 登录后出现两个：

```
openclaw-weixin default:                installed, configured, enabled
openclaw-weixin 054b1c52e357-im-bot:    installed, configured, enabled   ← 报错的是这个
```

`default` 疑为空壳，实际账号是 `<id>-im-bot`。停用插件时按 plugin 维度停用即可覆盖两者。

**② 扫码凭据不落 `openclaw.json`。** 配置里只留时间戳：

```json
{"openclaw-weixin": {"channelConfigUpdatedAt": "2026-08-22T16:04:10.425Z"}}
```

真实凭据在 `~/.openclaw/openclaw-weixin/`（仓库外）。
配置快照凭据扫描通过，无泄漏 —— 但**新 channel 接入仍应主动跑一次扫描**，
`SECRET_KEYS` 已有三次漏字段前例（`botId`、WeCom Agent 字段、`ownerAllowFrom`）。

## 与 ADR-008 的关系

这是三态模型中 `allowed-but-broken` 的又一实例，且属**最好的一种**：
它**显式报错**（`health:not-running`），不是静默降级。
对比 `memory_search` 缺 embedding provider 时只是悄悄退化为关键词检索 —— 后者危险得多。

**启示：channel/plugin 类失败通常显式；能力类降级（检索、媒体、语音）倾向静默。
审计重点应放在后者。**

## 待验证（阻塞）

个人微信**是否支持主动推送**仍无法实测。源码 `dist/src/messaging/send.js`
三处发送逻辑均为 `to_user_id: to` 必填 + `context_token: contextToken ?? undefined`（可选），
README L284 亦标注 `context_token | string?` —— **理论上支持主动推送**
（与企业微信 aibot 强依赖 `chatid` 不同，见 EXP-006）。

但插件无法加载，**结论未经实测，不得当作事实使用**。待插件修复后补验。
