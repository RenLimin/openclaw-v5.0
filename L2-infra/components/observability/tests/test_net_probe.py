"""net_probe 回归测试。

策略：stub 掉 probe_dns / probe_tcp / probe_tls（collect() 的正下层），
不触碰真实网络与 socket——既确定性强，又贴近「判定与定责线索」这条被测逻辑。

覆盖：
1. 全通 → rc=0 且不落盘 incident
2. 目标 DNS 全挂 → rc=1，hint 落在 a/b 候选之一
3. 内网 DNS 挂 + 公共 DNS 通 → hint 明确指向 (b)
4. 代理死 → hint 指向 (a)
5. collect 自身异常 → rc=2
"""

import contextlib
import importlib.util
import io
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "net_probe.py"


def _load():
    spec = importlib.util.spec_from_file_location("net_probe", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _dns(ok=True, answers=("183.47.120.160",)):
    def fn(host, resolver=None):
        good = ok if "example.com" not in host else True  # control 永远通
        return {
            "resolver": resolver or "default",
            "ok": bool(good),
            "rc": 0 if good else 1,
            "ms": 5.0,
            "answers": list(answers) if good else [],
        }

    return fn


def _tcp(ok=True):
    return lambda ip, port: {"ok": ok, "ms": 5.0}


def _tls(ok=True):
    return lambda ip, port, sni: {"ok": ok, "ms": 9.0}


class _Stub:
    """把 collect() 的三个探针替换为可控实现，并记录 incident 写入。"""

    def __init__(self, mod, *, dns_fn=None, tcp_fn=None, tls_fn=None,
                 proxy_ok=True, raise_exc=None, incident_path=None):
        self.mod = mod
        self.written = []
        mod.probe_dns = dns_fn or _dns()
        mod.probe_tcp = tcp_fn or _tcp()
        mod.probe_tls = tls_fn or _tls()
        if not proxy_ok:
            orig_tcp = mod.probe_tcp

            def tcp(ip, port):
                if port == mod.PROXY_PORT:
                    return {"ok": False, "ms": 5.0}
                return orig_tcp(ip, port)

            mod.probe_tcp = tcp
        mod.write_incident = self.written.append
        if incident_path is not None:
            mod.INCIDENT_FILE = incident_path
        if raise_exc:

            def boom(*a, **k):
                raise raise_exc

            mod.collect = boom

    def restore(self):
        pass  # 模块每次 _load() 都是新实例，无需还原


def _run(mod, *extra):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mod.main(list(extra))
    return rc, buf.getvalue()


def test_all_green_rc0_no_incident(tmp_path):
    mod = _load()
    stub = _Stub(mod, incident_path=tmp_path / "inc.jsonl")
    rc, out = _run(mod)
    assert rc == 0, out
    assert stub.written == [], stub.written


def test_target_dns_all_fail_is_abnormal(tmp_path):
    mod = _load()
    stub = _Stub(mod, dns_fn=_dns(ok=False), incident_path=tmp_path / "inc.jsonl")
    rc, out = _run(mod, "--json")
    payload = json.loads(out)
    assert rc == 1, rc
    assert payload["failed"], payload
    assert "(a)" in payload["hint"] or "(b)" in payload["hint"], payload["hint"]
    assert len(stub.written) == 1


def test_intranet_fail_public_ok_points_to_b(tmp_path):
    mod = _load()
    orig = _dns()

    def selective(host, resolver=None):
        r = orig(host, resolver)
        if resolver in ("172.16.6.3", "172.16.6.4"):
            return dict(r, ok=False, answers=[], rc=1)
        return r

    _Stub(mod, dns_fn=selective, incident_path=tmp_path / "inc.jsonl")
    rc, out = _run(mod, "--json")
    payload = json.loads(out)
    assert rc == 1, rc
    assert "(b)" in payload["hint"], payload["hint"]


def test_dead_proxy_points_to_a(tmp_path):
    mod = _load()
    _Stub(mod, dns_fn=_dns(ok=False), proxy_ok=False, incident_path=tmp_path / "inc.jsonl")
    rc, out = _run(mod, "--json")
    payload = json.loads(out)
    assert rc == 1, rc
    assert "(a)" in payload["hint"], payload["hint"]


def test_collect_exception_returns_rc2(tmp_path):
    mod = _load()
    _Stub(mod, raise_exc=RuntimeError("boom"), incident_path=tmp_path / "inc.jsonl")
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        rc = mod.main([])
    assert rc == 2, rc


if __name__ == "__main__":
    import tempfile

    failures = 0
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        with tempfile.TemporaryDirectory() as d:
            try:
                fn(Path(d))
                print(f"✅ {fn.__name__}")
            except AssertionError as exc:
                failures += 1
                print(f"❌ {fn.__name__}: {exc}")
    print("全部通过" if not failures else f"{failures} 个失败")
    sys.exit(1 if failures else 0)
