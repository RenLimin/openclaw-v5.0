# DESIGN：企业微信 macOS AX 采集器 Phase 1

> **⚠️ 现状更新指针（2026-11-24）**：本文为 Phase 1 原始设计，其中「`chat --session` 点击切换会话」
> 已被 owner 红线取代（引擎物理移除点击）；「图片不可得」也被 `AXImageData` 直出推翻。
> 现行实现与验收以 `L2-infra/components/wecom-ax-collector/` 为准
> （引擎子命令 `sessions|chat|snapshot|images`，严格只读）。

- 版本：v0.1 ｜ 日期：2026-11-24 ｜ 状态：设计中
- 上游证据：`VERIFICATION-wecom-ax-collection-poc-v1.0.md`（PoC 5 项验收全过）
- 广度调研：`RESEARCH-wechat-wecom-broader-lanes-v1.1.md`
- 关联旧稿：`RESEARCH-mac-wechat-wecom-group-message-access-v1.1.md`（文件名 v1.0，内容 v1.1）

---

## 1. 需求与边界（PRD）

### 1.1 目标
把 PoC 验证过的 AX 只读采集能力工程化为可长期运行的采集器：轮询指定企微会话，读取文字消息 + 元数据，去重后输出到 JSONL / webhook，供上层（告警、摘要、知识沉淀、RAG）消费。

### 1.2 明确不做（Phase 1）
- 发送消息
- 富媒体内容识别（图片/文件/语音/视频本体）
- 事件推送（仍是轮询）
- 多账号

### 1.3 「全部信息」边界（诚实声明）
- **可全量**：文字正文、发送者、@提及、链接、时间戳、系统消息、群公告、会话元数据、群成员列表
- **不可得**：图片/文件/语音/视频本体，仅文本占位
- **历史回溯**：可，通过模拟滚动加载；全量回溯效率低，需按需

---

## 2. 业界最佳实践与调研来源

本方案遵循的架构原则与依据：

1. **零侵入优于注入**：相比 Windows Hook（WeChatFerry/wxhelper 需 DLL 注入、面临封号风险），纯 AX 只读不修改客户端进程，风险最低。来源：`RESEARCH-wechat-wecom-broader-lanes-v1.1.md` §Windows Hook 硬前提。
2. **轮询 + 指纹去重**是 UI 自动化的通用模式：采集快照 → 计算指纹集合 → 差集为新消息。参考 RPA/无障碍采集通行做法。
3. **关注点分离**：采集引擎（只读、无状态）与调度/输出层（有状态、可替换）分离，便于替换存储后端与触发方式。
4. **幂等输出**：每条消息生成确定性 ID，重复消费不产生副作用。

### 方案取舍
| 备选 | 取舍理由 |
|---|---|
| 全 Python（pyobjc AXUIElement） | pyobjc 对 AX C API 封装不完整，`AXValue` 读取易踩坑；**Swift 直调 C API 已验证稳定**，复用之 |
| Swift 引擎 + Python 调度（✅ 选定） | 采集层用已验证 Swift；调度/去重/输出用 Python，开发快、可测 |
| Electron/JXA 自动化 | JXA 对 AX 支持弱于 Swift，且性能差 |
| 直接接本地库（Info.db 解密） | 需完全磁盘访问 + SQLCipher 密钥派生，富媒体同样拿不到，且侵入性高，本期不做 |

---

## 3. 架构

```
┌─────────────────────┐    JSON(text)    ┌──────────────────────────┐
│ wecom_ax_engine     │ ───────────────► │ wecom_collector.py       │
│ (Swift, 只读)        │                  │ - 轮询调度                │
│ - 会话列表           │                  │ - 指纹去重                │
│ - 消息区             │                  │ - JSONL / webhook 输出    │
│ - 点击切换           │                  │ - 错误恢复                │
└─────────────────────┘                  └──────────────────────────┘
        ▲                                         │
        │ pid + 会话定位                            ▼
   企业微信 5.0.13                          上层消费（告警/摘要/RAG）
```

### 3.1 模块职责
- **`wecom_ax_engine.swift`**：编译为 `wecom_ax_engine` 二进制。子命令：
  - `sessions`：输出会话列表 JSON（含坐标）
  - `chat --session <关键词>`：切换到会话并输出消息区 JSON
  - `snapshot`：单次快照（会话列表 + 当前消息区 + 窗口状态）
- **`wecom_collector.py`**：调度循环。读取配置 → 定时 snapshot → 解析 → 指纹去重 → 写 JSONL → 可选 webhook。

### 3.2 关键数据结构
```json
// 会话
{"name": "示例部门群A", "tag": "部门", "last_msg": "...", "time": "昨天",
 "unread": 0, "frame": [60,353,287,64], "is_group": true}

// 消息
{"sender": "张三", "content": "...", "ts": "昨天 18:04",
 "is_self": false, "is_system": false, "mentions": ["李四"],
 "msg_id": "<确定性哈希>"}
```

### 3.3 去重指纹策略
`msg_id = sha1(会话名 + 归一化y坐标桶 + 发送者 + 内容)`，并用内容 hash 二次校验滚动漂移。
已见集合持久化到 `.seen_ids.json`，重启不丢。

### 3.4 错误恢复
- AX 树读取失败 / 超时 → 指数退避重试（最多 5 次）
- 窗口不存在 → 等待 + 提示用户打开企微
- 会话切换失败 → 记录，下一轮重试
- **绝不无限重试**（红线：同一操作最多 5 次）

---

## 4. 验收标准（Phase 1 完成定义）

| # | 标准 | 验证方式 |
|---|---|---|
| A1 | 连续运行 ≥5 分钟轮询，无崩溃、无内存泄漏 | 观察进程 RSS 稳定 |
| A2 | 期间新消息被检出且不重复输出 | 人工发一条测试消息，JSONL 恰出现 1 条 |
| A3 | 最小化/后台时采集不中断 | 切走前台应用，5 分钟内仍正常 |
| A4 | 切换会话后 ≤1s 内消息区刷新正确 | 计时 |
| A5 | 输出字段完整（sender/content/ts/mentions/msg_id） | 抽查 JSONL |
| A6 | 崩溃/杀进程后可恢复且不重复输出旧消息 | 杀掉重启，`.seen_ids` 生效 |

---

## 5. 风险与合规

1. **隐私**：采集的是工作对话，需明确用途、访问控制与留存策略；不写入任何凭据。
2. **版本耦合**：企微升级改 AX 结构会导致解析失效，需版本适配测试。
3. **辅助功能权限**：必须授权；提供自检脚本。
4. **频率控制**：轮询间隔 ≥2s，避免高频操作触发异常检测。
5. **富媒体缺口**：如需图片/文件内容，另行评估截图 OCR/VLM 叠加，不在本期。

---

## 6. 目录规划

```
docs/research/
├── DESIGN-wecom-ax-collector-phase1.md   (本文档)
├── VERIFICATION-wecom-ax-collector-phase1.md  (验收报告，收尾产出)
scripts/  (PoC 脚本已在 /tmp，工程化版本后续归档到 L2-infra/components/)
```
