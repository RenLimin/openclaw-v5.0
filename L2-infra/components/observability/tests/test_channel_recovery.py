#!/usr/bin/env python3
"""channel_recovery 单元测试 — 判定、节流、解析、环境注入。"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

COMP_DIR = Path(__file__).resolve().parent.parent
SCRIPT = COMP_DIR / "scripts" / "channel_recovery.py"

spec = importlib.util.spec_from_file_location("channel_recovery", SCRIPT)
cr = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(cr)

CST = timezone(timedelta(hours=8))
NOW = datetime(2026, 11, 17, 14, 30, tzinfo=CST).timestamp()


def _ts(dt: datetime) -> float:
    return dt.replace(tzinfo=CST).timestamp()


# --------------------------------------------------------------------------
# 环境注入
# --------------------------------------------------------------------------

def test_ensure_env_injects_homebrew_path():
    os.environ["PATH"] = "/usr/gnu/bin:/usr/local/bin:/bin:/usr/bin"
    env = cr.ensure_env()
    parts = env["PATH"].split(":")
    assert parts[0] == "/opt/homebrew/bin"
    assert parts[1] == "/opt/homebrew/sbin"


def test_ensure_env_preserves_existing_path():
    os.environ["PATH"] = "/Users/x/bin:/usr/bin"
    env = cr.ensure_env()
    assert "/Users/x/bin" in env["PATH"].split(":")
    assert "/usr/bin" in env["PATH"].split(":")


# --------------------------------------------------------------------------
# 事件解析
# --------------------------------------------------------------------------

SAMPLE = """\
2026-11-17T08:11:31.100+08:00 [wecom] [default] Connection lost, reconnecting in 1000ms (attempt 1/10)...
2026-11-17T08:11:32.200+08:00 [wecom] [default] WebSocket error: getaddrinfo ENOTFOUND openws.work.weixin.qq.com
2026-11-17T08:12:00.300+08:00 [wecom] [other] Authentication successful
2026-11-17T08:15:09.400+08:00 [wecom] [default] Authentication successful
2026-11-17T08:16:00.500+08:00 [wecom] [default] Max reconnect attempts reached (10), giving up
2026-11-17T08:17:00.600+08:00 [wecom] [default] Connecting to WebSocket: wss://openws.work.weixin.qq.com...
2026-11-17T08:18:00.700+08:00 [wecom-cli:tool] registerTool ctx: sessionKey="agent:main:main"
not-a-timestamp line
"""


def test_parse_events_filters_account_and_kinds():
    events = cr.parse_events(SAMPLE)
    kinds = [k for _, k in events]
    assert kinds.count("auth_ok") == 1          # 只取 default，排除 other
    assert kinds.count("conn_lost") == 1
    assert kinds.count("gave_up") == 1
    assert kinds.count("reconnect") == 1
    assert all(k != "other" for _, k in events)
    # 非 channel 行、无时间戳行被忽略
    assert len(events) == 4


def test_parse_events_empty_on_no_match():
    assert cr.parse_events("") == []
    assert cr.parse_events("garbage\nmore garbage") == []


def test_classify_variants():
    assert cr._classify("giving up after 10 restart attempts") == "gave_up"
    assert cr._classify("Max reconnect attempts reached (10), giving up") == "gave_up"
    assert cr._classify("WebSocket disconnected: code: 1006") == "conn_lost"
    assert cr._classify("Connection lost, reconnecting in 30000ms") == "conn_lost"
    assert cr._classify("Authentication successful") == "auth_ok"
    assert cr._classify("registerTool ctx") is None


def test_apply_events_sets_down_since_on_first_failure():
    state = {"last_auth_ok": 100.0}
    cr.apply_events(state, [(110.0, "conn_lost"), (120.0, "reconnect")])
    assert state["down_since"] == 110.0


def test_apply_events_clears_down_since_on_auth():
    state = {"last_auth_ok": 100.0, "down_since": 110.0}
    cr.apply_events(state, [(130.0, "auth_ok")])
    assert state["down_since"] is None


def test_reconnect_alone_does_not_open_down_since():
    # 正常建连流程中 auth 之后会紧跟 Connecting to WebSocket，
    # 若把 reconnect 当失败会导致健康期被误判 down
    state = {"last_auth_ok": 100.0}
    cr.apply_events(state, [(110.0, "reconnect")])
    assert state.get("down_since") is None
    assert cr.evaluate(state, {}, 150.0) == "up"


def test_apply_events_keeps_max():
    state = {"last_auth_ok": 1.0, "last_conn_lost": 5.0}
    cr.apply_events(state, [(3.0, "auth_ok"), (2.0, "conn_lost"), (9.0, "conn_lost")])
    assert state["last_auth_ok"] == 3.0
    assert state["last_conn_lost"] == 9.0


# --------------------------------------------------------------------------
# 判定
# --------------------------------------------------------------------------

def test_evaluate_up_when_no_failure_since_auth():
    state = {"last_auth_ok": NOW - 60, "last_conn_lost": NOW - 120, "down_since": None}
    assert cr.evaluate(state, None, NOW) == "up"


def test_evaluate_down_when_streak_exceeds_stable_period():
    # 断连持续 900s（>= STABLE 600s）
    state = {"last_auth_ok": NOW - 900, "last_conn_lost": NOW - 900, "down_since": NOW - 900}
    assert cr.evaluate(state, None, NOW) == "down"


def test_evaluate_down_unstable_within_stable_window():
    # 断连持续 10s（< STABLE 600s）
    state = {"last_auth_ok": NOW - 900, "last_conn_lost": NOW - 10, "down_since": NOW - 10}
    assert cr.evaluate(state, None, NOW) == "down-unstable"


def test_evaluate_up_when_idle_even_after_long_silence():
    # 安静是正常态：自上次鉴权后无失败 → 健康，不因静默时长判 stale
    state = {"last_auth_ok": NOW - 7200, "down_since": None}
    assert cr.evaluate(state, None, NOW) == "up"


def test_evaluate_stale_when_down_streak_goes_silent():
    # streak 已持续且日志再无动静 → 无法确认现状，不动作
    state = {"last_auth_ok": NOW - 7200, "down_since": NOW - 7200,
             "last_conn_lost": NOW - 7200, "last_reconnect": NOW - 7200}
    assert cr.evaluate(state, None, NOW) == "stale"


def test_evaluate_unknown_without_baseline():
    assert cr.evaluate({}, None, NOW) == "unknown"


def test_status_fallback_flags_down_after_two_streaks():
    state = {"status_down_streak": 0}
    status = {"account": {"running": False, "lastError": "ENOTFOUND"}}
    assert cr._evaluate_status_fallback(state, status, NOW) == "unknown"
    assert cr._evaluate_status_fallback(state, status, NOW) == "down"


def test_status_fallback_recovers_on_healthy():
    state = {"status_down_streak": 1}
    status = {"account": {"running": True, "lastError": None}}
    assert cr._evaluate_status_fallback(state, status, NOW) == "unknown"
    assert state["status_down_streak"] == 0


# --------------------------------------------------------------------------
# 节流与决策
# --------------------------------------------------------------------------

def test_decide_action_none_when_up():
    state = {}
    assert cr.decide_action(state, "up", None, NOW)[0] == "none"


def test_decide_action_light_when_down():
    state = {"light_day": "2026-11-17", "light_count": 0, "consecutive_light_failures": 0}
    action, _ = cr.decide_action(state, "down", None, NOW)
    assert action == "light"


def test_decide_action_skip_in_cooldown():
    state = {"last_recovery_at": NOW - 100}
    action, reason = cr.decide_action(state, "down", None, NOW)
    assert action == "skip"
    assert "cooldown" in reason


def test_decide_action_skip_on_fresh_last_start():
    state = {}
    status = {"account": {"lastStartAt": int((NOW - 30) * 1000)}}
    assert cr.decide_action(state, "down", status, NOW)[0] == "skip"


def test_decide_action_alert_at_daily_cap():
    state = {"light_day": "2026-11-17", "light_count": 5}
    action, reason = cr.decide_action(state, "down", None, NOW)
    assert action == "alert"
    assert "cap" in reason


def test_decide_action_full_after_two_light_failures():
    state = {"consecutive_light_failures": 2}
    assert cr.decide_action(state, "down", None, NOW)[0] == "full"


def test_decide_action_resets_daily_counter_on_new_day():
    state = {"light_day": "2026-11-16", "light_count": 5}
    action, _ = cr.decide_action(state, "down", None, NOW)
    assert action == "light"
    assert state["light_day"] == "2026-11-17"
    assert state["light_count"] == 0


def test_decide_action_skips_intentional_stop():
    # 用户手动 stop：running=false 且 stop 晚于上次鉴权 → 不自动拉起
    state = {"last_auth_ok": NOW - 900}
    status = {"account": {"running": False, "lastStopAt": int((NOW - 30) * 1000)}}
    action, reason = cr.decide_action(state, "down", status, NOW)
    assert action == "skip"
    assert "intentional" in reason


def test_decide_action_recovers_after_gave_up_even_if_stopped():
    # 插件自身 gave-up（非人为）→ 仍应恢复
    state = {"last_auth_ok": NOW - 900, "last_gave_up": NOW - 60}
    status = {"account": {"running": False, "lastStopAt": int((NOW - 60) * 1000)}}
    action, _ = cr.decide_action(state, "down", status, NOW)
    assert action == "light"


# --------------------------------------------------------------------------
# 端口解析
# --------------------------------------------------------------------------

def test_gateway_port_fallback_on_missing_config(tmp_path, monkeypatch):
    monkeypatch.setattr(cr, "OPENCLAW_CONFIG", tmp_path / "nope.json")
    assert cr.gateway_port() == 18789


def test_gateway_port_reads_config(tmp_path, monkeypatch):
    cfg = tmp_path / "openclaw.json"
    cfg.write_text(json.dumps({"gateway": {"port": 19999}}), encoding="utf-8")
    monkeypatch.setattr(cr, "OPENCLAW_CONFIG", cfg)
    assert cr.gateway_port() == 19999


# --------------------------------------------------------------------------
# 状态读写
# --------------------------------------------------------------------------

def test_state_roundtrip(tmp_path, monkeypatch):
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(cr, "STATE_FILE", state_file)
    cr.save_state({"version": 1, "log_offset": 42})
    assert cr.load_state()["log_offset"] == 42


def test_load_state_tolerates_corruption(tmp_path, monkeypatch):
    state_file = tmp_path / "state.json"
    state_file.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(cr, "STATE_FILE", state_file)
    assert cr.load_state() == {"version": 1}
