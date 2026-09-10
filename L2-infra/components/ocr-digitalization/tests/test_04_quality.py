"""
测试 4: 质量评分计算

覆盖：
- 置信度评分
- 文本密度评估
- 布局完整性评估
- 综合质量评分
- 评级（A/B/C/D/F）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from ocr_engine.quality import (
    compute_confidence_score,
    estimate_text_density,
    estimate_layout_completeness,
    compute_quality_score,
    chinese_text_quality,
)
from ocr_engine.types import OCRLine, QualityScore
from PIL import Image


def _make_lines(n=10, conf=0.9, y_step=30):
    """生成测试用行列表"""
    lines = []
    for i in range(n):
        lines.append(OCRLine(
            text=f"第{i+1}行测试文字 content {i+1}",
            bbox=(50.0, 50.0 + i * y_step, 550.0, 70.0 + i * y_step),
            confidence=conf,
        ))
    return lines


class TestConfidenceScore:
    def test_empty(self):
        score = compute_confidence_score([])
        assert score == 0.0

    def test_single_line(self):
        lines = [OCRLine(text="test", bbox=(0, 0, 10, 10), confidence=0.8)]
        score = compute_confidence_score(lines)
        assert score == 80.0

    def test_mixed_confidence(self):
        lines = [
            OCRLine(text="a", bbox=(0, 0, 10, 10), confidence=1.0),
            OCRLine(text="b", bbox=(0, 0, 10, 10), confidence=0.0),
        ]
        score = compute_confidence_score(lines)
        assert score == 50.0


class TestTextDensity:
    def test_empty_lines(self):
        score = estimate_text_density([], (100, 100))
        assert score == 0.0

    def test_normal_density(self):
        lines = _make_lines(n=20, y_step=30)
        score = estimate_text_density(lines, (600, 900))
        assert 0 <= score <= 100

    def test_too_sparse(self):
        from ocr_engine.quality import estimate_text_density
        # 超稀疏（几乎空白）vs 正常密度
        sparse_lines = [OCRLine(text="t", bbox=(0, 0, 5, 5), confidence=0.9)]
        sparse_score = estimate_text_density(sparse_lines, (1000, 1000))
        # 正常密度
        normal_lines = []
        for i in range(20):
            normal_lines.append(OCRLine(
                text="x" * 30,
                bbox=(100.0, 100.0 + i * 40, 300.0, 120.0 + i * 40),
                confidence=0.9,
            ))
        normal_score = estimate_text_density(normal_lines, (600, 1000))
        # 正常密度得分应该高于极稀疏
        assert normal_score > sparse_score


class TestLayoutCompleteness:
    def test_empty(self):
        score = estimate_layout_completeness([], (100, 100))
        assert score == 0.0

    def test_single_line(self):
        lines = [OCRLine(text="test", bbox=(50, 50, 200, 70), confidence=0.9)]
        score = estimate_layout_completeness(lines, (600, 800))
        assert 0 <= score <= 100

    def test_uniform_lines(self):
        lines = _make_lines(n=20, y_step=30)
        score = estimate_layout_completeness(lines, (600, 800))
        # 均匀分布的行应该有较高的布局分
        assert score > 50


class TestQualityScore:
    def test_compute_basic(self):
        lines = _make_lines(n=10, conf=0.9)
        qs = compute_quality_score(lines, image_size=(600, 800))
        assert isinstance(qs, QualityScore)
        assert 0 <= qs.overall <= 100
        assert 0 <= qs.confidence <= 100
        assert 0 <= qs.clarity <= 100
        assert 0 <= qs.text_density <= 100
        assert 0 <= qs.layout_completeness <= 100

    def test_grade_a(self):
        q = QualityScore(overall=95.0)
        assert q.grade == "A"

    def test_grade_b(self):
        q = QualityScore(overall=80.0)
        assert q.grade == "B"

    def test_grade_c(self):
        q = QualityScore(overall=65.0)
        assert q.grade == "C"

    def test_grade_d(self):
        q = QualityScore(overall=45.0)
        assert q.grade == "D"

    def test_grade_f(self):
        q = QualityScore(overall=10.0)
        assert q.grade == "F"

    def test_custom_weights(self):
        lines = _make_lines(n=5, conf=0.9)
        weights = {"confidence": 0.5, "clarity": 0.1, "text_density": 0.2, "layout_completeness": 0.2}
        qs = compute_quality_score(lines, image_size=(600, 800), weights=weights)
        assert 0 <= qs.overall <= 100

    def test_with_image(self, gradient_image):
        lines = _make_lines(n=10, conf=0.9)
        qs = compute_quality_score(lines, image=gradient_image)
        assert isinstance(qs, QualityScore)
        assert qs.details["image_size"] == list(gradient_image.size)

    def test_details(self):
        lines = _make_lines(n=15, conf=0.85)
        qs = compute_quality_score(lines, image_size=(600, 800))
        assert "num_lines" in qs.details
        assert qs.details["num_lines"] == 15
        assert "avg_confidence" in qs.details
        assert abs(qs.details["avg_confidence"] - 0.85) < 0.01


class TestChineseTextQuality:
    def test_chinese_text(self):
        text = "这是一段中文测试文字，用于验证中文文本质量检测功能。"
        result = chinese_text_quality(text)
        assert "chinese_ratio" in result
        assert "messy_ratio" in result
        assert "error_pattern_count" in result
        assert result["chinese_ratio"] > 0.5

    def test_english_text(self):
        text = "This is all English text."
        result = chinese_text_quality(text)
        assert result["chinese_ratio"] < 0.1
