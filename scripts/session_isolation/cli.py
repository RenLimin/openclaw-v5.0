#!/usr/bin/env python3
"""
会话隔离与共享组件 — CLI 入口
Copyright (c) 2026 Bangcle, Inc. All rights reserved.
"""
import argparse
import sys
sys.path.insert(0, '.')
from scripts.session_isolation import TaskInitializer, EventLogger, StateReducer

def main():
    parser = argparse.ArgumentParser(description="Session Isolation Sharing CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # task init
    parser_task_init = subparsers.add_parser("task-init", help="Initialize new task")
    parser_task_init.add_argument("--task-id", required=True, help="Task ID (task-YYYYMMDD-slug)")
    parser_task_init.add_argument("--name", required=True, help="Task name")
    parser_task_init.add_argument("--owner", required=True, help="Owner (main-agent / ...)")
    parser_task_init.add_argument("--scope-project", required=True, help="Scope project")
    parser_task_init.add_argument("--scope-component", required=True, help="Scope component")
    parser_task_init.add_argument("--scope-version", required=True, help="Scope version")
    parser_task_init.add_argument("--priority", default="medium", choices=["low", "medium", "high", "urgent"], help="Priority")
    parser_task_init.add_argument("--context-paths", nargs="*", help="Context file paths (relative to workspace root)")

    # state write
    parser_state_write = subparsers.add_parser("state-write", help="Write state (apply reducer)")
    parser_state_write.add_argument("--scope", required=True, help="State scope (e.g. project/bdms)")
    parser_state_write.add_argument("--key", required=True, help="State key")
    parser_state_write.add_argument("--data", required=True, help="New data (JSON string)")
    parser_state_write.add_argument("--reducer", default="last-write-wins", choices=["append", "merge", "last-write-wins"], help="Reducer")

    # event log
    parser_event_log = subparsers.add_parser("event-log", help="Log event to task")
    parser_event_log.add_argument("--task-id", required=True, help="Task ID")
    parser_event_log.add_argument("--type", required=True, help="Event type")
    parser_event_log.add_argument("--data", help="Event data (JSON string)")

    args = parser.parse_args()

    if args.command == "task-init":
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
            priority=args.priority
        )
        print(msg)
        sys.exit(0 if ok else 1)

    elif args.command == "state-write":
        import json
        try:
            data = json.loads(args.data)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON data: {e}")
            sys.exit(1)
        sr = StateReducer()
        ok, msg = sr.write_state(
            scope=args.scope,
            key=args.key,
            new_data=data,
            reducer=args.reducer
        )
        print(msg)
        sys.exit(0 if ok else 1)

    elif args.command == "event-log":
        import json
        data = None
        if args.data:
            try:
                data = json.loads(args.data)
            except json.JSONDecodeError as e:
                print(f"Invalid JSON data: {e}")
                sys.exit(1)
        el = EventLogger()
        ok, msg = el.log_event(
            task_id=args.task_id,
            event_type=args.type,
            data=data
        )
        print(msg)
        sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
