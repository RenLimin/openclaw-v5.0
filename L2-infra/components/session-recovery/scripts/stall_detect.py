#!/usr/bin/env python3
"""会话"卡住"识别纯函数（P1-b，stdlib 零依赖）。

形态：会话 status 仍为 running（turn 超时后 OpenClaw 不一定标 failed），
但最近一次 turn 以 LLM request timed out / FailoverError 终态，且之后静默
超过阈值——这正是 2026-11-03 本会话的情形，旧 check_and_retry 只认
status=failed + 写死 agent:main:main，因而漏检。

本模块只做"给定日志行"的纯判定，不读文件、不起进程，便于单测；
游标读取与 sessions 状态由 check_and_retry 负责。
"""
import re
from datetime import datetime

# 超时终态签名（高置信）
TIMEOUT_RE = re.compile(
    r"LLM request timed out|FailoverError|failed before reply"
)
# 该会话成功恢复的标志：turn 正常结束 / 新的成功 run / 恢复后继续输出
RECOVERED_RE = re.compile(
    r"embedded run agent end:.*isError=false"
    r"|lane task success|turn complete.*isError=false"
)
TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})")


def _line_ts(line):
    m = TS_RE.match(line)
    if not m:
        return None
    try:
        # 日志带 +08:00 偏移；取前 19 位按本地 naive 解析（日志即本地时间）
        return datetime.fromisoformat(m.group(1))
    except Exception:
        return None


def detect_stall(session_key, log_lines, now, *, silent_min=10):
    """判定某会话是否"running 但 turn 超时卡住"。

    参数：
      session_key: 会话 key（子串匹配日志行中的 sessionKey=）
      log_lines:   自上次扫描以来的新增日志行
      now:         datetime，当前时刻（本地，与日志 naive 时间同基准）
      silent_min:  超时后至少静默多少分钟才判卡住（避免误判正在重试）

    返回 (stalled: bool, evidence: str|None)。

    判据全部满足才 stalled：
      1) 新增行中存在该会话的超时终态行；
      2) 该超时行之后没有成功恢复行；
      3) 距超时行时间戳已静默 >= silent_min。
    """
    key = session_key or ""
    if not key:
        return False, None

    last_timeout_line = None
    last_timeout_ts = None
    recovered_after_timeout = False

    for line in log_lines:
        if key not in line:
            continue
        ts = _line_ts(line)
        if TIMEOUT_RE.search(line):
            last_timeout_line = line.strip()
            last_timeout_ts = ts
            recovered_after_timeout = False  # 新一次超时，重置恢复标记
        elif last_timeout_line is not None and RECOVERED_RE.search(line):
            # 仅当恢复行发生在最近超时之后（靠遍历顺序保证）才算恢复
            recovered_after_timeout = True

    if last_timeout_line is None or recovered_after_timeout:
        return False, None

    # 无时间戳无法判断静默时长：保守不判
    if last_timeout_ts is None:
        return False, None

    silent_sec = (now - last_timeout_ts).total_seconds()
    if silent_sec < silent_min * 60:
        return False, None

    return True, last_timeout_line[:240]


# ── 跨轮状态机：游标每轮只投递一次超时行，故需持久化"未恢复的超时" ──────────
SESSION_KEY_RE = re.compile(r"sessionKey=(\S+)")
SUCCESS_RUN_RE = re.compile(r"embedded run agent end:.*isError=false")


def _extract_session_key(line):
    m = SESSION_KEY_RE.search(line)
    return m.group(1) if m else None


def update_stall_state(state, log_lines):
    """纯函数：用本轮新增日志行更新"各会话未恢复超时"状态。

    state: {session_key: {"last_timeout_ts": "YYYY-MM-DDTHH:MM:SS",
                          "last_timeout_line": str}}
    - 见到该会话超时终态行 → 写入/覆盖（新一次超时）；
    - 见到该会话成功 run 结束行 → 清除（已恢复）。
    返回新的 state（不就地改入参）。
    """
    new_state = dict(state or {})
    for line in log_lines:
        key = _extract_session_key(line)
        if not key:
            continue
        if TIMEOUT_RE.search(line):
            ts = _line_ts(line)
            new_state[key] = {
                "last_timeout_ts": ts.isoformat(timespec="seconds") if ts else None,
                "last_timeout_line": line.strip()[:240],
            }
        elif SUCCESS_RUN_RE.search(line) and key in new_state:
            # 成功 run 结束 = 该会话已从超时中恢复
            new_state.pop(key, None)
    return new_state


def stalled_sessions(state, now, *, silent_min=10):
    """根据持久化状态返回当前确属"卡住"的会话列表 [(key, evidence_line)]。

    条件：存在未恢复超时，且距该超时已静默 >= silent_min。
    无时间戳的条目不判（保守）。
    """
    out = []
    for key, entry in (state or {}).items():
        ts_raw = (entry or {}).get("last_timeout_ts")
        if not ts_raw:
            continue
        try:
            ts = datetime.fromisoformat(ts_raw)
        except Exception:
            continue
        if (now - ts).total_seconds() >= silent_min * 60:
            out.append((key, entry.get("last_timeout_line", "")))
    return out
