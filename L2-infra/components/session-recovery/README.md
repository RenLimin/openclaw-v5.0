# session-recovery — 会话失败自动重试与断点记忆（v1.2 SQLite）

## 组件职责
1. `task_tracker.py`：会话级任务状态机（SQLite 隔离存储）
2. `check_and_retry.py`：检测会话失败 → 自动唤醒重试（上限 2 次）
3. `stall_detect.py`：running 但超时卡住识别

## task_tracker v1.2（2026-11-10）
存储从单一全局 `memory/current-task.md` 迁移到 **`memory/tasks.db`**（SQLite，
用户资产，OpenClaw 升级不触碰；仅 stdlib `sqlite3`）。

核心设计：
- 一行一任务，`(task_id, session_key)` 归属绑定；`update/complete/increment-fail`
  走**条件 UPDATE**，归属不匹配 rowcount=0 → exit 2 拒绝，绝不写入。
- 一会话一活跃任务（`ux_session_active` partial unique index）。
- `complete` 后仍写 `memory/task-history/*.md` 归档（保审计链 + lane_d 历史读取不变）。

## CLI
```bash
# 开始任务（--session-key 必填）
python3 scripts/task_tracker.py start --task-id T --name N --session-key S [--phase P --steps JSON] [--replace]

# 更新进度（校验归属）
python3 scripts/task_tracker.py update --task-id T --session-key S [--phase P] [--step-index I] [--progress TEXT]

# 失败计数
python3 scripts/task_tracker.py increment-fail --task-id T --session-key S [--reason R]

# 完成归档
python3 scripts/task_tracker.py complete --task-id T --session-key S [--result R]

# 查询（--session-key 指定会话；无 scope 时仅全局唯一 active 可用）
python3 scripts/task_tracker.py current [--session-key S] [--json]
python3 scripts/task_tracker.py list [--all] [--json]

# 一次性迁移 legacy
python3 scripts/task_tracker.py migrate-legacy [--apply]
```

环境变量（测试隔离）：`TASK_TRACKER_WORKSPACE` / `TASK_TRACKER_DB`。

## 下游适配（v1.2 同步）
- `system-governor lane_d_tasks.py`：从 `tasks.db` 读各会话 active 任务，逐任务 Finding。
- `check_and_retry.py`：按 `--session` 绑定的 active 任务处理，scoped 未命中回退全局唯一。
- `scan_errors.py`：遗留死命令 `save --current` 改为有效 `current --json`。

## 测试
- 单测：`tests/test_task_tracker.py`（26 用例）+ check_and_retry（34 用例）
- 真实路径集成：`tests/integration_task_tracker_v12.py`（AC1-AC7，subprocess 跑真实 CLI，24 用例）
