"""Tests for revenue_recognition.v1.validator module."""

import pytest
from revenue_recognition.v1 import validator


class TestCellDiff:
    """Test CellDiff dataclass."""

    def test_creation(self):
        diff = validator.CellDiff(
            cell="B5",
            auto_value=100.0,
            manual_value=99.9,
            diff=0.1,
            is_match=False
        )
        assert diff.cell == "B5"
        assert diff.auto_value == 100.0
        assert diff.manual_value == 99.9
        assert diff.diff == 0.1
        assert diff.is_match is False


class TestValidationReport:
    """Test ValidationReport dataclass."""

    def test_is_passed_when_no_mismatches(self):
        report = validator.ValidationReport(
            sheet_name="汇总",
            total_cells=10,
            matched_cells=10,
            mismatched_cells=0,
            missing_in_auto=0,
        )
        assert report.is_passed is True

    def test_is_failed_when_mismatches(self):
        report = validator.ValidationReport(
            sheet_name="汇总",
            total_cells=10,
            matched_cells=9,
            mismatched_cells=1,
            missing_in_auto=0,
        )
        assert report.is_passed is False

    def test_is_failed_when_missing_in_auto(self):
        report = validator.ValidationReport(
            sheet_name="汇总",
            total_cells=10,
            matched_cells=10,
            mismatched_cells=0,
            missing_in_auto=1,
        )
        assert report.is_passed is False

    def test_summary_pass(self):
        report = validator.ValidationReport(
            sheet_name="汇总",
            total_cells=10,
            matched_cells=10,
        )
        s = report.summary()
        assert "PASS" in s
        assert "汇总" in s

    def test_summary_fail(self):
        report = validator.ValidationReport(
            sheet_name="汇总",
            total_cells=10,
            matched_cells=9,
            mismatched_cells=1,
        )
        s = report.summary()
        assert "FAIL" in s


class TestIsNumeric:
    """Test _is_numeric helper."""

    def test_int(self):
        assert validator._is_numeric(42) is True

    def test_float(self):
        assert validator._is_numeric(3.14) is True

    def test_string(self):
        assert validator._is_numeric("hello") is False

    def test_none(self):
        assert validator._is_numeric(None) is False


class TestValuesEqual:
    """Test _values_equal helper."""

    def test_both_none(self):
        assert validator._values_equal(None, None) is True

    def test_none_vs_zero(self):
        assert validator._values_equal(None, 0) is True

    def test_zero_vs_none(self):
        assert validator._values_equal(0, None) is True

    def test_none_vs_nonzero(self):
        assert validator._values_equal(None, 5) is False

    def test_numeric_within_tolerance(self):
        assert validator._values_equal(100.0, 100.005, tolerance=0.01) is True

    def test_numeric_outside_tolerance(self):
        assert validator._values_equal(100.0, 100.1, tolerance=0.01) is False

    def test_string_match(self):
        assert validator._values_equal("hello", "hello") is True

    def test_string_mismatch(self):
        assert validator._values_equal("hello", "world") is False

    def test_string_stripped(self):
        assert validator._values_equal(" hello ", "hello") is True

    def test_custom_tolerance(self):
        assert validator._values_equal(1.0, 1.5, tolerance=1.0) is True
        assert validator._values_equal(1.0, 2.5, tolerance=1.0) is False


class TestCalcDiff:
    """Test _calc_diff helper."""

    def test_numeric_diff(self):
        assert validator._calc_diff(100.0, 95.0) == 5.0

    def test_numeric_diff_reversed(self):
        assert validator._calc_diff(95.0, 100.0) == 5.0

    def test_string_diff(self):
        assert validator._calc_diff("a", "b") == 0.0

    def test_none_diff(self):
        assert validator._calc_diff(None, None) == 0.0


class TestPrintReport:
    """Test print_report function."""

    def test_empty_reports(self, capsys):
        validator.print_report([])
        # Should not error

    def test_with_passing_report(self, capsys):
        report = validator.ValidationReport(
            sheet_name="汇总",
            total_cells=5,
            matched_cells=5,
        )
        validator.print_report([report])
        captured = capsys.readouterr()
        assert "汇总" in captured.out

    def test_with_failing_report(self, capsys):
        report = validator.ValidationReport(
            sheet_name="汇总",
            total_cells=5,
            matched_cells=3,
            mismatched_cells=2,
        )
        validator.print_report([report])
        captured = capsys.readouterr()
        assert "差异" in captured.out or "存在" in captured.out
