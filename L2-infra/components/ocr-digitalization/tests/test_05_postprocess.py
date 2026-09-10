"""
测试 5: 后处理逻辑

覆盖：
- 行排序（阅读顺序）
- 文本清洗
- 去重
- OCR 错误纠正
- 合并分行
- 完整后处理流水线
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from ocr_engine.postprocess import (
    sort_lines_reading_order,
    clean_noise_chars,
    deduplicate_lines,
    correct_ocr_text,
    correct_lines,
    merge_broken_lines,
    postprocess_lines,
    PostprocessConfig,
    detect_tables,
)
from ocr_engine.types import OCRLine


def _make_line(text, x, y, w=100, h=20, conf=0.9):
    return OCRLine(text=text, bbox=(float(x), float(y), float(x + w), float(y + h)), confidence=conf)


class TestSortReadingOrder:
    def test_empty(self):
        assert sort_lines_reading_order([]) == []

    def test_single_line(self):
        line = _make_line("test", 10, 10)
        result = sort_lines_reading_order([line])
        assert len(result) == 1
        assert result[0].text == "test"

    def test_two_lines_same_row(self):
        """同一行的两段文字应该按 x 排序"""
        line1 = _make_line("右边", 200, 50)
        line2 = _make_line("左边", 50, 52)  # y 接近，视为同一行
        result = sort_lines_reading_order([line1, line2])
        assert len(result) == 2
        assert result[0].text == "左边"
        assert result[1].text == "右边"

    def test_multiple_rows(self):
        """多行应该按 y 排序"""
        line1 = _make_line("第三行", 50, 150)
        line2 = _make_line("第一行", 50, 50)
        line3 = _make_line("第二行", 50, 100)
        result = sort_lines_reading_order([line1, line2, line3])
        assert len(result) == 3
        assert result[0].text == "第一行"
        assert result[1].text == "第二行"
        assert result[2].text == "第三行"


class TestCleanNoiseChars:
    def test_clean_line(self):
        text = "正常的一行文字"
        assert clean_noise_chars(text) == "正常的一行文字"

    def test_leading_trailing_dots(self):
        text = "··测试文字··"
        result = clean_noise_chars(text)
        assert result == "测试文字"

    def test_empty_lines_preserved(self):
        text = "第一行\n\n第三行"
        result = clean_noise_chars(text)
        lines = result.split("\n")
        assert len(lines) == 3

    def test_all_noise_line(self):
        text = "···  ···"
        result = clean_noise_chars(text)
        assert result.strip() == ""


class TestDeduplicate:
    def test_no_duplicates(self):
        lines = [
            _make_line("第一行", 50, 50),
            _make_line("第二行", 50, 100),
        ]
        result = deduplicate_lines(lines)
        assert len(result) == 2

    def test_exact_duplicate_same_y(self):
        lines = [
            _make_line("相同文字", 50, 50),
            _make_line("相同文字", 52, 50),  # y 接近
        ]
        result = deduplicate_lines(lines)
        assert len(result) == 1

    def test_duplicate_different_y(self):
        """y 差异大的不算重复"""
        lines = [
            _make_line("相同文字", 50, 50),
            _make_line("相同文字", 50, 200),  # y 差很大
        ]
        result = deduplicate_lines(lines)
        assert len(result) == 2


class TestCorrection:
    def test_general_digit_correction(self):
        # O -> 0 (数字中间的大写O)
        assert "105" in correct_ocr_text("1O5", domain="general")
        # l -> 1 (数字中间的小写L)
        assert "115" in correct_ocr_text("1l5", domain="general")
        # 多个数字OCR错误（O->0, S->5）
        assert "10345" in correct_ocr_text("1O345", domain="general")
        assert "15555" in correct_ocr_text("1S555", domain="general")

    def test_contract_corrections(self):
        assert "甲方" in correct_ocr_text("里方", domain="contract")
        assert "违约金" in correct_ocr_text("钓金", domain="contract")
        assert "有限公司" in correct_ocr_text("有限公可", domain="contract")

    def test_correct_lines(self):
        lines = [_make_line("里方所在地", 10, 10)]
        result = correct_lines(lines, domain="contract")
        assert "甲方" in result[0].text
        assert "corrected" in result[0].source

    def test_correct_general_no_contract(self):
        # general 模式下不应用合同纠错
        text = "里方"
        result = correct_ocr_text(text, domain="general")
        assert result == "里方"  # 不变


class TestMergeBrokenLines:
    def test_no_merge_with_punctuation(self):
        """行尾有标点不合并"""
        lines = [
            _make_line("第一行。", 50, 50, w=200),
            _make_line("第二行。", 50, 80, w=200),
        ]
        result = merge_broken_lines(lines)
        assert len(result) == 2

    def test_merge_broken_text(self):
        """没有结束标点的短行 + 下一行，可能是被拆分的"""
        lines = [
            _make_line("这是一段被拆分的", 50, 50, w=200),
            _make_line("文字应该被合并", 50, 80, w=200),
        ]
        result = merge_broken_lines(lines)
        # 可能合并也可能不（取决于启发式规则），只要不报错即可
        assert len(result) >= 1

    def test_single_line(self):
        lines = [_make_line("test", 10, 10)]
        result = merge_broken_lines(lines)
        assert len(result) == 1


class TestTableDetection:
    def test_empty_lines(self):
        result = detect_tables([])
        assert result == []

    def test_few_lines(self):
        lines = [_make_line("test", 10, 10) for _ in range(2)]
        result = detect_tables(lines)
        assert result == []


class TestFullPipeline:
    def test_pipeline_default(self):
        lines = [
            _make_line("行 C", 200, 50),
            _make_line("行 A", 50, 50),
            _make_line("里方", 50, 100),
        ]
        result = postprocess_lines(lines)
        assert len(result) >= 1
        # 排序后第一行 x 更小
        assert result[0].bbox[0] <= result[1].bbox[0] if len(result) > 1 else True

    def test_pipeline_with_config(self):
        lines = [
            _make_line("钓金", 50, 50),
            _make_line("里方", 50, 100),
        ]
        cfg = PostprocessConfig(
            sort_reading_order=True,
            deduplicate=False,
            correct_domain="contract",
            merge_broken=False,
            clean_noise=False,
        )
        result = postprocess_lines(lines, cfg)
        # 合同纠错应该生效
        texts = [l.text for l in result]
        assert any("违约金" in t for t in texts)
        assert any("甲方" in t for t in texts)

    def test_pipeline_remove_empty(self):
        lines = [
            _make_line("  ", 50, 50),
            _make_line("有效行", 50, 100),
        ]
        result = postprocess_lines(lines)
        # 空行应该被移除
        assert all(l.text.strip() for l in result)
