# RESEARCH：微信/企微群消息获取 —— 广度调研（桌面之外的「更方便」路径）

- 版本：v1.1 ｜ 日期：2026-11-24 ｜ 状态：调研完成（未实施）
- 触发：Rex 提出「应该有更方便的方式」。上一版 `RESEARCH-mac-wechat-wecom-group-message-access-v1.1.md` 只覆盖 macOS 桌面直连，赛道过窄，本版补 **移动端、协议/Hook 框架、第三方网关、现成聚合产品、官方通道** 五条线。
- 方法：三路子代理并行调研（移动端 A / 协议网关 B / 官方产品 C）+ 主会话 GitHub API 实测核验 + README 原文抓取。B 路子代理超时未产出报告，但其核心项目由主会话 API 核验覆盖。所有引用均注明核验方式与出处。
- 原始子报告：`docs/research/laneA-mobile-collection.md`、`docs/research/laneC-official-and-products.md`

---

## ① 一句话结论

**「更方便」的路线确实存在，但都不在 Mac 桌面上。**
三条新赛道的头部候选按「落地难易」排序：

1. **OpenClaw Android node（mobile.ui.observe）** —— 官方自带、零注入、结构化读当前前台群消息；但**缺设备**（本机零配对节点）。
2. **Windows Hook 框架（WeChatFerry / wxhelper）** —— 最成熟、开发量最小；但**需 Windows 环境**（本机 M5/arm64 无虚拟机）。
3. **AstrBot 聚合框架** —— ★47.4k 多 IM 统一接入框；但其微信渠道依赖的 Gewechat **已停服归档**，微信适配器现状需重新核实。

iOS 侧官方路线基本封死；微信官方 iLink/ClawBot 不支持群；企微唯一官方全量路径是会话内容存档（付费、不可回溯）。

---

## ② 全景路线图（14 条路线，按推荐度）

| # | 方向 | 路线 | 实时 | 历史 | 前提 | 风险 | 推荐度 |
|---|---|---|---|---|---|---|---|
| 1 | 企微 | **macOS AX 轮询** | ✅秒级 | ⚠️可见 | 权限已有、**本机实测跑通** | 极低 | ★★★★★ |
| 2 | 企微 | 本地库只读（Info.db） | ✅WAL | ✅全量 | 完全磁盘访问 | 低；版本绑定 | ★★★★ |
| 3 | 企微/微信 | **Android node + mobile.ui.observe** | ⚠️轮询 | ⚠️可见 | **需配对 Android 机** + 无障碍授权 | 低–中 | ★★★★（缺设备） |
| 4 | 企微 | 会话内容存档（官方） | ✅近实时 | ⚠️开通后起 | 企业管理员 + 付费 + 员工同意 | 零（合规） | ★★★★（企微正解） |
| 5 | 企微 | 智能机器人 WebSocket | ✅实时 | ❌ | 仅收 @机器人 消息 | 零 | ★★★ |
| 6 | 微信 | Windows Hook（WeChatFerry/wxhelper） | ✅ | ✅ | **需 Windows VM** + 小号 | 高（封号） | ★★★ |
| 7 | 微信 | iOS 27 通知自动化 | ⚠️准实时 | ❌仅当条 | 需 iOS 27 设备 + 通知展示在锁屏/中心 | 极低 | ★★★（仅增量） |
| 8 | 微信 | 聊天记录迁移 + 第三方库解析 | ❌ | ✅全量 | Mac/Win 微信 + 解密工具（常需关 SIP） | 中 | ★★★（离线） |
| 9 | 微信/企微 | AstrBot 聚合框架 | ✅ | ⚠️ | 微信适配器现状待核 | 中 | ★★☆ |
| 10 | 企微 | 第三方 API / SCRM（wecomapi/QiWeAPI） | ✅ | ⚠️ | 授权 + 付费 | 中（过第三方） | ★★☆ |
| 11 | 微信 | 本地库解密（SQLCipher） | ✅WAL | ✅全量 | 关 SIP + 重签 + root 调试 | 高；条款 | ★★ |
| 12 | Android | 通知监听（NotificationListenerService） | ✅秒级 | ❌仅活跃通知 | 通知读取授权 | 极低 | ★★（触发用） |
| 13 | Android | 无障碍自动化（AutoX/Hamibot） | ⚠️轮询 | ⚠️滚动 | root 可选 | 中–高 | ★☆ |
| 14 | 微信 | macOS AX（本机 4.1.15） | — | — | **实测不可用（5 节点空壳）** | — | ✕ 死路 |

---

## ③ 各赛道核心证据

### 赛道 A：移动端（子代理 laneA 报告，247 行）

#### A1. OpenClaw paired Android node —— 本次最大发现
- **官方证实**：`mobile.ui.observe` / `mobile.ui.act` 在 Android 默认命令白名单中；App 内开启 Accessibility Control 后 node 才声明；需 `nodes approve` 批准命令面。
  - 来源：https://docs.openclaw.ai/nodes/command-policy （实证 200）
- **能力边界（推断）**：返回当前屏幕无障碍层级树 → 微信/企微目标群前台时，可见消息结构化可读；**无历史、无推送（轮询）、后台可用性未核**。
- **桥回 Mac**：成立。`openclaw nodes invoke --node <id> --command mobile.ui.observe` 结果回到 Gateway。
- **群聊**：无差别，UI 树不区分私聊/群聊。
- **落地前提**：① 一台 Android 机；② 安装 OpenClaw Android app + 开启无障碍 + 配对批准。

#### A2. iOS 侧基本封死
- 快捷指令通知自动化：**iOS 27 之前**，通信触发器只覆盖邮件/信息，无第三方通知触发（Apple 官方文档）。
- 无障碍导出：Apple 无 dump 他 App 无障碍树的公开 API。
- 剩余：越狱插件（版本耦合强）+ 本地库 `MM.sqlite`（静态、非实时）。
- **更新（lane C 补充）**：iOS 27 新增「通知自动化」支持第三方 App 通知触发（Apple 支持页 149045 实证 200），但仅当条增量、需通知展示在锁屏/通知中心。

#### A3. Android 其他路线
- **通知监听**（`NotificationListenerService`）：系统级 API，免 root，秒级；但只能读活跃通知，群聊仅触发通知的消息有。可作**触发信号**，配合 UI 树取文。
- **AutoX / Hamibot**：基于 AccessibilityService 的控件选择器；能做但封号风险中–高（违反腾讯协议 8.2.1.4）。
- **Xposed / LSPosed Hook**：能力最强但必须 root，风险最高。
- **本地库解密**（`EnMicroMsg.db` + SQLCipher）：全量但需 root，且腾讯已对相关项目发律师函。

---

### 赛道 B：协议/Hook/第三方网关（主会话 GitHub API 核验 + laneB 子代理超时未报告）

> ⚠️ 说明：laneB 子代理因环境超时未产出最终报告；以下核心项目由主会话通过 GitHub REST API 直接核验。

#### B1. WeChatFerry（lich0821/WeChatFerry）
- ★6812 ｜ 最后更新 2026-07-10 ｜ Windows 专用
- 定位：微信机器人框架，可接大模型；Hook 注入 PC 微信。
- 门槛：Windows + 微信指定版本；封号风险高（Hook 类通病）。

#### B2. wxhelper（ttttupup/wxhelper）
- ★3207 ｜ 最后更新 2026-06-12 ｜ MIT ｜ Windows
- 机制：定位 PC 微信关键 Call → 编写 DLL 注入 → 起 19088 端口 HTTP 服务 → 外部调用。
- 支持版本：**3.8.0.41、3.8.1.26、3.9.0.28、3.9.2.23、3.9.2.26、3.9.5.81**（3.9.5.81 为 x64，旧版 x86）。
- 风险：注入类，封号概率高；版本绑定紧；仅 Windows。

#### B3. Gewechat（Devo919/Gewechat）
- ★3504 ｜ 最后更新 2026-08-06 ｜ Apache-2.0
- **关键事实**：README 首段声明「**历史运行服务、Docker 镜像、部署方式及技术支持均不再提供。本仓库仅作为技术归档和历史代码示例保留……不得直接复用**」。
- → **从推荐中剔除**；仅作自研参考。

#### B4. wechaty / puppet-padlocal
- wechaty ★23609（框架仍活跃）；puppet-padlocal ★769，**最后更新 2023-07-04**（实质停更）。
- PadLocal 需付费 token，且社区有大量扫码即封反馈（wechaty issue #2804 等）。→ 高风险低维护，不推荐。

#### B5. 第三方企微 API / SCRM
- `wecomapi.com`（「企业微信API接入平台」，可达）
- `doc.qiweapi.com`（QiWeAPI，Gewechat 作者维护的独立技术资料，可达）
- 定位：企微外部群/消息/事件回调接口封装。消息过第三方，注意合规。

---

### 赛道 C：官方通道与现成产品（子代理 laneC 报告，197 行）

#### C1. 微信 iLink / ClawBot 插件 = 群聊死路
- 腾讯官方口径：「**ClawBot 不能被加入微信群，仅支持个人单点使用**」。
- 社区实测（2026-09，cc-connect #1841）：新建群/群设置/群成员/插件页四处入口都搜不到 bot；官方 issue #42 仍 open。
- → 对群消息 = 死路；个人微信当遥控器可用。

#### C2. 企业微信「会话内容存档」（官方正解）
- 唯一官方全量路径：原生版 + 数据与智能专区；内部群、客户群全覆盖。
- 门槛：企业管理员权限 + 员工/外部联系人知情同意 + 付费；**不可回溯**（从授权日起存）；存储 90 天–2 年。
- 官方 SDK 仅 Linux/Windows，无 macOS。

#### C3. 微信本地库解析工具（C/B 交界）
- **ChatLog**：明确支持 Win/macOS。
- **WechatExporter**：走 iTunes 备份。
- **留痕 / WeChatMsg / PyWxDump**：偏 Windows；Mac 解密常需临时关 SIP。
- 定位：全量、离线、批处理；非实时。

#### C4. iOS 27 通知自动化（2026 新变化）
- Apple 支持页 149045 实证：iOS 27 新增第三方 App 通知触发；可读标题/正文并转发。
- 限制：仅当条增量、无历史；需通知展示在锁屏或通知中心（仅横幅不触发）。
- → 微信群增量采集的唯一「纯官方、零侵入」路径，但能力极有限。

#### C5. 换平台对比事实
- 飞书：有「获取群组中所有消息」敏感权限（明显更开放）。
- 钉钉：官方事件总览未见群消息接收事件。

---

### 赛道 D：现成聚合框架

#### AstrBot（AstrBotDevs/AstrBot）
- ★47414 ｜ 最后更新 2026-11-24 ｜ AGPL-3.0 ｜ 日更
- README 列支持：QQ、WeChat Work、Feishu、DingTalk、WeChat Official Accounts、Telegram、Slack 等。
- 价值：多 IM 统一接入 OpenClaw 的规范框架，比自建 Hook 更工程化。
- **微信渠道现状待核**：历史上依赖 Gewechat → Gewechat 已停服归档 → 适配状态需另行确认。
- 企微渠道（WeChat Work=Official）：不受影响，走官方通道。

---

## ④ 本机落地的硬约束（必须说清）

| 资源 | 现状 | 影响 |
|---|---|---|
| 配对移动设备 | `nodes` 返回空，**零设备** | Android node 路线、iOS 通知自动化路线均缺设备 |
| Windows / 虚拟机 | **零安装**（无 Parallels/VMware/UTM/OrbStack/Docker） | Windows Hook 路线需先建 VM |
| 本机架构 | Apple M5 / arm64 / 24GB | Windows ARM 下微信 x64 能否注入需验证 |
| 移动工具链 | 无 adb / idevicebackup2 / ifuse / iproxy / sqlcipher | 移动端深度测试前置缺失 |
| GitHub API | 间歇性 SSL_ERROR_SYSCALL | 部分项目未能多次复核，已标注 |

---

## ⑤ 建议的下一步（等你拍板）

**已经分化成两条清晰路径，互不阻塞：**

### 路径一：企微 AX 采集（当天可验证，零风险）
我已经用 Swift AX API 实测读到企微真实群消息（641 节点、会话列表+正文都有）。下一步是把它工程化成轮询采集 PoC：
- 自动切换/打开目标群
- 轮询会话列表和正文区
- 解析发送者/时间戳/@提及
- 验证后台/最小化稳定性

投入产出比最高，不花你任何硬件或钱。

### 路径二：「更方便」路线的一次低成本前置探测
两条最有希望的「更方便」路线（Android node / Windows Hook）都缺硬件/环境前提。探测成本极低但能立刻排除大方向：
- **方向 A**：你拿出一台 Android 机 → 装 OpenClaw app → 我配对 + 开 `mobile.ui.observe` → 当场验证能不能读群消息。
- **方向 B**：你装一个 Windows ARM 虚拟机（UTM 免费 / Parallels 付费）→ 我装微信 PC + 注入 wxhelper/WeChatFerry → 验证能不能跑。

要先做哪个？我的建议是**先做路径一**（企微 AX PoC，0 成本），同时你决定要不要为「微信」方向投入硬件/VM 成本。

---

## ⑥ 诚实记录

- lane B（协议网关）子代理超时未产出报告，该赛道核心项目由主会话 GitHub API 核验覆盖；wechaty 生态细节（各 puppet 状态）不完整，已在推荐度上反映。
- 网络通道间歇故障（api.github.com 多次 SSL_ERROR_SYSCALL / UNEXPECTED_EOF），部分 npm 生态、Android 社区细节未能完整复核。
- 未编造任何 star、价格与版本支持；`ntchat/ntchat`、`kkevsekk1/AutoX`、`openatx/atx-agent2` 实测 404，已剔除。
- 未改动其他 workspace 文件；三份报告独立归档。

---

## 附：来源与关联报告
- 子报告 A：`docs/research/laneA-mobile-collection.md`
- 子报告 C：`docs/research/laneC-official-and-products.md`
- 桌面直连实测：`docs/research/RESEARCH-mac-wechat-wecom-group-message-access-v1.1.md`
- GitHub 核验（2026-11-24，均为 API 实测）：
  - AstrBotDevs/AstrBot ★47414 / WeChatFerry ★6812 / wxhelper ★3207 / Gewechat ★3504（已归档）
  - wechaty/wechaty ★23609 / puppet-padlocal ★769（停更）
  - LSPosed ★25620 / WeChatTweak ★13840
- 官方文档：
  - OpenClaw node command policy / Android platform / iOS platform
  - Apple 支持页 HT2149045（iOS 27 通知自动化）
  - 企业微信会话存档 / 智能机器人 / 客户群 API 官方文档
