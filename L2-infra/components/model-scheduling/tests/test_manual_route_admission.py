#!/usr/bin/env python3
"""手动路由 provider 准入回归测试（2026-11-25）。

背景：deepseek 余额耗尽（HTTP 402）。此前手动指定模型路径完全不校验
provider enabled/健康状态，导致用户手动指定 deepseek 时反复直撞 402
（11-25 日志两次均属此类）。

v1.2 修复：手动路由与 fallback 链同口径——provider 未启用或健康状态
unreachable/exhausted 时拒绝手动直连，转自动路由。

本测试锁死该行为，防止准入检查被回退。
"""
import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import proxy  # noqa: E402


class TestProviderBlockReason(unittest.TestCase):
    """_provider_block_reason 各分支。"""

    def _provs(self, enabled=True):
        return {"providers": {"deepseek": {"enabled": enabled, "base_url": "http://x"}}}

    def test_disabled_provider_blocked(self):
        with patch.object(proxy, "_get_provider_health", return_value="healthy"):
            r = proxy._provider_block_reason("deepseek", self._provs(enabled=False))
        self.assertIsNotNone(r)
        self.assertIn("禁用", r)

    def test_enabled_healthy_not_blocked(self):
        with patch.object(proxy, "_get_provider_health", return_value="healthy"):
            r = proxy._provider_block_reason("deepseek", self._provs(enabled=True))
        self.assertIsNone(r)

    def test_exhausted_provider_blocked(self):
        with patch.object(proxy, "_get_provider_health", return_value="exhausted"):
            r = proxy._provider_block_reason("deepseek", self._provs(enabled=True))
        self.assertIsNotNone(r)
        self.assertIn("exhausted", r)

    def test_unreachable_provider_blocked(self):
        with patch.object(proxy, "_get_provider_health", return_value="unreachable"):
            r = proxy._provider_block_reason("deepseek", self._provs(enabled=True))
        self.assertIsNotNone(r)

    def test_unknown_provider_not_blocked(self):
        """健康状态 unknown（从未探测）→ 放行，让请求自然暴露问题。"""
        with patch.object(proxy, "_get_provider_health", return_value="unknown"):
            r = proxy._provider_block_reason("deepseek", self._provs(enabled=True))
        self.assertIsNone(r)

    def test_missing_provider_conf_blocked(self):
        """配置缺失 → 拦截（与 fallback 链一致：pconf.get(enabled) 缺失即 False）。"""
        with patch.object(proxy, "_get_provider_health", return_value="healthy"):
            r = proxy._provider_block_reason("deepseek", {"providers": {}})
        self.assertIsNotNone(r)


class _FakeWriter:
    def __init__(self):
        self.buf = bytearray()

    def write(self, data):
        self.buf.extend(data)

    async def drain(self):
        return None

    def close(self):
        pass

    async def wait_closed(self):
        return None


class TestManualRouteAdmission(unittest.IsolatedAsyncioTestCase):
    """手动指定被禁用 provider 的模型 → 应拒绝直连并转自动路由，绝不调 _forward_once。"""

    def _make_handler(self):
        with patch.object(proxy.aiohttp, "ClientSession"):
            h = proxy.ProxyHandler()
        h.session = None
        h.gate.enabled = False
        return h

    def _configs(self, enabled):
        return {
            "models.yaml": {
                "models": [
                    {"id": "deepseek/deepseek-chat", "provider": "deepseek",
                     "status": "active", "context_window": 131072,
                     "input_types": ["text"]}
                ]
            },
            "providers.yaml": {
                "providers": {
                    "deepseek": {"enabled": enabled, "base_url": "http://x"}
                }
            },
            "routing.yaml": {"routing": {}},
        }

    async def test_manual_disabled_provider_not_forwarded(self):
        h = self._make_handler()
        w = _FakeWriter()
        body = ('{"model":"deepseek/deepseek-chat",'
                '"messages":[{"role":"user","content":"hi"}]}').encode()
        cfg = self._configs(enabled=False)

        forwarded = []
        async def fake_forward(request, model, pconf, stream, writer):
            forwarded.append(model.get("id"))

        with patch.object(proxy, "estimate_tokens", return_value=10), \
             patch.object(proxy.watcher, "get", side_effect=lambda n: cfg.get(n, {})), \
             patch.object(proxy, "build_fallback_chain", return_value=[]), \
             patch.object(proxy, "_get_provider_health", return_value="healthy"), \
             patch.object(h, "_forward_once", fake_forward):
            # 自动路由空链 → _send_error 500；无 _forward_once 调用即证明被拦
            with patch.object(h, "_send_error", return_value=None):
                await h._handle_chat(body, w)

        self.assertEqual(forwarded, [],
                         "手动指定被禁用 provider 时不应调用 _forward_once")

    async def test_manual_enabled_provider_forwarded(self):
        h = self._make_handler()
        w = _FakeWriter()
        body = ('{"model":"deepseek/deepseek-chat",'
                '"messages":[{"role":"user","content":"hi"}]}').encode()
        cfg = self._configs(enabled=True)

        forwarded = []
        async def fake_forward(request, model, pconf, stream, writer):
            forwarded.append(model.get("id"))
            return True, 200, {"ok": 1}

        with patch.object(proxy, "estimate_tokens", return_value=10), \
             patch.object(proxy.watcher, "get", side_effect=lambda n: cfg.get(n, {})), \
             patch.object(proxy, "build_fallback_chain", return_value=[]), \
             patch.object(proxy, "_get_provider_health", return_value="healthy"), \
             patch.object(h, "_forward_once", fake_forward):
            await h._handle_chat(body, w)

        self.assertEqual(forwarded, ["deepseek/deepseek-chat"],
                         "provider 启用时应正常手动直连")

    async def test_manual_exhausted_provider_not_forwarded(self):
        """健康状态 exhausted 的手动指定同样拦截（402 后标记 exhausted 的 provider）。"""
        h = self._make_handler()
        w = _FakeWriter()
        body = ('{"model":"deepseek/deepseek-chat",'
                '"messages":[{"role":"user","content":"hi"}]}').encode()
        cfg = self._configs(enabled=True)

        forwarded = []
        async def fake_forward(request, model, pconf, stream, writer):
            forwarded.append(model.get("id"))

        with patch.object(proxy, "estimate_tokens", return_value=10), \
             patch.object(proxy.watcher, "get", side_effect=lambda n: cfg.get(n, {})), \
             patch.object(proxy, "build_fallback_chain", return_value=[]), \
             patch.object(proxy, "_get_provider_health", return_value="exhausted"), \
             patch.object(h, "_forward_once", fake_forward), \
             patch.object(h, "_send_error", return_value=None):
            await h._handle_chat(body, w)

        self.assertEqual(forwarded, [],
                         "exhausted 的手动指定也应被拦截，不再直撞 402")


if __name__ == "__main__":
    unittest.main()
