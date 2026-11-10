# task_tracker 并发安全改造 — 详细设计 (DESIGN-DETAIL v1.1)

> 组件：session-recovery / scripts/task_tracker.py
> 版本：v1.1（存储层 + 归属校验 + 并发控制；CLI 语义向后兼容）
> 日期：2026-11-10
> 状态：⏳ 待 Rex 评审（关联 PRD-v1.1）
> 关联事故：2026-11-10 多会话并发信息污染（21:00 活体复现，见 PRD-v1.1 §1）

## 1. 设计目标

1. **分文件存储**：任务状态按 `task_id + session_key` 落盘，单文件不再被多会话共享。
2. **归属强校验**：start 强制写 session_key；update/increment-fail/complete 校验 `task_id + session_key` 双因子，不匹配即拒绝且不写盘。
3. **并发安全**：任务文件级 flock + 原子写，杜绝读改写竞争。
4. **查询能力**：`current` 按会话查当前任务；`current --all` 列所有会话活跃任务。
5. **兼容**：既有 CLI 命令语义不变；current-task.md 降级为受控兼容视图（仅主会话）。

## 2. 存储布局

```
memory/
├── current-task.md            # 兼容视图（仅 agent:main:main 活跃任务；由 tracker 受控刷新）
├── tasks/
│   └── active/
│       ├── <safe_task_id>__<session_hash8>.md   # 活跃任务，一任务一文件
│       └── ...
└── task-history/
    └── {YYYYMMDD-HHMMSS}_<safe_task_id>__<session_hash8>.md  # 归档（命名带 session 维度）
```

### 2.1 文件名安全编码

| 字段 | 规则 |
|---|---|
| `safe_task_id` | 非 `[A-Za-z0-9._-]` 字符替换为 `_` |
| `session_hash8` | `sha256(session_key.encode()).hexdigest()[:8]`（防文件名注入 + 防碰撞） |

同 `task_id` + 同 `session_key` → 同一文件（幂等）；同 `task_id` + 异 `session_key` → 不同文件（互不干扰）。

### 2.2 WORKSPACE 可配置化

- 新增 `--workspace` 参数 + 环境变量 `TASK_TRACKER_WORKSPACE`，默认 `/Users/bangcle/.openclaw/workspace`。
- 目的：测试以**真实子进程**跑 CLI 时注入 tmp 工作区（conftest 直接改模块常量在子进程内不生效，见 §7）。

## 3. 数据模型（frontmatter 契约）

```markdown
---
task_id: task-20261110-task-tracker-concurrency
name: 修复 task_tracker 多会话并发污染
session_key: agent:main:dashboard:85ebd218-4692-4ff9-adf1-32721eabe8f3   # 必填，v1.1 强制
session_label: dashboard-85ebd218                                        # 可选，可读标识
phase: 设计变更文档
step_index: 0
total_steps: 7
failure_count: 0
started_at: 2026-11-10T18:35:05
last_updated: 2026-11-10T18:35:05
archived_at: <仅归档文件>
archive_reason: <仅归档文件: completed|interrupted-by-new|rejected>
result: <仅归档文件>
---

任务描述

### 进度记录
- [2026-11-10T18:35:05] 任务启动: ...
```

约束：
- `task_id` 非空；`session_key` **非空**（start 阶段强制；迁移期 legacy 数据允许 `unknown-legacy` 占位，见 MIGRATION-PLAN §3）。
- `step_index`/`total_steps`/`failure_count` 整数化（沿用 v1.0 解析逻辑）。

## 4. 归属校验规则（核心）

### 4.1 start

| 条件 | 行为 |
|---|---|
| `--session-key` 为空 且 环境变量无值 | **拒绝**：stderr `❌ session_key 必填（--session-key 或 TASK_TRACKER_SESSION_KEY）`，exit 2，不产生任何文件 |
| 同一 session 已有活跃任务（含同 task_id 不同内容） | 先归档旧任务（`interrupted-by-new`，命名带其 session_hash），再建新文件 |
| 无冲突 | 创建分文件 + 原子写 |

### 4.2 update / increment-fail / complete（写操作三件套）

1. **定位**：按 `--session-key`（或 env）定位该会话的活跃任务文件。
   - 无活跃任务 → stderr `❌ 会话 <key> 没有进行中的任务`，exit 4，不写盘。
2. **双因子校验**：
   - `--task-id`（update/increment-fail 新增可选参数；complete 新增可选参数）若提供：与文件内 `task_id` 不一致 → **拒绝**，stderr `❌ 归属不匹配：任务 <file> 属于 task_id=<file.task_id>，请求 task_id=<args.task_id>`，exit 3，不写盘、不归档。
   - 文件内 `session_key` 与请求 `session_key` 不一致 → **拒绝**，同上 exit 3（理论上不会发生，因按 session 定位；防御性保留）。
3. **并发写**：`flock` 独占锁包裹「读 → 改 → 原子写」；写失败/锁超时（默认 10s）→ exit 5。
4. **complete 额外动作**：写入归档文件（命名带 session_hash）→ 删除活跃文件 → 若本会话是主会话，刷新 current-task.md 视图。

### 4.3 错误码契约

| exit | 含义 |
|---|---|
| 0 | 成功 |
| 2 | session_key 缺失（start） |
| 3 | 归属不匹配（task_id / session_key）—— 拒绝且零写入 |
| 4 | 该会话无活跃任务 |
| 5 | 锁超时 / 写盘失败 |

所有拒绝路径：stderr 明确错误 + **不产生任何文件写入**（含归档）。

## 5. current / current --all

```
task_tracker.py current [--json] [--session-key KEY] [--all]
```

| 场景 | 行为 |
|---|---|
| `--all` | 遍历 `tasks/active/*.md`，按 `last_updated` 倒序输出全部活跃任务（json: `{"active": true, "tasks": [...]}` / 文本列表） |
| `--session-key KEY` | 输出该会话活跃任务（无 → active:false） |
| 无参数（兼容回退） | 优先读 current-task.md 兼容视图（若存在且含 task_id）；同时若 tasks/active 恰有一个文件也列出；输出标注数据来源 |

JSON 输出字段沿用 v1.0（`active/task_id/name/.../progress_entries_total/progress_entries_recent`），`--all` 时每任务同构。

## 6. current-task.md 兼容视图（决策 D2 建议 (b)）

- **只读派生**：由 tracker 在写操作后受控刷新；外部不再直接写它。
- **刷新规则**：仅当写操作会话 == `agent:main:main`（主会话常量，`MAIN_SESSION_KEY` 可配置）时刷新为其活跃任务；其他会话的写操作不触碰该文件。
- **目的**：check_and_retry / lane_d_tasks / ADR-032 恢复流程对主会话的既有读取语义不破。
- 迁移期后如确认无依赖，可移除（决策 D2 待 Rex 拍板）。

## 7. 并发控制实现

```python
import fcntl, os, tempfile

def _locked_update(path, mutate):
    with open(path, "a+") as f:          # a+ 不截断，锁文件即目标文件
        fcntl.flock(f, fcntl.LOCK_EX)    # 阻塞式独占锁（可加超时：非阻塞循环 10s）
        data = _read_file(path)
        new = mutate(data)
        _atomic_write(path, new)         # tmp + os.replace
        fcntl.flock(f, fcntl.LOCK_UN)
```

- 读与写在同一锁内完成，避免「读 A 版本 → 改 → 写覆盖 B 版本」的 lost update。
- 原子写：`tempfile.NamedTemporaryFile(dir=同目录)` + `os.replace`，避免半截文件被并发读者看到。
- 跨平台注：fcntl 为 POSIX；本项目环境 macOS/Linux 均可用。

## 8. 下游适配（PRD F9）

| 调用方 | v1.0 行为 | v1.1 适配 |
|---|---|---|
| `check_and_retry.py` | `current --json` 读全局任务 | `current --json --session-key agent:main:main`；`increment-fail` 追加 `--session-key`；wake 消息不变 |
| `system-governor/.../lane_d_tasks.py` | 读 `memory/current-task.md` 单文件 | 改为遍历 `memory/tasks/active/*.md` 聚合 Finding；current-task.md 视图存在时合并去重（按 task_id+session_hash） |
| `scripts/error_handler/scan_errors.py` | `save --current`（子命令不存在，死调用） | 删除该行（或改为 `current --json --session-key <key>`，实现时按最小变更处理） |
| `LONG-TASK-SPEC.md` / `DESIGN.md` / README / OPERATIONS | 示例命令无 session-key | 文档同步：start/update/complete 示例补 `--session-key`；AGENTS.md 任务登记示例同步 |

## 9. 测试方案（真实操作路径，禁止单元桩替代）

### 9.1 测试基建

- `conftest.py` 扩展：fixture 构造 tmp 工作区（含 memory/tasks/active、memory/task-history），通过 **env `TASK_TRACKER_WORKSPACE` + subprocess 真实 CLI** 执行，断言 stdout/stderr/exit code/磁盘文件。
- 保留既有单元测试（解析/格式化），新增集成测试文件 `tests/test_task_tracker_concurrency.py`。

### 9.2 用例清单（映射 PRD AC1-AC10）

| # | 场景 | 操作路径 | 断言 |
|---|---|---|---|
| T1 | 多任务隔离 | 会话 A start ta；会话 B start tb（真实 CLI 两次调用） | 生成 2 个分文件；A 文件无 B 内容 |
| T2 | start 缺 session_key | `start --task-id x --name y`（无 key、无 env） | exit 2；stderr 含「session_key 必填」；无任何新文件 |
| T3 | 跨会话写拒绝 | A start ta → 以 B 的 key `update --task-id ta --phase X` | exit 3；stderr 含「归属不匹配」；ta 文件内容不变；无归档产生 |
| T4 | 同会话不同任务互不影响 | A start ta、A start tb（tb 触发 ta 归档 interrupted-by-new） | ta 进入归档（带 A 的 session_hash）；tb 活跃 |
| T5 | 同 task_id 异会话并存 | A start t9；B start t9 | 两个文件；`current --all` 显示 2 条 |
| T6 | 并发 update 同任务 | 同一会话 key，10 个 shell 子进程同时 `update --progress pN` | 全部 exit 0；最终进度条目数 = 1(启动) + 10；无内容撕裂 |
| T7 | 并发异任务 | 3 会话 × 各 3 子进程 update | 各文件条目数正确，零串扰 |
| T8 | 断点恢复 | start → 多轮 update → `current --json --session-key K` | phase/step/progress 与最新一致 |
| T9 | complete 校验 | B 对 A 任务 `complete`（无 task-id） | exit 3 拒绝；A 任务仍活跃 |
| T10 | complete 正常路径 | A 对自身任务 `complete --task-id ta --result r` | 归档生成（命名含 A session_hash）；活跃文件删除；主会话时刷新视图 |
| T11 | migrate | 构造 legacy current-task.md → `migrate --dry-run` → `--apply` | dry-run 零写入；apply 生成分文件（session_key=注入值或 unknown-legacy）；原文件默认保留 |
| T12 | 视图刷新 | 主会话 key 写操作后 | current-task.md 反映主会话任务；非主会话写操作后该文件不变 |

### 9.3 回归

- 既有 `tests/test_task_tracker.py` 全部通过（解析/格式化/归档字段兼容）。
- `tests/test_check_and_retry.py` 适配 session-key 参数后全绿。

## 10. 风险与回滚

| 风险 | 缓解 |
|---|---|
| 调用方漏传 session-key 被拒 | 拒绝信息给出修复提示；AGENTS.md/LONG-TASK-SPEC 示例同步；`--session-key` 允许 env 注入，减少调用改动 |
| flock 在极端并发下锁等待 | 非阻塞重试 + 10s 超时 exit 5，不无限挂起 |
| 迁移误搬污染内容 | MIGRATION-PLAN §2 特例：污染现场默认不自动迁移，冻结留证 |
| 回滚 | 旧版脚本保留为 `task_tracker_v1_0.py`（仅当 Rex 要求时）或 git revert；分文件方案不破坏旧归档，可读旧文件 |

## 11. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-11-10 | v1.1 初稿（分文件 + 归属校验 + flock/原子写 + 兼容视图 + 下游适配） |
