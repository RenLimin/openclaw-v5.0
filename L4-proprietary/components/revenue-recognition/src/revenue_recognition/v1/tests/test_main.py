"""Tests for revenue_recognition.v1.main module."""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


class TestMain:
    """Test main entry point."""

    @patch("revenue_recognition.v1.main.print_report")
    @patch("revenue_recognition.v1.main.validate_all_sheets")
    @patch("revenue_recognition.v1.main.RevenueExporter")
    @patch("revenue_recognition.v1.main.RevenueEngine")
    @patch("revenue_recognition.v1.main.import_all")
    @patch("revenue_recognition.v1.main.init_db")
    def test_main_returns_0_on_success(
        self, mock_init, mock_import, mock_engine_cls,
        mock_exporter_cls, mock_validate, mock_print
    ):
        mock_import.return_value = {"plan_draft": 5, "budget_exec": 10}
        mock_engine = MagicMock()
        mock_engine.compute_summary.return_value = {"new": [], "deferred": []}
        mock_engine.compute_monthly_detail.return_value = []
        mock_engine.compute_performance_summary.return_value = {
            "new": {"budget": 0, "actual": 0},
            "deferred": {"budget": 0, "actual": 0},
        }
        mock_engine_cls.return_value = mock_engine

        mock_exporter = MagicMock()
        mock_exporter.export.return_value = Path("/fake/output.xlsx")
        mock_exporter_cls.return_value = mock_exporter

        mock_report = MagicMock()
        mock_report.is_passed = True
        mock_validate.return_value = [mock_report]

        from revenue_recognition.v1 import main
        result = main.main()
        assert result == 0

    @patch("revenue_recognition.v1.main.print_report")
    @patch("revenue_recognition.v1.main.validate_all_sheets")
    @patch("revenue_recognition.v1.main.RevenueExporter")
    @patch("revenue_recognition.v1.main.RevenueEngine")
    @patch("revenue_recognition.v1.main.import_all")
    @patch("revenue_recognition.v1.main.init_db")
    def test_main_returns_1_on_failure(
        self, mock_init, mock_import, mock_engine_cls,
        mock_exporter_cls, mock_validate, mock_print
    ):
        mock_import.return_value = {"plan_draft": 5, "budget_exec": 10}
        mock_engine = MagicMock()
        mock_engine.compute_summary.return_value = {"new": [], "deferred": []}
        mock_engine.compute_monthly_detail.return_value = []
        mock_engine.compute_performance_summary.return_value = {
            "new": {"budget": 0, "actual": 0},
            "deferred": {"budget": 0, "actual": 0},
        }
        mock_engine_cls.return_value = mock_engine

        mock_exporter = MagicMock()
        mock_exporter.export.return_value = Path("/fake/output.xlsx")
        mock_exporter_cls.return_value = mock_exporter

        mock_report = MagicMock()
        mock_report.is_passed = False
        mock_validate.return_value = [mock_report]

        from revenue_recognition.v1 import main
        result = main.main()
        assert result == 1

    @patch("revenue_recognition.v1.main.print_report")
    @patch("revenue_recognition.v1.main.validate_all_sheets")
    @patch("revenue_recognition.v1.main.RevenueExporter")
    @patch("revenue_recognition.v1.main.RevenueEngine")
    @patch("revenue_recognition.v1.main.import_all")
    @patch("revenue_recognition.v1.main.init_db")
    def test_main_calls_all_phases(
        self, mock_init, mock_import, mock_engine_cls,
        mock_exporter_cls, mock_validate, mock_print
    ):
        """Verify main() calls init → import → compute → export → validate."""
        mock_import.return_value = {"plan_draft": 1, "budget_exec": 1}
        mock_engine = MagicMock()
        mock_engine.compute_summary.return_value = {"new": [], "deferred": []}
        mock_engine.compute_monthly_detail.return_value = []
        mock_engine.compute_performance_summary.return_value = {
            "new": {"budget": 0, "actual": 0},
            "deferred": {"budget": 0, "actual": 0},
        }
        mock_engine_cls.return_value = mock_engine

        mock_exporter = MagicMock()
        mock_exporter.export.return_value = Path("/fake/output.xlsx")
        mock_exporter_cls.return_value = mock_exporter

        mock_report = MagicMock()
        mock_report.is_passed = True
        mock_validate.return_value = [mock_report]

        from revenue_recognition.v1 import main
        main.main()

        mock_init.assert_called_once()
        mock_import.assert_called_once()
        mock_engine.compute_summary.assert_called_once()
        mock_engine.compute_monthly_detail.assert_called_once()
        mock_engine.compute_performance_summary.assert_called_once()
        mock_exporter.export.assert_called_once()
        mock_validate.assert_called_once()
        mock_print.assert_called_once()
