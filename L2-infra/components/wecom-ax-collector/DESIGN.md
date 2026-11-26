# DESIGN：企业微信 macOS AX 只读采集器（L2 组件）

- 版本：v1.0 ｜ 日期：2026-11-25 ｜ 状态：**在用**
- 组件入口：`python3 scripts/wecom_collector.py --config <file> [--once|--list]`
- 引擎入口：`engine/wecom_ax_engine <sessions|chat|snapshot|images>`
- 上游设计：`docs/research/DESIGN-wecom-ax-collector-phase1.md`（Phase 1 原始稿）
- 广度调研：`docs/research/RESEARCH-wechat-wecom-broader-lanes-v1.1.md`
- PoC 验收：`docs/research/VERIFICATION-wecom-ax-collection-poc-v1.0.md`
- 工程验收：`./VERIFICATION-v1.0.md`

> **与上游稿的差异（重要）**：Phase 1 稿中的「点击切换会话」已被 owner 红线取代
> （引擎物理移除点击能力）；「图片不可得」已被 `AXImageData` 直出推翻。
> 本文件是**现行实现的权威描述**；上游稿仅作历史设计依据保留。

---

## 1. 需求与边界

### 1.1 目标
把 PoC 验证过的 AX 只读采集能力工程化：轮询企微会话，读取文字消息 + 元数据，
指纹去重后输出 JSONL / webhook，供上层（告警、摘要、知识沉淀、RAG）消费。

### 1.2 明确不做
- 发送消息、模拟输入、切换会话（见 §6 只读红线）
- 事件推送（仍是轮询）
- 多账号

### 1.3 信息边界（诚实声明）
- **可全量**：文字正文、发送者、@提及、链接、时间戳、系统消息、群公告、会话元数据、群成员列表
- **图片**：可通过 `AXImageData` 取到原始像素数据（`images --with-data`），但**不做** OCR/VLM 内容理解
- **文件/语音/视频本体**：不可得，仅文本占位

---

## 2. 业界最佳实践与调研来源

遵循的架构原则与依据：

1. **零侵入优于注入**：相比 Windows Hook（WeChatFerry/wxhelper 需 DLL 注入、有封号风险），
   纯 AX 只读不修改客户端进程，风险最低。
   来源：`RESEARCH-wechat-wecom-broader-lanes-v1.1.md` §Windows Hook 硬前提。
2. **轮询 + 指纹去重**是 UI 自动化通用模式：采集快照 → 计算指纹集合 → 差集为新消息。
3. **关注点分离**：采集引擎（只读、无状态）与调度/输出层（有状态、可替换）分离。
4. **幂等输出**：每条消息生成确定性 ID，重复消费不产生副作用。
5. **隐私默认最小化**：运行期数据（真实对话）默认不入库，`.gitignore` 强制排除
   `data/`、`*.jsonl`、`.seen_ids.json`。

### 方案取舍
| 备选 | 取舍理由 |
|---|---|
| 全 Python（pyobjc） | pyobjc 对 AX C API 封装不完整，`AXValue` 读取易踩坑；Swift 直调 C API 已验证稳定 |
| **Swift 引擎 + Python 调度（✅ 选定）** | 采集层用已验证 Swift；调度/去重/输出用 Python，开发快、可测 |
| Electron/JXA | JXA 对 AX 支持弱于 Swift，性能差 |
| 本地库解密（Info.db + SQLCipher） | 需完全磁盘访问 + 密钥派生，富媒体同样拿不到，侵入性高，本期不做 |

---

## 3. 架构

```
┌──────────────────────┐   JSON(text/images)   ┌────────────────────────┐
│ wecom_ax_engine      │ ────────────────────► │ wecom_collector.py     │
│ (Swift, 严格只读)     │                       │ - 轮询调度              │
│ - sessions           │                       │ - 结构化解析(parser)     │
│ - chat               │                       │ - 指纹去重              │
│ - snapshot           │                       │ - JSONL / webhook 输出  │
│ - images             │                       │ - 错误恢复              │
└──────────────────────┘                       └────────────────────────┘
        ▲                                               │
        │ pid + 会话定位（只读 Get）                        ▼
   企业微信客户端                                  上层消费（告警/摘要/RAG）
```

### 3.1 模块职责
| 模块 | 行数 | 职责 |
|---|---|---|
| `engine/wecom_ax_engine.swift` | ~429 | AX 树遍历 + 元素描述 + 4 个子命令；**唯一直接触碰 AX API 的地方** |
| `scripts/wecom_collector.py` | ~559 | 调度循环、前置检查、去重存储、JSONL 落盘、webhook |
| `scripts/wecom_parser.py` | ~235 | 从引擎原始 items 还原「发送者/内容/时间/@提及」（实测锚点，非通用假设） |
| `scripts/wecom_images.py` | ~152 | `AXImageData` 图片导出 |

### 3.2 引擎子命令（全部只读）
- `sessions`：输出会话列表 JSON（含坐标、未读数、是否群聊）
- `chat [--session <kw>]`：输出当前消息区 JSON；`--session` 仅作调用方标签透传，**不触发切换**
- `snapshot`：会话列表 + 当前消息区 + 窗口状态
- `images [--out DIR] [--with-data]`：图片清单；`--with-data` 直出像素

### 3.3 关键数据结构
```json
// 会话
{"name": "示例部门群A", "tag": "部门", "last_msg": "...", "time": "昨天",
 "unread": 0, "frame": [60,353,287,64], "is_group": true}

// 消息
{"sender": "张三", "content": "...", "ts": "昨天 18:04",
 "is_self": false, "is_system": false, "mentions": ["李四"],
 "msg_id": "<确定性哈希>"}
```

### 3.4 去重指纹策略
`msg_id = sha1(会话名 + 归一化 y 坐标桶 + 发送者 + 内容)`，并用内容 hash 二次校验滚动漂移。
已见集合持久化到 `.seen_ids.json`，重启不丢（`SeenStore`）。

### 3.5 错误恢复
- AX 树读取失败 / 超时 → 指数退避重试（最多 5 次）
- 窗口不存在 → 等待 + 提示用户打开企微
- **绝不无限重试**（红线：同一操作最多 5 次，已写入 AGENTS.md）

---

## 4. 只读红线（owner 明令，最高优先级）

> gateway-owner 2026-11-24 明令：通过已登录的企业微信/微信做 AX/GUI 自动化时，**严格只读不写**。

| 禁止 | 说明 |
|---|---|
| 发送消息 / 回车 / 点发送 | 任何形式的消息外发 |
| `CGEvent` 鼠标/键盘事件合成 | `.post(tap:)` / `CGEventSource` 等 |
| `AXUIElementPerformAction` | 任何 PerformAction |
| `AXUIElementSetAttributeValue` | 给输入框写值 |
| 模拟键入 / 粘贴 / 切会话 / 开关 UI | 一律禁止；切会话由**人工手动**完成 |
| webhook 外发 | 默认必须关闭，方向只能是「读出」 |

**允许**：`AXUIElementCopyAttributeValue` 系列只读 Get；图片只取 `AXImageData`。

**机器门禁**：`tests/test_02_readonly_guard.py` 静态扫描引擎源码，出现任何禁用 API 即测试失败。

---

## 5. 测试与验收标准

| # | 标准 | 验证方式 | 状态 |
|---|---|---|---|
| A1 | 连续运行 ≥5min 无崩溃、内存稳定 | RSS 观察 | ✅（5m04s，RSS 15~17MB） |
| A2 | 新消息检出且不重复 | JSONL 计数 | ✅（new=15→0→0→0，71 行 0 重复） |
| A3 | 最小化/后台仍采集 | 切前台应用后复测 | ✅ |
| A4 | 切会话后刷新正确 | 计时 | ⚠️ 通过但有代价（曾 5.76s） |
| A5 | 输出字段完整 | 抽查 JSONL | ✅ |
| A6 | 崩溃后可恢复不重复 | 杀进程重启 | ⚠️ 部分（缺真实 kill -9 演练） |

回归测试：`pytest tests/`（parser / readonly_guard / images / crash_safety 四组）。

---

## 6. 风险与合规

1. **隐私**：采集工作对话，须明确用途、访问控制与留存策略；不写入凭据；运行期数据不入库。
2. **版本耦合**：企微升级改 AX 结构会导致解析失效，需版本适配测试。
3. **辅助功能权限**：必须授权；提供自检脚本（`check_prerequisites`）。
4. **频率控制**：轮询间隔 ≥2s，避免高频操作触发异常检测。
5. **已知边界**：A4 切换延迟、A6 缺真实崩溃演练（详见 `VERIFICATION-v1.0.md`）。

---

## 7. 变更历史

- 2026-11-25：补建组件级 DESIGN.md（统一设计文档判定口径时确认本组件唯一真实缺失）。
- 2026-11-24：Phase 1 上线并通过验收（见 VERIFICATION-v1.0.md）。
