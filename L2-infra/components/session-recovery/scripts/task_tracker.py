#!/usr/bin/env python3
"""
task_tracker — 会话级任务状态（SQLite 隔离存储，v1.2）

存储：memory/tasks.db（用户资产；OpenClaw 升级不触碰）。仅用 Python stdlib。
归属：start/update/increment-fail/complete 均按 (task_id, session_key) 隔离，
      update/complete 走条件 UPDATE，归属不匹配 rowcount=0 → 拒绝，绝不写入。

用法：
  start    --task-id T --name N --session-key S [--description D --phase P --steps JSON] [--replace]
  update   --task-id T --session-key S [--phase P] [--step-index I] [--progress TEXT]
  increment-fail --task-id T --session-key S [--reason R]
  complete --task-id T --session-key S [--result R]
  current  [--session-key S] [--json]
  list     [--all] [--json]
  migrate-legacy [--apply]
"""
import json
import os
import sys
import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

WORKSPACE = Path(os.environ.get(
    "TASK_TRACKER_WORKSPACE", "/Users/bangcle/.openclaw/workspace"))
CURRENT_TASK_FILE = WORKSPACE / "memory" / "current-task.md"   # legacy，仅迁移用
HISTORY_DIR = WORKSPACE / "memory" / "task-history"
DB_FILE = Path(os.environ.get(
    "TASK_TRACKER_DB", str(WORKSPACE / "memory" / "tasks.db")))

ACTIVE = "active"
ACTIVE_STATUSES = (ACTIVE,)


def _now():
    return datetime.now().isoformat(timespec="seconds")


# ── DB ────────────────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
  task_id       TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  session_key   TEXT NOT NULL,
  description   TEXT NOT NULL DEFAULT '',
  phase         TEXT NOT NULL DEFAULT '',
  step_index    INTEGER NOT NULL DEFAULT 0,
  total_steps   INTEGER NOT NULL DEFAULT 0,
  failure_count INTEGER NOT NULL DEFAULT 0,
  status        TEXT NOT NULL DEFAULT 'active',
  result        TEXT NOT NULL DEFAULT '',
  entries_json  TEXT NOT NULL DEFAULT '[]',
  started_at    TEXT NOT NULL,
  last_updated  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_key);
CREATE UNIQUE INDEX IF NOT EXISTS ux_session_active ON tasks(session_key)
  WHERE status='active';
"""


def _connect(db_file: Path = None):
    db = db_file or DB_FILE
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db), timeout=5.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA user_version=1")
    conn.executescript(SCHEMA)
    return conn


def _row_to_dict(row: sqlite3.Row):
    d = dict(row)
    try:
        d["progress_entries"] = json.loads(d.pop("entries_json") or "[]")
    except json.JSONDecodeError:
        d["progress_entries"] = []
    return d


def _get_active(conn, session_key):
    cur = conn.execute(
        "SELECT * FROM tasks WHERE session_key=? AND status='active'", (session_key,))
    row = cur.fetchone()
    return _row_to_dict(row) if row else None


def _get_task(conn, task_id):
    cur = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,))
    row = cur.fetchone()
    return _row_to_dict(row) if row else None


# ── Markdown 归档（保审计链 + lane_d 历史读取不变）──────────────────────────
_FM_ORDER = ["task_id", "name", "session_key", "phase", "step_index",
             "total_steps", "failure_count", "started_at", "last_updated",
             "archived_at", "archive_reason", "result"]


def _write_md_archive(data, reason, result=None, archive_file=None):
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    d = dict(data)
    d["archived_at"] = _now()
    d["archive_reason"] = reason
    if result:
        d["result"] = result
    lines = ["---"]
    for k in _FM_ORDER:
        if d.get(k) not in (None, ""):
            lines.append(f"{k}: {d[k]}")
    lines.append("---")
    if d.get("description"):
        lines += ["", d["description"]]
    entries = d.get("progress_entries", [])
    if entries:
        lines += ["", "### 进度记录"]
        for e in entries:
            lines.append(f"- [{e.get('time', '?')}] {e.get('text', '')}")
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = archive_file or (HISTORY_DIR / f"{ts}_{d.get('task_id','unknown')}.md")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ── Commands ───────────────────────────────────────────────────────────────
def _require_scope(session_key):
    if not session_key:
        print("❌ 缺少 --session-key：无法确认任务归属（多会话隔离要求）", file=sys.stderr)
        sys.exit(2)


def cmd_start(args):
    _require_scope(args.session_key)
    now = _now()
    steps = []
    if args.steps:
        try:
            steps = json.loads(args.steps)
        except json.JSONDecodeError:
            print("❌ --steps 不是合法 JSON 数组", file=sys.stderr)
            sys.exit(2)
    conn = _connect()
    try:
        existing = _get_active(conn, args.session_key)
        if existing and existing["task_id"] != args.task_id:
            if not args.replace:
                print(f"❌ 会话已有活跃任务 {existing['task_id']}；"
                      f"先 complete 或加 --replace", file=sys.stderr)
                sys.exit(3)
            conn.execute(
                "UPDATE tasks SET status='interrupted', last_updated=? "
                "WHERE task_id=? AND session_key=? AND status='active'",
                (now, existing["task_id"], args.session_key))
            _write_md_archive(existing, reason="interrupted-by-new")
        # 同 task_id 重入 → 幂等返回
        same = _get_task(conn, args.task_id)
        if same and same["status"] == ACTIVE and same["session_key"] == args.session_key:
            print(f"✅ 任务已在进行（幂等）: {args.task_id}")
            return
        entries = [{"time": now, "text": f"任务启动: {args.name}"}]
        conn.execute(
            "INSERT INTO tasks(task_id,name,session_key,description,phase,step_index,"
            "total_steps,failure_count,status,result,entries_json,started_at,last_updated)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (args.task_id, args.name, args.session_key, args.description or "",
             args.phase or "启动", 0, len(steps), 0, ACTIVE, "",
             json.dumps(entries, ensure_ascii=False), now, now))
        conn.commit()
    finally:
        conn.close()
    print(f"✅ 任务已启动: {args.task_id} — {args.name}")
    print(f"   DB: {DB_FILE}")


def _load_owned(conn, task_id, session_key):
    task = _get_task(conn, task_id)
    if not task or task["session_key"] != session_key or task["status"] != ACTIVE:
        print(f"❌ 拒绝：task_id={task_id} 不属于会话 {session_key} 或非活跃",
              file=sys.stderr)
        sys.exit(2)
    return task


def cmd_update(args):
    _require_scope(args.session_key)
    conn = _connect()
    try:
        task = _load_owned(conn, args.task_id, args.session_key)
        phase = args.phase if args.phase is not None else task["phase"]
        step = args.step_index if args.step_index is not None else task["step_index"]
        entries = list(task["progress_entries"])
        if args.progress:
            entries.append({"time": _now(), "text": args.progress})
        cur = conn.execute(
            "UPDATE tasks SET phase=?, step_index=?, entries_json=?, last_updated=? "
            "WHERE task_id=? AND session_key=? AND status='active'",
            (phase, step, json.dumps(entries, ensure_ascii=False), _now(),
             args.task_id, args.session_key))
        if cur.rowcount == 0:
            print("❌ 更新被拒（归属/状态不匹配），未写入", file=sys.stderr)
            sys.exit(2)
        conn.commit()
    finally:
        conn.close()
    print(f"✅ 进度已更新: phase={phase}, step={step}")


def cmd_increment_fail(args):
    _require_scope(args.session_key)
    conn = _connect()
    try:
        task = _load_owned(conn, args.task_id, args.session_key)
        count = task["failure_count"] + 1
        entries = list(task["progress_entries"])
        entries.append({"time": _now(),
                        "text": f"⚠️ 失败 #{count}: {args.reason or '未知原因'}"})
        cur = conn.execute(
            "UPDATE tasks SET failure_count=?, entries_json=?, last_updated=? "
            "WHERE task_id=? AND session_key=? AND status='active'",
            (count, json.dumps(entries, ensure_ascii=False), _now(),
             args.task_id, args.session_key))
        if cur.rowcount == 0:
            print("❌ 失败计数被拒（归属不匹配），未写入", file=sys.stderr)
            sys.exit(2)
        conn.commit()
    finally:
        conn.close()
    print(f"⚠️ 失败计数: {count} (原因: {args.reason})")


def cmd_complete(args):
    _require_scope(args.session_key)
    conn = _connect()
    try:
        task = _load_owned(conn, args.task_id, args.session_key)
        entries = list(task["progress_entries"])
        entries.append({"time": _now(),
                        "text": f"✅ 完成: {args.result or '任务结束'}"})
        now = _now()
        cur = conn.execute(
            "UPDATE tasks SET status='done', phase='完成', result=?, "
            "entries_json=?, last_updated=? "
            "WHERE task_id=? AND session_key=? AND status='active'",
            (args.result or "", json.dumps(entries, ensure_ascii=False), now,
             args.task_id, args.session_key))
        if cur.rowcount == 0:
            print("❌ 完成被拒（归属不匹配），未写入", file=sys.stderr)
            sys.exit(2)
        task.update(status="done", phase="完成", result=args.result or "",
                    progress_entries=entries, last_updated=now)
        path = _write_md_archive(task, reason="completed", result=args.result)
        conn.commit()
    finally:
        conn.close()
    print(f"✅ 任务已完成并归档: {args.task_id}")
    print(f"   归档: {path}")


def _public_view(task):
    entries = task.get("progress_entries", [])
    out = {"active": True,
           "task_id": task["task_id"], "name": task["name"],
           "session_key": task["session_key"], "description": task.get("description", ""),
           "phase": task["phase"], "step_index": task["step_index"],
           "total_steps": task["total_steps"], "failure_count": task["failure_count"],
           "status": task["status"], "result": task.get("result", ""),
           "started_at": task["started_at"], "last_updated": task["last_updated"],
           "progress_entries_total": len(entries),
           "progress_entries_recent": entries[-5:]}
    return out


def cmd_current(args):
    conn = _connect()
    try:
        if args.session_key:
            task = _get_active(conn, args.session_key)
        else:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status='active'").fetchall()
            if len(rows) == 1:
                task = _row_to_dict(rows[0])
            else:
                if args.json:
                    print(json.dumps(
                        {"active": False, "scope_needed": True,
                         "active_count": len(rows)}, ensure_ascii=False, indent=2))
                else:
                    print("ℹ️ 存在多个/无活跃任务，请用 --session-key 指定")
                return
    finally:
        conn.close()
    if not task:
        print(json.dumps({"active": False}, ensure_ascii=False, indent=2)
              if args.json else "ℹ️ 没有进行中的任务")
        return
    if args.json:
        print(json.dumps(_public_view(task), ensure_ascii=False, indent=2))
    else:
        print(f"任务: {task['name']} ({task['task_id']})")
        print(f"阶段: {task['phase']}")
        print(f"步骤: {task['step_index']}/{task['total_steps']}")
        print(f"失败次数: {task['failure_count']}")
        print(f"最后更新: {task['last_updated']}")
        for e in task["progress_entries"][-5:]:
            print(f"  - [{e.get('time')}] {e.get('text')}")


def cmd_list(args):
    conn = _connect()
    try:
        where = "" if args.all else "WHERE status='active'"
        rows = conn.execute(
            f"SELECT * FROM tasks {where} ORDER BY last_updated DESC").fetchall()
    finally:
        conn.close()
    tasks = [_public_view(_row_to_dict(r)) for r in rows]
    if args.json:
        print(json.dumps({"count": len(tasks), "tasks": tasks},
                         ensure_ascii=False, indent=2))
    else:
        for t in tasks:
            print(f"[{t['status']}] {t['task_id']} | {t['name']} | "
                  f"sess={t['session_key']} | phase={t['phase']} | "
                  f"fail={t['failure_count']}")


# ── legacy 迁移 ───────────────────────────────────────────────────────────
def _parse_frontmatter(content):
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, content
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}, content
    data = {}
    for line in lines[1:end]:
        if ":" in line:
            k, _, v = line.partition(":")
            val = v.strip()
            if val.startswith('"') and val.endswith('"'):
                val = val[1:-1]
            data[k.strip()] = val
    for k in ("failure_count", "step_index", "total_steps"):
        if k in data:
            try:
                data[k] = int(data[k])
            except ValueError:
                pass
    return data, "\n".join(lines[end + 1:]).strip()


def cmd_migrate_legacy(args):
    if not CURRENT_TASK_FILE.exists():
        print("ℹ️ 无 current-task.md，无需迁移")
        return
    data, body = _parse_frontmatter(CURRENT_TASK_FILE.read_text(encoding="utf-8"))
    tid, skey = data.get("task_id"), data.get("session_key")
    if not tid or not skey:
        print("❌ legacy 记录缺 task_id/session_key，不导入（避免臆造归属）", file=sys.stderr)
        sys.exit(2)
    entries = []
    in_prog = False
    import re
    for line in body.split("\n"):
        if line.strip() == "### 进度记录":
            in_prog = True
            continue
        if in_prog:
            m = re.match(r'^- \[(.+?)\] (.+)$', line.strip())
            if m:
                entries.append({"time": m.group(1), "text": m.group(2)})
    now = _now()
    conn = _connect()
    try:
        if _get_task(conn, tid):
            print(f"ℹ️ {tid} 已存在，跳过导入")
        else:
            conn.execute(
                "INSERT INTO tasks(task_id,name,session_key,description,phase,step_index,"
                "total_steps,failure_count,status,result,entries_json,started_at,last_updated)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (tid, data.get("name", tid), skey, data.get("description", ""),
                 data.get("phase", ""), data.get("step_index", 0),
                 data.get("total_steps", 0), data.get("failure_count", 0),
                 ACTIVE, "", json.dumps(entries, ensure_ascii=False),
                 data.get("started_at", now), data.get("last_updated", now)))
            conn.commit()
            print(f"✅ 已导入 {tid} (session={skey})")
    finally:
        conn.close()
    if args.apply:
        bak = CURRENT_TASK_FILE.with_name("current-task.legacy.bak.md")
        CURRENT_TASK_FILE.rename(bak)
        print(f"   原文件已保留为 {bak}")


def main():
    p = argparse.ArgumentParser(description="task_tracker — SQLite 会话任务状态 v1.2")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("start"); s.add_argument("--task-id", required=True)
    s.add_argument("--name", required=True); s.add_argument("--description", default="")
    s.add_argument("--session-key", default=""); s.add_argument("--phase", default="启动")
    s.add_argument("--steps", default="[]"); s.add_argument("--replace", action="store_true")

    u = sub.add_parser("update"); u.add_argument("--task-id", required=True)
    u.add_argument("--session-key", default=""); u.add_argument("--phase")
    u.add_argument("--step-index", type=int); u.add_argument("--progress")

    f = sub.add_parser("increment-fail"); f.add_argument("--task-id", required=True)
    f.add_argument("--session-key", default=""); f.add_argument("--reason", default="")

    c = sub.add_parser("complete"); c.add_argument("--task-id", required=True)
    c.add_argument("--session-key", default=""); c.add_argument("--result", default="")

    cur = sub.add_parser("current"); cur.add_argument("--session-key", default="")
    cur.add_argument("--json", action="store_true")

    lst = sub.add_parser("list"); lst.add_argument("--all", action="store_true")
    lst.add_argument("--json", action="store_true")

    mig = sub.add_parser("migrate-legacy"); mig.add_argument("--apply", action="store_true")

    args = p.parse_args()
    {
        "start": cmd_start, "update": cmd_update,
        "increment-fail": cmd_increment_fail, "complete": cmd_complete,
        "current": cmd_current, "list": cmd_list,
        "migrate-legacy": cmd_migrate_legacy,
    }[args.command](args)


if __name__ == "__main__":
    main()
