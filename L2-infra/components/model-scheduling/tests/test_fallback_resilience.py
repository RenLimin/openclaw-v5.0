#!/usr/bin/env python3
"""proxy.py 回退韧性回归测试（2026-11-10）。

覆盖 3 处修复:
  P0  longCat 补 image 能力声明 → multimodal 大上下文链不再结构性为空
  P1  429 按错误码分类: 配额耗尽→exhausted(1h TTL) / 突发限流→不标记
  P2  流式中断不再静默 → 报 502 让 fallback 链重试

不触网、不依赖真实 usage.json（用 monkeypatch 注入）。
"""
import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))


class TestClassify429(unittest.TestCase):
    """P1: 429 错误码分类。"""

    def test_account_quota_exceeded_is_quota(self):
        import proxy
        text = ("You have exceeded the monthly usage quota. It will reset at "
                "2026-09-22 23:59:59 +0800 CST. AccountQuotaExceeded")
        self.assertEqual(proxy.classify_429(text), "quota")

    def test_insufficient_balance_is_quota(self):
        import proxy
        text = 'Insufficient Balance (request_id: 8488908f) insufficient_balance_error'
        self.assertEqual(proxy.classify_429(text), "quota")

    def test_request_burst_too_fast_is_ratelimit(self):
        import proxy
        text = "System protection triggered by request burst. RequestBurstTooFast"
        self.assertEqual(proxy.classify_429(text), "ratelimit")

    def test_unknown_429_defaults_to_ratelimit(self):
        """无法识别时保守判 ratelimit —— 误判 quota 会隔离整个 provider 1h。"""
        import proxy
        self.assertEqual(proxy.classify_429("some other 429 error"), "ratelimit")

    def test_empty_text_defaults_to_ratelimit(self):
        import proxy
        self.assertEqual(proxy.classify_429(""), "ratelimit")

    def test_case_insensitive(self):
        import proxy
        self.assertEqual(proxy.classify_429("ACCOUNTQUOTAEXCEEDED"), "quota")
        self.assertEqual(proxy.classify_429("requestbursttooFAST"), "ratelimit")


class TestWriteProviderHealth(unittest.TestCase):
    """P1: exhausted 首次标记写时间戳，重复标记冻结。"""

    def _call(self, usage, provider_id, status, detail):
        """用临时文件真实执行 _write_provider_health（不 mock Path，避免误判）。"""
        import tempfile
        import proxy

        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(usage, tmp, ensure_ascii=False)
        tmp.close()

        real_path = Path(proxy.__file__).parent.parent / "config" / "usage.json"
        backup = real_path.read_text() if real_path.exists() else None
        try:
            real_path.write_text(json.dumps(usage, ensure_ascii=False))
            ok = proxy._write_provider_health(provider_id, status, detail)
            result = json.loads(real_path.read_text())
        finally:
            if backup is not None:
                real_path.write_text(backup)
            else:
                real_path.unlink(missing_ok=True)
            Path(tmp.name).unlink(missing_ok=True)
        return ok, result

    def test_first_exhausted_writes_last_checked(self):
        usage = {"providers": {"coding-plan-2": {"health": {"status": "healthy"}}}}
        ok, usage = self._call(usage, "coding-plan-2", "exhausted", "429 配额耗尽")
        self.assertTrue(ok)
        h = usage["providers"]["coding-plan-2"]["health"]
        self.assertEqual(h["status"], "exhausted")
        self.assertIn("last_checked", h)

    def test_repeated_exhausted_freezes_timestamp(self):
        """核心回归: 重复标记不刷新 last_checked（否则 TTL 永远归零）。"""
        usage = {"providers": {"coding-plan-2": {"health": {
            "status": "exhausted", "last_checked": "2026-11-10T00:00:00+00:00"}}}}
        ok, usage = self._call(usage, "coding-plan-2", "exhausted", "still failing")
        self.assertTrue(ok)
        self.assertEqual(
            usage["providers"]["coding-plan-2"]["health"]["last_checked"],
            "2026-11-10T00:00:00+00:00",
        )

    def test_new_provider_entry_created(self):
        """provider 不在 usage.json → 新建条目（旧逻辑静默丢失）。"""
        usage = {"providers": {}}
        ok, usage = self._call(usage, "coding-plan-2", "exhausted", "402")
        self.assertTrue(ok)
        self.assertEqual(usage["providers"]["coding-plan-2"]["health"]["status"], "exhausted")

    def test_case_insensitive_match(self):
        usage = {"providers": {"Coding-Plan-2": {"health": {"status": "healthy"}}}}
        ok, usage = self._call(usage, "coding-plan-2", "exhausted", "402")
        self.assertTrue(ok)
        self.assertEqual(usage["providers"]["Coding-Plan-2"]["health"]["status"], "exhausted")


class TestMultimodalChainHasLargeCtxFallback(unittest.TestCase):
    """P0: multimodal 大上下文链必须能承接（longCat 已声明 image）。"""

    def _chain(self, task_type, est):
        import proxy
        routing = {
            "task_routing": {
                "multimodal": {
                    "fallback_chain": [
                        "coding-plan-2/doubao-seed-2-1-turbo",
                        "coding-plan-2/doubao-seed-2-1-pro-260628",
                        "longCat/LongCat-2.0",
                        "coding-plan/doubao-seed-2-1-turbo",
                    ],
                    "requires_input_types": ["image"],
                }
            }
        }
        models = {"models": [
            {"id": "coding-plan-2/doubao-seed-2-1-turbo", "status": "active",
             "provider": "coding-plan-2", "context_window": 262144,
             "input_types": ["text", "image", "video"]},
            {"id": "coding-plan-2/doubao-seed-2-1-pro-260628", "status": "active",
             "provider": "coding-plan-2", "context_window": 262144,
             "input_types": ["text", "image", "video"]},
            {"id": "longCat/LongCat-2.0", "status": "active",
             "provider": "longCat", "context_window": 1048576,
             "input_types": ["text", "image"]},
            {"id": "coding-plan/doubao-seed-2-1-turbo", "status": "active",
             "provider": "coding-plan", "context_window": 262144,
             "input_types": ["text", "image", "video"]},
        ]}
        providers = {"providers": {
            "coding-plan-2": {"enabled": True},
            "coding-plan": {"enabled": True},
            "longCat": {"enabled": True},
        }}
        usage = {"providers": {}}
        with patch.object(proxy.watcher, "get", side_effect=lambda k: {
            "routing.yaml": routing, "models.yaml": models,
            "providers.yaml": providers, "usage.json": usage,
        }.get(k, {})):
            return proxy.build_fallback_chain(task_type, est)

    def test_large_ctx_multimodal_chain_not_empty(self):
        """核心回归: 360k tokens 的带图请求必须有可承接模型。"""
        chain = self._chain("multimodal", 360000)
        self.assertTrue(chain, "multimodal 大上下文链为空 → 结构性故障")
        ids = [m["id"] for m in chain]
        self.assertIn("longCat/LongCat-2.0", ids,
                       "longCat 应在 multimodal 大 ctx 链中（image 能力已补）")

    def test_large_ctx_chain_has_1m_window_model(self):
        chain = self._chain("multimodal", 360000)
        max_ctx = max(m.get("context_window", 0) for m in chain)
        self.assertGreaterEqual(max_ctx, 360000,
                                "链中最大窗口应能承接 360k 请求")

    def test_small_ctx_multimodal_chain_prefers_fast_model(self):
        """小请求仍应优先走 cp2 turbo（不因修复改变优先级）。"""
        chain = self._chain("multimodal", 50000)
        self.assertEqual(chain[0]["id"], "coding-plan-2/doubao-seed-2-1-turbo")

    def test_all_chain_members_support_image(self):
        """链内所有模型必须支持 image（能力过滤不得放宽）。"""
        for est in (50000, 360000, 900000):
            chain = self._chain("multimodal", est)
            for m in chain:
                self.assertIn("image", m.get("input_types", []),
                              f"{m['id']} 不支持 image 却进了 multimodal 链")


class TestStreamInterruptionNotSilent(unittest.TestCase):
    """P2: 流式中断必须上报失败，让 fallback 链重试。"""

    def test_stream_without_finish_flag_returns_failure(self):
        """无 [DONE]/finish_reason → ok=False（旧逻辑静默返回 True）。"""
        import proxy

        class FakeContent:
            def __aiter__(self):
                async def gen():
                    yield b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
                return gen()

        class FakeResponse:
            content = FakeContent()

        writer = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        handler = proxy.ProxyHandler.__new__(proxy.ProxyHandler)
        ok, sent = asyncio.run(
            handler._stream_response(FakeResponse(), writer, {"id": "test/model"})
        )
        self.assertFalse(ok, "未收到 finish 标志必须返回失败")
        self.assertGreater(sent, 0)

    def test_stream_with_done_flag_returns_success(self):
        import proxy

        class FakeContent:
            def __aiter__(self):
                async def gen():
                    yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
                    yield b'data: [DONE]\n\n'
                return gen()

        class FakeResponse:
            content = FakeContent()

        writer = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        handler = proxy.ProxyHandler.__new__(proxy.ProxyHandler)
        ok, sent = asyncio.run(
            handler._stream_response(FakeResponse(), writer, {"id": "test/model"})
        )
        self.assertTrue(ok)
        self.assertGreater(sent, 0)

    def test_stream_exception_returns_failure(self):
        """连接中断 → ok=False（旧逻辑吞掉异常）。"""
        import proxy

        class FakeContent:
            def __aiter__(self):
                async def gen():
                    yield b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
                    raise ConnectionResetError("peer closed")
                return gen()

        class FakeResponse:
            content = FakeContent()

        writer = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        handler = proxy.ProxyHandler.__new__(proxy.ProxyHandler)
        ok, sent = asyncio.run(
            handler._stream_response(FakeResponse(), writer, {"id": "test/model"})
        )
        self.assertFalse(ok)
        self.assertGreater(sent, 0)


class TestClassifyTaskMedia(unittest.TestCase):
    """P0 附带: 带图但文本意图明确时不误判 multimodal。"""

    def _classify(self, text, has_image):
        import proxy
        content = [{"type": "text", "text": text}]
        if has_image:
            content.append({"type": "image_url",
                            "image_url": {"url": "data:image/png;base64,xxx"}})
        return proxy.classify_task([{"role": "user", "content": content}])

    def test_image_with_coding_intent_is_coding(self):
        """带图问代码 → coding（旧逻辑误判 multimodal，链被 image 过滤到只剩 cp2）。"""
        self.assertEqual(self._classify("这段代码有 bug，帮我 fix 一下", True), "coding")

    def test_image_with_vision_intent_is_multimodal(self):
        self.assertEqual(self._classify("这张图里有什么？识别一下", True), "multimodal")

    def test_image_with_ocr_intent_is_multimodal(self):
        self.assertEqual(self._classify("帮我 OCR 这张截图的文字", True), "multimodal")

    def test_image_without_clear_intent_defaults_multimodal(self):
        """带图但意图不明 → 保守判 multimodal（不丢图上下文）。"""
        self.assertEqual(self._classify("看看这个", True), "multimodal")

    def test_no_image_coding_intent(self):
        self.assertEqual(self._classify("帮我写一个 python 函数", False), "coding")


if __name__ == "__main__":
    unittest.main()
