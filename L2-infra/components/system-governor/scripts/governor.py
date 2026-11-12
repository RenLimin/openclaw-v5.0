"""system-governor 统一入口 CLI。

契约见 DESIGN-DETAIL-system-governor-v1.0.md §2.1。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 允许从源码目录直接运行（python3 .../scripts/governor.py）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from functools import partial

from src import ledger, orchestrator  # noqa: E402
from src import audit_flow  # noqa: E402
from src.lanes import lane_a_issues, lane_b_assets, lane_c_files, lane_d_tasks  # noqa: E402


def build_runners(only: str, apply: bool) -> dict[str, object]:
    """根据 --only 构建 lane runner 字典，注入 apply 标志。"""
    selected = [x.strip().upper() for x in only.split(",") if x.strip()]
    runners: dict[str, object] = {}
    factory = {
        "A": lane_a_issues.run,
        "B": lane_b_assets.run,
        "C": lane_c_files.run,
        "D": lane_d_tasks.run,
    }
    for lane in factory:
        if lane in selected:
            runners[lane] = partial(factory[lane], apply)
    return runners


def cmd_run(args: argparse.Namespace) -> int:
    runners = build_runners(args.only, args.apply)
    if not runners:
        print("ERROR: no lanes selected (--only A,B,C,D)", file=sys.stderr)
        return 2

    lane_results = orchestrator.orchestrate(runners, apply=args.apply)
    report = ledger.build_report(lane_results, invoked="cli", apply=args.apply)
    path = ledger.save_report(report, args.ledger)

    if args.json:
        print(json.dumps({
            "timestamp": report.timestamp,
            "apply": report.apply,
            "summary": report.summary,
            "lanes": {
                lane: {"stats": r.stats, "findings_count": len(r.findings)}
                for lane, r in sorted(lane_results.items())
            },
            "ledger_path": path,
        }, ensure_ascii=False, indent=2))
    else:
        s = report.summary
        print(f"=== system-governor run (apply={args.apply}) ===")
        print(f"lanes: {', '.join(sorted(lane_results))} | "
              f"total {s['total_unique']} unique findings "
              f"(auto-fixed {s['auto_fixed']}, needs-human {s['needs_human']}, "
              f"planned {s['planned']}, open {s['open']})")
        for lane, r in sorted(lane_results.items()):
            print(f"  lane {lane}: {r.stats}")
        print(f"ledger: {path}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    path = Path(args.ledger)
    if not path.exists():
        print(f"no ledger at {path} — run `governor.py run` first", file=sys.stderr)
        return 1
    payload = json.loads(path.read_text(encoding="utf-8"))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    """资产审计六环节（默认零写）。"""
    only = None
    if args.only:
        only = {x.strip().upper() for x in args.only.split(",") if x.strip()}
        bad = {x for x in only if x not in {"P1", "P2", "P3", "P4", "P5", "P6"}}
        if bad:
            print(f"ERROR: invalid probe(s) {bad} (expected P1-P6)", file=sys.stderr)
            return 2
    try:
        payload = audit_flow.run(
            apply=args.apply,
            only=only,
            timeout=args.timeout,
        )
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: audit failed: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        s = payload["summary"]
        print(f"=== system-governor audit (apply={args.apply}) ===")
        print(f"total {s['total']} | pending {s['pending']} | done {s['done']} | "
              f"needs-human {s['needs_human']} | skipped {s['skipped']}")
        print(f"regression: {payload['regression']['remaining_count']} warning(s) remain")
        for i in payload["items"]:
            print(f"  [{i['tier']}/{i['status']}] {i['category']} — {i['id'][:50]}")
            print(f"      → {i['suggestion'][:70]}")
        print(f"ledger: {payload['ledger_path']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="governor", description="system-governor 统一治理入口")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="运行治理 lane")
    p_run.add_argument("--only", default="A,B,C,D", help="lane 选择，逗号分隔（默认全跑）")
    p_run.add_argument("--apply", action="store_true", help="执行 L0/L1 写动作（默认 dry-run）")
    p_run.add_argument("--json", action="store_true", help="stdout 输出 JSON 摘要")
    p_run.add_argument("--ledger", default=None, help="账本路径覆盖")
    p_run.set_defaults(func=cmd_run)

    p_rep = sub.add_parser("report", help="读取最近一次账本")
    p_rep.add_argument("--ledger", default=None, help="账本路径覆盖")
    p_rep.set_defaults(func=cmd_report)

    p_aud = sub.add_parser("audit", help="资产审计六环节（默认零写）")
    p_aud.add_argument("--apply", action="store_true", help="执行 L1 git mv 写动作（默认 dry-run）")
    p_aud.add_argument("--json", action="store_true", help="stdout 输出完整 JSON 报告")
    p_aud.add_argument("--only", default=None, help="限定探针，逗号分隔（P1-P6，默认全部）")
    p_aud.add_argument("--timeout", type=int, default=300, help="整体 wall-clock 预算秒（默认 300）")
    p_aud.set_defaults(func=cmd_audit)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
