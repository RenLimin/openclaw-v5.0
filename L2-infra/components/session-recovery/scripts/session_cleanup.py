#!/usr/bin/env python3
"""会话清理脚本 — 定期清理过期的子会话和已完成任务。

策略:
- cron-run: 超过 6 小时自动清理（由 cron.sessionRetention 控制）
- subagent: 已完成且超过 6 小时自动删除
- dashboard: 已完成且超过 6 小时自动删除
- 主会话、wecom 群会话、cron 主任务: 保留不删

用法:
  python3 session_cleanup.py              # 预览（dry-run）
  python3 session_cleanup.py --yes        # 实际执行
  python3 session_cleanup.py --hours 12   # 自定义过期时间（小时）
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def get_sessions() -> list[dict]:
    result = run(["openclaw", "sessions", "list", "--limit", "500", "--json"])
    if result.returncode != 0:
        print(f"获取会话列表失败: {result.stderr[:200]}")
        return []
    data = json.loads(result.stdout)
    return data.get("sessions", [])


def classify_session(s: dict) -> str:
    key = s.get("key", "")
    if key == "agent:main:main":
        return "main"
    if "wecom:group" in key:
        return "wecom-group"
    if "cron" in key and ":run:" in key:
        return "cron-run"
    if "cron" in key and ":run:" not in key:
        return "cron-main"
    if "subagent" in key:
        return "subagent"
    if "dashboard" in key:
        return "dashboard"
    return "other"


def should_delete(s: dict, hours: float) -> tuple[bool, str]:
    """判断是否应该删除，返回 (是否删除, 原因)"""
    kind = classify_session(s)
    age_ms = s.get("ageMs", 0)
    status = s.get("status", "unknown")
    age_hours = age_ms / (1000 * 60 * 60)

    # 主会话、wecom 群、cron 主任务 —— 永远不删
    if kind in ("main", "wecom-group", "cron-main"):
        return False, "系统关键会话"

    # cron-run 由 cron.sessionRetention 管理，这里不重复删
    if kind == "cron-run":
        return False, "由 cron.sessionRetention 管理"

    # subagent 和 dashboard：已完成且超过过期时间才删
    if kind in ("subagent", "dashboard"):
        if status == "running":
            return False, "运行中"
        if age_hours >= hours:
            return True, f"已完成 {age_hours:.1f}h，超过 {hours}h 阈值"
        return False, f"仅 {age_hours:.1f}h，未到阈值"

    return False, f"未知类型: {kind}"


def delete_session(key: str, dry_run: bool) -> bool:
    if dry_run:
        return True
    result = run(["openclaw", "sessions", "delete", "--yes", key])
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="清理过期子会话")
    parser.add_argument("--yes", action="store_true", help="实际执行删除（默认 dry-run）")
    parser.add_argument("--hours", type=float, default=6, help="过期时间（小时），默认 6")
    args = parser.parse_args()

    dry_run = not args.yes
    mode = "DRY-RUN" if dry_run else "EXECUTE"

    print(f"=== 会话清理 [{mode}] ===")
    print(f"过期阈值: {args.hours}h")
    print()

    sessions = get_sessions()
    if not sessions:
        print("未获取到会话列表")
        return

    # 分类统计
    from collections import Counter
    kind_counts = Counter(classify_session(s) for s in sessions)
    print(f"总会话数: {len(sessions)}")
    for kind, count in sorted(kind_counts.items(), key=lambda x: -x[1]):
        print(f"  {kind}: {count}")
    print()

    # 筛选可删除
    to_delete = []
    skipped = []
    for s in sessions:
        delete, reason = should_delete(s, args.hours)
        if delete:
            to_delete.append((s, reason))
        else:
            skipped.append((s, reason))

    print(f"可删除: {len(to_delete)}")
    print(f"保留: {len(skipped)}")
    print()

    if to_delete:
        print("待删除列表:")
        for s, reason in to_delete:
            label = s.get("label", "(无标签)")
            key = s.get("key", "")
            age_h = s.get("ageMs", 0) / (1000 * 60 * 60)
            print(f"  [{age_h:.1f}h] {label[:40]} — {reason}")
            print(f"      key: {key}")
        print()

        if dry_run:
            print("[dry-run] 未实际删除。加 --yes 执行删除。")
        else:
            print("执行删除...")
            success = 0
            fail = 0
            for s, reason in to_delete:
                key = s["key"]
                if delete_session(key, dry_run=False):
                    success += 1
                    print(f"  ✅ {s.get('label', key)[:40]}")
                else:
                    fail += 1
                    print(f"  ❌ {s.get('label', key)[:40]}")
            print()
            print(f"完成: 成功 {success}，失败 {fail}")
    else:
        print("没有需要删除的会话。")

    print()
    print("=== 结束 ===")


if __name__ == "__main__":
    main()
