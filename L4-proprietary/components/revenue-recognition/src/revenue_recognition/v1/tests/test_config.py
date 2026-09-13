"""Tests for revenue_recognition.v1.config module."""

import pytest
from pathlib import Path
from revenue_recognition.v1 import config


class TestPaths:
    """Test path constants."""

    def test_module_dir_exists(self):
        assert config.MODULE_DIR.exists()

    def test_data_dir_defined(self):
        assert isinstance(config.DATA_DIR, Path)
        assert "data" in config.DATA_DIR.name

    def test_output_dir_defined(self):
        assert isinstance(config.OUTPUT_DIR, Path)
        assert "output" in config.OUTPUT_DIR.name

    def test_db_path_defined(self):
        assert isinstance(config.DB_PATH, Path)
        assert config.DB_PATH.name == "revenue.db"

    def test_manual_report_path_defined(self):
        assert isinstance(config.MANUAL_REPORT_PATH, Path)


class TestSheetNames:
    """Test sheet name constants."""

    def test_sheet_plan_draft(self):
        assert config.SHEET_PLAN_DRAFT == "计划确收底稿"

    def test_sheet_budget_exec(self):
        assert config.SHEET_BUDGET_EXEC == "预算执行表"

    def test_sheet_summary(self):
        assert config.SHEET_SUMMARY == "汇总"

    def test_sheet_summary_analysis(self):
        assert config.SHEET_SUMMARY_ANALYSIS == "汇总分析"

    def test_sheet_monthly_record(self):
        assert config.SHEET_MONTHLY_RECORD == "月度汇总记录"

    def test_sheet_performance_record(self):
        assert config.SHEET_PERFORMANCE_RECORD == "履约汇总记录"

    def test_sheet_variance(self):
        assert config.SHEET_VARIANCE == "确收差异分析"

    def test_sheet_trend(self):
        assert config.SHEET_TREND == "预算趋势分析"

    def test_sheet_legend(self):
        assert config.SHEET_LEGEND == "图例"

    def test_sheet_rebuild_perf(self):
        assert config.SHEET_REBUILD_PERF == "重拆履约"


class TestBudgetCol:
    """Test BudgetCol column mapping."""

    def test_category_col(self):
        assert config.BudgetCol.CATEGORY == 1

    def test_contract_no_col(self):
        assert config.BudgetCol.CONTRACT_NO == 2

    def test_month_range(self):
        assert config.BudgetCol.MONTH_START == 21
        assert config.BudgetCol.MONTH_END == 32

    def test_actual_range(self):
        assert config.BudgetCol.ACTUAL_START == 38
        assert config.BudgetCol.ACTUAL_END == 43

    def test_perf_amount_col(self):
        assert config.BudgetCol.PERF_AMOUNT == 12

    def test_rev_method_col(self):
        assert config.BudgetCol.REV_METHOD == 11


class TestPlanCol:
    """Test PlanCol column mapping."""

    def test_note_col(self):
        assert config.PlanCol.NOTE == 1

    def test_contract_no_col(self):
        assert config.PlanCol.CONTRACT_NO == 4

    def test_perf_id_col(self):
        assert config.PlanCol.PERF_ID == 8

    def test_rev_method_col(self):
        assert config.PlanCol.REV_METHOD == 34

    def test_contract_amount_col(self):
        assert config.PlanCol.CONTRACT_AMOUNT == 38

    def test_perf_amount_col(self):
        assert config.PlanCol.PERF_AMOUNT == 40


class TestSummaryMonths:
    """Test summary months list."""

    def test_length(self):
        assert len(config.SUMMARY_MONTHS) == 12

    def test_first_month(self):
        assert config.SUMMARY_MONTHS[0] == "202601"

    def test_last_month(self):
        assert config.SUMMARY_MONTHS[11] == "202612"

    def test_format(self):
        for m in config.SUMMARY_MONTHS:
            assert m.startswith("2026")
            assert len(m) == 6
