# AGENTS.md - Your Workspace

This folder is home. Treat it that way.

## 重复规则自动记录

用户强调过 **3 遍及以上** 的规则、机制，自动记录到本文件或 USER.md 对应章节，不再反复询问。

### 查找业界最佳实践要求

查找业界最佳实践必须覆盖：AI Agent官方文档、AI Agent对应社区的方案、GitHub/Clawhub等相关开源网站的方案，不能只找本地已有或用户提供的个别案例。
<!-- observed: 2026-10-10 | status: active -->

### 资产生命周期闭环铁律（调研-设计-测试/验收标准-建设-测试-验收）

所有系统资产（组件/skill）建设必须走完闭环，**且每一段都有机器门禁**：

| 阶段 | 要求 | 机器门禁 |
|---|---|---|
| 1. 调研 | 动手前先 `--query` 查能力注册表（避免重复建设），再基于 PRD 做业界最佳实践调研（AI Agent 官方文档/社区、GitHub、Clawhub） | pre-commit step 8（新增资产无设计文档即阻断） |
| 2. 设计 | PRD/DESIGN 必须包含：业界最佳实践引用、调研来源、方案取舍 | 同上 |
| 3. 测试/验收标准 | 先定验收标准（怎么算「做成」），再写测试 | — |
| 4. 建设 | 禁止跳过设计直接写代码 | — |
| 5. 测试 | 真实运行验证（非仅读代码） | pre-commit step 0/3 等 |
| 6. 验收 | 产出 `VERIFICATION*.md`（验收结论 + 证据）；完成 #1 闭环后登记入册 | `--lifecycle` 报告 |

- Always 新增组件/skill 目录 → 先写 DESIGN/PRD/SKILL.md，再写代码；否则 pre-commit step 8 阻断。
- Always 完成闭环后当日登记：registry.yaml 补条目（entry 可直接调用）→ `--coverage` 必须 100%。
- Never 把「规则只在 AGENTS.md」当达标——规则必须转为 pre-commit 门禁（可发现 + 前置门禁，而非靠自觉）。
<!-- observed: 2026-11-20 | status: active -->

## 子进程执行规范（防静默失控）
- Always 执行预计 >8s 的 exec 命令时设 `yieldMs>=60000`，让命令在前台跑完直接拿输出，避免超过默认 10s 被自动转后台、回执静默导致状态断层。
- 若命令已被转后台（session id 但无输出），立即用 `process(action=log)` 拉取该 session 日志确认，不盲猜、不重复跑。
- Never 对同一命令无确认地重复执行（防并行重复）；先 `process(action=list)` 或 `ps` 确认无残留。
<!-- observed: 2026-11-10 | status: active -->

## 定时任务环境降级红线（事故 2026-11-19）
- 现象：launchd `ai.openclaw.system-audit`（PATH 仅 `/usr/bin:/bin`）跑 `gen_asset_inventory.py`，8 处 `openclaw`/`node` 命令全部找不到 → 生成器**静默降级**成「⚠️ 数据源不可用」写入 `01-asset-inventory.md`；而 `--check` 比对的是**降级稿 vs 降级稿**，于是审计日志报「漂移归零」把降级内容当权威固化。
- 根因：生成器用 `subprocess.run(["openclaw", ...])` 裸命令名，依赖 PATH；定时任务环境 PATH 与交互 shell 不同。
- Always 定时任务/子进程调外部 CLI 时用**绝对路径兜底**（`shutil.which` + 候选绝对路径），禁止裸命令名依赖 PATH。
- Always 「数据源不可用」出现即视为**缺陷**，不得当作正常输出提交/登记；`--check` 的「无漂移」结论只在数据源全可用时才有证明力。
- 修复：`gen_asset_inventory.py` 加 `_resolve_bin()`/`_resolve_cmd()` 兜底（含 `.mjs` 用 node 显式执行）；回归测试 `L2-infra/components/config/tests/test_gen_asset_inventory.py`（最小 PATH 下 0 降级）。
- Always 会话任务收尾若新增/变更组件或资产，必须**显式**重生成资产清单并确认新能力入册（`python3 L2-infra/components/config/gen_asset_inventory.py`），不依赖 pre-commit 是否触发；`--check` 报「无漂移」前须先确认输出无「数据源不可用」降级行，否则该结论无效。
<!-- observed: 2026-11-19 | status: active -->

## LaunchAgent PATH 声明红线（事故 2026-11-25）
- 现象：`ai.openclaw.colima-check` / `ai.openclaw.daily-summary` 在 launchd 下 exit=1，日志 `FileNotFoundError: 'colima'/'openclaw'`；两任务实际**长期没在跑**而无人知晓。
- 根因一：launchd 裸环境 PATH 不含 `/opt/homebrew/bin`，plist 里 `source ~/.zshenv` 无效——**该文件只 export API key，根本没有 PATH**。
- 根因二：即使 PATH 正确，`~/.openclaw/tmp/agent-cli/openclaw` 这类临时路径也不可靠；必须用 `/opt/homebrew/bin/openclaw`。
- Always 每个 `ai.openclaw.*.plist` **必须显式声明** `EnvironmentVariables.PATH=/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin`（由 OpenClaw service-env wrapper 托管的 gateway 除外，其 `.env` 含 `export PATH=`）。
- Never 在 plist 里靠 `source ~/.zshenv` / `source ~/.zshrc` 获取 PATH——登录 shell 初始化在 launchd 下不保证生效。
- Always 脚本内调外部 CLI 一律绝对路径（`/opt/homebrew/bin/openclaw` 等），或 `shutil.which` + 候选绝对路径兜底。
- 门禁：`scheduler-guard/audit.py` 新增 plist 卫生检查（缺 PATH / 引用失效路径即报），且 `--json` 与报告模式均非零退出；回归测试 `tests/test_plist_hygiene.py`（7 用例）。
<!-- observed: 2026-11-25 | status: active -->

## 检测器口径单一事实源红线（事故 2026-11-25）
- 现象：健康检查把 5 个已有设计文档的组件（`DESIGN-OUTLINE-*` / `docs/DESIGN-*`）误报为缺失，还把 `.deprecated` 算进组件清单；而 pre-commit 门禁放行——两套口径不一致，监控长期说谎。
- 根因：`health_check.py` 自行实现「只查根级 `DESIGN.md`」，与 `capability_registry._asset_docs`（递归 docs/、前缀 DESIGN/PRD/SKILL、排除缓存/废弃）不同。
- Always 资产文档判定统一复用 `capability_registry._asset_docs()`，禁止各处自造匹配规则；判定逻辑改动必须同步两侧。
- Always 服务健康注册表的 URL/端口/fix 命令以**实测**为准，不得沿用旧稿；按需服务（如 llama.cpp embedding，idleStopMs 空闲即停）必须标 `lifecycle: on_demand` + `manager` 探针，判 standby 而非 failed。
- 门禁：`system-health-check` 的设计文档检查已改为调用 registry；`services.json` 已对齐实测端口（BDMS `:8000/api/health`）与运行时端口发现。
<!-- observed: 2026-11-25 | status: active -->

## task_tracker 并发竞态红线（事故 2026-11-10）
- task_tracker 用**单一全局** `memory/current-task.md`，多会话并行时会互相覆盖；`complete`/`update` **不校验 task_id**。
- Always 调 `complete` 前先读 `current-task.md` 的 `task_id`，确认是自己的任务；不一致（被并行线占用）→ **绝不 complete/update**，改用独立记录或等 Rex。
- Never 把自己的 result 写进非本人任务的归档。发现文件被多线污染时，停手汇报，不擅自还原其他会话状态。
- 待根本修复：tracker 按 task_id 分文件 + complete 强制 task_id 校验（单独立项）。
<!-- observed: 2026-11-10 | status: active -->

## git index 共享红线（事故 2026-11-10 22:11）
- git index 是**跨会话共享**的：别的会话 `git add` 过的文件会留在 index 里，本会话 `git add <自己的文件>` + 裸 `git commit` 会把**所有已 stage 内容**一起提交（曾把 CDI 会话的 SKILL/DECISION 捎带进 governor 的 commit）。
- Always commit 前先 `git diff --cached --name-only` 核对 staged 列表，只应有自己的文件。
- Always 若 index 里有外来 staged 文件：用 `git commit -- <自己的路径列表>`（只提交指定路径），**绝不裸 commit**；不擅自 unstage/改别人的文件。
- 已推送的混合 commit 不自动 rewrite（force-push 需 Rex 批准）；发现即汇报，记录而非掩盖。

## 共享 index 过期：`git status` 假删除（事故 2026-11-19）
- 现象：`git status` 把**已提交且工作树完好**的文件显示为 staged `D`（删除），`git diff --cached` 满屏 deletions。
- 根因：并行会话用**隔离临时 index**（`GIT_INDEX_FILE=…`）提交后**不回写共享 `.git/index`**；共享 index mtime 停在旧时刻（如 `b534f65` 16:15），而 HEAD 已前进数次。index 缺条目 → `git status` 把「HEAD 有、index 无」判为 staged 删除。
- Always 判定：先 `stat .git/index` 看 mtime 是否早于 `git log -1 --format=%ci`；再用**临时 index** 取真实状态（不碰共享 index）：
  ```bash
  TMPIDX=$(mktemp -u /tmp/idxprobe.XXXXXX)
  GIT_INDEX_FILE=$TMPIDX git read-tree HEAD
  GIT_INDEX_FILE=$TMPIDX git status --porcelain   # 这才是真实改动
  rm -f "$TMPIDX"
  ```
- Never 凭失真 `git status` 就去 `git reset --mixed`/`checkout`「修复」——那会动到并行会话的在途暂存。
- Always 真实改动以 `git diff HEAD --name-only` + 逐文件 `git show HEAD:<path> | diff - <path>` 为准。
- 修复（仅当确认无并行会话在途）：`git reset -q --mixed HEAD`（只重写 index，不动工作树）；否则等对方提交完。
<!-- observed: 2026-11-19 | status: active -->

## First Run

If `BOOTSTRAP.md` exists, follow it, figure out who you are, then delete it.

## Session Startup

Use runtime-provided startup context first. Do not manually reread startup files unless explicitly asked or missing something needed.

### 任务启动/接收检查清单（必做）

每次接收到新任务，必须按顺序执行以下检查：

### 1. 会话恢复自检

每次主会话启动后，先检查 `memory/current-task.md`：

```bash
python3 L2-infra/components/session-recovery/scripts/task_tracker.py current --json
```

| 条件 | 动作 |
|---|---|
| 无 current-task | 继续下一步 |
| failure_count = 0 | 等用户指令 |
| 1 ≤ failure_count < 2 | 自动从断点恢复，说明从哪里恢复，然后继续 |
| failure_count ≥ 2 | 停止重试，告知用户等你拍板 |

恢复策略：从 `progress_entries` 最新一条确定进度，跳过已完成步骤，从当前 step_index 继续。

### 2. 需求理解核对

- **复述需求**：用 1-2 句话复述用户的请求，确认理解正确
- **识别类型**：区分是新任务还是断点恢复、是查询还是开发、是文档修改还是代码变更
- **核对已有规范**：如果是已有规范的领域（开发、测试、验收等），先读对应规范文档
- 如果用户需求不清晰（不满足：明确类型 + 已有资产位置 + 期望结果），持续提问直至需求清晰，不要猜测着开始

### 已建成能力检索铁律 ★★★（2026-11-10，FB-20261110-01）

> Rex 批评：接合同/业务任务时，我先查本地库/文件，本地空就换数据源（BDMS），
> 而没有先查 memory + skill + 已建组件能力——导致把**已建成能力**当缺口，反复犯。
> 此规则与「品牌素材检索铁律」同源：**先查记忆与已建能力，再判定缺失**。

**能力注册表是权威索引（2026-11-20 全量固化）**：已建能力统一登记在
`L2-infra/components/config/capability-registry/registry.yaml`（**85 条目 = L2 41 + L3 15 + L4 29，其中 `skill-*` 28；每条含 `domain`/`authority`(authoritative|overlap|deprecated)；覆盖率 100%**，口径以 `--coverage` 实时输出为准），
同时渲染进 `docs/architecture/01-asset-inventory.md` §能力注册表。**先查表，再动手**。
> 路由用法：`--query <词>` 命中同域多条时非权威项自动降权并标 `[overlap→权威:<id>]`；只要权威入口加 `--strict`。
```bash
python3 L2-infra/components/config/capability-registry/capability_registry.py --query <关键词>
python3 L2-infra/components/config/capability-registry/capability_registry.py --coverage   # 全量覆盖率硬指标
```

- Always 接业务需求（合同/财务/DMS/PPT/ONES/OA 等）先 `memory_search` + 读对应 `SKILL.md`
  的**路由表与已建能力清单**，确认能力是否已存在，再决定是复用还是新建。
- Always 判断"能力缺失"前，先查能力注册表——**注册表已全量覆盖所有组件/skill**，
  查不到就是真没有；但仍需确认是否只是**未固化**（/tmp 临时脚本、散落脚本）。
- Always 判断"能力缺失"前，先确认是否只是**未固化**（/tmp 临时脚本、散落脚本、
  会话记忆里有使用记录）——未固化 = 沉淀修复，不是重新建设。
- Always 当天生产验证过的临时脚本/管线，**当日固化**进组件 + 更新 SKILL.md + 补注册表条目，不留 /tmp 资产。
- Always 新建组件/skill 目录 → **必须**同日补 registry.yaml 条目，否则 pre-commit step 6 阻断。
- Always 新脚本命名命中重复家族（OA/ONES 导出、登录、诊断类）时，pre-commit step 5 会阻断并指出权威入口；
  确需新建 → 先补 registry.yaml 条目（含 entry/notes），或登记 allow 并写明理由。
- 合同正文权威来源 = OA（`contractctl oa-fetch`/`review --oa-billid`）；BDMS/底稿摘要
  只作财务/确收视角的补充，**禁止**作为合同条款结论的替代来源。 <!-- observed: 2026-11-10 | status: active -->

### 3. 记忆/文档检索（三层，缺一不可）

**第一层：知识库（必须先搜）**
- 涉及任何已有能力/经验/方案：先搜知识库
  ```bash
  python3 L2-infra/components/knowledge-base/kb_index.py --query <关键词>
  ```
- 涉及 ONES/合同/财务/DMS/PPT 等已有系统：先查对应 skill 和知识库条目
- **原则：能复用的不重造，已有经验的不踩同坑**

**第二层：memory / SKILL**
- 涉及已有决策、偏好、历史记录：`memory_search` 检索相关记忆
- 涉及已有技能领域：读对应 `SKILL.md`

> **品牌/官方素材检索铁律 ★★★（2026-11-09，FB-20261109-01）：**
> - 用户**当场提供的路径 / 凭据 / 边界 / 命名口径**，必须**当回合**写入 `USER.md`（Always 指令 + observed 元数据），不得只留在会话或 `dreaming` 语料。
> - 凡涉及 Bangcle 品牌素材（PPT/Logo/模板/图标/字体/色板），检索范围**必须**覆盖 `/Users/bangcle/Bangcle Workspace/00. Bangcle Manual/02. Bangcle Template/`，不得只搜 workspace。
> - 已知信息不得反向反复询问；压缩恢复后先查 USER.md + 该品牌目录再决定是否需要用户补充。违反 = 重复询问事故。

**第三层：代码/文档**
- 涉及已有文档规范：先读对应文档，确认规则
- 涉及代码文件：先读文件内容，再开始修改

### 4. 任务登记

**重要任务必须登记：** 预计 > 5 步 exec / 批量文件操作 / 长构建的任务，开工前先 `task_tracker start`。

### 完成检查后再开始

只有完成以上 4 步检查，才能开始执行任务。

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

**测试规范：** Web/安全功能验收必须用真实 HTTP；禁止用 FastAPI TestClient 测试网络安全/Cookie/访问控制；所有 E2E 自测务必使用真实的模拟人工操作的方式进行；E2E 测试必须覆盖真实用户操作路径；后端 API 应同时兼容多种输入格式。 <!-- observed: 2026-10-07 | status: active -->

**PPT 字体与布局校验铁律：** 生成 PPT 一律使用目标机确定已安装的字体（Windows/Office 环境优先微软雅黑、宋体），禁止假设「思源黑体/Source Han」等用户未声明安装的字体；布局是否溢出不得只看渲染预览（预览可能用替代字体造成假象），必须用真实字体的字宽（fontTools 读 hmtx）机器校验折行与碰撞。 <!-- observed: 2026-11-09 | status: active -->

**进度条铁律：** 所有响应时间超过 10s 的用户操作，必须展示实时进度条（分步进度 + 当前步骤说明），禁止让用户面对空白页面等待。后端用 job 表异步 + 前端轮询模式实现。 <!-- observed: 2026-10-21 | status: active -->

**文档命名：** `DESIGN-OUTLINE-<topic>-<version>.md` / `DESIGN-DETAIL-<module>-<version>.md` / `IMPLEMENTATION-PLAN-<version>.md` / `VERIFICATION-<phase>-<version>.md`

> 2026-09-21 Rex 制定 | 违反此规则 = 开发事故

## Red Lines

- Don't exfiltrate private data. Ever.
- **NEVER close user-manual-opened browser sessions/tabs without explicit user approval.** Before closing, ask first and wait for approval.
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

## GitHub 凭据链路（事故 2026-11-23，一次做对）

- **SSOT**：`~/.openclaw/secrets/github.token`（`chmod 600`、**无尾换行**）；派生目标 `~/.config/gh/hosts.yml`（`chmod 600`）。
- **同步命令**：`python3 L2-infra/components/credentials/github_credential_sync.py`（幂等，写 hosts.yml + 自检）。
- **换 token 必做 3 步**（缺一即翻车）：
  1. 写 SSOT → `printf %s '<token>' > ~/.openclaw/secrets/github.token && chmod 600 …`
  2. 跑同步脚本（更新 gh hosts.yml）
  3. **清 keychain 旧条目**：`printf 'protocol=https\nhost=github.com\n\n' | git credential-osxkeychain erase`
     → 否则 `git credential fill` 仍返回旧 token，push 照挂（本次实测：SSOT 已新、push 仍用旧 `gho_`）。
- **验证口径（不打印 token）**：`git credential fill` 取 password → 打 `x-oauth-scopes`；含 `workflow` 才允许推 `.github/workflows/*` 改动。
- **device flow 授权（`gh auth refresh -s workflow`）只能由 Rex 在终端完成**：助手是 headless，等不到浏览器确认。**最多发起 1 次**并把一次性码交 Rex，禁止反复发起（本次连发 7 次全超时 = 事故）。
- **token 传递红线**：**禁止**把 token 走剪贴板（`pbpaste` 会被不定时清空，实测丢 2 次）或聊天正文；只走 Rex 本机终端命令字符串。
- **push 被拒原文**：`refusing to allow an OAuth App to create or update workflow … without workflow scope` → 根因恒为 token 缺 `workflow` scope，非网络问题。

## 工具策略（Tools）

**Skills 落盘位置：** 新建 skill 必须落到 workspace 分层目录才会持久化 + 进 git：
- `L2-infra/skills/` — 通用基础能力
- `L3-business/skills/` — 通用业务
- `L4-proprietary/skills/` — 专有业务
- 注册路径：`openclaw.json` → `skills.load.extraDirs`
- `~/.openclaw/skills/` + `~/.openclaw/plugin-skills/` 是系统级目录，勿动
- ⚠️ **根 `skills/`（沙箱内）是 OpenClaw 同步托管目录**（受 `.openclaw-sync.json` 管理），手动新建的技能会被周期同步清空。新建 skill 一律写入上面三个分层目录，写后即校验存在性。 <!-- observed: 2026-10-27 | status: active -->

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

**会话隔离铁律 ★★★（2026-11-03，FB-20261103-03）：**
- ❌ 禁止用 `sessions_send` 把用户消息/旁路排查请求转发给 pinned、dashboard 或任何正在执行任务的 live 会话
- ✅ 旁路排查一律 `sessions_spawn(mode="run", context="isolated")` 一次性子会话，用完即弃
- ✅ inter-session 回执只提取结论，**禁止引用对方任务的上下文/术语**写进给用户的回复
- ✅ 压缩恢复后先核对当前会话任务身份（任务卡/首条用户消息），再继续输出
- ⚠️ 技术护栏已上线：`session-boundary-guard` 插件（ADR-202611-036）拦截 `sessions_send`/`sessions_spawn(visible)` 指向 `dashboard:*` 的调用（approve 弹批准 / block 硬拒绝），审计在 `~/.openclaw/state/session-boundary-guard.jsonl`；即使越过行为规则也调不通
- 违反 = 串台事故，必须按 delivery-quality 记账

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

### 既有组件增量扩展的完成检查 ★（2026-11-03，FB-20261103-04）

在**已交付组件上加新能力**时，"代码跑通+OPERATIONS更新"**不算完成**，还必须逐项落实：

| # | 检查项 | 动作 |
|---|---|---|
| 1 | 技能固化 | 对应专家/组件的分层 SKILL（`L2/L3/L4` 分层目录）加能力描述与路由 |
| 2 | 资产清单 | frontmatter 改后由 pre-commit 自动重生成 `01-asset-inventory.md`，确认新能力进清单 |
| 3 | 文档版本对齐 | PRD/设计/计划/验收随能力**升版**（增量文档如 `*-<topic>-vX.Y.md`），旧版加变更指针、不回改正文 |
| 4 | README/scripts | 组件 README 的脚本清单与用法同步 |

**红线：** 禁止把建设后的能力回改进历史版本正文冒充当初设计；用新版本/变更指针并存，保审计链。


## 交付质量反馈闭环 ★★★（2026-10-30，ADR-035 §4）

**Rex 对交付结果提出问题/纠正/质疑时，默认（无需提醒）把每条反馈记入错误库：**

```bash
python3 L2-infra/components/delivery-quality/record.py \
  --domain project|contract|product|cross|other \
  --dimension data_fidelity|calculation_logic|data_completeness|missing_risk_analysis|missing_context|best_practice_gap|sourcing|format_presentation|other \
  --severity high|medium|low --target "<对象>" --finding "<问题>" \
  --root-cause "<初判根因>" --corrective-action "<已纠正动作>" --status corrected
```

- 当场已纠正的记 `--status corrected`；待处理留 `open`。
- 一条反馈一条记录，不要合并；finding 写问题本身，不贴敏感数据。
- **每次确认反馈（record 记录）后立即自动跑 review**（事件驱动，record.py 内置触发，无 cron）；review 做聚类/复发/高危单次提示。**复发≥2 或 high 级问题，review 报告提示后由 Rex 拍板**：收紧 P2 契约 + checker、加黄金 fixture、或沉淀 KB。助手不擅自改核心契约文件。
- 完整规范：`L2-infra/components/delivery-quality/README.md` + `SCHEMA.md`。


## 异常自动处置

### Gateway 重启安全铁律 ★★★（2026-10-27）

- **所有 agent / 脚本主动发起的重启，必须走**
  `L2-infra/components/gateway-safety/scripts/safe_restart.sh`（它先跑 pre-restart guard）。
  ❌ 禁止裸调 `openclaw gateway restart`——会绕过 guard、可能打断进行中的压缩/关键工作。
- **Guard 判据**：`~/.openclaw/state/compaction-state.json`，由 `compaction-guard` hook
  （`hooks/compaction-guard/`，订阅 `session:compact:before/after`）维护。`running` 标记超 6 分钟视为 stale。
- **config-patch 触发的内部自动重启拦不住**（OpenClaw 无外部否决点；in-process hook 只能观察、无法 cancel）。
  对策：改 config 前手动跑 guard；能用热加载（如 compaction 设置）就不要硬重启。
- 事故记录：20:15/20:54 多次 compaction 180s 超时；21:15 扫描器把一次超时重复计数 5 次并裸调 restart 自杀式重启。已修：timeoutSeconds=300 + 按分钟去重 + 重启走 guard。

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

### 上下文过大处理流程
当提示 `⚠️ Context is too large and auto-compaction could not recover this turn`:
- 第一步：尝试 `/compact` — 让 AI Agent 原生压缩上下文，保留必要对话
- 第二步：如果 `/compact` 后仍然超出阈值，尝试 `/reset` — 清理会话内部状态，但保留 transcript 历史
- 第三步：如果 `/reset` 后仍然超出，直接执行 `/new` 启动全新干净会话，工作进度不会丢失
- 自动压缩失效的根本原因：大段注入的元数据被保留策略保留，累积后仍超过阈值
- 新会话会重新加载必要上下文，token 回到安全水位

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

## 资产检索前置铁律 ★★★（2026-11-10，FB-20261110-02）

> Rex 批评：我每次先自己造，等他提示才转向复用已有资产。这是元能力缺陷。

- Always 开工第一步：**穷尽检索已有资产**（memory_search + 知识库 + `find`/`grep` 全仓 + 对应 SKILL.md），
  把「复用既有组件/模板/脚本」当**默认动作**，证明不可复用后才新建。
- Never 未盘点就先写自实现（auth/client/取数器/渲染器/PPT 引擎等）。
- Always 新建任何模块前，先自问：这个能力仓库里是否已存在？是否有 L2/L3/L4 组件或 skill 已提供？
- 检索结果（找到了什么、为何不可直接复用）要在动手前能一句话说清。
<!-- observed: 2026-11-10 | status: active -->

## task_tracker v1.2 已根治（2026-11-10，FB-20261110-03 修复完成）
- 存储已迁移 `memory/tasks.db`（SQLite，按 task_id+session_key 隔离，条件 UPDATE 归属强校验）；
  单文件 `memory/current-task.md` 已停用（改名 current-task.legacy.bak.md 保留证据）。
- Always 调 task_tracker 命令：start 必带 `--session-key`；update/complete/increment-fail 必带 `--task-id` + `--session-key`；归属不匹配将 exit 2 拒绝。
- 跨会话巡检（lane_d / check_and_retry）已改为按 session 维度读 `tasks.db`，不再读全局单文件。
<!-- observed: 2026-11-10 | status: active -->

## pre-commit hook auto-add 也是跨会话污染源 + 隔离 index 提交法（2026-11-10）
- 实证（非推测）：`git commit -- <pathspec>` **挡不住 pre-commit hook 内部的 `git add`**；
  hook 强 `git add` 的文件（如它自动重生的 `docs/architecture/01-asset-inventory.md`、
  `docs/knowledge-base/INDEX.md`）照样进 commit。别的会话留下的相关未提交差异会被 hook
  强行带入下一个任何人的提交 → 第三类跨会话污染（前两类：全局 current-task.md、共享 index）。
- Always 需严格只提交本任务内容、且共享 index/hook 状态不可信时，用**隔离临时 index**：
  ```bash
  BASE=<最后干净点>; TMPIDX=$(mktemp -t cleanindex).idx
  GIT_INDEX_FILE=$TMPIDX git read-tree "$BASE"
  GIT_INDEX_FILE=$TMPIDX git add -- <只列自己的路径>
  python3 L2-infra/components/config/secret-scan/secret_scan.py   # 手动补安全门禁
  TREE=$(GIT_INDEX_FILE=$TMPIDX git write-tree)
  NEW=$(git commit-tree "$TREE" -p "$BASE" -m "<msg>")
  git update-ref refs/heads/main "$NEW" "<old-main>"   # old-value 守卫
  git read-tree "$NEW"                                 # 同步共享 index，不触 working tree
  ```
  全程不碰共享 index、不跑会 auto-add 的 hook；secret scan 手动补，门禁不丢。
- Never 因 hook 是「系统托管文件」就默认把它 auto-add 的内容当本任务内容——提交后必用
  `git show --stat HEAD` 核对实际文件清单（`diff --cached` 在临时 index 口径下可能误导）。
<!-- observed: 2026-11-10 | status: active -->
- Always 隔离 index 提交时**逐条显式列出路径**，禁止 `git add -- $FILES` 变量展开：**zsh 不做变量分词**，会把整串当成单个 pathspec → 静默 `git add` 失败、`commit-tree` 产出**空提交**（事故 2026-11-18：`b0c3512` 空提交，幸未推送）。提交后必查 `git show --stat HEAD` 非空。
- Always `git read-tree "$NEW"` 同步共享 index 前**必须先 `unset GIT_INDEX_FILE`**，否则只更新临时 index，共享 index 落后一个提交 → 工作区显示假 `D`/`MM`（磁盘文件完好，勿 `checkout` 还原）。
<!-- observed: 2026-11-18 | status: active -->

## 统一安全提交规则（2026-11-25 owner 指示重立）

**权威工具**：`L2-infra/components/config/safe_commit.py`（隔离临时 index + plumbing，内置门禁预检）。

- Always 本仓（`~/.openclaw/workspace`）提交一律走该工具：`--paths <逐条显式列出>`。
- Never 裸 `git commit`；Never `git add -- $FILES`（zsh 不对无引号变量分词）；Never 依赖共享 `.git/index`。
- Always 一个逻辑变更 = 一个 commit，提交信息用 Conventional Commits（`docs/conventions/commit-and-config.md` §1）；
  消息较长时写 `--message-file`，避免 shell 转义。
- Always 提交后核对 `git show --stat` **非空且清单与预期一致**（工具已内建对账，不一致即报错）。
- Always 新增/变更资产或组件后，重生成 `docs/architecture/01-asset-inventory.md` 并过 `--check`，
  与 registry 改动同批提交（工具 `--skip-preflight` 仅限明确知情时使用）。
- Pre-flight 含：明文凭据扫描 + registry 自校验（entry 路径存在性）。二者不过则禁止提交。
- push 由 owner 单独决定；`pre-push` hook 负责 GitHub 凭据链路门禁（不因本次提交而自动推送）。

**跨机仓库口径**：仅代提交 owner 自有仓库（如 `RenLimin/openclaw-v5.0`）；
第三方上游 fork（CosyVoice / rvc / facefusion 等）不代提交其 `.venv/`、`assets/` 等运行产物；
备份仓（`~/backups/openclaw-auto`、`~/openclaw-backup-*`）与 sandbox 副本不做提交流程。
<!-- observed: 2026-11-25 | status: active -->

## 会话清理红线（事故 2026-11-11，FB：未归档空闲会话被批量剪枝）
- **手动归档的唯一权威信号 = `archivedAt` 非空**（通常伴 `archiveReason=manual`/`stale-dashboard`）。
  `status=done/failed` 只是「一轮跑完待输入」的**正常空闲态，绝不是可清除信号**。
- **真凶**：内置 `session.maintenance` 默认 `mode=enforce` + 历史命令
  `openclaw sessions cleanup --enforce --all-agents`，会按年龄自动剪枝**未归档**会话。
  合法模式仅 `enforce|warn`（无 report/off）；已永久改为 **`warn`**（只警告、不自动剪枝，源码
  `if (maintenance.mode !== "enforce") return`）。
- Always 任何会话清理脚本：未归档（`archivedAt` 为空）一律不删，只删显式归档项。
- launchd 跑 CLI 脚本必须先解析 `openclaw` 绝对路径（`shutil.which` 兜底），否则 PATH 缺失静默崩溃。
- OpenClaw 无官方 undelete：恢复 = 从删除前快照把 `session_nodes` + transcript 等 10 张
  实体表精确合并回活库（不整库还原），新行 `entry_valid=0` 需经 canonical 校验后置 1。
<!-- observed: 2026-11-11 | status: active -->

## stale 误杀根因与长任务纪律（事故 2026-11-17，FB-20261118-01）

**事故**：11-17 两次 reply run 被判 `Reply operation expired as stale` 强杀，最长一次空转 2h10m53s。

**根因链（实证，非推测）：**
1. `recordActivity()` 只在**工具开始/工具结果/事件**触发，**工具执行期间不记进度**；
   `RUN_STALE_TAKEOVER_MS=6e5`(10min)、`BLOCKED_TOOL_CALL_ABORT_FLOOR_MS=9e5`(15min)。
   → 一个长命令跑 2h，`lastActivityAtMs` 停在 2h 前 → 必判 stale。
2. 叠加会话**上下文溢出**（242572 vs 预算 242144），且恢复链全断
   （`compactionAttempts=0`、`toolResultReducibleChars=0`）→ 模型回合 precheck 必败，
   **不可能推进** = 空转本质。
3. 环境共犯（独立隐患）：macOS Clamshell Sleep 全天 55 次
   `host timing gap detected: process was frozen ~Xms`，冻结期同样不更新活动时间 → 人为制造 stale 误判。

**纪律（Always）：**
- Never 在**已溢出或压力 critical** 的会话里起任何长任务。先 `/reset`/拆会话，再干活。
- Always 长 pytest/构建：**分块**（每块 < 6min）+ 落盘 `/tmp/*.log` + 每块有明确结论；
  禁止单块整跑（11-17 整跑被回收 5 次，全是无用重跑）。
- Always 长任务先 `task_tracker start` + 每块后 `update`（phase/step-index/progress），
  **让用户随时能看到状态**；禁止"凭空跑而不自知"。
- Always 判活以 `ps`/落盘日志为准；上下文里的 "Active exec sessions: none" 快照**不可信**（11-18 四次误报）。
- 收到「继续」时先 `process(action=list)` + `ps` + 读落盘日志核对，**不盲目重跑非幂等命令**。

**可选缓解（需 Rex 拍板）：**
- ~~`diagnostics.stuckSessionAbortMs` / `stuckSessionWarnMs` 调大阈值~~ ❌ **2026-11-18 查证作废**：该配置键不存在。
  - `RUN_STALE_TAKEOVER_MS=6e5` 是 `dist/diagnostic-run-activity-*.mjs` 的**硬编码常量**，无 env/配置覆盖。
  - `stuckSessionAbortMs` 仅存在于 QA 诊断模块（env `QA_DIAGNOSTIC_STUCK_SESSION_ABORT_MS`，且需 `OPENCLAW_QA_PARENT_PID` 存在才生效），**非生产可用**。
  - → **阈值不可调**；唯一可靠缓解 = 本节「纪律」+ 下方电源项。
- 接电源 + `disablesleep` 消除睡眠冻结（治本环境项）。
<!-- observed: 2026-11-18 | status: active -->

## skill-sync 镜像红线（事故 2026-11-18，FB：sandbox skills 被同步删除）

**现象**：sandbox `skills/ones-browser-export/` 下 `scripts/oa_workflow_ones.py`、
`references/oa-workflow-fields.md` 变成 `D`（工作树删除），但 HEAD `425599f` 里仍在。

**根因（实证）**：sandbox 的 `skills/` 是 OpenClaw `workspace-skill-sync` **单向镜像**，
**不是** git 工作树：
- 源 = `L2-infra/skills` + `L3-business/skills` + `L4-proprietary/skills`（`openclaw.json` → `skills.load.extraDirs`）
- 目标 = `<sandbox>/skills`，`dist/workspace-skill-sync.runtime-*.mjs` → `syncWorkspaceSkills()`
- 逻辑：比对 `skills/.openclaw-sync.json` 的 `skillsVersion`/`skillRootsFingerprint` → 不符即
  **先删目标目录**（`fsp.rm(childPath,{recursive:true})`）**再 `fsp.cp` 权威源**；
  `shouldSyncSkillPath` 只排除 `.git`/`node_modules`，**放行 scripts/references**。
- 触发点：任意 agent 会话启动/同步时（日志 `[skills] Skipping invalid skill` 同一时刻可见）。

**结论**：只提交/只落在 sandbox 的 skill 文件 = **必然丢失**；权威源没有 = 下次同步就删。
`git log`/`reflog` 查不到删除（删除不产生 git 提交），只能靠源-目标比对与同步源码定位。

**纪律（Always）：**
- Always 新增/修改 skill 内容，**先写权威源**（`L4-proprietary/skills/<name>/…`），再同步/使用；
  sandbox `skills/` 只读，**禁止**当作编辑目标。
- Always 提交前确认主仓（`/Users/bangcle/.openclaw/workspace`）权威源已含该文件；
  提交后核对 `git show --stat HEAD` 实际清单。
- 镜像已回拷权威源后，sandbox 里同名文件是**副本**；发现 `D`/`M` 不要 `git checkout` 乱还原，
  先比对权威源与 sandbox 内容，再以权威源为准。
- 主仓 hook（`pre-commit`）会 auto-add，**严格只提交本任务内容仍须用隔离临时 index**
  （`GIT_INDEX_FILE=$TMPIDX git read-tree/write-tree/commit-tree` + `update-ref` 守卫）。
<!-- observed: 2026-11-18 | status: active -->

## 已登录客户端只读红线（gateway-owner 2026-11-24 明令，最高优先级）

> 通过本机已登录的**企业微信 / 微信**（及同类 IM 客户端）做 AX/GUI/自动化时，
> **严格只读不写**。这是 owner 当面下的硬红线。

- **Never** 通过 AX/模拟输入等任何方式向企微/微信**发送消息**或触发发送（回车、点发送按钮、`AXUIElementPerformAction`）。
- **Never** 合成鼠标点击/键盘事件（`CGEvent`/`CGEventSource`/`.post(tap:)`），
  也不得 `AXUIElementSetAttributeValue` 给输入框写值、不得模拟键入/粘贴/切换会话/开关任何 UI。
- **Always** 只允许 `AXUIElementCopyAttributeValue` 系列**只读 Get**；切会话由**人工手动**操作，程序不得代点。
- 唯一允许的网络出口（如 webhook 导出到**自有**端点）默认必须关闭（`webhook_url=null`），且方向只能是「读出」，绝不是向 IM 写入。
- 机器门禁：`L2-infra/components/wecom-ax-collector/tests/test_02_readonly_guard.py`
  静态扫描引擎源码，出现任何点击/键盘/设值/PerformAction API 即测试失败。
  新增/修改该引擎必须保持此守卫通过；例外须 owner 书面授权，且不得放宽默认。
- 适用范围：企业微信、微信，以及任何用 owner 真实身份登录的 IM/社交客户端。
<!-- observed: 2026-11-24 | status: active -->
