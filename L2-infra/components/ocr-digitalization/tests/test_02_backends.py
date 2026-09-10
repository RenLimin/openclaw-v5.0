"""
测试 2: 后端自动发现与选择

覆盖：
- OCRBackend 基类接口
- 后端注册与发现
- 后端优先级排序
- 语言支持检测
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from ocr_engine.backends.base import OCRBackend
from ocr_engine.backends import (
    register_backend, get_backend_class, list_available_backends,
    _BACKEND_REGISTRY,
)


class TestBackendBase:
    def test_abstract_class(self):
        # 不能直接实例化抽象基类
        import abc
        assert abc.ABC in OCRBackend.__bases__ or hasattr(OCRBackend, '__abstractmethods__')
        # recognize 应该是抽象方法
        assert 'recognize' in OCRBackend.__abstractmethods__

    def test_default_values(self):
        # 创建一个简单的具体子类来测试基类功能
        class SimpleBackend(OCRBackend):
            name = "test"
            def recognize(self, image):
                return []

        b = SimpleBackend()
        assert b.available() is False
        assert b.name == "test"


class TestBackendRegistry:
    def test_register_and_get(self):
        @register_backend("test_dummy")
        class DummyBackend(OCRBackend):
            name = "test_dummy"
            def recognize(self, image):
                return []

        assert "test_dummy" in list_available_backends()
        cls = get_backend_class("test_dummy")
        assert cls is not None
        assert cls.name == "test_dummy"

    def test_get_nonexistent(self):
        cls = get_backend_class("definitely_not_exist_xyz")
        assert cls is None


class TestMockBackend:
    """使用 conftest 中的 mock backend 测试"""

    def test_mock_backend_lifecycle(self, mock_backend_class):
        mock_backend_class.set_should_fail(False)
        mock_backend_class.set_mock_results([])

        b = mock_backend_class()
        assert b.available() is False

        success = b.load("chi_sim+eng")
        assert success is True
        assert b.available() is True

        b.unload()
        assert b.available() is False

    def test_mock_backend_recognize(self, mock_backend_class, simple_mock_results):
        mock_backend_class.set_should_fail(False)
        mock_backend_class.set_mock_results(simple_mock_results)

        b = mock_backend_class()
        b.load()

        from PIL import Image
        img = Image.new("RGB", (100, 100))
        results = b.recognize(img)

        assert len(results) == 3
        assert results[0][1] == "这是第一行文字"
        assert results[0][2] == 0.95

    def test_mock_backend_fail_load(self, mock_backend_class):
        mock_backend_class.set_should_fail(True)

        b = mock_backend_class()
        success = b.load()
        assert success is False
        assert b.available() is False

    def test_mock_backend_info(self, mock_backend_class):
        mock_backend_class.set_should_fail(False)
        b = mock_backend_class()
        b.load("eng")

        info = b.info()
        assert info["name"] == "mock"
        assert info["loaded"] is True
        assert info["lang"] == "eng"
        assert info["priority"] == 10

    def test_mock_backend_supports_lang(self, mock_backend_class):
        b = mock_backend_class()
        # 默认 supports_languages 为空，支持所有语言
        assert b.supports_lang("chi_sim+eng") is True
        assert b.supports_lang("eng") is True


class TestBackendPriority:
    def test_priority_sorting(self):
        """测试后端按 priority 排序"""
        from ocr_engine.backends import _BACKEND_REGISTRY

        # 先确认注册
        if "pri_test_low" not in _BACKEND_REGISTRY:
            @register_backend("pri_test_low")
            class LowPriBackend(OCRBackend):
                name = "pri_test_low"
                priority = 100
                def recognize(self, image): return []

        if "pri_test_high" not in _BACKEND_REGISTRY:
            @register_backend("pri_test_high")
            class HighPriBackend(OCRBackend):
                name = "pri_test_high"
                priority = 5
                def recognize(self, image): return []

        backends = [cls() for name, cls in _BACKEND_REGISTRY.items()
                    if name.startswith("pri_test_")]
        backends.sort(key=lambda b: b.priority)

        assert len(backends) == 2
        assert backends[0].priority <= backends[-1].priority
        # high priority (lower number) should come first
        high = [b for b in backends if b.name == "pri_test_high"][0]
        low = [b for b in backends if b.name == "pri_test_low"][0]
        assert high.priority < low.priority
