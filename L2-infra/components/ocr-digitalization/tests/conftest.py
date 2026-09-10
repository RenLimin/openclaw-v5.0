"""
OCR 组件测试配置

- 提供 mock OCR 后端（session 级注册，避免测试间类对象不一致）
- 提供合成测试图片
- 设置 pytest 路径
"""
import sys
import os
from pathlib import Path

import pytest
import numpy as np
from PIL import Image, ImageDraw, ImageFont


# ---- 路径配置 ----
COMP_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = COMP_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


# ---- Session 级 Mock Backend 注册 ----
@pytest.fixture(scope="session", autouse=True)
def _register_mock_backend():
    """会话开始时注册 mock 后端，会话结束时清理"""
    from ocr_engine.backends import _BACKEND_REGISTRY, register_backend
    from ocr_engine.backends.base import OCRBackend

    class MockOCRBackend(OCRBackend):
        name = "mock"
        priority = 10
        _mock_results = []
        _should_fail = False

        def load(self, lang="chi_sim+eng"):
            if self._should_fail:
                return False
            self._loaded = True
            self._lang = lang
            return True

        def recognize(self, image):
            if self._should_fail:
                return []
            return self._mock_results

    register_backend("mock")(MockOCRBackend)
    yield
    # 清理
    _BACKEND_REGISTRY.pop("mock", None)


@pytest.fixture(autouse=True)
def _reset_mock_state(simple_mock_results):
    """每个测试前重置 mock 后端的状态，确保测试隔离"""
    from ocr_engine.backends import get_backend_class
    cls = get_backend_class("mock")
    if cls is not None:
        cls.set_mock_results = classmethod(lambda c, r: setattr(c, '_mock_results', r))
        cls.set_should_fail = classmethod(lambda c, f: setattr(c, '_should_fail', f))
        cls._mock_results = simple_mock_results
        cls._should_fail = False
    yield


@pytest.fixture
def mock_backend_class():
    """返回 mock 后端类"""
    from ocr_engine.backends import get_backend_class
    return get_backend_class("mock")


@pytest.fixture
def simple_mock_results():
    """简单的 mock 识别结果：3 行文字"""
    return [
        ([[10, 20], [200, 20], [200, 45], [10, 45]], "这是第一行文字", 0.95),
        ([[10, 155], [250, 155], [250, 180], [10, 180]], "This is the second line", 0.92),
        ([[10, 290], [180, 290], [180, 315], [10, 315]], "第三行数字 12345", 0.88),
    ]


# ---- 合成测试图片 ----
@pytest.fixture
def white_image():
    """纯白图片 400x300"""
    return Image.new("RGB", (400, 300), color="white")


@pytest.fixture
def gradient_image():
    """渐变图片（用于清晰度/对比度测试）"""
    arr = np.zeros((300, 400), dtype=np.uint8)
    for i in range(300):
        arr[i, :] = int(i * 255 / 299)
    return Image.fromarray(arr).convert("RGB")


@pytest.fixture
def text_image():
    """带文字的合成图片（用于真实预处理测试）"""
    img = Image.new("RGB", (600, 200), color="white")
    draw = ImageDraw.Draw(img)
    for i, y in enumerate([30, 70, 110, 150]):
        draw.rectangle([20, y, 580, y + 25], fill="black")
    return img


@pytest.fixture
def noisy_image():
    """带噪声的图片（用于去噪测试）"""
    np.random.seed(42)
    arr = np.random.randint(200, 256, (200, 300), dtype=np.uint8)
    noise = np.random.choice([0, 255], size=(200, 300), p=[0.05, 0.95]).astype(np.uint8)
    arr = np.minimum(arr, noise)
    return Image.fromarray(arr).convert("RGB")


@pytest.fixture
def tmp_output_dir(tmp_path):
    """临时输出目录"""
    out = tmp_path / "ocr_output"
    out.mkdir()
    return out
