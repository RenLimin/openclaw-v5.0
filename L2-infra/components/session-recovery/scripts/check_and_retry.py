#!/usr/bin/env python3
"""
会话失败自动重试检测器

职责：
1. 扫描主会话及其子会话的最近运行状态
2. 检测到失败 + 有未完成 current-task + 失败次数 < 2 → 自动唤醒重试
3. 超过阈值 → 标记 blocked，等人工介入

用法：
    python3 check_and_retry.py                # 检测并自动重试（dry-run）
    python3 check_and_retry.py --apply        # 实际执行重试
    python3 check_and_retry.py --session agent:main:main  # 指定会话

设计原则：
- 最多自动重试 2 次（防止死循环）
- 重试间隔 >= 5 分钟（避免风暴）
- 每次重试前 increment-fail
- 所有操作写入日志：memory/session-retry.log
"""
import json
import os
import sys
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

WORKSPACE = Path("/Users/bangcle/.openclaw/workspace")
TRACKER_SCRIPT = WORKSPACE / "L2-infra/components/session-recovery/scripts/task_tracker.py"
LOG_FILE = WORKSPACE / "memory" / "session-retry.log"

# 配置
MAX_RETRIES = 2
MIN_RETRY_INTERVAL_MIN = 5  # 两次重试最小间隔


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _log(msg):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{_now()}] {msg}\n"
    with open(LOG_FILE, "a") as f:
        f.write(line)
    print(line, end="")


def _run(cmd, timeout=30):
    """运行命令，返回 (stdout, returncode)"""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "TIMEOUT", -1
    except Exception as e:
        return str(e), -1


def get_current_task():
    """读取 current-task，返回 dict 或 None"""
    out, rc = _run(f"python3 {TRACKER_SCRIPT} current --json")
    if rc != 0 or not out:
        return None
    try:
        data = json.loads(out)
        if not data.get("active"):
            return None
        return data
    except json.JSONDecodeError:
        return None


def increment_fail(reason):
    """增加失败计数"""
    _run(f"python3 {TRACKER_SCRIPT} increment-fail --reason '{reason}'")


def check_session_failed(session_key, lookback_minutes=30):
    """检查指定会话最近是否失败。返回 (is_failed, last_error, last_run_at)"""
    # 用 sessions_history 查最近几条消息
    cmd = f"openclaw sessions history --session {session_key} --limit 10 --json 2>/dev/null"
    out, rc = _run(cmd)
    if rc != 0 or not out:
        # 备用：用 sessions list 查 status
        cmd2 = f"openclaw sessions --agent main --json 2>/dev/null"
        out2, rc2 = _run(cmd2)
        if rc2 != 0:
            return False, None, None
        try:
            data = json.loads(out2)
            sessions = data.get("sessions", []) if isinstance(data, dict) else []
            for s in sessions:
                if s.get("key") == session_key:
                    status = s.get("status", "")
                    is_failed = status == "failed" or status == "error"
                    updated_at = s.get("updatedAt", 0) / 1000 if s.get("updatedAt") else None
                    return is_failed, status, updated_at
        except:
            pass
        return False, None, None

    # 解析 sessions_history 输出
    try:
        data = json.loads(out)
        messages = data.get("messages", [])
        cutoff = datetime.now() - timedelta(minutes=lookback_minutes)
        for msg in messages:
            ts = msg.get("timestamp", 0)
            if isinstance(ts, (int, float)) and ts > 0:
                msg_time = datetime.fromtimestamp(ts / 1000 if ts > 1e12 else ts)
                if msg_time < cutoff:
                    continue
            # 检查 stopReason
            openclaw = msg.get("__openclaw", {})
            stop_reason = msg.get("stopReason", "")
            # 检查是否是错误消息
            content = msg.get("content", "")
            if isinstance(content, list):
                for c in content:
                    if c.get("type") == "text" and "The agent run failed" in c.get("text", ""):
                        return True, c["text"][:200], ts / 1000 if ts > 1e12 else ts
            if stop_reason == "error" and msg.get("role") == "assistant":
                return True, f"stopReason=error", ts / 1000 if ts > 1e12 else ts
    except:
        pass
    return False, None, None


def find_failed_sessions():
    """查找所有失败的子会话（主会话派生的）"""
    failed = []
    cmd = "openclaw sessions --agent main --json 2>/dev/null"
    out, rc = _run(cmd)
    if rc != 0:
        return failed
    try:
        data = json.loads(out)
        sessions = data.get("sessions", []) if isinstance(data, dict) else []
        for s in sessions:
            status = s.get("status", "")
            if status in ("failed", "error"):
                key = s.get("key", "")
                name = s.get("displayName") or s.get("label") or key
                updated_at = s.get("updatedAt", 0) / 1000
                failed.append({
                    "key": key,
                    "name": name,
                    "status": status,
                    "updated_at": updated_at,
                })
    except:
        pass
    return failed


def wake_session(session_key, task_info, retry_count, reason):
    """通过 sessions_send 唤醒会话，带上恢复提示"""
    task_name = task_info.get("name", "未完成任务")
    task_id = task_info.get("task_id", "")
    phase = task_info.get("phase", "")
    step = task_info.get("step_index", 0)
    total = task_info.get("total_steps", "?")
    progress_entries = task_info.get("progress_entries_recent", [])
    progress_summary = ""
    if progress_entries:
        # 取最近 3 条
        recent = progress_entries[-3:]
        lines = [f"  - {e.get('text', '')}" for e in recent]
        progress_summary = "\n".join(lines)

    message = f"""⚠️ **自动重试（第 {retry_count} 次）**

检测到上次运行失败，自动恢复未完成任务。

**任务**: {task_name} ({task_id})
**当前阶段**: {phase} (步骤 {step}/{total})
**失败原因**: {reason}

**最近进度**:
{progress_summary}

请从断点继续。current-task.md 已更新失败计数，你可以用以下命令查看：
```
python3 L2-infra/components/session-recovery/scripts/task_tracker.py current
```

继续干活。"""

    cmd = f"openclaw sessions send --session {session_key} --message {json.dumps(message)} 2>/dev/null"
    # 用 sessions_send 工具的等价 CLI 方式
    _log(f"  → 唤醒会话 {session_key} (retry #{retry_count})")
    out, rc = _run(cmd, timeout=15)
    if rc != 0:
        _log(f"  ⚠️ 唤醒失败: {out[:200]}")
        return False
    _log(f"  ✅ 唤醒成功")
    return True


def check_and_retry(apply=False):
    """主流程：检测主会话失败并尝试重试"""
    _log("=== 会话失败检测 ===")

    # 1. 读 current-task
    task = get_current_task()
    if not task:
        _log("ℹ️ 没有进行中的任务，跳过")
        return True

    task_id = task.get("task_id")
    fail_count = task.get("failure_count", 0)
    task_name = task.get("name", "")
    _log(f"📋 当前任务: {task_name} ({task_id}), 已失败 {fail_count} 次")

    # 2. 检查是否已达最大重试次数
    if fail_count >= MAX_RETRIES:
        _log(f"🛑 已达最大重试次数 ({MAX_RETRIES})，停止自动重试，等人工介入")
        return False

    # 3. 检查主会话状态
    main_session = "agent:main:main"
    is_failed, error, last_run = check_session_failed(main_session)

    # 子会话失败只做信息记录，不触发主会话重试
    # （子会话有自己的任务卡，归 taskflow 管）
    failed_subs = find_failed_sessions()
    if failed_subs:
        _log(f"ℹ️ 发现 {len(failed_subs)} 个失败子会话（仅记录，不自动重试）:")
        for s in failed_subs[:5]:
            when = datetime.fromtimestamp(s["updated_at"]).strftime("%H:%M:%S") if s["updated_at"] else "?"
            _log(f"   - {s['name']} status={s['status']}, updated={when}")

    if not is_failed:
        _log("✅ 主会话运行正常，无需重试")
        return True

    # 4. 检查最小间隔（距离上次失败）
    if last_run:
        elapsed = datetime.now().timestamp() - last_run
        if elapsed < MIN_RETRY_INTERVAL_MIN * 60:
            _log(f"⏳ 距上次失败仅 {int(elapsed)}s，小于 {MIN_RETRY_INTERVAL_MIN}min，再等等")
            return True

    # 5. 执行重试
    _log(f"🔄 准备重试（当前失败计数: {fail_count}, 上限: {MAX_RETRIES}）")
    
    if not apply:
        _log("  [dry-run] 跳过实际重试，加 --apply 执行")
        return True

    # 更新失败计数
    fail_reason = error or "检测到会话运行失败"
    increment_fail(fail_reason)
    
    # 唤醒主会话
    task["failure_count"] = fail_count + 1
    wake_session(main_session, task, task["failure_count"], fail_reason)
    
    _log(f"✅ 重试已触发 (第 {task['failure_count']} 次)")
    return True


def main():
    parser = argparse.ArgumentParser(description="会话失败自动重试检测器")
    parser.add_argument("--apply", action="store_true", help="实际执行重试（默认 dry-run）")
    parser.add_argument("--session", default="agent:main:main", help="要检测的会话 key")
    args = parser.parse_args()

    try:
        ok = check_and_retry(apply=args.apply)
        sys.exit(0 if ok else 1)
    except Exception as e:
        _log(f"❌ 检测脚本异常: {e}")
        import traceback
        _log(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
