"""
测试 6: OCREngine 主类与批量处理

使用 mock backend 测试：
- 引擎初始化与后端加载
- 单图识别
- 批量识别
- 质量评分集成
- 输出格式转换
"""
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pytest
from PIL import Image


@pytest.fixture
def engine_with_mock(mock_backend_class, simple_mock_results):
    """创建一个使用 mock backend 的 OCREngine"""
    from ocr_engine.engine import OCREngine
    from ocr_engine.backends import _BACKEND_REGISTRY, register_backend

    # 注册 mock 后端
    if "mock" not in _BACKEND_REGISTRY:
        register_backend("mock")(mock_backend_class)

    mock_backend_class.set_should_fail(False)
    mock_backend_class.set_mock_results(simple_mock_results)

    from ocr_engine.postprocess import PostprocessConfig
    post_cfg = PostprocessConfig(
        merge_broken=False,  # 测试用：不合并分行，确保 mock 行数不变
    )
    engine = OCREngine(
        backend="mock",
        lang="chi_sim+eng",
        multi_version=False,  # 单版本，更快
        quality_analysis=True,
        postprocess_config=post_cfg,
    )
    return engine


class TestOCREngineInit:
    def test_create_engine(self, mock_backend_class):
        from ocr_engine.engine import OCREngine
        from ocr_engine.backends import _BACKEND_REGISTRY, register_backend

        if "mock" not in _BACKEND_REGISTRY:
            register_backend("mock")(mock_backend_class)

        mock_backend_class.set_should_fail(False)
        mock_backend_class.set_mock_results([])

        engine = OCREngine(backend="mock", multi_version=False)
        assert engine.backend_name == "mock"
        assert engine.lang == "chi_sim+eng"
        assert engine._loaded is False  # 延迟加载

    def test_invalid_backend(self):
        from ocr_engine.engine import OCREngine
        with pytest.raises((ValueError, RuntimeError)):
            engine = OCREngine(backend="definitely_not_a_real_backend_xyz", multi_version=False)
            engine.load()


class TestRecognize:
    def test_recognize_image_object(self, engine_with_mock, white_image):
        result = engine_with_mock.recognize(white_image, preprocess=False)
        assert result.total_pages == 1
        assert result.total_lines == 3
        assert result.confidence > 0

    def test_recognize_image_path(self, engine_with_mock, tmp_path):
        # 保存一个测试图片
        img_path = tmp_path / "test.png"
        Image.new("RGB", (400, 300), "white").save(img_path)

        result = engine_with_mock.recognize(str(img_path), preprocess=False)
        assert result.total_pages == 1
        assert result.total_lines == 3

    def test_recognize_with_preprocess(self, engine_with_mock, white_image):
        result = engine_with_mock.recognize(white_image, preprocess=True)
        assert result.total_pages == 1
        # 预处理后仍能识别（mock 不关心内容）

    def test_result_quality_score(self, engine_with_mock, white_image):
        result = engine_with_mock.recognize(white_image, preprocess=False)
        assert hasattr(result, "quality_score")
        qs = result.quality_score
        assert 0 <= qs.overall <= 100
        # 每页的 quality.details 中有 num_lines
        assert result.pages[0].quality.details["num_lines"] == 3


class TestBatch:
    def test_recognize_batch(self, engine_with_mock, tmp_path):
        # 创建多张测试图片
        paths = []
        for i in range(3):
            p = tmp_path / f"page_{i}.png"
            Image.new("RGB", (400, 300), "white").save(p)
            paths.append(str(p))

        result = engine_with_mock.recognize_batch(paths, preprocess=False)
        assert result.total_pages == 3
        assert result.total_lines == 9  # 3 页 × 3 行
        # 页码应该是连续的
        page_nums = [p.page_num for p in result.pages]
        assert page_nums == [1, 2, 3]

    def test_batch_empty_list(self, engine_with_mock):
        result = engine_with_mock.recognize_batch([], preprocess=False)
        assert result.total_pages == 0


class TestOutputFormats:
    def test_to_text(self, engine_with_mock, white_image):
        result = engine_with_mock.recognize(white_image, preprocess=False)
        text = result.to_text()
        assert isinstance(text, str)
        assert len(text) > 0
        assert "这是第一行文字" in text

    def test_to_markdown(self, engine_with_mock, white_image):
        result = engine_with_mock.recognize(white_image, preprocess=False)
        md = result.to_markdown()
        assert "# OCR" in md
        assert "## 第 1 页" in md
        assert "```text" in md

    def test_to_json(self, engine_with_mock, white_image):
        result = engine_with_mock.recognize(white_image, preprocess=False)
        json_str = result.to_json()
        data = json.loads(json_str)
        assert "pages" in data
        assert "summary" in data
        assert "meta" in data
        assert data["summary"]["total_pages"] == 1
        assert data["summary"]["total_lines"] == 3

    def test_to_dict(self, engine_with_mock, white_image):
        result = engine_with_mock.recognize(white_image, preprocess=False)
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "pages" in d
        assert "meta" in d
        assert "summary" in d


class TestBackendInfo:
    def test_available_backends(self, engine_with_mock):
        engine_with_mock.load()
        backends = engine_with_mock.available_backends
        assert isinstance(backends, list)
        assert "mock" in backends

    def test_get_backend_info(self, engine_with_mock):
        engine_with_mock.load()
        info = engine_with_mock.get_backend_info()
        assert isinstance(info, list)
        assert len(info) >= 1
        assert info[0]["name"] == "mock"
        assert info[0]["loaded"] is True
