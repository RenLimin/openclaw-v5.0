"""wecom/通道运行时探针回归测试。

背景（2026-11-26 wecom 稳定性审计）：health_check.py 的 wecom-status 原先只读
`openclaw channels list` 的静态配置态——实测断连 1 小时后仍报 pass。
本测试锁住新的运行时口径（gateway call channels.status → running/lastError），
并保留「RPC 不可用时不误报」的保守语义。
"""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "health_check.py"


def _load():
    spec = importlib.util.spec_from_file_location("health_check", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_pass_when_running_without_error():
    mod = _load()
    payload = {
        "channels": {
            "wecom": {"configured": True, "running": True, "lastStartAt": 1795663969043, "lastError": None},
        }
    }
    probes = dict((n, (s, d)) for n, s, d in mod.runtime_channel_probes(payload))
    assert probes["wecom-runtime"][0] == "pass", probes


def test_fail_when_not_running():
    mod = _load()
    payload = {
        "channels": {
            "wecom": {"configured": True, "running": False, "lastError": None},
        }
    }
    probes = dict((n, (s, d)) for n, s, d in mod.runtime_channel_probes(payload))
    assert probes["wecom-runtime"][0] == "fail", probes


def test_fail_when_last_error_present():
    mod = _load()
    payload = {
        "channels": {
            "wecom": {"configured": True, "running": True, "lastError": "ENOTFOUND openws.work.weixin.qq.com"},
        }
    }
    probes = dict((n, (s, d)) for n, s, d in mod.runtime_channel_probes(payload))
    status, detail = probes["wecom-runtime"]
    assert status == "fail", probes
    assert "ENOTFOUND" in detail, detail


def test_rpc_unavailable_is_skip_not_fail():
    mod = _load()
    probes = mod.runtime_channel_probes(None)
    assert all(s == "skip" for _, s, _ in probes), probes


def test_unconfigured_is_warn():
    mod = _load()
    payload = {"channels": {"wecom": {"configured": False}}}
    probes = dict((n, (s, d)) for n, s, d in mod.runtime_channel_probes(payload))
    assert probes["wecom-runtime"][0] == "warn", probes


def test_parse_gateway_call_json_handles_prefix_line():
    mod = _load()
    out = "Gateway call: channels.status\n{\"ts\": 1, \"channels\": {}}"
    payload = mod.parse_gateway_call_json(out)
    assert isinstance(payload, dict), payload
    assert payload.get("ts") == 1


def test_parse_gateway_call_json_returns_none_on_garbage():
    mod = _load()
    assert mod.parse_gateway_call_json("no json here") is None
    assert mod.parse_gateway_call_json("") is None


if __name__ == "__main__":
    import sys

    failures = 0
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        try:
            fn()
            print(f"✅ {fn.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"❌ {fn.__name__}: {exc}")
    print("全部通过" if not failures else f"{failures} 个失败")
    sys.exit(1 if failures else 0)
