#!/usr/bin/env python3
"""
沙箱隔离组件 — CLI 入口
Copyright (c) 2026 Bangcle, Inc. All rights reserved.
"""
import argparse
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
L1_RUNTIME = WORKSPACE_ROOT / "L1-runtime"
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKSPACE_ROOT))
sys.path.insert(0, str(L1_RUNTIME))
sys.path.insert(0, str(SCRIPT_DIR.parent))
sys.path.insert(0, str(SCRIPT_DIR))

from sandbox import SandboxManager
from policy import SandboxPolicy
from service import SandboxIsolationService

def main():
    parser = argparse.ArgumentParser(description="Sandbox Isolation CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create sandbox
    parser_create = subparsers.add_parser("create", help="Create new sandbox")
    parser_create.add_argument("--policy", required=True, help="Policy name")
    parser_create.add_argument("--workdir", help="Working directory (optional)")

    # destroy sandbox
    parser_destroy = subparsers.add_parser("destroy", help="Destroy sandbox")
    parser_destroy.add_argument("--id", required=True, help="Sandbox ID")

    # start sandbox
    parser_start = subparsers.add_parser("start", help="Start command in sandbox")
    parser_start.add_argument("--id", required=True, help="Sandbox ID")
    parser_start.add_argument("command", nargs="+", help="Command to run")

    # stop sandbox
    parser_stop = subparsers.add_parser("stop", help="Stop running sandbox")
    parser_stop.add_argument("--id", required=True, help="Sandbox ID")

    # list sandboxes
    parser_list = subparsers.add_parser("list", help="List all sandboxes")

    # info
    parser_info = subparsers.add_parser("info", help="Get sandbox info")
    parser_info.add_argument("--id", required=True, help="Sandbox ID")

    # output
    parser_output = subparsers.add_parser("output", help="Get sandbox output")
    parser_output.add_argument("--id", required=True, help="Sandbox ID")
    parser_output.add_argument("--offset", type=int, default=0, help="Offset")
    parser_output.add_argument("--limit", type=int, help="Limit")

    # wait
    parser_wait = subparsers.add_parser("wait", help="Wait for sandbox to exit")
    parser_wait.add_argument("--id", required=True, help="Sandbox ID")
    parser_wait.add_argument("--timeout", type=int, help="Timeout seconds")

    # create policy
    parser_policy_create = subparsers.add_parser("policy-create", help="Create new policy")
    parser_policy_create.add_argument("--name", required=True, help="Policy name")
    parser_policy_create.add_argument("--allowed-commands", nargs="+", required=True, help="Allowed commands (e.g. python pip)")
    parser_policy_create.add_argument("--allowed-paths", nargs="*", default=[], help="Allowed paths (supports *)")
    parser_policy_create.add_argument("--blocked-paths", nargs="*", default=[], help="Blocked paths (supports *)")

    # list policies
    parser_policy_list = subparsers.add_parser("policy-list", help="List all policies")

    args = parser.parse_args()

    service = SandboxIsolationService()

    if args.command == "create":
        ok, msg, sandbox_id = service.create_sandbox(
            policy_name=args.policy,
            workdir=args.workdir
        )
        print(msg)
        if ok:
            print(f"SANDBOX_ID={sandbox_id}")
        sys.exit(0 if ok else 1)

    elif args.command == "destroy":
        ok, msg = service.destroy_sandbox(args.id)
        print(msg)
        sys.exit(0 if ok else 1)

    elif args.command == "start":
        ok, msg = service.start_sandbox(args.id, args.command)
        print(msg)
        sys.exit(0 if ok else 1)

    elif args.command == "stop":
        ok, msg = service.stop_sandbox(args.id)
        print(msg)
        sys.exit(0 if ok else 1)

    elif args.command == "list":
        infos = service.list_sandboxes()
        print(f"Found {len(infos)} sandboxes:")
        for info in infos:
            print(f"  {info.sandbox_id:<20} {info.status:<10} {info.policy_name:<15} {info.created_at}")
        sys.exit(0)

    elif args.command == "info":
        info, err = service.get_sandbox_info(args.id)
        if err:
            print(err)
            sys.exit(1)
        if not info:
            print(f"Sandbox {args.id} not found")
            sys.exit(1)
        print(f"Sandbox ID: {info.sandbox_id}")
        print(f"Status: {info.status}")
        print(f"Policy: {info.policy_name}")
        print(f"Workdir: {info.workdir}")
        print(f"Created: {info.created_at}")
        sys.exit(0)

    elif args.command == "output":
        output, err = service.get_output(args.id, args.offset, args.limit)
        if err:
            print(err)
            sys.exit(1)
        if output:
            print(output)
        sys.exit(0 if output is not None else 1)

    elif args.command == "wait":
        exit_code, err = service.wait_sandbox(args.id, args.timeout)
        print(err)
        sys.exit(exit_code)

    elif args.command == "policy-create":
        ok, msg = service.policy.create_policy(
            policy_name=args.name,
            allowed_commands=args.allowed_commands,
            allowed_paths=args.allowed_paths,
            blocked_paths=args.blocked_paths
        )
        print(msg)
        sys.exit(0 if ok else 1)

    elif args.command == "policy-list":
        policies = service.policy.list_policies()
        print(f"Found {len(policies)} policies:")
        for p in policies:
            print(f"  {p}")
        sys.exit(0)

if __name__ == "__main__":
    main()
