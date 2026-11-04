#!/usr/bin/env python3
"""endpoint_probe 单元测试：stdlib http.server 起本地端点，不触网。"""
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS)
import endpoint_probe as ep  # noqa: E402


def make_handler(code=200):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # 静音
            pass

        def do_GET(self):
            self.send_response(code)
            self.end_headers()
            self.wfile.write(b"{}")
    return H


def start_server(code=200):
    srv = HTTPServer(("127.0.0.1", 0), make_handler(code))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


class ProbeEndpointsTest(unittest.TestCase):
    def setUp(self):
        self.srv200 = start_server(200)
        self.srv401 = start_server(401)
        self.b200 = f"http://127.0.0.1:{self.srv200.server_port}/v1"
        self.b401 = f"http://127.0.0.1:{self.srv401.server_port}/v1"

    def tearDown(self):
        self.srv200.shutdown()
        self.srv401.shutdown()

    def _prov(self, base):
        return {"enabled": True, "base_url": base,
                "health_check": {"endpoint": "/models", "timeout_ms": 3000}}

    def test_all_up(self):
        res = ep.probe_endpoints({"a": self._prov(self.b200)})
        self.assertTrue(res["a"]["ok"])
        self.assertEqual(res["a"]["status"], 200)
        self.assertIsNotNone(res["a"]["latency_ms"])

    def test_auth_failure_marked_down(self):
        res = ep.probe_endpoints({"a": self._prov(self.b401)})
        self.assertFalse(res["a"]["ok"])
        self.assertTrue(res["a"]["reachable"], "401 有 HTTP 响应，端点应判 reachable")
        self.assertEqual(res["a"]["status"], 401)

    def test_unreachable_is_down_not_raised(self):
        # 127.0.0.1:1 惯例无服务 → 连接拒绝
        res = ep.probe_endpoints(
            {"a": self._prov("http://127.0.0.1:1/v1")}, timeout=1)
        self.assertFalse(res["a"]["ok"])
        self.assertFalse(res["a"]["reachable"], "连接拒绝应判不可达")
        self.assertTrue(res["a"]["error"])

    def test_summarize_mixed_and_all_down(self):
        providers = {
            "good": self._prov(self.b200),
            "bad": self._prov("http://127.0.0.1:1/v1"),
        }
        res = ep.probe_endpoints(providers, timeout=1)
        all_unreach, any_unreach, total = ep.summarize(res)
        self.assertEqual(total, 2)
        self.assertFalse(all_unreach)
        self.assertTrue(any_unreach)

        res_all = ep.probe_endpoints({"x": self._prov("http://127.0.0.1:1/v1")},
                                     timeout=1)
        self.assertTrue(ep.summarize(res_all)[0])  # 全不可达

    def test_disabled_skipped(self):
        cfg = {"enabled": False, "base_url": self.b200}
        self.assertEqual(ep.probe_endpoints({"a": cfg}), {})


class LoadProvidersTest(unittest.TestCase):
    def test_minimal_parser_fallback(self):
        yaml_text = '''providers:
  coding-plan:
    enabled: true
    base_url: "https://example.com/v3"
  off:
    enabled: false
    base_url: "https://off.example.com"
'''
        # 强制走最小解析器
        provs = ep._parse_providers_minimal(yaml_text)
        self.assertEqual(provs["coding-plan"]["base_url"], "https://example.com/v3")
        self.assertEqual(provs["off"]["enabled"], "false")
        self.assertTrue(ep._truthy(provs["coding-plan"]["enabled"]))
        self.assertFalse(ep._truthy(provs["off"]["enabled"]))

    def test_load_real_config_nonempty(self):
        provs = ep.load_providers()
        # 真实 providers.yaml 至少有 coding-plan / longCat / deepseek
        self.assertGreaterEqual(len(provs), 1)
        self.assertIn("base_url", list(provs.values())[0])


if __name__ == "__main__":
    unittest.main()
