# RESEARCH：macOS 本机已登录「企业微信 / 微信」群消息获取能力调研

- 版本：v1.1 ｜ 日期：2026-11-24 ｜ 状态：调研完成 + 本机 AX 实测验证（未实施）
- 目标环境：macOS 27.0.1 (arm64)、企业微信 **5.0.13**（Mac App Store 沙盒版）、微信 **4.1.15**（Mac App Store 沙盒版 4.x 原生架构）；均为个人账号已登录
- 方法：三条信息源全覆盖（官方文档 / 中文社区 / GitHub·Clawhub），两条线并行子代理调研 + **本机一手 AX 实测（权威，覆盖并修正社区结论）** + 关键仓库链接二次核验
- ⚠️ **v1.1 修订（2026-11-24）**：本机实测推翻「微信 macOS 4.x 仍向 AX 暴露会话/输入控件」的社区转述，并发现企微 AX 树完全可读。详见 §② 与 §⑥。
- 关联：`docs/knowledge-base/`（知识沉淀）、能力注册表 `L2-infra/components/config/capability-registry/registry.yaml`（当前无「消息读取」条目）

---

## ① 结论速览（两方向合并）

| 方向 | 首选路线 | 历史消息 | 实时新消息 | 门槛 | 风险 | 推荐度 |
|---|---|---|---|---|---|---|
| **企业微信** | **Accessibility（AX）实时采集** | ⚠️ 已加载可见 | ✅ 轮询（已实测跑通） | 辅助功能（**已有**） | 极低（等同人工操作） | ★★★★★（**当天可落地**） |
| **企业微信** | 本地库只读解析（`io_data.json` 派生密钥） | ✅ 全量 | ✅ 秒级（WAL 轮询） | 完全磁盘访问 TCC（**未开通**） | 低（只读不触网）；版本绑定脆弱 | ★★★★（历史全量补充） |
| **企业微信** | 官方智能机器人 API（WebSocket 长连接） | ❌ | ✅ 仅 @机器人 | 需创建机器人权限；仅内部群 | 零（官方） | ★★★★（合规回复通道） |
| **企业微信** | 截图 + OCR/VLM（视觉 RPA） | ⚠️ 仅可见 | ✅ 轮询 diff | 屏幕录制 + 辅助功能 | 低 | ★★★（兜底） |
| **企业微信** | 会话内容存档（msgaudit） | ❌ 不可回溯 | ✅ | 企业管理员 + 收费 + 盖章 | 合规但个人不可用 | ★★ |
| **微信** | Accessibility（AX 控件树） | ❌ **本机实测空壳** | ❌ **实测失败** | 辅助功能权限（已有） | — | ✕ 不可用（见 §⑥） |
| **微信** | 本地库解密（SQLCipher key） | ✅ 全量 | ✅ WAL 监听 | 关 SIP + 重签 + root 调试 | 中（违反使用条款） | ★★★★（历史全量首选） |
| **微信** | 截图 OCR / VLM | ⚠️ 仅可见 | ✅ 轮询 | 屏幕录制权限 | 低 | ★★（兜底） |
| **微信** | 腾讯官方 iLink 插件 | ❌ | ✅ **仅私信** | 低 | 无 | ⭐⭐⭐ 但不支持群聊 |

**一句话结论（v1.1 实测修正）**：两个方向都没有「官方/合规的群消息直连 API」。但**分化极大**——
- **企业微信**：AX 路线**已在本机实测跑通**（641 节点、真实消息文本+发送者+时间戳、内外群可辨），实时采集当天即可落地，且零注入、零封号风险。
- **微信**：AX 路线**本机实测不可用**（subtree=5，坐标命中 -25208），报告里 BiboyQG/WeChat-MCP 的「4.x 可读」是版本/状态相关结论，**不能直接照搬**。微信只剩「本地库解密」一条重路线。

---

## ② 本机一手事实（Jerry 实测，非转述）

| 事实 | 值 |
|---|---|
| 企业微信版本 / 来源 | 5.0.13，App Store 收据=1（沙盒） |
| 微信版本 / 来源 | 4.1.15，App Store 收据=1（沙盒） |
| 进程 | 均运行中；企微含 CEF Renderer（wxwork/5.0.13）、WeDrive node 组件；微信含 WeChatAppEx（小程序宿主） |
| 沙盒数据目录 shell 直读 | **被 TCC 拒绝**：`Operation not permitted`（需「完全磁盘访问」授权） |
| AX 权限 | **已开通**（System Events 可读进程与窗口名；`AXEnhancedUserInterface` 在册） |
| **AX 树规模（实测深度 14）** | **企业微信 = 641 节点**（完整 SplitGroup/Table/Row/Cell/StaticText，含真实消息）；**微信 = 5 节点**（仅标题栏按钮） |
| **AX 坐标命中测试** | 企微：窗口内采样点全部命中 `AXCell`（subtree 3–5）；微信：全部 `-25208 kAXErrorCannotComplete` |
| **微信前台复核** | 激活到前台 + sleep 3s 后重测：仍 subtree=5、仍 -25208 → 排除「非前台未构建 AX」变量 |
| **企微实证内容** | dump 出真实数据：会话列表（群名/最后消息/时间戳，示例一律用合成占位，如「示例同事A: 第47周相关会议纪要供参考@所有人 / 昨天」）、内外群标签（`AXTextArea val=外部`/`部门`/`全员`）、右侧消息正文长文本 |
| wecom-cli 插件 | 已白名单（profile=full）；技能面**只有发消息**（限最近会话/授权人），**无读消息/群消息拉取**；tool 调用报「插件运行时未初始化」 |
| 能力注册表 | `--query 消息/message/群` 全部未命中；仅 `wecomcli-contact`（通讯录） |

---

## ③ 企业微信详述

### 官方路线（developer.work.weixin.qq.com）
- **会话内容存档（唯一全量合规路线）**：`GetChatData` SDK，单次≤1000 条、限**最近 5 天**密文，需持续轮询落库；门槛 = 企业管理员 + 盖章确认函 + **强制告知**（客户端出现不可关闭存档提示，外部微信用户按会话粒度单独同意）；收费（2026）：原生 900/1800 元/员工/年，数据专区 300/500；**官方 SDK 仅 Linux/Windows，无 macOS**；不可回溯。→ 个人不可行。
- **群机器人 Webhook**：单向推送（20 条/分），**只能发不能收**，外部群不支持；2026 新版客户端入口已隐藏。
- **智能机器人 API（2026-05 上线，最现实入站通道）**：WebSocket 长连接（本地可跑，免公网回调）或 HTTP 回调。限制：群聊**只推 @机器人**的消息、群聊仅文本/图文、单用户最多 3 条在途、需超管/被授权成员创建、**不能进外部客户群**。官方帮助中心确认 OpenClaw 接入「暂不支持外部群/客户群」。
- **自建应用回调**：仅「用户向应用发消息」1 对 1 应用会话事件，非群消息。

### 本地库路线（首选，证据链）
- 结构（5.0.8/5.0.10 实证）：沙盒内 `Info.db` / `Session.db` / `io_data.json`；消息库为 **wxSQLite3 AES-128-CBC（plaintext header），非 SQLCipher**；密钥可从 `io_data.json` 的 `login_keys` 派生（另有内存扫描 `task_for_pid+mach_vm_read` 读 16B key 的实现）。轮询主库 + WAL 可达秒级。
- **格式闸门（5.0.13 待验证的关键）**：`xxd Info.db | head -2`，offset 0–7 应为 magic `a4 1d 91 37 …`。命中即路线成立。
- 公开实现：`freanocank/wecom-agent`（26★，MIT，Python，实测 5.0.8 / Apple Silicon，定位即 Agent Skill）。**没有任何项目声称验证过 5.0.13**——这是最大不确定性。
- 腾讯官方 `WecomTeam/wecom-cli` + `WecomTeam/wecom-openclaw-plugin` 存在且维护积极，但只解决机器人收发。

### Clawhub/OpenClaw 生态
**无任何官方/Clawhub 插件能读桌面客户端本地群消息**；该方向仅 1 个 26★ 仓库 + 1 个 Gist。

---

## ④ 微信详述

### 官方路线
- 公众平台/开放平台**无个人号消息 API**；个人微信不存在群 webhook 机器人。
- 微信网页版已死（2017 限新号、2019 后关闭）→ itchat / wechaty-puppet-wechat 失效。
- **腾讯官方 OpenClaw 插件 `@tencent-weixin/openclaw-weixin`**（iLink API，扫码登录，支持私信+媒体）——但官方明确「能力元数据未声明支持群聊（仅私信）」，群聊仍空白。
- 第三方 `Devo919/openclaw-wechat-channel` 依赖商业协议服务（SyNodeAi），**非官方授权、消息过第三方**。

### Accessibility 路线 —— ⚠️ 本机实测不可用（推翻社区转述）
> **v1.1 实测结论（权威，优先于下列社区来源）**：在 macOS 27.0.1 + 微信 4.1.15 App Store 沙盒版上，AX 对微信主窗口只暴露 **5 个节点**（3 个标题栏按钮 + window），无任何内容节点；`AXUIElementCopyElementAtPosition` 在窗口内部采样点全部返回 `-25208 kAXErrorCannotComplete`；激活到前台后复核不变。**因此「读取群消息文本」在本机不可行**。
> 社区来源（保留供参考，但均为**版本/状态相关结论，不能照搬到 4.1.15**）：
- yage.ai（2026-03-27）多 Agent 调研：称 macOS 4.x 仍暴露会话项 `session_item_{name}`、输入框 `chat_input_field`；且 AX 树不暴露发送者，需截图判色。
- `BiboyQG/WeChat-MCP`（303★，MIT，`pip install wechat-mcp-server`）、`Cybing521/wechat-mcp`（6★，TS/AppleScript + AX 轮询）——在本机前提不成立。
- 老牌纯 AX CLI `qiqijin/macos-wechat-cli` 作者自述**仅支持微信 3.8**（GitHub 链接核验 404）。

### 视觉 RPA 路线（仅兜底，可能可行）
若 AX 为空壳，唯一剩下的非注入读法 = **截屏 + OCR/VLM**（按坐标区域切会话列表与消息区）。风险低但脆弱、只拿可见内容、速度慢。未在本机验证。

### 本地库解密路线（历史全量，但脆弱）
- 路径（4.x）：`~/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/<wxid>/db_storage/`
- 参数演进：macOS 3.x = SQLCipher v3/page 1024/原始密钥；**4.0 起 SQLCipher v4、page 4096、KDF 256000、HMAC SHA-256**；**4.1.x 实测进一步变为 HMAC-SHA512 / 64 字节 MAC / 80 字节保留区，运行时不再走 PBKDF2 口令派生**（diegoyc.com 2026-04 报告）。
- Mac 取 key 需关 SIP；lldb 断 `sqlite3_key` 的老办法**仅微信 ≤3.8.5 有效**；App Store 版重签后**版本升级即失效**。→ 4.1.15 上可行性低，列为历史全量的理论选项而非推荐。

### 死路（明确排除）
dylib 注入 / WeChatTweak 类（4.x 已基本死亡、封号高）、协议 puppet（wechaty PadLocal 等，大规模封号史、多停更）、Web 协议、通知中心旁路（群静音/折叠即丢）。

---

## ⑤ 落地方案（Top 2，含验证标准）

### 企业微信 —— AX 实时采集已实证可行，直接落地
1. **Accessibility 采集（首选，实测通过）**
   - 已有条件：AX 权限已开通；实测 dump 到 641 节点含真实会话列表与消息正文。
   - 步骤：用 pyobjc/swift 脚本枚举会话列表 Table 行（群名/最后消息/时间戳/内外群标签），轮询 diff 检测新消息；或按群名定位后读右侧消息区。
   - **验证标准（新增消息时延）**：在测试群发一条消息，确认 N 秒轮询内被捕获、发送者/文本正确。
   - 风险：仅能拿可见内容（未滚动的会话/消息）；UI 改版会失效。
2. **本地库只读（补充历史全量，需先开权限）**
   - 前置：给终端授「完全磁盘访问」。步骤：列 `Messages1/{Info.db,Info.db-wal}`、`io_data.json` → `cp -c` 副本到隔离目录 → `xxd Info.db | head -2` 看 magic。
   - **验证标准**：magic `a4 1d 91 37…` 命中 + 解出 `MESSAGE` 表 = 5.0.13 成立。
3. **官方智能机器人 WebSocket**（合规回复通道，仅内部群 @）——需机器人创建权限。

### 微信 —— AX 路线已证伪，只剩重路线
1. **视觉 RPA（截屏 + OCR/VLM）** —— 当前唯一非注入的读法，但脆弱、仅可见、慢；需本机再验证。
2. **本地库解密（SQLCipher key）** —— 全量历史唯一途径，但需关 SIP + 重签（版本升级即失效）+ root 调试，4.1.x 参数已漂移（HMAC-SHA512），**成本高且违反使用条款**；仅在确实需要全量归档时评估。
3. **不要**采用 `BiboyQG/WeChat-MCP` 等 AX 方案（前提在本机不成立）。

### 组合建议（修正后）
- **企微**：AX 轮询（已跑通）→ 归一化 → 喂 OpenClaw；需要历史时再加本地库解密。
- **微信**：仅在有明确全量需求时才动本地库解密；实时性需求优先看「视觉 RPA」或换平台（如另备 Android 端）。
- 通用纪律：所有采集**默认只读、不自动回复**，稳定一周后再考虑开放写操作。

---

## ⑥ 来源清单

**官方**
- https://developer.work.weixin.qq.com/document/path/91774 （会话存档 GetChatData）
- https://developer.work.weixin.qq.com/document/path/91552 （会话存档 FAQ，SDK 仅 Linux/Win）
- https://developer.work.weixin.qq.com/document/path/100023 ｜ /99871 ｜ /100252 （数据与智能专区）
- https://open.work.weixin.qq.com/help2/pc/21657 （OpenClaw 接入，不支持外部群）
- https://docs.openclaw.ai/channels/wecom ｜ https://docs.openclaw.ai/zh-CN/channels/wechat （官方微信插件仅私信）
- https://www.npmjs.com/package/@tencent-weixin/openclaw-weixin

**社区**
- https://juejin.cn/post/7680457986105933851 （2026 四种收消息路线实测边界）
- https://panzhongxian.cn/cn/2026/06/wecom-bot-comparison （回调 vs 长连接）
- https://docs.astrbot.app/platform/wecom_ai_bot
- https://zhuanlan.zhihu.com/p/2017258541057090832 ｜ https://www.sohu.com/a/1028752914_122489536 （2026 存档收费）
- https://bbs.kanxue.com/thread-284417.htm （微信 4.0 数据库解密分析）
- https://sarv.blog/posts/chatlog （跨版本 SQLCipher 参数）
- https://diegoyc.com/wp-content/uploads/2026/04/WeChat-macOS-4.1.x-Database-Decryption-%E2%80%94-Process-Report.pdf （4.1.x HMAC-SHA512 实证）
- https://www.uscardforum.com/t/topic/460509 （Mac 微信逆向踩坑长帖）
- https://yage.ai/share/wechat-uia-platform-feasibility-survey-20260327.html （跨平台 UI 自动化调研）
- https://blog.ax0x.ai/wechat-automation-macos （DB+AX 工程实录）

**GitHub（已核验 HTTP 200）**
- https://github.com/freanocank/wecom-agent （26★ MIT，企微 5.0.8 本地库解密 + Skill）
- https://github.com/WecomTeam/wecom-cli ｜ https://github.com/WecomTeam/wecom-openclaw-plugin （腾讯官方）
- https://github.com/BiboyQG/WeChat-MCP （303★ MIT，AX 群消息 MCP）
- https://github.com/Cybing521/wechat-mcp （6★ MIT）
- https://github.com/sunnyyoung/WeChatTweak ｜ https://github.com/wechaty/wechaty

**已剔除（核验 404，不作为依据）**
- kiqijin/macos-wechat-cli、Numaira/weclaw-cua

---

## 附：本次调研的执行事故记录

- 子代理默认模型 `coding-plan/doubao-seed-2-1-turbo` 在长任务（>约 2 分钟）反复触发「Request timed out before a response was generated」，主因是 **provider 侧 LLM 空闲/流看门狗隐含 ~120s 上限**（`models.providers.<id>.timeoutSeconds` 未设置，文档明示可用它抬升该上限）。
- 缓解：子代理 `runTimeoutSeconds` 显式设为 1500；报告回执因模型 503 未投递，改由 `sessions_history` + `sessions_send` 分段取回（每段再被显示层截断，故多次补发）。
- 结论未受影响，但流程冗长。后续同类调研建议：provider 超时显式配置 + 子代理产物直接写文件（而非靠最终文本回执）。
