#!/usr/bin/env python3
"""
会话隔离组件 — 统一 CLI 入口
Copyright (c) 2026 Bangcle, Inc. All rights reserved.

用法：
  python3 cli.py task-init ...         # 创建任务卡
  python3 cli.py state-write ...       # 写入共享状态
  python3 cli.py state-read ...        # 读取共享状态
  python3 cli.py event-log ...         # 记录事件
  python3 cli.py scheduler ...         # 运行任务调度器
"""

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from task_init import TaskInitializer
from event_logger import EventLogger
from state_reducer import StateReducer


def cmd_task_init(args):
    """创建任务卡"""
    goals = [{"id": "g1", "description": "Initialize task", "status": "in-progress"}]
    ti = TaskInitializer()
    ok, msg = ti.create_task(
        task_id=args.task_id,
        name=args.name,
        owner=args.owner,
        scope_project=args.scope_project,
        scope_component=args.scope_component,
        scope_version=args.scope_version,
        goals=goals,
        context_paths=args.context_paths,
        priority=args.priority,
    )
    print(msg)
    sys.exit(0 if ok else 1)


def cmd_state_write(args):
    """写入共享状态"""
    try:
        data = json.loads(args.data)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON data: {e}")
        sys.exit(1)
    sr = StateReducer(root_path=args.root)
    ok, msg = sr.write_state(
        scope=args.scope,
        key=args.key,
        new_data=data,
        reducer=args.reducer,
    )
    print(msg)
    sys.exit(0 if ok else 1)


def cmd_state_read(args):
    """读取共享状态"""
    sr = StateReducer(root_path=args.root)
    data, msg = sr.read_state(scope=args.scope, key=args.key)
    if data is None:
        print(msg)
        sys.exit(1)
    print(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_state_list(args):
    """列出 scope 下所有状态键"""
    sr = StateReducer(root_path=args.root)
    keys, msg = sr.list_states(scope=args.scope)
    if keys is None:
        print(msg)
        sys.exit(1)
    for k in keys:
        print(k)


def cmd_event_log(args):
    """记录任务事件"""
    data = None
    if args.data:
        try:
            data = json.loads(args.data)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON data: {e}")
            sys.exit(1)
    el = EventLogger()
    ok, msg = el.log_event(task_id=args.task_id, event_type=args.type, data=data)
    print(msg)
    sys.exit(0 if ok else 1)


def cmd_event_read(args):
    """读取任务事件"""
    el = EventLogger()
    events, msg = el.read_events(task_id=args.task_id, limit=args.limit)
    if events is None:
        print(msg)
        sys.exit(1)
    for evt in events:
        print(json.dumps(evt, ensure_ascii=False))


def cmd_scheduler(args):
    """运行任务调度器"""
    # scheduler 在组件根目录，加到 path
    COMP_ROOT = SCRIPT_DIR.parent
    sys.path.insert(0, str(COMP_ROOT))
    from scheduler import TaskScheduler

    scheduler = TaskScheduler(default_start_interval_sec=args.interval)

    if args.dry_run:
        print("=== DRY RUN MODE ===")
        stats = scheduler.run(lambda t: True, dry_run=True)
    else:
        try:
            from adapters.openclaw.spawner import OpenClawTaskSpawner
        except ImportError as e:
            print(f"无法导入 OpenClawTaskSpawner: {e}")
            print("请确保在 OpenClaw 运行时环境下使用，或使用 --dry-run")
            sys.exit(1)
        spawner = OpenClawTaskSpawner(
            default_model=args.model,
            default_run_timeout=args.timeout,
        )
        stats = scheduler.run(
            lambda t: spawner.spawn_task(t), interval_sec=args.interval
        )

    print("\n=== 调度统计 ===")
    for k, v in stats.items():
        print(f"{k}: {v}")

    sys.exit(0 if stats["started"] == stats["total_pending"] else 1)


def main():
    parser = argparse.ArgumentParser(description="Session Isolation CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ---- task-init ----
    p = subparsers.add_parser("task-init", help="创建任务卡")
    p.add_argument("--task-id", required=True, help="Task ID (task-YYYYMMDD-slug)")
    p.add_argument("--name", required=True, help="任务名称")
    p.add_argument("--owner", required=True, help="负责人")
    p.add_argument("--scope-project", required=True, help="项目范围")
    p.add_argument("--scope-component", required=True, help="组件范围")
    p.add_argument("--scope-version", required=True, help="版本范围")
    p.add_argument(
        "--priority",
        default="medium",
        choices=["low", "medium", "high", "urgent"],
        help="优先级",
    )
    p.add_argument("--context-paths", nargs="*", help="上下文文件路径列表")

    # ---- state-write ----
    p = subparsers.add_parser("state-write", help="写入共享状态（应用 reducer）")
    p.add_argument("--scope", required=True, help="状态范围 (e.g. project/bdms)")
    p.add_argument("--key", required=True, help="状态键")
    p.add_argument("--data", required=True, help="JSON 字符串")
    p.add_argument(
        "--reducer",
        default="last-write-wins",
        choices=["append", "merge", "last-write-wins"],
        help="合并策略",
    )
    p.add_argument("--root", default="state", help="状态根目录")

    # ---- state-read ----
    p = subparsers.add_parser("state-read", help="读取共享状态")
    p.add_argument("--scope", required=True, help="状态范围")
    p.add_argument("--key", required=True, help="状态键")
    p.add_argument("--root", default="state", help="状态根目录")

    # ---- state-list ----
    p = subparsers.add_parser("state-list", help="列出 scope 下所有状态键")
    p.add_argument("--scope", required=True, help="状态范围")
    p.add_argument("--root", default="state", help="状态根目录")

    # ---- event-log ----
    p = subparsers.add_parser("event-log", help="记录任务事件")
    p.add_argument("--task-id", required=True, help="任务ID")
    p.add_argument("--type", required=True, help="事件类型")
    p.add_argument("--data", help="事件数据 (JSON)")

    # ---- event-read ----
    p = subparsers.add_parser("event-read", help="读取任务事件日志")
    p.add_argument("--task-id", required=True, help="任务ID")
    p.add_argument("--limit", type=int, default=None, help="最大条数")

    # ---- scheduler ----
    p = subparsers.add_parser("scheduler", help="运行任务调度器")
    p.add_argument("--dry-run", action="store_true", help="只排序不发起")
    p.add_argument(
        "--interval", type=float, default=10.0, help="任务启动间隔秒数 (default 10)"
    )
    p.add_argument("--model", default=None, help="默认模型")
    p.add_argument(
        "--timeout", type=int, default=1800, help="运行超时秒数 (default 1800)"
    )

    args = parser.parse_args()

    dispatch = {
        "task-init": cmd_task_init,
        "state-write": cmd_state_write,
        "state-read": cmd_state_read,
        "state-list": cmd_state_list,
        "event-log": cmd_event_log,
        "event-read": cmd_event_read,
        "scheduler": cmd_scheduler,
    }

    dispatch[args.command](args)


if __name__ == "__main__":
    main()
