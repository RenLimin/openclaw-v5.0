#!/usr/bin/env python3
"""
Pre-restart safety guard.

Decides whether a Gateway restart is safe *right now*. Exit code:
  0 = safe to restart
  1 = blocked (in-flight critical work); reason printed as JSON
  2 = guard error / indeterminate (fail-closed for --strict)

Checks:
  1. In-flight compaction via ~/.openclaw/state/compaction-state.json
     (maintained by the compaction-guard hook). A `running` marker is only
     honored inside FRESH_WINDOW_SECONDS; older markers are treated as stale.
  2. Very recent compaction failure in the gateway log (last FRESH_WINDOW)
     is reported as a warning, not a hard block — a restart is a valid way to
     clear a wedged engine, but the operator should know.

The guard cannot intercept an internal config-patch auto-restart (OpenClaw has
no external veto point). It is invoked by safe_restart.sh before any
agent-initiated restart, and should be run manually before config edits that
may trigger a restart.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

STATE_FILE = os.path.expanduser("~/.openclaw/state/compaction-state.json")
GATEWAY_LOG = os.path.expanduser("~/Library/Logs/openclaw/gateway.log")
FRESH_WINDOW_SECONDS = 6 * 60  # keep in sync with handler.js FRESH_MS


def _now():
    return datetime.now(timezone.utc)


def _parse_ts(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def check_inflight_compaction():
    """Return (live_keys, stale_keys)."""
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
    except FileNotFoundError:
        return [], []
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"cannot read compaction state: {exc}") from exc

    live, stale = [], []
    running = state.get("running", {}) or {}
    now = _now()
    for key, info in running.items():
        started = _parse_ts((info or {}).get("since"))
        if started is None:
            # Unknown age: treat as live within the safe window, fail toward
            # caution but do not block forever — count it live.
            live.append(key)
            continue
        age = (now - started).total_seconds()
        (live if age <= FRESH_WINDOW_SECONDS else stale).append(key)
    return live, stale


def check_recent_compaction_failure():
    """Return the most recent compaction-timeout line within the window, or None."""
    if not os.path.exists(GATEWAY_LOG):
        return None
    cutoff = _now().timestamp() - FRESH_WINDOW_SECONDS
    pattern = re.compile(r"\[compaction-diag\] end .* outcome=failed")
    latest = None
    try:
        # Tail a bounded slice; the log can be tens of MB.
        import subprocess
        out = subprocess.run(
            ["tail", "-n", "2000", GATEWAY_LOG],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except Exception:
        return None
    for line in out.splitlines():
        if not pattern.search(line):
            continue
        ts = line[:24]
        parsed = _parse_ts(ts)
        if parsed and parsed.timestamp() >= cutoff:
            latest = line.strip()
    return latest


def main():
    strict = "--strict" in sys.argv

    result = {
        "safe": None,
        "inflight_compaction": [],
        "stale_compaction_markers": [],
        "recent_compaction_failure": None,
    }

    try:
        live, stale = check_inflight_compaction()
        result["inflight_compaction"] = live
        result["stale_compaction_markers"] = stale
    except RuntimeError as exc:
        result["error"] = str(exc)
        result["safe"] = False if strict else None
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if strict else 2

    result["recent_compaction_failure"] = check_recent_compaction_failure()

    if live:
        result["safe"] = False
        result["reason"] = (
            f"compaction in progress for {', '.join(live)}; "
            f"restart would interrupt it. Wait for it to finish."
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    result["safe"] = True
    result["reason"] = "no in-flight compaction; safe to restart"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
