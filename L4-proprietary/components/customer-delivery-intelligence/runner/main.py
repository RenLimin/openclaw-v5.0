"""CDI 命令行入口。"""
from __future__ import annotations
import argparse, json, sys, uuid
from .assembly import build_engine, load_config
from .steps.n1_guard import validate, GuardError


def _print(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="cdi", description="customer-delivery-intelligence")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("start"); sp.add_argument("--customer", required=True)
    sp.add_argument("--period-start", required=True); sp.add_argument("--period-end", required=True)
    sp.add_argument("--audience", required=True, choices=["internal", "external"])
    sp.add_argument("--config", default=None)

    sp = sub.add_parser("status"); sp.add_argument("task_id")
    sp = sub.add_parser("decide"); sp.add_argument("task_id")
    sp.add_argument("--gate", required=True, choices=["gate1", "gate2"])
    sp.add_argument("--decision", required=True)
    sp = sub.add_parser("resume"); sp.add_argument("task_id")
    sp = sub.add_parser("tasks")

    args = p.parse_args(argv)
    config = load_config(getattr(args, "config", None)) if hasattr(args, "config") else load_config()
    engine = build_engine(config)

    if args.cmd == "start":
        raw = {"customer": args.customer,
               "period": {"start": args.period_start, "end": args.period_end},
               "audience": args.audience}
        try:
            norm = validate(raw)
        except GuardError as e:
            print(str(e), file=sys.stderr); return 2
        task_id = f"cdi-{uuid.uuid4().hex[:10]}"
        state = engine.start(task_id, norm)
        _print({"task_id": task_id, "state": state["current_state"]})
        return 0
    if args.cmd == "status":
        st = engine.get(args.task_id)
        if not st: print("not found", file=sys.stderr); return 1
        _print({"task_id": args.task_id, "state": st["current_state"], "errors": st["errors"]})
        return 0
    if args.cmd == "decide":
        st = engine.decide(args.task_id, args.gate, args.decision)
        _print({"task_id": args.task_id, "state": st["current_state"]}); return 0
    if args.cmd == "resume":
        st = engine.resume(args.task_id)
        _print({"task_id": args.task_id, "state": st["current_state"]}); return 0
    if args.cmd == "tasks":
        _print(engine.store.all_tasks()); return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
