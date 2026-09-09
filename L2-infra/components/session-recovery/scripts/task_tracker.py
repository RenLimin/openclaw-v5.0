#!/usr/bin/env python3
"""
current-task.md 管理器 — 会话断点记忆

用法：
    # 开始新任务
    python3 task_tracker.py start --task-id "task-20260909-retry" \
        --name "会话失败自动重试" \
        --description "实现主会话失败后的自动重试 + 断点恢复" \
        --phase "设计方案" \
        --steps '["盘现状","设计","实现","测试"]'

    # 更新进度
    python3 task_tracker.py update --phase "实现中" --step-index 2 --progress "已完成 current-task 模块"

    # 标记失败（失败计数 +1）
    python3 task_tracker.py increment-fail --reason "LLM timeout"

    # 标记完成（归档）
    python3 task_tracker.py complete --result "三个模块全部通过测试"

    # 读取当前任务
    python3 task_tracker.py current --json
"""
import json
import sys
import argparse
from datetime import datetime
from pathlib import Path

WORKSPACE = Path("/Users/bangcle/.openclaw/workspace")
CURRENT_TASK_FILE = WORKSPACE / "memory" / "current-task.md"
HISTORY_DIR = WORKSPACE / "memory" / "task-history"


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _parse_frontmatter(content):
    """解析 Markdown frontmatter，返回 (data_dict, body_text)"""
    lines = content.split("\n")
    if len(lines) < 3 or lines[0].strip() != "---":
        return {}, content
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}, content
    data = {}
    for line in lines[1:end_idx]:
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if val.startswith('"') and val.endswith('"'):
                val = val[1:-1]
            data[key] = val
    for int_key in ["failure_count", "step_index", "total_steps"]:
        if int_key in data:
            try:
                data[int_key] = int(data[int_key])
            except (ValueError, TypeError):
                pass
    body = "\n".join(lines[end_idx + 1:]).strip()
    return data, body


def _read_current():
    """读取 current-task.md，解析为 dict。不存在返回 None。"""
    if not CURRENT_TASK_FILE.exists():
        return None
    content = CURRENT_TASK_FILE.read_text()
    data, body = _parse_frontmatter(content)
    if not data.get("task_id"):
        return None
    # 从 body 解析进度条目（反向兼容）
    entries = []
    in_progress = False
    for line in body.split("\n"):
        if line.strip() == "### 进度记录":
            in_progress = True
            continue
        if in_progress and line.startswith("- ["):
            # - [2026-09-09T13:00:00] 文本
            import re
            m = re.match(r'^- \[(.+?)\] (.+)$', line.strip())
            if m:
                entries.append({"time": m.group(1), "text": m.group(2)})
    data["progress_entries"] = entries
    data["body"] = body
    return data


def _format_frontmatter(data):
    """生成 frontmatter 字符串"""
    keys_order = ["task_id", "name", "phase", "step_index", "total_steps",
                  "failure_count", "started_at", "last_updated",
                  "archived_at", "archive_reason", "result"]
    lines = ["---"]
    for key in keys_order:
        if key in data and data[key] is not None:
            lines.append(f"{key}: {data[key]}")
    lines.append("---")
    return "\n".join(lines)


def _format_body(data):
    """生成 body 文本"""
    parts = []
    if data.get("description"):
        parts.append(data["description"])
    entries = data.get("progress_entries", [])
    if entries:
        parts.append("")
        parts.append("### 进度记录")
        for e in entries:
            parts.append(f"- [{e.get('time', '?')}] {e.get('text', '')}")
    return "\n".join(parts)


def _write_current(data):
    """写入 current-task.md"""
    CURRENT_TASK_FILE.parent.mkdir(parents=True, exist_ok=True)
    data["last_updated"] = _now()
    fm = _format_frontmatter(data)
    body = _format_body(data)
    CURRENT_TASK_FILE.write_text(fm + "\n\n" + body + "\n")


def _archive(data, reason="completed", result=None):
    """归档到 task-history/"""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    task_id = data.get("task_id", "unknown")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_file = HISTORY_DIR / f"{timestamp}_{task_id}.md"
    # 加归档元数据
    data = dict(data)
    data["archived_at"] = _now()
    data["archive_reason"] = reason
    if result:
        data["result"] = result
    fm = _format_frontmatter(data)
    body = _format_body(data)
    archive_file.write_text(fm + "\n\n" + body + "\n")


def cmd_start(args):
    """开始新任务"""
    existing = _read_current()
    if existing and existing.get("task_id") != args.task_id:
        _archive(existing, reason="interrupted-by-new")

    steps = json.loads(args.steps) if args.steps else []
    now = _now()
    data = {
        "task_id": args.task_id,
        "name": args.name,
        "description": args.description or "",
        "phase": args.phase or "启动",
        "step_index": 0,
        "total_steps": len(steps),
        "failure_count": 0,
        "started_at": now,
        "last_updated": now,
        "progress_entries": [{"time": now, "text": f"任务启动: {args.name}"}],
    }
    _write_current(data)
    print(f"✅ 任务已启动: {args.task_id} — {args.name}")
    print(f"   文件: {CURRENT_TASK_FILE}")


def cmd_update(args):
    """更新任务进度"""
    data = _read_current()
    if not data:
        print("❌ 没有进行中的任务", file=sys.stderr)
        sys.exit(1)
    if args.phase:
        data["phase"] = args.phase
    if args.step_index is not None:
        data["step_index"] = args.step_index
    if args.progress:
        entries = data.get("progress_entries", [])
        entries.append({"time": _now(), "text": args.progress})
        data["progress_entries"] = entries
    _write_current(data)
    print(f"✅ 进度已更新: phase={data.get('phase')}, step={data.get('step_index')}")


def cmd_increment_fail(args):
    """失败计数 +1"""
    data = _read_current()
    if not data:
        print("❌ 没有进行中的任务", file=sys.stderr)
        sys.exit(1)
    data["failure_count"] = data.get("failure_count", 0) + 1
    reason = args.reason or "未知原因"
    entries = data.get("progress_entries", [])
    entries.append({
        "time": _now(),
        "text": f"⚠️ 失败 #{data['failure_count']}: {reason}"
    })
    data["progress_entries"] = entries
    _write_current(data)
    print(f"⚠️ 失败计数: {data['failure_count']} (原因: {reason})")


def cmd_complete(args):
    """标记完成，归档"""
    data = _read_current()
    if not data:
        print("ℹ️ 没有进行中的任务")
        return
    entries = data.get("progress_entries", [])
    entries.append({"time": _now(), "text": f"✅ 完成: {args.result or '任务结束'}"})
    data["progress_entries"] = entries
    data["phase"] = "完成"
    _archive(data, reason="completed", result=args.result)
    CURRENT_TASK_FILE.unlink()
    print(f"✅ 任务已完成并归档: {data.get('task_id')}")


def cmd_current(args):
    """查看当前任务"""
    data = _read_current()
    if not data:
        if args.json:
            print(json.dumps({"active": False}, ensure_ascii=False, indent=2))
        else:
            print("ℹ️ 没有进行中的任务")
        return
    if args.json:
        out = {"active": True}
        # 只输出元数据 + 最近 5 条进度，避免输出过大
        out.update({k: v for k, v in data.items() if k != "progress_entries" and k != "body"})
        entries = data.get("progress_entries", [])
        out["progress_entries_total"] = len(entries)
        out["progress_entries_recent"] = entries[-5:] if entries else []
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"任务: {data.get('name')} ({data.get('task_id')})")
        print(f"阶段: {data.get('phase')}")
        print(f"步骤: {data.get('step_index', 0)}/{data.get('total_steps', '?')}")
        print(f"失败次数: {data.get('failure_count', 0)}")
        print(f"最后更新: {data.get('last_updated')}")
        entries = data.get("progress_entries", [])
        if entries:
            print(f"\n最近进度:")
            for e in entries[-5:]:
                print(f"  - [{e.get('time')}] {e.get('text')}")


def main():
    parser = argparse.ArgumentParser(description="Task Tracker — current-task.md 断点记忆")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p = subparsers.add_parser("start", help="开始新任务")
    p.add_argument("--task-id", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--phase", default="启动")
    p.add_argument("--steps", default="[]", help="JSON 数组")

    p = subparsers.add_parser("update", help="更新进度")
    p.add_argument("--phase")
    p.add_argument("--step-index", type=int)
    p.add_argument("--progress", help="进度说明（追加）")

    p = subparsers.add_parser("increment-fail", help="失败计数 +1")
    p.add_argument("--reason", default="未知原因")

    p = subparsers.add_parser("complete", help="完成并归档")
    p.add_argument("--result", default="")

    p = subparsers.add_parser("current", help="查看当前任务")
    p.add_argument("--json", action="store_true")

    args = parser.parse_args()

    if args.command == "start":
        cmd_start(args)
    elif args.command == "update":
        cmd_update(args)
    elif args.command == "increment-fail":
        cmd_increment_fail(args)
    elif args.command == "complete":
        cmd_complete(args)
    elif args.command == "current":
        cmd_current(args)


if __name__ == "__main__":
    main()
