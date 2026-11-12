#!/usr/bin/env python3
"""proxy.py 流式超时回归测试（2026-11-12）。

背景: 2026-11-12 事故 — 长回合（247k ctx → 700KB+ SSE）流式输出超过 120s
被 proxy 用 aiohttp.ClientTimeout(total=120) 主动砍断，gateway 收到半截
tool call → 报 'Provider returned an incomplete or malformed tool call'。

修复: 流式请求改用 ClientTimeout(total=None, sock_connect=30, sock_read=120)
—— 总时长不设限，仅 120s 无数据才判死；非流式请求 total=300。

本测试锁定该契约，防回归。不触网。
"""
import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))


class TestStreamTimeoutConfig(unittest.TestCase):
    """流式/非流式超时参数契约。"""

    def _make_handler(self):
        import proxy
        handler = proxy.ProxyHandler.__new__(proxy.ProxyHandler)
        handler.session = MagicMock()
        return handler

    def _fake_response(self, with_done=True):
        class FakeContent:
            def __aiter__(self):
                async def gen():
                    yield b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
                    if with_done:
                        yield b'data: [DONE]\n\n'
                return gen()

        class FakeResponse:
            status = 200
            content = FakeContent()
            async def text(self):
                return ""
            async def read(self):
                return b'{"choices": [{"message": {"content": "ok"}}]}'
        return FakeResponse()

    def _run_forward(self, stream, response=None):
        """调用 _forward_once 并捕获 ClientTimeout 调用参数。"""
        import proxy

        handler = self._make_handler()
        fake_resp = response or self._fake_response()

        class FakePost:
            def __init__(self, resp):
                self._resp = resp
            async def __aenter__(self):
                return self._resp
            async def __aexit__(self, *args):
                return False

        handler.session.post = MagicMock(return_value=FakePost(fake_resp))
        writer = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        captured = {}
        orig_timeout = proxy.aiohttp.ClientTimeout

        def capture_timeout(**kwargs):
            captured.update(kwargs)
            return orig_timeout(**kwargs)

        with patch.object(proxy, "get_api_key", return_value="fake-key"), \
             patch.object(proxy.aiohttp, "ClientTimeout", side_effect=capture_timeout):
            asyncio.run(handler._forward_once(
                {"messages": [{"role": "user", "content": "hi"}], "stream": stream},
                {"id": "test/model", "model_id": "test-model", "provider": "test"},
                {"base_url": "http://127.0.0.1:1/v1"},
                stream,
                writer,
            ))
        return captured

    def test_stream_timeout_has_no_total_limit(self):
        """流式请求: total 必须为 None（不限制总时长）。"""
        captured = self._run_forward(stream=True)
        self.assertIn("total", captured)
        self.assertIsNone(
            captured["total"],
            "流式请求不能用 total 总时长超时，否则长回合被砍断 → malformed tool call",
        )

    def test_stream_timeout_has_sock_read_idle(self):
        """流式请求: sock_read 空闲超时（120s 无数据才判死）。"""
        captured = self._run_forward(stream=True)
        self.assertEqual(captured.get("sock_read"), 120)

    def test_non_stream_timeout_has_total(self):
        """非流式请求: total=300（保留总时长上限，防悬挂）。"""
        captured = self._run_forward(stream=False)
        self.assertEqual(captured.get("total"), 300)

    def test_stream_no_finish_flag_returns_failure(self):
        """流式无 finish 标志 → ok=False（沿用 2026-11-10 修复语义）。"""
        import proxy

        handler = self._make_handler()
        fake_resp = self._fake_response(with_done=False)

        class FakePost:
            def __init__(self, resp):
                self._resp = resp
            async def __aenter__(self):
                return self._resp
            async def __aexit__(self, *args):
                return False

        handler.session.post = MagicMock(return_value=FakePost(fake_resp))
        writer = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        import proxy
        with patch.object(proxy, "get_api_key", return_value="fake-key"):
            ok, status, result = asyncio.run(handler._forward_once(
                {"messages": [{"role": "user", "content": "hi"}], "stream": True},
                {"id": "test/model", "model_id": "test-model", "provider": "test"},
                {"base_url": "http://127.0.0.1:1/v1"},
                True,
                writer,
            ))
        self.assertFalse(ok)
        self.assertEqual(status, 502)


if __name__ == "__main__":
    unittest.main()
