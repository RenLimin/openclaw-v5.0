#!/usr/bin/env python3
"""自动清理已完成的子会话，标记 archived。

Usage:
  python3 L2-infra/components/session-recovery/scripts/cleanup_done_subsessions.py [--dry-run]

- 遍历所有 kind=other/spawn-child 的子会话（由 sessions_spawn 创建）
- 找到 status=done 的子会话，标记 archived=True
- --dry-run 只预览不修改
"""

import argparse
import json
import subprocess
import sys
from typing import List, Dict


def list_subsessions() -> List[Dict]:
    """列出所有未归档的子会话。"""
    result = subprocess.run(
        ["openclaw", "sessions", "list", "--agent", "main", "--active", "10080", "--json"],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"❌ 列出会话失败: {result.stderr}")
        return []
    try:
        data = json.loads(result.stdout)
        return data.get("sessions", [])
    except json.JSONDecodeError as e:
        print(f"❌ 解析会话列表失败: {e}")
        return []


def archive_session(session_key: str, session_id: str) -> bool:
    """标记会话为 archived。"""
    result = subprocess.run(
        [
            "openclaw", "sessions", "archive",
            session_key
        ],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"❌ 归档失败 {session_key}: {result.stderr}")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="自动清理已完成的子会话")
    parser.add_argument("--dry-run", action="store_true", help="只预览不修改")
    args = parser.parse_args()

    print("=== 清理已完成子会话 ===\n")

    sessions = list_subsessions()
    if not sessions:
        print("✅ 没有需要清理的子会话")
        sys.exit(0)

    done_sessions = [
        s for s in sessions
        if s.get("status") == "done" and not s.get("archived")
    ]

    if not done_sessions:
        print("✅ 没有已完成未归档的子会话")
        sys.exit(0)

    print(f"发现 {len(done_sessions)} 个已完成未归档的子会话:\n")
    for s in done_sessions:
        print(f"  - {s.get('displayName', 'unnamed')} ({s.get('sessionId')})")

    if args.dry_run:
        print("\n⚠️  --dry-run 模式，不执行修改")
        sys.exit(0)

    print("\n开始归档...\n")
    success = 0
    failed = 0
    for s in done_sessions:
        ok = archive_session(s["key"], s["sessionId"])
        if ok:
            print(f"✅ 已归档: {s.get('displayName', 'unnamed')}")
            success += 1
        else:
            failed += 1

    print(f"\n=== 完成 ===")
    print(f"总计: {len(done_sessions)} | 成功: {success} | 失败: {failed}")


if __name__ == "__main__":
    main()
