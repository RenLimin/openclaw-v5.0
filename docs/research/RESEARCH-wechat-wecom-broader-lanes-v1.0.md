# RESEARCH：微信/企微群消息获取 —— 更广赛道补充调研（桌面之外的「更方便」路径）

- 版本：v1.0 ｜ 日期：2026-11-24 ｜ 状态：调研完成（未实施）
- 触发：Rex 提出「应该有更方便的方式」。上一版 `RESEARCH-mac-wechat-wecom-group-message-access-v1.1.md` 只覆盖 macOS 桌面直连，赛道过窄，本版补 **协议/Hook 框架、第三方网关、现成聚合产品、移动端** 四条线。
- 方法：GitHub API 实测核验（star/更新时间/arch/license/描述）+ README 原文抓取 + 社区搜索。所有引用均注明核验方式；网络间歇故障导致部分链接未能复核的，明确标注「未核实」。

---

## ① 一句话结论

**「更方便」的路线确实存在，但都在 Windows/服务器侧，且都建立在个人号风险或商业授权之上。**
- 最成熟省事的 = **Windows Hook 框架**（WeChatFerry / wxhelper），Windows 微信 PC 端注入 DLL，HTTP 收发群消息。
- 但它们都是 **Windows 专用**；本机是 **Apple Silicon（M5, arm64）且未装任何虚拟机** → 必须先解决 Windows ARM 环境。
- 聚合层首选 **AstrBot**（★47.4k，2026-11 仍活跃），可作为统一接入框，其微信渠道走 Gewechat——**而 Gewechat 官方已停止服务与 Docker，仅剩归档**（见 §③），这条路要重新评估。
- 手机端路线当前**不可落地**：本机无配对设备、无 adb/iOS 工具链。

---

## ② 关键项目实测核验表（GitHub API，2026-11-24）

| 项目 | Star | 最后更新 | License | 状态 | 平台 |
|---|---|---|---|---|---|
| `AstrBotDevs/AstrBot` | ★47414 | 2026-11-24 | AGPL-3.0 | 活跃 | 跨平台聚合框架 |
| `LSPosed/LSPosed` | ★25620 | 2026-10-14 | GPL-3.0 | 活跃 | Android |
| `sunnyyoung/WeChatTweak` | ★13840 | 2026-02-08 | AGPL-3.0 | 活跃 | macOS 微信插件 |
| `lich0821/WeChatFerry` | ★6812 | 2026-07-10 | — | 活跃 | Windows Hook |
| `wechatferry/wechatferry` | ★2112 | 2025-07-18 | — | 停更 | Windows |
| `wechaty/wechaty` | ★23609 | 2026-11-24 | Apache-2.0 | 活跃 | 框架 |
| `Devo919/Gewechat` | ★3504 | 2026-08-06 | Apache-2.0 | **仅归档** | 服务端 API |
| `ttttupup/wxhelper` | ★3207 | 2026-06-12 | MIT | 活跃 | Windows Hook |
| `BiboyQG/WeChat-MCP` | ★304 | 2026-03-09 | MIT | 活跃 | macOS AX |
| `Cybing521/wechat-mcp` | ★6 | 2026-01-20 | MIT | 活跃 | macOS AX |
| `wechaty/puppet-padlocal` | ★769 | **2023-07-04** | Apache-2.0 | 实质停更 | Pad 协议 |

**要点**
- **WeChatFerry**（微信机器人框架，可接大模型）与 **wxhelper**（PC 微信逆向，DLL 注入，默认端口 19088 HTTP 调用）是当前 Windows 侧最主流的两条；wxhelper README 明示支持到 **微信 3.9.5.81（x64）**，旧版为 x86。
- **Gewechat** README 首段即声明：「历史运行服务、Docker 镜像、部署方式及技术支持均不再提供，本仓库仅作为技术归档……不得直接复用」。→ **从推荐中剔除，或仅作自研参考。**
- **wechaty-puppet-padlocal** 最后更新 2023-07，PadLocal 需付费 token 且封号史明显（wechaty issue #2804 集中反馈扫码即封）。→ 高风险、低维护，不推荐。
- **WeChatTweak**（macOS）主打撤回拦截等 UI tweak，非群消息读取框架，且不适用企业微信。

---

## ③ 四条新赛道的评估

### 赛道 A：Windows Hook 框架（最「省事」，但有环境前提）
- 原理：Windows 微信 PC 端 → 注入 DLL → 起本地 HTTP 服务 → 收发群消息。WeChatFerry / wxhelper 是代表。
- 优点：开发量最小，社区方案多，可直接对接 LLM（WeChatFerry 明示）。
- 门槛：**需要 Windows**。本机 M5/arm64 未装任何 VM（无 Parallels/VMware/UTM/OrbStack/Docker）。
- 待验证：① Windows ARM 下是否有微信 PC 原生 ARM 版可注入；② wxhelper 3.9.5.81 是 x64，ARM 模拟能否跑；③ 账号风险（Hook 类历史上封号率高）。
- 判断：**技术上最便捷，但落地第一步是建 Windows 环境**，且必须用小号。

### 赛道 B：现成聚合产品（AstrBot）
- **AstrBot**（★47.4k，AGPL-3.0，2026-11 仍日更）是多 IM 聚合 Agent 框架，README 列支持 QQ/企微/飞书/钉钉/公众号/Telegram 等；其微信群渠道历史上依赖 Gewechat。
- 价值：若目标是「多平台统一接入 OpenClaw」，AstrBot 比自建 Hook 更规范。
- 致命点：其微信适配器 Gewechat 已停服归档 → **AstrBot 的微信渠道现状需另行核实**（README 标 WeChat Work=Official，即企微走官方通道可用）。
- 判断：**企微方向可用（官方通道）；微信方向需确认适配器是否已切换。**

### 赛道 C：第三方企微 API / SCRM（合规但商业）
- 实测可达：`wecomapi.com`（「企业微信API接入平台｜二次开发与企业级接口服务」）、`doc.qiweapi.com`（QiWeAPI，Gewechat 作者维护的独立技术资料）。
- 定位：提供企微外部群/消息/事件回调接口，属**第三方中间层**——数据经第三方，需注意合规与授权。
- 判断：企微**外部客户群消息**唯一相对省事的现实通道；个人自用时需评估「消息过第三方」的风险。

### 赛道 D：移动端采集（当前不可落地）
- 本机实测：`nodes` 返回空（**无任何配对设备**）；无 adb / libimobiledevice / ifuse / iproxy。
- 因此 Android 通知监听 / AutoX.js / Hamibot / iOS 快捷指令这些方案，**本机缺前置条件**，本轮不做深入实测。
- 判断：若你愿意配一台 Android 机并装 AutoX/Hamibot，这条值得后续单独立项验证；本轮不作为可达路线。

---

## ④ 修正后的总体路线排序（含上一版桌面结论）

| 优先级 | 方向 | 路线 | 历史 | 实时 | 前提 | 风险 |
|---|---|---|---|---|---|---|
| 1 | 企微 | **Accessibility（AX）轮询** | ⚠️可见 | ✅秒级 | 权限已有、**本机已实测跑通** | 极低 |
| 2 | 企微 | 本地库只读（Info.db magic 闸门） | ✅全量 | ✅WAL | 完全磁盘访问 | 低；版本绑定 |
| 3 | 企微 | 官方智能机器人 WebSocket | ❌ | ✅仅@ | 机器人权限 | 零（官方） |
| 4 | 企微 | 第三方 API（wecomapi/QiWeAPI） | ⚠️ | ✅ | 授权+付费 | 中（过第三方） |
| 5 | 微信 | Windows Hook（WeChatFerry/wxhelper） | ✅ | ✅ | **需 Windows 环境** | 高（封号） |
| 6 | 微信 | AstrBot（聚合层） | ⚠️ | ✅ | 适配器现状待核 | 中 |
| 7 | 微信 | 本地库解密 | ✅全量 | ✅ | 关 SIP+重签 | 高；条款 |
| 8 | 微信 | macOS AX | — | — | **本机实测不可用** | — |

---

## ⑤ 建议的下一步（等你拍板）

**两个方向已经清楚分化：**
- **企微**：AX 轮询当天可落地（我已实测读到真实消息），是投入产出比最高的动作。
- **微信**：桌面 AX 死了，剩下的要么上 Windows（建 VM + Hook 框架），要么付代价做本地库解密。

我倾向：**先把企微 AX 采集 PoC 做完**（只读、零风险），同时**并行验证 Windows 可行性**——具体只需一步低成本探测：确认能否在 M5 上跑起一个 Windows 11 ARM 虚拟机、以及是否有可注入的微信 PC 版。这个探测不产生任何副作用。

---

## ⑥ 执行备注（诚实记录）

- 本轮三条子代理（移动端/协议网关/官方产品）均在早期被环境中断，产物未落盘；改由主会话直连 GitHub API 完成核验。
- 网络通道间歇故障（api.github.com 多次 SSL_ERROR_SYSCALL / UNEXPECTED_EOF），故 **npm 生态、iOS/Android 社区细节未能完整复核**，标注为未核实。
- 未编造 star、价格与版本支持；`ntchat/ntchat`、`kkevsekk1/AutoX`、`openatx/atx-agent2` 实测 404，已剔除。

---

## 附：来源
- 核验通道：GitHub REST API `repos/` 与 `search/repositories`（2026-11-24）
- https://github.com/lich0821/WeChatFerry （★6812，2026-07-10）
- https://github.com/ttttupup/wxhelper （★3207，2026-06-12，支持至 3.9.5.81 x64）
- https://github.com/Devo919/Gewechat （★3504，已停服归档）
- https://github.com/AstrBotDevs/AstrBot （★47414，2026-11-24）
- https://github.com/wechaty/puppet-padlocal （★769，2023-07-04 后停更）
- https://github.com/sunnyyoung/WeChatTweak （★13840）
- https://wecomapi.com ｜ https://doc.qiweapi.com/
- 关联：`docs/research/RESEARCH-mac-wechat-wecom-group-message-access-v1.1.md`
