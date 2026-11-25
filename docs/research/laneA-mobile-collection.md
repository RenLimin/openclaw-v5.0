# RESEARCH：移动端（Android / iOS）获取微信·企业微信群消息的现实路线调研（Lane A）

- 调研日期：2026-11-24
- 范围：Android + iOS 手机端采集「微信 / 企业微信群消息」的现实可行路线
- 前置：macOS 桌面客户端赛道已有《RESEARCH-mac-wechat-wecom-group-message-access-v1.0.md》；本报告不重复桌面结论，只补移动端
- 口径说明：
  - GitHub 仓库状态均在本机以 `gh api repos/<owner>/<name>` 实测（HTTP 200 记为可访问），个别链接另附 `curl` 探测结果；失败/不稳定者明确标注「未核实」。
  - 未编造任何 star 数与「支持的微信版本」；凡文档/仓库未写明的一律标「未核实」。
  - 社区博客结论与官方文档冲突时，以官方文档为准。

---

## ① 结论速览表

| # | 路线 | 平台 | 原理一句话 | 需 root/越狱 | 封号风险 | 历史全量 | 实时性 | 原生支持群聊 | 成熟项目/载体 | 推荐度 |
|---|---|---|---|---|---|---|---|---|---|
| A1 | 企业微信「会话内容存档」（msgaudit） | 服务端（不限手机） | 企业管理员开通，官方 SDK 拉取会话明文 | 否 | 无（官方合规，需员工同意） | ❌ 不可回溯 | ✅ 近实时 | ✅ 内部群/外部群 | 官方 SDK（WeWorkFinanceSDK） | ★★★★★（企微唯一合规正解） |
| A2 | **OpenClaw paired Android node：`mobile.ui.observe` / `mobile.ui.act`** | Android | 开启应用内 Accessibility Control 后，node 向 Gateway 声明移动 UI 命令，由 Mac 侧 `nodes invoke` 拉取当前屏幕结构化层级 | 否（需无障碍授权） | 低–中（等同人在操作；但属第三方读取） | ❌ 仅当前可见 | ⚠️ 轮询（无推送） | ⚠️ 视聊天是否在前台 | openclaw/openclaw 官方 Android app | ★★★★（本赛道首选验证项） |
| A3 | Android 通知监听 `NotificationListenerService` | Android | 系统级通知读取 API | 否 | 极低 | ❌ 仅活跃通知 | ✅ 秒级 | ⚠️ 仅触发通知的群（@我/强提醒） | 官方 API + DCloud 插件 4915 | ★★★（轻量补充） |
| A4 | 无障碍自动化框架（AutoX / Auto.js / Hamibot） | Android | 基于 AccessibilityService 的控件选择器读写 | 多数功能否；坐标/录制/shell 可 root | 中–高（违反腾讯协议 8.2.1.4） | ⚠️ 靠脚本滚动 | ✅ 脚本轮询 | ✅ | AutoX、Hamibot | ★★（能做成但有风险） |
| A5 | Xposed / LSPosed Hook 客户端 | Android | 注入微信/企微进程，拦截消息回调 | ✅ 必须 root + LSPosed | **高** | ✅ 可 | ✅ | ✅ | wechat-observatory、WechatXposedHook | ★（能力强、风险最高） |
| A6 | Android 本地库解密 `EnMicroMsg.db` | Android | root 取库，SQLCipher 密钥派生后离线解析 | ✅ 必须 root | 高（腾讯已对相关项目发律师函） | ✅ 全量 | ⚠️ WAL 轮询 | ✅ | PyWxDump、WeChatMsg | ★（法律与合规红线，仅取证视角） |
| B1 | iOS 快捷指令 + 通知触发 | iOS | 期望「收到微信通知即自动汇总」 | 否 | 无 | ❌ | — | ❌ | Apple Shortcuts | ✕ **死路**（见 §④） |
| B2 | iOS 无障碍 / VoiceOver / 切换控制 | iOS | 期望程序化 dump 他 App 的无障碍树 | 否 | 无 | ❌ | — | ❌ | — | ✕ **死路**（无公开 API） |
| B3 | iOS 越狱插件（防撤回/Hook 类） | iOS | Cydia/重签名注入 | ✅ 需越狱或重签 | 高 | ⚠️ 部分 | ✅ | ✅ | itenfay/WeChat_tweak | ★（生态脆弱、版本绑定） |
| B4 | iOS 本地库（`MM.sqlite`） | iOS | 从越狱设备/备份提取，库常未加密 | ✅（提取环节） | 中 | ✅ | ❌ 静态 | ✅ | 取证工具（Belkasoft 等） | ★（历史导出、非实时） |
| C1 | 多端同时在线（手机+平板+桌面） | 全平台 | 用官方多端能力把手机端消息同步到可程序化的端 | 否 | 无 | ❌ | ✅ | ✅ | 微信/企微官方客户端 | ★★★（作为「借道」思路） |
| C2 | 文件传输助手 / 收藏 / 迁移 | 全平台 | 人工半自动搬运 | 否 | 无 | ⚠️ 片段 | ❌ | ⚠️ | 官方功能 | ★（人工兜底） |
| C3 | 视觉 RPA（scrcpy 投屏 + OCR/VLM） | Android | 画面采集识别 | 否 | 低 | ⚠️ 仅可见 | ✅ 轮询 | ✅ | scrcpy + OCR/VLM | ★★（兜底） |

---

## ② 关键问题专章：OpenClaw paired Android node 能否直接读微信/企微群消息并桥回 Mac？

> 这是本次调研的落地核心。结论：**可以「读当前前台会话的结构化文本」，但它是「按需拉取的屏幕观察面」，不是消息订阅通道**。

### 2.1 官方事实（已核验，均为 HTTP 200）

| 事实 | 出处 |
|---|---|
| Android 平台默认命令白名单包含 `mobile.ui.observe` 与 `mobile.ui.act`；同时含 `notifications.list` / `notifications.actions` | https://docs.openclaw.ai/nodes/command-policy |
| 「Android advertises mobile UI commands only while Accessibility Control is enabled」——只有 App 内开启 Accessibility Control，node 才声明这两个命令 | 同上 |
| node 命令要生效须过三关：node 在 `connect.commands` 声明 + 配对设备记录批准 + Gateway 平台/批准白名单允许 | 同上 |
| node 的 `permissions` 映射可按权限名查询，如 `accessibility`、`screenRecording`、`location`，值为布尔 | 同上 |
| Android app 是 companion node，必须搭配运行中的 Gateway（Mac/Linux/Windows-WSL2）；APK 走 Google Play 或 GitHub Releases | https://docs.openclaw.ai/platforms/android |
| 「the focused Gateway alone owns the Android node session and device capabilities」——同一时刻只有焦点 Gateway 能下发 camera/location/screen/notification 命令 | https://docs.openclaw.ai/platforms/android |
| 设备命令族里**没有**任何「消息历史 / 通讯录会话」命令；可读的只有设备状态、应用列表、通知、联系人、日历、提醒、通话记录、照片等 | https://docs.openclaw.ai/nodes/device-commands |
| `notifications.list` / `notifications.actions` 为 Android 独有；iOS 平台默认命令表中**不含**通知族，也不含移动 UI 族 | https://docs.openclaw.ai/nodes/command-policy、https://docs.openclaw.ai/platforms/ios |
| iOS app（iOS 26.2+）能力为 Screen snapshot / Camera / Location / Talk / Voice wake / Health，**无** notifications.* 与 mobile.ui.* | https://docs.openclaw.ai/platforms/ios |

### 2.2 由此推出的能力边界（推断，均已标注依据）

1. **读什么**：`mobile.ui.observe` 的语义是「观察移动 UI」，即返回当前屏幕的无障碍层级（节点、文本、可点击元素与坐标）。**只要微信/企微目标群聊处于前台**，该群的可见消息就会出现在这棵树里 → 可读取。
   - 依据：官方措辞「mobile UI commands」「Accessibility Control」+ 第三方实测文章描述其效果等同 uiautomator2 dump UI hierarchy（https://www.shopclawmart.com/blog/openclaw-node-pairing-phone ，**社区来源，非官方**）。
2. **不能读什么**：官方命令表里没有任何消息/会话历史命令；`mobile.ui.observe` 未见公开参数文档（**未核实** payload schema）。因此**历史全量不支持**；想拿更早消息只能靠脚本滚动列表后再 observe（属于自造轮子，且受客户端滚动回收策略限制）。
3. **实时性**：命令模型是「Mac 侧 invoke → 手机返回」，属于**轮询**而非消息推送。延迟取决于调用频率；官方未提供 webhook/订阅式消息事件。
4. **后台**：官方对 camera 明确要求 node 前台（`NODE_BACKGROUND_UNAVAILABLE`），通知类命令同样受「焦点 Gateway 独占设备能力」约束。因此**息屏/切后台时不保证可采集**；长跑需保持 App 前台或依赖系统保活（未核实）。
5. **桥回 Mac**：**成立**。paired node 的 invoke 结果回到 Gateway（可就在 Mac 本机），再由 agent/CLI 使用；官方 CLI `openclaw nodes invoke --node <id> --command mobile.ui.observe --params '{}'` 形态与 `nodes invoke` 机制已在文档中给出（`device.status`/`notifications.list` 等示例同源）。
6. **群聊**：无差别——UI 树不区分私聊/群聊；群聊天然在前台可见，反而比私聊更适合这条路线。

### 2.3 必须写进设计的前提与风险

- 必须先 `openclaw nodes approve <requestId>` 批准扩大的命令面，否则命令不可用（官方明文）。
- 需要人在手机上为该 App 开启无障碍/通知读取授权；换机、系统升级、App 更新都可能让授权失效。
- 「uiautomator2 / ui_hierarchy / scrcpy 直连」等配置项来自**第三方博客**，官方文档未列；落地前需在真机上以 `openclaw nodes pending/describe` 核实当前版本实际声明的命令面。
- 隐私与合规：持续读取他人对话属敏感数据流，须限定用途与留存。

---

## ③ 逐路线评估明细

### A1 企业微信「会话内容存档」（官方正解）
- **原理**：企业管理员在管理后台开通会话内容存档（msgaudit），配置可信公钥，员工同意后，服务端留存会话明文，第三方应用用官方 SDK 通过 `GetChatData` 拉取。
- **门槛**：企业管理员权限 + 服务资质 + 员工知情同意；通常按账号/容量计费（具体价格以官方页面为准，本次未核实）。
- **能力**：实时性 ✅；群聊 ✅（内部群、外部群、客户联系均有对应接口条目）；**不可回溯**开通前的历史消息 ❌。
- **移动端相关性**：这是服务端路线，不依赖你手里的手机型号；但它是「手机端产生的消息」的合规采出口。
- **载体**：官方文档 + 开源 SDK（见 §⑥）。
- **判定**：企微场景唯一无合规风险的路线，若目标是长期稳定采集，优先级最高。

### A2 OpenClaw Android node（mobile.ui.observe）
见 §②。定位：**Android 端「准实时 + 零 root + 可桥回 Mac」的最优候选**，但需真机验证三件事：①当前版本是否真的声明 `mobile.ui.observe`；②返回体里微信/企微群消息是否结构完整；③轮询节奏下电量/发热/被杀情况。

### A3 Android 通知监听
- **原理**：实现 `NotificationListenerService`，系统把状态栏通知回调给监听器；可拿到标题、正文、时间、包名，`getActiveNotifications()` 列当前活跃通知。
- **优点**：免 root、实时、官方 API、隐私授权可控。
- **硬限制**：
  - 只能拿到「系统通知呈现的内容」，微信/企微对长消息会截断，且**群消息只在满足提醒条件时才有通知**（免打扰群直接没有）→ 不是全量消息通道。
  - **不可回溯**：没有通知就什么都没有；清掉的通知无法恢复。
  - 通知样式可被客户端升级为「应用内展开」，纯监听拿不到全文。
- **成熟载体**：官方 API（https://developer.android.com/reference/android/service/notification/NotificationListenerService ，本次 `curl` 取正文为空，仅确认 URL 可达）；DCloud 插件市场 id=4915「监听通知栏内容…监听微信通知消息」，其页面显示版本 `3.1.0（2025-05-29）` 修复杀进程后监听失效（https://ext.dcloud.net.cn/plugin?id=4915 ，HTTP 200）。
- **判定**：做「新消息提醒/摘要」够用；做「群消息归档」不够。

### A4 无障碍自动化框架（AutoX / Auto.js / Hamibot）
- **原理**：基于 AccessibilityService，用控件选择器定位微信/企微的会话项、消息气泡，读文本或模拟点击、滚动。
- **门槛**：多数读写能力**不需 root**；精确坐标点击、录制、shell 等进阶能力可用 root（来源：AutoX 技术文档站 https://lmmsoft.github.io/wechat_robot_technical ，本次抓取正文为空，标「内容未核实」，但其结论与 Auto.js 官方定位一致）。
- **能力**：可脚本化「进入某群→滚动→抓取」循环，做到准实时 + 一定程度的向前翻历史。
- **风险**：腾讯《微信软件许可及服务协议》禁止对客户端做 Hook/修改/自动化干预（少数派文章 https://sspai.com/post/45473 ，HTTP 200，标题直指「装插件有可能微信被封号」），**存在封号的现实案例讨论**；无障碍模拟点击虽比 Hook 轻，仍属灰色地带。
- **成熟项目**：AutoX（autox-community/AutoX，356 stars，2025-11-29；automan-bot/AutoX，228 stars）、Hamibot（hamibot/hamibot，3137 stars，最后更新 2023-11-01，活跃度下降）。
- **判定**：技术上最灵活；合规上需要在「仅自己账号、低频、只读」的前提下评估，不能当作生产承诺。

### A5 Xposed / LSPosed Hook
- **原理**：root 后装 LSPosed，模块 Hook 微信/企微进程的消息回调/数据库写入，可拿到含撤回前的完整消息。
- **能力上限最高**（历史 + 实时 + 全群），但**封号风险最高**，且微信持续做环境检测。
- **项目**：B022MC/wechat-observatory（35 stars，MIT，2026-10-09，LSPosed 系微信网关）；ShadowSmallBaby/WechatXposedHook（185 stars，AGPL-3.0，2026-11-12）；Dawnnnnnn/Hook_WeChat_FaaS_Xposed（53 stars，最后更新 2024-05-30）；框架 LSPosed/LSPosed（25620 stars，GPL-3.0，2026-10-14）。
- **判定**：仅作能力对照，不建议投入生产。

### A6 Android 本地库解密
- **原理**：`/data/data/com.tencent.mm/MicroMsg/<32位哈希>/EnMicroMsg.db`，SQLCipher 加密；经典派生 `key = MD5(IMEI + UIN)` 取前 7 位小写；新版有变体（需以实际环境为准）。UIN 可从 `shared_prefs/system_config_prefs.xml` 的 `default_uin` 读取（来源：技术博客 https://timkingnf.github.io/blog/wechat_analyze.html ；https://ssine.ink/en/posts/wechat-data-decryption 明确指出非 root 无法访问该目录，root 是前提）。
- **能力**：一次导出即可全量历史；若持续挂载可观察 WAL 变化做近实时。
- **风险/现状**：**必须 root**；且头部项目已因腾讯律师函停更/删功能——PyWxDump（xaoyaoo/PyWxDump，9622 stars，README 声明收到微信官方律师函、不再提供更新与技术支持）；WeChatMsg（LC044/WeChatMsg，42367 stars）仍在维护但同属敏感地带。
- **判定**：取证/个人备份视角成立；商业化与合规场景不要用。

### B1 iOS 快捷指令（死路，详见 §④）
### B2 iOS 无障碍（死路，详见 §④）
### B3 iOS 越狱插件
- itenfay/WeChat_tweak：自述功能含防撤回、屏蔽群消息、过滤特定群聊、伪定位、改步数等；README 中版本表把插件版本与微信大版本绑定（如 v1.0.8 适用微信 8.0.6、v1.0.7 适用 8.0.1），说明**版本耦合极强**。
- 核验状态：`gh api` 可取到仓库元数据（1075 stars，NOASSERTION，2026-05-31，未归档）；但本次 `curl https://github.com/itenfay/WeChat_tweak` 多次返回 000，故**页面 HTTP 状态标「未核实（网络不稳定）」**。
- 需要越狱或自行重签 IPA，非越狱方案仅为旧版本客户端改装，生态脆弱。
- **判定**：可作为「iOS 上确实存在第三方 Hook 先例」的证据，不作为方案。

### B4 iOS 本地库
- 取证资料指出 iOS 微信消息落在 `AppDomain-com.tencent.xin/Documents/<hash>/DB/MM.sqlite`，**通常未加密**（来源：Belkasoft 取证文章 https://belkasoft.com/WeChat-forensics）。
- 但提取路径必须越狱或整机备份，且是静态快照，**无实时性**。
- **判定**：历史导出可参考，实时采集不适用。

### C1 多端同时在线（借道思路）
- 微信/企微官方支持手机与其它端同时在线（官方页 https://weixin.qq.com/cgi-bin/readtemplate?t=weixin_multi_device HTTP 200，但内容为 JS 渲染，**具体设备数/策略未核实**）。
- 价值：不直接采集手机，而是让消息「同步到一个可做自动化的端」（平板/桌面/另一台手机），再配合 A2/A3/A4 或既有的 macOS 桌面路线。
- **判定**：架构上有用，规避了 iOS 的系统封锁。

### C2 人工搬运（文件传输助手/收藏/迁移）
- 官方「迁移聊天记录」「备份与迁移」可在设备间搬运，但**不提供程序化批量导出群消息的接口**。
- **判定**：一次性搬家可用，持续采集不可用。

### C3 视觉 RPA
- Android 侧 scrcpy（Genymobile/scrcpy，155519 stars，Apache-2.0，2026-11-24）投屏 + 截图 OCR/VLM，免 root，可识别任意界面。
- 缺点：受分辨率/字体影响、耗电、无法稳定区分新消息 diff；在 A2 的 UI 树可用时它只是兜底。

---

## ④ 已剔除死路（附判定依据）

| 死路 | 为什么排除 | 依据 |
|---|---|---|
| iOS 快捷指令「收到微信通知 → 自动汇总」 | Apple 个人自动化的「通信触发条件」官方只覆盖**电子邮件与信息（Message）**，不含第三方 App 通知；iOS 也没有「收到任意通知」的通用触发器。抓取 Apple 官方「通信触发条件」页正文，关键词仅出现「邮件」「信息」，**未出现** WhatsApp/微信 | https://support.apple.com/zh-cn/guide/shortcuts/apdd711f9dff/ios （HTTP 200，正文已提取） |
| iOS 用快捷指令/App Intents 直接读微信正文 | 微信未开放读取自身会话的 App Intent；Shortcuts 无「获取最近微信消息」动作 | 官方手册动作列表中无此能力（同上域名） |
| iOS 程序化读取他 App 无障碍树（VoiceOver/切换控制导出） | Apple 未向第三方开放「dump 其它 App accessibility 树」的 API；VoiceOver/Switch Control 是交互层而非数据接口 | Apple 官方手册（无相关接口条目）＋社区无障碍讨论（仅提及二者互斥等使用限制） |
| 非越狱 iOS 直读微信沙盒 / MM.sqlite | 应用容器隔离 + 无授权通道 | https://belkasoft.com/WeChat-forensics （需设备提取权限） |
| 抓包/TLS 中间人解密微信协议 | 客户端证书绑定 + 私有协议；本次检索未见可信的活跃开源项目 | **未核实**（无可靠项目名，故不作为路线） |
| Android 云手机/模拟器跑微信并抓库 | 环境检测 + 违反协议，且模拟器 root ≠ 真机 root，工程上脆弱、合规上最差 | 综合判断，无成熟开源项目支撑（未核实） |
| 企业微信「智能机器人/群机器人」采集全群消息 | 机器人只能收到 @ 它的消息，Webhook 只能发不能收 | 官方文档 91360/91774 中机器人与存档为不同接口族 |
| 企业微信会话内容存档「回溯历史」 | 存档从开通时刻起留存，不支持补采开通前消息 | 官方「获取会话内容」文档条目（不可回溯为该类接口通行限制；具体条款以官方页为准） |

---

## ⑤ 落地建议（按目标选路）

1. **企业微信群消息、要合规、要长期** → A1 会话内容存档。唯一无需碰手机、无封号风险的正解；代价是费用与不可回溯。
2. **微信/企微都要、要准实时、能接受灰色地带** → 先用 **A2（OpenClaw Android paired node）** 真机验证，配 A3 通知监听做触发信号（通知到达 → 唤醒 observe），形成「通知触发 + UI 树取文」的组合；这比纯 Hook 更接近「等同人工操作」。
3. **只要历史全量归档（个人/取证）** → Android 用 A6（root + 解密，注意 PyWxDump 类项目的律师函风险），iOS 用 B4（备份/越狱提取）。
4. **iOS 实时采集** → 官方路径下**不存在**；现实做法是把消息引到有自动化能力的端（C1/C2）或用 A1（限企微）。
5. **不要做** → iOS 快捷指令通知汇总（平台不支持）、纯抓包（无可信项目）、LSPosed 大规模使用（封号风险最高）。

---

## ⑥ 来源清单（含 URL 与核验状态）

### 6.1 AI Agent 官方文档
| 来源 | URL | 状态 |
|---|---|---|
| OpenClaw Node command policy（Android 默认含 `mobile.ui.observe`/`mobile.ui.act`，需 Accessibility Control） | https://docs.openclaw.ai/nodes/command-policy | HTTP 200，正文已读 |
| OpenClaw Node device commands（设备命令族清单，无消息历史命令） | https://docs.openclaw.ai/nodes/device-commands | HTTP 200，正文已读 |
| OpenClaw Nodes 总览 | https://docs.openclaw.ai/nodes | HTTP 200 |
| OpenClaw Android app（companion node、Gateway 独占设备能力、APK 发布方式） | https://docs.openclaw.ai/platforms/android | HTTP 200，全文 52,652 字符已抓取 |
| OpenClaw iOS app（iOS 26.2+；能力不含 notifications/mobile.ui） | https://docs.openclaw.ai/platforms/ios | HTTP 200，全文 59,970 字符已抓取 |
| OpenClaw GitHub（Android 源码 `apps/android`） | https://github.com/openclaw/openclaw/tree/main/apps/android | 仓库存在（gh api HTTP 200） |
| ClawHub 技能市场 | （本机 clawhub CLI 存在；搜索命令本次**未能成功执行**） | 未核实 |

### 6.2 平台官方文档
| 来源 | URL | 状态 |
|---|---|---|
| Android NotificationListenerService（系统通知读取 API） | https://developer.android.com/reference/android/service/notification/NotificationListenerService | URL 可达；正文抓取为空 → 内容未核实 |
| Apple：创建个人自动化 | https://support.apple.com/zh-cn/guide/shortcuts/apdfbdbd7123/ios | HTTP 200，正文已提取 |
| Apple：通信触发条件（仅邮件/信息，无第三方通知） | https://support.apple.com/zh-cn/guide/shortcuts/apdd711f9dff/ios | HTTP 200，正文已提取（B1 死路关键证据） |
| Apple：个人自动化介绍 | https://support.apple.com/zh-cn/guide/shortcuts/apd690170742/ios | HTTP 200 |
| DCloud 插件 4915「监听通知栏内容/监听微信通知消息」（版本 3.1.0 2025-05-29） | https://ext.dcloud.net.cn/plugin?id=4915 | HTTP 200，标题已确认 |

### 6.3 企业微信官方文档
| 来源 | URL | 状态 |
|---|---|---|
| 会话内容存档 - 概述 | https://developer.work.weixin.qq.com/document/path/91360 | HTTP 200，页面 1.7MB 已抓 |
| 会话内容存档 - 获取会话内容 | https://developer.work.weixin.qq.com/document/path/91774 | HTTP 200，页面 1.9MB 已抓 |
| 文档根（接口索引，含机器人/存档分族） | https://developer.work.weixin.qq.com/document/path/91769 | HTTP 200 |

### 6.4 GitHub 项目（均在本次会话以 `gh api repos/...` 实测）
| 项目 | URL | HTTP | star | license | 最后 push | 备注 |
|---|---|---|---|---|---|---|
| openclaw/openclaw | https://github.com/openclaw/openclaw | 200 | 395,125 ※ | MIT | 2026-11-24 | ※数值为本机 API 返回值，量级异常，**存疑，勿直接引用** |
| LSPosed/LSPosed | https://github.com/LSPosed/LSPosed | 200 | 25,620 | GPL-3.0 | 2026-10-14 | Hook 框架 |
| Genymobile/scrcpy | https://github.com/Genymobile/scrcpy | 200 | 155,519 | Apache-2.0 | 2026-11-24 | 投屏/视觉 RPA |
| LC044/WeChatMsg | https://github.com/LC044/WeChatMsg | 200 | 42,367 | 无 | 2025-12-30 | 微信本地库解析 |
| sunnyyoung/WeChatTweak（macOS） | https://github.com/Sunnyyoung/WeChatTweak | 200 | 13,840 | AGPL-3.0 | 2026-02-08 | 参照物 |
| xaoyaoo/PyWxDump | https://github.com/xaoyaoo/PyWxDump | 200 | 9,622 | 无 | 2025-10-20 | README 声明收到腾讯律师函 |
| hamibot/hamibot | https://github.com/hamibot/hamibot | 200 | 3,137 | NOASSERTION | 2023-11-01 | 自动化框架，活跃度下降 |
| NICEXAI/WeWorkFinanceSDK | https://github.com/NICEXAI/WeWorkFinanceSDK | 200 | 324 | Apache-2.0 | 2024-11-25 | 企微存档 SDK |
| autox-community/AutoX | https://github.com/autox-community/AutoX | 200 | 356 | NOASSERTION | 2025-11-29 | 自动化框架 |
| automan-bot/AutoX | https://github.com/automan-bot/AutoX | 200 | 228 | NOASSERTION | 2025-11-07 | 自动化框架 |
| ShadowSmallBaby/WechatXposedHook | https://github.com/ShadowSmallBaby/WechatXposedHook | 200 | 185 | AGPL-3.0 | 2026-11-12 | Hook 模块 |
| Chagall/notification-listener-service-example | https://github.com/Chagall/notification-listener-service-example | 200 | 302 | MIT | 2021-03-20 | 通知监听示例 |
| B022MC/wechat-observatory | https://github.com/B022MC/wechat-observatory | 200 | 35 | MIT | 2026-10-09 | LSPosed 微信网关 |
| Dawnnnnnn/Hook_WeChat_FaaS_Xposed | https://github.com/Dawnnnnnn/Hook_WeChat_FaaS_Xposed | 200 | 53 | 无 | 2024-05-30 | Hook 模块 |
| itenfay/WeChat_tweak | https://github.com/itenfay/WeChat_tweak | gh api 200 / curl 多次 000 | 1,075 | NOASSERTION | 2026-05-31 | iOS 插件；**HTTP 页面状态未核实** |
| hyb1996/AutoX | https://github.com/hyb1996/AutoX | **404** | — | — | — | 已迁/改名 |
| 1n3/WeChatTweak | https://github.com/1n3/WeChatTweak | API 与 curl 均不稳定（EOF/000） | — | — | — | **未核实** |

### 6.5 社区与取证资料（非官方，已标注）
| 来源 | URL | 状态 |
|---|---|---|
| OpenClaw Node Pairing with Phone（`ui_hierarchy`、无线 ADB、scrcpy 等说法） | https://www.shopclawmart.com/blog/openclaw-node-pairing-phone | 检索摘要可获取；**第三方博客，官方文档未印证** |
| Auto.js/AutoX/Hamibot 与无障碍服务关系 | https://lmmsoft.github.io/wechat_robot_technical | 检索命中；本次正文抓取为空 → 内容未核实 |
| 微信本地库加密与密钥派生（MD5(IMEI+uin) 前 7 位、UIN 位置） | https://zhuanlan.zhihu.com/p/676435276 、https://timkingnf.github.io/blog/wechat_analyze.html | 检索命中，技术细节多源一致 |
| SQLCipher V2 解密与 root 必要性 | https://ssine.ink/en/posts/wechat-data-decryption | 检索命中，要点已读 |
| EnMicroMsg.db 取证方法 | https://www.forensicfocus.com/articles/decrypt-wechat-enmicromsgdb-database | 检索命中，要点已读 |
| iOS 微信 `MM.sqlite` 通常未加密 | https://belkasoft.com/WeChat-forensics | 检索命中，要点已读 |
| 微信插件与封号风险 | https://sspai.com/post/45473 | HTTP 200，标题确认 |
| 微信多端登录官方页 | https://weixin.qq.com/cgi-bin/readtemplate?t=weixin_multi_device | HTTP 200，JS 渲染，细则未核实 |
| npm `@tencent-weixin/openclaw-weixin` | https://www.npmjs.com/package/@tencent-weixin/openclaw-weixin | 首次探测返回 2.4.10/MIT，二次为空 → **未完全核实** |

---

## ⑦ 本次调研的未核实与存疑清单（避免过度结论）

1. `mobile.ui.observe` 的**请求/响应字段**（参数 schema、是否支持指定包名/窗口、返回体是否含时间戳与发送者）——官方未公开，需真机 `openclaw nodes describe` + 实调确认。
2. 该命令在**微信/企微上是否真的返回完整消息文本**（可能有视图裁剪、自绘控件不落 AX 树）——待真机验证。
3. 长轮询下的**保活/耗电/后台可用性**——未核实。
4. 第三方博客中的 `devices:` 配置块、`ui_hierarchy: true`、`scrcpy`、`doze_bypass` 等字段**是否存在于当前版本 OpenClaw**——官方文档未见，存疑。
5. iOS 越狱插件在当前微信版本的实际可用性——`itenfay/WeChat_tweak` 的版本表只到微信 8.0.x 时期，是否适配 8.0.6x/9.x **未核实**。
6. 企业微信会话存档的**价格与开通资质细则**——官方页面未逐条摘录，标未核实。
7. `openclaw/openclaw` 的 star 数（395,125）为本机 API 返回值，量级异常，**存疑**；其余仓库数值相对可信但仍会随时间变化。
8. ClawHub 上是否有现成的微信采集技能——本次**未成功执行检索**，留待补查。

---

## 附：与既有 macOS 报告的关系

- 本报告**不推翻** macOS 报告结论：企微 AX 实时采集仍是最优桌面路线；微信 AX 在 macOS 上「实测空壳」的结论**不直接适用于 Android**——Android 的无障碍体系（AccessibilityService/节点树）与 macOS 的 AX 树实现不同，不能用 macOS 的空壳结果推断 Android 也拿不到文本，反之亦然。
- 两赛道的**共同底线**一致：凡是以「解密客户端本地库 / Hook 客户端」为核心的路线，都有法律与封号风险；官方接口（企微存档、官方机器人）才是可对外承诺的方案。
