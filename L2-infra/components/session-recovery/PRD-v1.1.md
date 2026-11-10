# session-recovery / task_tracker — 产品需求变更 (PRD v1.1)

> 组件：session-recovery (L2)
> 版本：v1.1（变更自 v1.0，仅针对 task_tracker 任务存储与归属；check_and_retry 语义随契约适配）
> 日期：2026-11-10
> 状态：⏳ 待 Rex 评审
> 关联事故：2026-11-10 多会话并发信息污染（同日 21:00 活体复现）

## 1. 背景与问题

v1.0 把任务状态写在单一全局文件 `memory/current-task.md`。多会话（主线/governor、建行 dashboard、BDMS 会话等）并发 `start/update/complete` 时：

| # | 缺陷 | 后果 |
|---|---|---|
| P1 | 单一全局文件承载所有会话任务 | 并发 start/update 互相覆盖 |
| P2 | frontmatter `session_key` 始终为空 | 任务未绑定所属会话，无法判归属 |
| P3 | `update/complete` 不校验持有者 | A 会话可 complete/update B 会话任务，提前归档 + 写错 result |
| P4 | 归档同一 task_id 出现多条被污染记录 | 历史不可信 |

2026-11-10 21:00:36 现场：本会话 18:35 start 的 `task-20261110-task-tracker-concurrency`（phase=设计变更文档,step=0），被另一并行会话 update 覆盖为 phase=Phase1取数解析、step=6、进度为其自身内容，task_id/session_key 仍挂在本会话名下。证据见 `memory/2026-11-10.md` §21:00 与当前 `memory/current-task.md`。

## 2. 目标

1. 任务状态按 **task_id + session_key** 分文件存储，杜绝单文件并发覆盖。
2. `start` 强制写入并校验 session_key；`update / increment-fail / complete` 必须同时校验 task_id + session_key 归属，不匹配即拒绝、返回明确错误，**绝不写入**。
3. 提供：查当前会话当前任务、列出所有会话任务的能力。
4. 保持既有 CLI 语义（start/update/increment-fail/current/complete）向后兼容；`current-task.md` 作为兼容读路径保留只读派生视图（是否保留见 §6 决策点）。
5. 提供迁移工具：把旧 `current-task.md` 中仍有效记录迁入分文件；历史归档不自动改写。

## 3. 功能清单（v1.1 变更）

| # | 功能 | 优先级 | v1.0 | v1.1 |
|---|---|---|---|---|
| F1 | 任务分文件存储（tasks/active/<safe>.md，文件名编码 task_id+session_key） | P0 | ❌ | ✅ |
| F2 | start 强制非空 session_key（--session-key 或环境变量自动获取） | P0 | 可空 | 强制 |
| F3 | update/increment-fail/complete 归属校验（task_id+session_key 双因子） | P0 | ❌ | ✅ |
| F4 | 拒绝操作返回明确错误码 + stderr 消息，exit code≠0，不写盘 | P0 | ❌ | ✅ |
| F5 | `current` 默认按当前会话过滤；`--all` 列出所有会话任务 | P0 | 全局单任务 | 会话维度 |
| F6 | 原子写（临时文件+os.replace）+ 任务文件级 flock 串行化 | P0 | 裸 write | 原子+锁 |
| F7 | `migrate` 子命令：旧 current-task.md → 分文件（默认 dry-run） | P1 | — | 新增 |
| F8 | current-task.md 兼容视图（仅由 tracker 受控生成/更新） | P1 | 权威文件 | 派生只读 |
| F9 | 下游适配（check_and_retry、lane_d_tasks、scan_errors 调用点） | P0 | — | 跟随 |

## 4. 用户故事

- 作为任一会话，我 start 后任务只属于本会话；其他会话的任何写操作都不能改动我的任务。
- 作为会话，我 update/complete 时若 task_id 或 session_key 不匹配，得到「拒绝 + 原因」，而不是静默污染。
- 作为 Rex，我能一条命令看到「当前会话任务」和「所有会话的活跃任务」。
- 作为崩溃恢复流程，旧 current-task.md 里仍有效的任务能被安全迁移，不丢断点。

## 5. 验收标准

| 编号 | 标准 | 验证方式 |
|---|---|---|
| AC1 | 两个会话各自 start 不同任务，生成两个独立文件，互不覆盖 | 真实 CLI 两进程 |
| AC2 | start 不提供且无法自动获取 session_key → 拒绝，exit 2，无文件产生 | 真实 CLI |
| AC3 | A 会话对 B 会话任务执行 update/increment-fail/complete → 全部拒绝（exit 3），目标文件内容不变、不产生归档 | 真实 CLI |
| AC4 | 同 task_id 但不同 session_key → 视为不同任务，各自独立 | 真实 CLI |
| AC5 | N 个进程并发 update 同一任务（同归属）→ 全部成功、进度条目数= N、无丢失/撕裂 | 真实多进程 |
| AC6 | 并发不同会话任务 → 文件数正确、内容零串扰 | 真实多进程 |
| AC7 | `current`（按会话）只返回本会话；`current --all` 返回全部活跃任务 | 真实 CLI |
| AC8 | 断点恢复：start→kill→重新 current（同 session_key）能读到最新 phase/step/progress | 真实 CLI |
| AC9 | migrate dry-run 不落盘；--apply 后旧记录进入分文件，且默认不删除原文件直到确认 | 真实 CLI |
| AC10 | 全量测试（含既有回归）通过；测试用真实子进程/真实文件锁，不用桩替代路径 | pytest + subprocess |

## 6. 待 Rex 拍板的决策点

| # | 决策点 | 选项 | Jerry 建议 |
|---|---|---|---|
| D1 | session_key 自动获取来源 | (a) 仅 `--session-key`；(b) 新增环境变量（需 Gateway 支持，当前 exec 环境未注入，已核实）；(c) 二者结合：显式参数优先，否则读环境变量 | (c)，但 v1.1 先落 (a)+预留 (b) 读取位；无 key 即拒绝 |
| D2 | 是否保留 current-task.md | (a) 完全废弃，下游全改读分文件；(b) 保留为「主会话 agent:main:main」的受控兼容视图；(c) 保留但仅迁移期可读 | (b)：check_and_retry 仍以 agent:main:main 为巡检对象，改动最小 |
| D3 | 任务文件名安全编码 | (a) 双字段哈希；(b) 可读 slug + 短哈希；(c) 目录分层 | (b)：`<task_id-slug>__<session_hash8>.md`，可读且防碰撞 |
| D4 | 同一会话能否并存多个活跃任务 | (a) 一会话一活跃（start 新任务需先归档旧的）；(b) 可多个 | (a)，符合「当前任务」语义，start 时校验同会话旧任务 |
| D5 | 旧 current-task.md 当前被污染内容如何处置 | 见独立迁移方案 MIGRATION-PLAN | 不自动处理，按方案逐项确认 |
| D6 | 归档命名是否也带 session 维度 | (a) 沿用时间戳_task_id；(b) 增加 session_hash | (b)，杜绝同 id 跨会话归档混淆 |

## 7. 非目标（明确不做）

- 不在本任务中替任何具体业务会话伪造、推断或还原业务状态（含当前被污染的 current-task.md）。
- 不自动改写、清洗 `memory/task-history/` 历史归档；历史污染仅登记清单。
- 不改动 session-isolation 的 subagent 任务卡（tasks/in-progress/...）体系。
- 不引入数据库/服务端进程；仍为纯文件 + Python CLI。

## 8. 变更影响

| 受影响项 | 影响 | 处理 |
|---|---|---|
| `scripts/task_tracker.py` | 存储层与归属校验重写，CLI 保持 | 主改动 |
| `scripts/check_and_retry.py` | current 调用需按会话；get_current_task 传 session | 适配 |
| `system-governor/.../lane_d_tasks.py` | 盘点改为遍历 tasks/active | 适配（只读） |
| `scripts/error_handler/scan_errors.py` | `save --current` 子命令当前不存在（死调用） | 修正为有效命令或删除 |
| `LONG-TASK-SPEC.md` / `DESIGN.md` / README / OPERATIONS | 文档同步 | v1.1 评审通过后更新 |
| AGENTS.md §task_tracker 红线 | 标注已修复版本与校验契约 | 实现完成后更新 |
