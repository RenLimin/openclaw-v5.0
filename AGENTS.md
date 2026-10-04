# AGENTS.md - Your Workspace

This folder is home. Treat it that way.

## 重复规则自动记录

用户强调过 **3 遍及以上** 的规则、机制，自动记录到本文件或 USER.md 对应章节，不再反复询问。

## First Run

If `BOOTSTRAP.md` exists, follow it, figure out who you are, then delete it.

## Session Startup

Use runtime-provided startup context first. Do not manually reread startup files unless explicitly asked or missing something needed.

### 会话恢复自检（必做）

每次主会话启动后，先检查 `memory/current-task.md`：

```bash
python3 L2-infra/components/session-recovery/scripts/task_tracker.py current --json
```

| 条件 | 动作 |
|---|---|
| 无 current-task | 正常开始 |
| failure_count = 0 | 等用户指令 |
| 1 ≤ failure_count < 2 | 自动从断点恢复，说明从哪里恢复 |
| failure_count ≥ 2 | 停止重试，告知用户等你拍板 |

恢复策略：从 `progress_entries` 最新一条确定进度，跳过已完成步骤，从当前 step_index 继续。

**重要任务必须登记：** 预计 > 5 步 exec / 批量文件操作 / 长构建的任务，开工前先 `task_tracker start`。

## Memory

- **Daily notes:** `memory/YYYY-MM-DD.md` - raw logs
- **User model:** `USER.md` - durable preferences and profile facts
- **Long-term:** `MEMORY.md** - durable non-profile facts and decisions (main session only, never leak to shared contexts)

Write stable preferences as `Always` / `Never` / `Prefer` directives with `<!-- observed: YYYY-MM-DD | status: active -->` metadata. Mark old entries `superseded` when changing.

Write It Down: "remember this" → update daily file; lesson learned → update AGENTS.md or skill; mistake → document it.

## 开发流程铁律（强制）

所有功能开发必须按顺序执行，不可跳步：

```
1. 明确需求 → PRD（功能清单 + 验收标准）
2. 设计大纲 → DESIGN-OUTLINE（整体架构 + 模块划分）
3. 详细设计 → DESIGN-DETAIL（接口契约 + 数据模型 + 技术方案）
4. 测试方案 → 验收标准 + 测试用例 + 黄金基准
5. 操作手册 → OPERATIONS（安装/启动/故障排查）
6. 开发计划 → IMPLEMENTATION-PLAN（Phase 拆分 + 工时）
7. 开发建设 → 按 Phase 逐步实现
8. E2E 自测 → 自动化测试全部通过
9. E2E 人工测试 → 按操作手册逐条执行
```

**红线：**
- ❌ 禁止跳过设计文档直接写代码
- ❌ 禁止先开发再补设计文档（追认制仅适用于紧急修复）
- ❌ 禁止设计文档未审核就开始建设
- ✅ 每份设计文档必须经 Rex 明确"通过"后才能进入下一阶段

**旧代码迁移规范：** 迁移前必须先读 DESIGN-DETAIL 文档；旧代码与文档契约不一致时以文档为准；迁移完成后验证数据流、生命周期、接口签名。

**测试规范：** Web/安全功能验收必须用真实 HTTP；禁止用 FastAPI TestClient 测试网络安全/Cookie/访问控制；E2E 测试必须覆盖真实用户操作路径；后端 API 应同时兼容多种输入格式。

**文档命名：** `DESIGN-OUTLINE-<topic>-<version>.md` / `DESIGN-DETAIL-<module>-<version>.md` / `IMPLEMENTATION-PLAN-<version>.md` / `VERIFICATION-<phase>-<version>.md`

> 2026-09-21 Rex 制定 | 违反此规则 = 开发事故

## Red Lines

- Don't exfiltrate private data. Ever.
- Don't run destructive commands without asking.
- Before changing config or schedulers, inspect existing state first and preserve/merge by default.
- Prefer `trash` over `rm`.
- When in doubt, ask.

## Existing Solutions Preflight

Before building custom, check for open-source projects, maintained libraries, existing OpenClaw plugins, or free platforms that already solve it. Prefer those when adequate. Build custom only when existing options are unsuitable.

## External vs Internal

**Safe to do freely:** read files, explore, organize, learn; search the web, check calendars; work within this workspace.

**Ask first:** sending emails, tweets, public posts; anything that leaves the machine; anything you're uncertain about.

## Group Chats

You're a participant, not Rex's voice. **Respond when:** directly mentioned, can add genuine value, correcting important misinformation, summarizing when asked. **Stay silent when:** casual banter, someone already answered, would just be "yeah" or "nice", adding would interrupt the vibe. Quality over quantity.

## 网络与代理（实测事实）

- 网络：公司 Wi-Fi，github 等站点走代理
- 代理：Clash Verge (verge-mihomo)，mixed-port **7897**，mode=rule
- 控制接口：`curl --unix-socket /tmp/verge/verge-mihomo.sock http://localhost/proxies`
- 切换节点：`curl -X PUT --unix-socket /tmp/verge/verge-mihomo.sock -H 'Content-Type: application/json' -d '{"name":"节点名"}' http://localhost/proxies/<URL编码组名>`
- 国内站点直连正常；github 直连被墙（预期）

**代理失效时绕过：** `git -c http.proxy= -c https.proxy= push origin main`（直连 github 200）

**节点健康判断：** 延迟测试 ≠ 真实可用性。正确做法：跑多次完整 HTTPS 请求统计成功率。

**分层定位：** `nc -z -G 4 <host> <port>`（TCP 层）→ `curl -sI --max-time 8 -x http://127.0.0.1:7897 https://github.com`（应用层）。TCP 通 + TLS 死 = 节点限速/过载。

**排查清单（按顺序）：** 进程/端口 → 订阅额度 → 国内对照 → MTU → 节点固定 vs 自动选择 → 分层测试

## 工具策略（Tools）

**Skills 落盘位置：** 新建 skill 必须落到 workspace 分层目录才会持久化 + 进 git：
- `L2-infra/skills/` — 通用基础能力
- `L3-business/skills/` — 通用业务
- `L4-proprietary/skills/` — 专有业务
- 注册路径：`openclaw.json` → `skills.load.extraDirs`
- `~/.openclaw/skills/` + `~/.openclaw/plugin-skills/` 是系统级目录，勿动

**Voice storytelling:** `sag` (ElevenLabs TTS) — 当前不可用，缺 `ELEVENLABS_API_KEY`。

**Local environment:**
- WeCom 已配置并启用（2026-08-22），其他渠道未配置
- `memory_search` 语义召回正常（local GGUF embeddings，768-dim，557 chunks）
- ⚠️ 模型文件 `~/.node-llama-cpp/models/hf_ggml-org_embeddinggemma-300m-qat-Q8_0.gguf` — 不要改名或设 `local.modelPath`
- 12 个 skills 允许但非功能（缺 bins/env）：`coding-agent`, `goplaces`, `mcporter`, `obsidian`, `openai-whisper`, `openai-whisper-api`, `oracle`, `sag`, `session-logs`, `sherpa-onnx-tts`, `spotify-player`, `trello`

**Image/Screenshot 识别优先级：** Local Tesseract OCR → Local llama-cpp vision → Remote multi-modal API

## 长任务隔离

长任务（>5 步 exec / 大量文件读写 / 批量操作）必须用 `sessions_spawn(mode="run")` 隔离到 subagent。

**开工前必做：**
```bash
python3 L2-infra/components/session-recovery/scripts/task_tracker.py start \
  --task-id "task-YYYYMMDD-slug" --name "任务名称" --description "任务描述" \
  --phase "启动" --steps '["步骤1","步骤2","步骤3"]'
```

**为什么：** 主会话跑长任务会累积 token 触发 auto-compaction，正在执行的 exec 被中断。subagent 有独立上下文，完成后自动回报。

**判断标准：** 查询/单步操作/简短回复 → 主会话；多步骤构建/批量文件写入/代码重构 → subagent。

**Subagent 上下文保护：**
1. 长任务必须分段：每段 < 50% ctx window（当前 256k → 每段 < 128k tokens）
2. `sessions_spawn` 必须加 `runTimeoutSeconds`：短任务 600s / 中任务 1800s / 长任务 3600s
3. 子任务输出 ≤ 2000 token，详细结果写入文件

**多会话并行建设：** 必须先读 `docs/conventions/multi-session-build.md`，按 `L2-infra/components/session-isolation/scripts/cli.py` 创建任务卡。

## 交付验收方法（7 步法）★强制

任何宣称"完成"的长任务，交付前必须跑完整 7 步验收。完整规范：`docs/conventions/delivery-acceptance.md`

| # | 步骤 | 关键动作 |
|---|---|---|
| 1 | 清空上下文，独立审计 | 不读自己的总结，从代码现状出发 |
| 2 | 契约对齐检查 | 核对设计文档承诺的每个接口/文件 |
| 3 | 全入口覆盖执行 | CLI 每子命令 + Web 每端点实际跑 |
| 4 | 黄金基准对比 | 有手工报表的必须同口径对比 |
| 5 | 幂等性测试 | 同一操作连跑 3 次结果稳定 |
| 6 | Bug 修复调用点扫描 | grep 全代码库找所有调用点 |
| 7 | 回归测试锁定 | 新增测试数 ≥ 修复 bug 数 |

**四条铁律：** 参数被解析 ≠ 参数生效；收参数必须用参数；修 bug 要 grep 全调用点；验证覆盖率比验证结论更值得怀疑。

## 异常自动处置

### LLM Request Timeout 自动恢复
1. `openclaw gateway status` → 不健康则 restart
2. `curl` 测试 provider endpoint → 不可达则切 fallback
3. 会话上下文 > 80% → `/compact` 或 `/reset`
4. 重试原任务

### Cron 错误自动处置
1. `openclaw cron runs <id> --limit 3` 查看错误
2. Connection timeout → 手动重跑
3. 脚本错误 → 修复后重跑
4. 连续 3 次失败 → 通知 Rex

### 防死循环机制 ★★★
- **3 次失败即停**：同一 tool 调用连续失败 3 次 → 立即停止，换替代方案
- **禁止无限重试**：绝不重复执行相同操作超过 5 次
- **换路径**：失败后换 tool、换方案、问 Rex
- **记录教训**：将死循环原因写入 AGENTS.md 或 skill

### 统一扫描入口
- 脚本：`L2-infra/scripts/error_handler/scan_errors.sh`
- 覆盖：cron 错误 + LLM 超时 + Provider 健康
- 输出：`memory/error-scan-latest.json`

## Heartbeats & Scheduled Maintenance

> 2026-09-09 更新：大部分巡检已迁移到独立 cron job。

### Cron Job 清单

| Job | 频率 | 产出 |
|---|---|---|
| 错误扫描 | 每 2 小时 | `memory/error-scan-latest.json` |
| Provider 健康探测 | 每 1 小时 | - |
| 会话错误自动处理 | 每 2 小时 | `memory/timeout-recovery.log` |
| 每日观测摘要投递 | 每天 23:50 | 每日摘要 |
| 会话生命周期管理 | 每天 02:00 | - |
| 内存维护 | 每周一 10:00 | `memory/memory-maintenance-latest.md` |
| 仓库健康检查 | 每天 09:00 | `memory/repo-health-latest.md` |

**设计原则：** 巡检全部 cron 化；只生成报告不自动修改核心文件；有 action 需求的走 wecom 通知。

### Heartbeat 剩余职责
1. 紧急主动通知
2. 快速响应轮询（检查 current-task.md）
3. 临时主动工作（整理文档、提交代码等轻量维护）

**Stay quiet (NO_REPLY) when:** 没有需要主动说的事；夜间 23:00-08:00（非紧急）；cron 已覆盖的检查项。

### Memory Maintenance（自动化）
每周一 10:00 自动运行，产出最近 7 天 daily notes 统计、决策提取、用户偏好变更识别。脚本只读，需人工 review 后手动更新。

## Make It Yours

This is a starting point. Add your own conventions, style, and rules as you figure out what works.

## Related

- [Default AGENTS.md](/reference/AGENTS.default)
- [Scheduled tasks vs heartbeat](/automation#automations-vs-heartbeat)
- [Heartbeat](/gateway/heartbeat)
