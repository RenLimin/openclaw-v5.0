#!/usr/bin/env python3
"""黄金基准回放 — 用真实 gateway.log 验证判定与实际故障窗口吻合。

背景（2026-11-17 实际时序）：
  00:21:44 断连 → 00:59:07 恢复
  08:11:31 断连 → 09:15:09 恢复（64min，本次故障）
  10:28:35 断连 → 10:28:36 恢复（1s，自愈）

这些检查点是回归基线：任何判定逻辑改动若与真实故障窗口不符，本测试失败。
日志不存在或非本机时 skip。
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

COMP_DIR = Path(__file__).resolve().parent.parent
SCRIPT = COMP_DIR / "scripts" / "channel_recovery.py"
GATEWAY_LOG = Path.home() / "Library" / "Logs" / "openclaw" / "gateway.log"
TARGET_DAY = "2026-11-17"
CST = timezone(timedelta(hours=8))

spec = importlib.util.spec_from_file_location("channel_recovery", SCRIPT)
cr = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(cr)

CHECKPOINTS = [
    ("07:00:00", "up"),              # 断连前
    ("08:15:00", "down-unstable"),   # 断连后 3.5min
    ("08:25:00", "down"),            # 断连后 13.5min
    ("09:10:00", "down"),            # 恢复前
    ("09:20:00", "up"),              # 恢复后
    ("10:29:00", "up"),              # 秒断已自愈
    ("14:00:00", "up"),              # 当前
]


def _load_day_events() -> list[tuple[float, str]]:
    text = GATEWAY_LOG.read_text(encoding="utf-8", errors="ignore")
    events = cr.parse_events(text)
    return sorted(
        e for e in events
        if datetime.fromtimestamp(e[0], CST).strftime("%Y-%m-%d") == TARGET_DAY
    )


@pytest.fixture(scope="module")
def day_events() -> list[tuple[float, str]]:
    if not GATEWAY_LOG.exists():
        pytest.skip("gateway.log 不存在（非本机环境）")
    events = _load_day_events()
    if len(events) < 20:
        pytest.skip(f"{TARGET_DAY} 事件过少（{len(events)}），基线不适用")
    return events


@pytest.mark.parametrize("hhmmss,expected", CHECKPOINTS)
def test_golden_replay_decision(day_events, hhmmss: str, expected: str):
    t = datetime.strptime(f"{TARGET_DAY}T{hhmmss}", "%Y-%m-%dT%H:%M:%S").replace(tzinfo=CST)
    state: dict = {}
    cr.apply_events(state, [e for e in day_events if e[0] <= t.timestamp()])
    assert cr.evaluate(state, None, t.timestamp()) == expected


def test_recovery_decision_at_down_checkpoint(day_events):
    """down 检查点必须触发轻量恢复（而非无动作/告警）。"""
    t = datetime.strptime(f"{TARGET_DAY}T08:25:00", "%Y-%m-%dT%H:%M:%S").replace(tzinfo=CST)
    state: dict = {}
    cr.apply_events(state, [e for e in day_events if e[0] <= t.timestamp()])
    assert cr.evaluate(state, None, t.timestamp()) == "down"
    action, _ = cr.decide_action(state, "down", None, t.timestamp())
    assert action == "light"


def test_reconnect_events_do_not_corrupt_streak(day_events):
    """10:28:35 秒断自愈后，streak 必须清零（否则健康期被误判 down）。"""
    t = datetime.strptime(f"{TARGET_DAY}T10:29:00", "%Y-%m-%dT%H:%M:%S").replace(tzinfo=CST)
    state: dict = {}
    cr.apply_events(state, [e for e in day_events if e[0] <= t.timestamp()])
    assert state.get("down_since") is None
