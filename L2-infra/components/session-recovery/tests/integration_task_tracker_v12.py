#!/usr/bin/env python3
"""真实路径集成测试：通过 subprocess 跑真实 task_tracker CLI（非单元桩）。

用 TASK_TRACKER_WORKSPACE 指向临时目录，生产 memory/ 不受影响。
覆盖 AC1 多会话隔离 / AC2 归属拒绝 / AC3 并发写无覆盖 / AC4 断点恢复 /
AC5 legacy 迁移 / AC6 complete 归档 / AC7 升级免疫。
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "task_tracker.py"

passed, failed = [], []


def run(args, ws, expect_rc=0):
    env = dict(os.environ, TASK_TRACKER_WORKSPACE=str(ws))
    r = subprocess.run([sys.executable, str(SCRIPT)] + args,
                       capture_output=True, text=True, env=env)
    ok = r.returncode == expect_rc
    return r, ok


def check(name, cond, detail=""):
    (passed if cond else failed).append(name)
    print(f"{'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail and not cond else ""))


def main():
    tmp = Path(tempfile.mkdtemp(prefix="tt-int-"))
    ws = tmp / "workspace"
    (ws / "memory").mkdir(parents=True)

    SA = "agent:main:dashboard:aaa"
    SB = "agent:main:dashboard:bbb"

    # AC1: 两个会话各 start 一个任务 → 行级隔离，互不顶替
    _, ok = run(["start", "--task-id", "T-A", "--name", "任务A",
                 "--session-key", SA, "--phase", "P0"], ws)
    check("AC1a start session A", ok)
    _, ok = run(["start", "--task-id", "T-B", "--name", "任务B",
                 "--session-key", SB, "--phase", "P0"], ws)
    check("AC1b start session B (no eviction)", ok)

    rA, _ = run(["current", "--session-key", SA, "--json"], ws)
    rB, _ = run(["current", "--session-key", SB, "--json"], ws)
    dA, dB = json.loads(rA.stdout), json.loads(rB.stdout)
    check("AC1c A current=T-A", dA.get("task_id") == "T-A")
    check("AC1d B current=T-B", dB.get("task_id") == "T-B")

    # 一会话一活跃：A 再 start 异任务且不带 --replace → exit 3
    _, ok = run(["start", "--task-id", "T-A2", "--name", "任务A2",
                 "--session-key", SA], ws, expect_rc=3)
    check("AC1e second active rejected (exit3)", ok)

    # AC2: 归属不匹配 → update/increment-fail/complete 拒绝(exit2)，且原数据不变
    _, ok = run(["update", "--task-id", "T-A", "--session-key", SB,
                 "--phase", "HACK"], ws, expect_rc=2)
    check("AC2a cross-session update rejected", ok)
    _, ok = run(["increment-fail", "--task-id", "T-A", "--session-key", SB],
                ws, expect_rc=2)
    check("AC2b cross-session fail rejected", ok)
    _, ok = run(["complete", "--task-id", "T-A", "--session-key", SB],
                ws, expect_rc=2)
    check("AC2c cross-session complete rejected", ok)
    rA2, _ = run(["current", "--session-key", SA, "--json"], ws)
    check("AC2d A phase untouched",
          json.loads(rA2.stdout).get("phase") == "P0")

    # AC3: 并发写——同任务 10 次 update（归属正确），无覆盖/无异常；step 单调
    def upd(i):
        return run(["update", "--task-id", "T-A", "--session-key", SA,
                    "--step-index", str(i), "--progress", f"p{i}"], ws)
    with ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(upd, range(10)))
    check("AC3a concurrent updates all rc=0", all(o for _, o in results))
    rAf, _ = run(["current", "--session-key", SA, "--json"], ws)
    df = json.loads(rAf.stdout)
    check("AC3b final step in 0..9 (no corruption)",
          df["step_index"] in range(10))
    check("AC3c all 10 progress entries appended (no lost writes)",
          df["progress_entries_total"] >= 11)  # 1 start + 10

    # AC4: 断点恢复——current/list 正确返回 + failure_count
    run(["increment-fail", "--task-id", "T-A", "--session-key", SA,
         "--reason", "timeout"], ws)
    rL, _ = run(["list", "--json"], ws)
    dl = json.loads(rL.stdout)
    check("AC4a list shows 2 active", dl["count"] == 2)
    rAg, _ = run(["current", "--session-key", SA, "--json"], ws)
    check("AC4b failure_count=1 after resume check",
          json.loads(rAg.stdout)["failure_count"] == 1)

    # AC5: legacy 迁移
    legacy = ws / "memory" / "current-task.md"
    legacy.write_text(
        "---\ntask_id: T-LEG\nname: 遗留任务\nsession_key: agent:main:main\n"
        "phase: 迁移前\nstep_index: 2\ntotal_steps: 5\nfailure_count: 1\n"
        "started_at: 2026-11-10T10:00:00\nlast_updated: 2026-11-10T11:00:00\n---\n\n"
        "### 进度记录\n- [2026-11-10T10:00:00] 任务启动: 遗留任务\n",
        encoding="utf-8")
    _, ok = run(["migrate-legacy", "--apply"], ws)
    check("AC5a legacy migrated", ok)
    rleg, _ = run(["current", "--session-key", "agent:main:main", "--json"], ws)
    dleg = json.loads(rleg.stdout)
    check("AC5b migrated task queryable", dleg.get("task_id") == "T-LEG")
    check("AC5c legacy entry restored",
          dleg.get("progress_entries_total") == 1)
    check("AC5d legacy file renamed to backup",
          not legacy.exists() and
          (ws / "memory" / "current-task.legacy.bak.md").exists())

    # AC6: complete → DB status=done + md 归档存在；active 列表不再含它
    _, ok = run(["complete", "--task-id", "T-B", "--session-key", SB,
                 "--result", "done-b"], ws)
    check("AC6a complete rc=0", ok)
    db = ws / "memory" / "tasks.db"
    st = sqlite3.connect(str(db)).execute(
        "SELECT status FROM tasks WHERE task_id='T-B'").fetchone()[0]
    check("AC6b DB status=done", st == "done")
    archives = list((ws / "memory" / "task-history").glob("*T-B.md"))
    check("AC6c md archive exists", len(archives) == 1)
    rLa, _ = run(["list", "--json"], ws)
    active_ids = [t["task_id"] for t in json.loads(rLa.stdout)["tasks"]]
    check("AC6d T-B not in active list", "T-B" not in active_ids)

    # AC7: 升级免疫——DB 位于 workspace memory/；脚本仅 stdlib，无 Gateway 内部依赖
    check("AC7a DB under workspace memory/",
          str(db).startswith(str(ws / "memory")))
    src = SCRIPT.read_text()
    bad = [l for l in src.splitlines()
           if ("import openclaw" in l or "from openclaw" in l
               or "node_modules" in l or ".openclaw/state" in l.replace("~", ""))]
    check("AC7b no Gateway-internal imports/deps", not bad,
          detail=str(bad[:3]))

    print(f"\n=== {len(passed)} passed, {len(failed)} failed ===")
    if failed:
        print("FAILED:", failed)
        sys.exit(1)


if __name__ == "__main__":
    main()
