# DESIGN-DETAIL task_tracker v1.2 — SQLite 隔离存储

> 状态：Rex 2026-11-10 22:08 拍板「按推荐方案 B 执行」。
> 取代 v1.1 的「分文件+flock」方向；不删除历史文档，仅以本文件 + 变更指针并存，保审计链。
> 工程范式：coleifer/huey SqliteStorage（WAL + busy_timeout + 条件 UPDATE + 复合主键 + lease）。

## 1. 核心约束
- 数据库文件 = 用户资产：`memory/tasks.db`（随 workspace，**OpenClaw 升级不触碰**）。
- 仅用 Python stdlib：`sqlite3 / json / pathlib / argparse`；不 import、不改 Gateway 内部库。
- CLI 既有命令（start/update/increment-fail/complete/current）语义向后兼容；新增 list。

## 2. 存储模型（memory/tasks.db）
```sql
PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000; PRAGMA user_version=1;

CREATE TABLE tasks (
  task_id        TEXT PRIMARY KEY,
  name           TEXT NOT NULL,
  session_key    TEXT NOT NULL,          -- 归属/隔离键
  description    TEXT NOT NULL DEFAULT '',
  phase          TEXT NOT NULL DEFAULT '',
  step_index     INTEGER NOT NULL DEFAULT 0,
  total_steps    INTEGER NOT NULL DEFAULT 0,
  failure_count  INTEGER NOT NULL DEFAULT 0,
  status         TEXT NOT NULL DEFAULT 'active', -- active|done|interrupted
  result         TEXT NOT NULL DEFAULT '',
  entries_json   TEXT NOT NULL DEFAULT '[]',    -- 进度条目
  started_at     TEXT NOT NULL,
  last_updated   TEXT NOT NULL
);
CREATE INDEX idx_tasks_session ON tasks(session_key);
-- 一会话一活跃任务（对齐 OpenAI Assistants 单活跃 Run）
CREATE UNIQUE INDEX ux_session_active ON tasks(session_key)
  WHERE status='active';
```

## 3. 归属与并发（根治点）
- `start`：`--session-key` 必填（缺失 exit 2）。该会话已有 active 异 task_id → 默认 exit 3 拒绝；
  `--replace` 才把旧任务置 interrupted 并写 md 归档（archive_reason=interrupted-by-new）。
- `update / increment-fail / complete`：强制 `--task-id` + `--session-key`，用条件 UPDATE：
```sql
UPDATE tasks SET phase=?, step_index=?, entries_json=?, last_updated=?
 WHERE task_id=? AND session_key=? AND status='active';   -- rowcount=0 → exit 2 拒绝，绝不写入
```
- complete：条件更新 status='done'（rowcount=0 拒绝），同事务后写 task-history/*.md（保审计链 + lane_d 历史读取不变）。
- 所有写操作短事务；WAL + busy_timeout 由数据库层串行化，杜绝跨会话覆盖。

## 4. 读 API
- `current --session-key K --json`：该会话 active 任务（canonical）。
  不带 scope：仅当全局恰好 1 个 active 时返回（兼容旧巡检），否则返回 active=false + scope_needed=true。
- `list [--all] --json`：列出全部 active（或含历史）任务，供 lane_d / check_and_retry 跨会话巡检。

## 5. 下游适配
- lane_d_tasks.py：current_task 从「读全局 md」改为 `task_tracker list --json`，逐 active 任务一条 Finding；
  历史归档读取（task-history/*.md）与其余逻辑不变。
- check_and_retry.py：current/list/increment-fail/complete 一律带 task_id+session_key；
  按 `--session` 绑定的 active 任务处理；找不到绑定时，仅当全局唯一 active 才沿用旧行为。
- scan_errors.py:1162 死命令 `save --current`（本不存在、stderr 被吞）改为有效 no-op `current --json`。

## 6. 迁移（一次性，migrate-legacy）
- 读取 memory/current-task.md，若 task_id+session_key 完整则导入为 active（身份正确；污染字段不臆造）；
- 原文件改名 memory/current-task.legacy.bak.md 保留（不删除、不伪造其他会话状态）。
- task-history/*.md 历史污染只登记不清洗。

## 7. 真实路径测试（非单元桩）
- AC1 多会话同发 start/update/complete 行级隔离；AC2 归属不匹配 exit 2 且无写入；
- AC3 并发写无覆盖（多进程条件 UPDATE）；AC4 断点恢复 current/list 正常；
- AC5 legacy 迁移；AC6 complete 后 md 归档存在且 DB status=done；AC7 升级免疫（DB 在 memory/，零外部 import）。
