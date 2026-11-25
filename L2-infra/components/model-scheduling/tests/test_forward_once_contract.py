#!/usr/bin/env python3
"""proxy.py `_forward_once` 返回值契约回归（2026-11-25）。

事故：provider key 缺失时 `_forward_once` 走
    `await self._send_error(...); return`
→ 返回 **None**，而调用方是三元组解包
    `success, status_code, result = await self._forward_once(...)`
→ TypeError: cannot unpack non-iterable NoneType object
→ 被 handle_request 外层 catch 成「请求处理失败」，**fallback 链不再重试**。

v1.1 给该函数包了准入闸门，若同一处再崩会直接击穿闸门上下文，故必须锁死契约：
任何分支都必须返回 (success, status_code, result)。
"""
import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import proxy  # noqa: E402


class _FakeWriter:
    """最小 writer：记录写入、async drain。"""

    def __init__(self):
        self.buf = bytearray()
        self.closed = False

    def write(self, data):
        self.buf.extend(data)

    async def drain(self):
        return None

    def close(self):
        self.closed = True

    async def wait_closed(self):
        return None


def _make_handler():
    """构造 handler，但不真正建立 aiohttp 连接池（无事件循环环境下也能用）。"""
    with patch.object(proxy.aiohttp, "ClientSession"):
        h = proxy.ProxyHandler()
    h.session = None
    return h


class TestForwardOnceContract(unittest.IsolatedAsyncioTestCase):
    """`_forward_once` 所有出口都必须返回三元组。"""

    async def test_missing_api_key_returns_triple_not_none(self):
        h = _make_handler()
        w = _FakeWriter()
        with patch.object(proxy, "get_api_key", return_value=""):
            ret = await h._forward_once(
                {"messages": []}, {"id": "p/m", "provider": "nope"},
                {}, stream=False, writer=w,
            )
        self.assertIsInstance(ret, tuple, "返回 None 会让调用方解包崩溃")
        self.assertEqual(len(ret), 3)
        success, status, result = ret
        self.assertFalse(success)
        self.assertEqual(status, 500)
        self.assertIn("API key", str(result))

    async def test_error_response_written_before_return(self):
        """错误既要写给客户端，也要返回给调用方（二者缺一不可）。"""
        h = _make_handler()
        w = _FakeWriter()
        with patch.object(proxy, "get_api_key", return_value=""):
            await h._forward_once(
                {"messages": []}, {"id": "p/m", "provider": "nope"},
                {}, stream=False, writer=w,
            )
        self.assertIn(b"500", bytes(w.buf), "未向客户端写出错误状态")


class TestHandleChatSurvivesKeyFailure(unittest.IsolatedAsyncioTestCase):
    """端到端：key 缺失不应把异常抛到 handle_request（否则 fallback 失效）。"""

    async def test_no_exception_propagates(self):
        h = _make_handler()
        w = _FakeWriter()
        request = {"model": "p/m", "messages": [{"role": "user", "content": "hi"}],
                   "stream": False}
        models_config = {"models": [{"id": "p/m", "provider": "nope",
                                     "status": "active", "context_window": 1000}]}
        provs_config = {"providers": {"nope": {"enabled": True, "base_url": "http://x"}}}
        # gate 旁路，避免引入等待
        h.gate.enabled = False
        with patch.object(proxy, "estimate_tokens", return_value=10), \
             patch.object(proxy.watcher, "get", side_effect=lambda n: {
                 "models.yaml": models_config, "providers.yaml": provs_config,
                 "routing.yaml": {}}.get(n, {})), \
             patch.object(proxy, "build_fallback_chain",
                          return_value=[{"id": "p/m", "provider": "nope"}]), \
             patch.object(proxy, "get_api_key", return_value=""), \
             patch.object(proxy, "_get_provider_health", return_value="unknown"):
            try:
                await h._handle_chat(__import__("json").dumps(request).encode(), w)
            except Exception as e:  # noqa: BLE001
                self.fail(f"_handle_chat 抛出异常（说明契约仍被破坏）: {e!r}")


if __name__ == "__main__":
    unittest.main()
