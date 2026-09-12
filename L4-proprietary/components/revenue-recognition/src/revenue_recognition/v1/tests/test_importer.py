"""Tests for revenue_recognition.v1.importer module."""

import sqlite3
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from revenue_recognition.v1 import importer


class TestSafeFloat:
    """Test _safe_float helper."""

    def test_none_returns_none(self):
        assert importer._safe_float(None) is None

    def test_int_returns_float(self):
        assert importer._safe_float(42) == 42.0

    def test_float_returns_float(self):
        assert importer._safe_float(3.14) == 3.14

    def test_string_number(self):
        assert importer._safe_float("123.45") == 123.45

    def test_string_with_comma(self):
        assert importer._safe_float("1,234,567.89") == 1234567.89

    def test_invalid_string_returns_none(self):
        assert importer._safe_float("not a number") is None

    def test_empty_string_returns_none(self):
        assert importer._safe_float("") is None


class TestSafeStr:
    """Test _safe_str helper."""

    def test_none_returns_none(self):
        assert importer._safe_str(None) is None

    def test_string_stripped(self):
        assert importer._safe_str("  hello  ") == "hello"

    def test_empty_string_returns_none(self):
        assert importer._safe_str("") is None

    def test_whitespace_only_returns_none(self):
        assert importer._safe_str("   ") is None

    def test_number_converted(self):
        assert importer._safe_str(42) == "42"


def _make_plan_row(contract_no="C001", archive_month="202601"):
    """Build a full-length plan_draft row (45+ columns)."""
    row = [None] * 46
    row[0] = "说明"           # A: note
    row[1] = "2026-06-30"    # B: init_est_date
    row[2] = "2026-06-30"    # C: est_date
    row[3] = contract_no     # D: contract_no
    row[4] = archive_month   # E: archive_month
    row[5] = contract_no     # F: contract_no2
    row[6] = "1"             # G: prod_seq
    row[7] = "P001"          # H: perf_id
    row[8] = "P001"          # I: budget_perf_id
    row[9] = "部门A"         # J: dept
    row[10] = "合同1"        # K: contract_name
    row[11] = "客户A"        # L: customer
    row[12] = "用户A"        # M: end_user
    row[13] = "备注1"        # N: contract_note
    row[14] = "操作备注"     # O: ops_note
    row[15] = 0.06           # P: tax_rate
    row[16] = "2025-01-01"   # Q: sign_date
    row[17] = "2025-01-01"   # R: contract_start
    row[18] = "2026-12-31"   # S: contract_end
    row[19] = 24             # T: service_months
    row[20] = "标准"         # U: contract_type
    row[21] = "V1"           # V: version_type
    row[22] = "否"           # W: gift
    row[23] = "安全服务"     # X: prod_category
    row[24] = "产品1"        # Y: prod_name
    row[25] = "履约1"        # Z: perf_detail
    row[26] = "标准产品"     # AA: std_prod_name
    row[27] = "收入科目"     # AB: rev_subject
    row[28] = "税金科目"     # AC: tax_subject
    row[29] = "价格依据"     # AD: price_basis
    row[30] = "验收单"       # AE: accept_type
    row[31] = "验收条款"     # AF: accept_term
    row[32] = "收款节奏"     # AG: payment_term
    row[33] = "时段法"       # AH: rev_method
    row[34] = None           # AI: no_exec_reason
    row[35] = "次"           # AJ: qty_unit
    row[36] = 10             # AK: qty
    row[37] = 100000.0       # AL: contract_amount
    row[38] = 100000.0       # AM: confirm_amount
    row[39] = 100000.0       # AN: perf_amount
    row[40] = 100000.0       # AO: plan_perf_amount
    row[41] = 50000.0        # AP: rev_before_2025
    row[42] = 50000.0        # AQ: rev_2026_future
    row[43] = 0              # AR: plan_disappear
    row[44] = None           # AS: disappear_reason
    return tuple(row)


def _make_budget_row(contract_no="C001", category="新签"):
    """Build a full-length budget_exec row (47 columns)."""
    row = [None] * 47
    row[0] = category        # A: category
    row[1] = contract_no     # B: contract_no
    row[2] = contract_no     # C: contract_no_cal
    row[3] = "客户A"         # D: customer
    row[4] = "用户A"         # E: end_user
    row[5] = "签约主体"      # F: sign_subject
    row[6] = "202601"        # G: archive_month
    row[7] = "P001"          # H: perf_id_budget
    row[8] = "履约明细"      # I: perf_detail_budget
    row[9] = "P001"          # J: perf_id
    row[10] = "时段法"       # K: rev_method
    row[11] = 100000.0       # L: perf_amount
    row[12] = 50000.0        # M: rev_prior
    row[13] = 50000.0        # N: rev_future
    row[14] = 0              # O: no_plan
    row[15] = 50000.0        # P: unrev_prior
    row[16] = 50000.0        # Q: unrev_adj
    row[17] = "2026-01-01"   # R: plan_start
    row[18] = "2026-12-31"   # S: plan_end
    row[19] = "2026-06-30"   # T: plan_done
    # U(20)-AF(31): monthly plan
    for i in range(12):
        row[20 + i] = 8333.33
    row[32] = 100000.0       # AG: year_est
    row[33] = 50000.0        # AH: h1_plan
    row[34] = 50000.0        # AI: h1_actual
    row[35] = 10000.0        # AJ: h1_ahead
    row[36] = 5000.0         # AK: h1_behind
    # AL(37)-AQ(42): monthly actual
    for i in range(6):
        row[37 + i] = 8333.33
    row[43] = 0              # AR: disappear_2026
    row[44] = 0              # AS: disappear_future
    row[45] = None           # AT: disappear_note
    row[46] = None           # AU: rebuild_perf
    return tuple(row)


class TestImportPlanDraft:
    """Test import_plan_draft with mocked openpyxl."""

    @patch("revenue_recognition.v1.importer.openpyxl")
    def test_imports_rows(self, mock_openpyxl, tmp_db_path):
        from revenue_recognition.v1.db import init_db
        init_db(tmp_db_path)

        mock_wb = MagicMock()
        mock_ws = MagicMock()
        mock_openpyxl.load_workbook.return_value = mock_wb
        mock_wb.__getitem__ = lambda self, key: mock_ws

        mock_ws.iter_rows.return_value = [_make_plan_row()]

        count = importer.import_plan_draft(
            excel_path=Path("/fake/path.xlsx"),
            db_path=tmp_db_path
        )
        assert count == 1

    @patch("revenue_recognition.v1.importer.openpyxl")
    def test_skips_empty_rows(self, mock_openpyxl, tmp_db_path):
        from revenue_recognition.v1.db import init_db
        init_db(tmp_db_path)

        mock_wb = MagicMock()
        mock_ws = MagicMock()
        mock_openpyxl.load_workbook.return_value = mock_wb
        mock_wb.__getitem__ = lambda self, key: mock_ws

        mock_ws.iter_rows.return_value = [
            (None, None, None, None),
            None,
        ]

        count = importer.import_plan_draft(
            excel_path=Path("/fake/path.xlsx"),
            db_path=tmp_db_path
        )
        assert count == 0

    @patch("revenue_recognition.v1.importer.openpyxl")
    def test_skips_rows_without_contract_no(self, mock_openpyxl, tmp_db_path):
        from revenue_recognition.v1.db import init_db
        init_db(tmp_db_path)

        mock_wb = MagicMock()
        mock_ws = MagicMock()
        mock_openpyxl.load_workbook.return_value = mock_wb
        mock_wb.__getitem__ = lambda self, key: mock_ws

        row = [None] * 46
        row[0] = "新签"
        # row[3] = None → no contract_no

        mock_ws.iter_rows.return_value = [tuple(row)]

        count = importer.import_plan_draft(
            excel_path=Path("/fake/path.xlsx"),
            db_path=tmp_db_path
        )
        assert count == 0

    @patch("revenue_recognition.v1.importer.openpyxl")
    def test_clears_old_data(self, mock_openpyxl, tmp_db_path):
        """Should DELETE old data before importing."""
        from revenue_recognition.v1.db import init_db, get_connection
        init_db(tmp_db_path)

        conn = get_connection(tmp_db_path)
        conn.execute("""
            INSERT INTO plan_draft (contract_no, customer) VALUES ('OLD', 'old_customer')
        """)
        conn.commit()
        conn.close()

        mock_wb = MagicMock()
        mock_ws = MagicMock()
        mock_openpyxl.load_workbook.return_value = mock_wb
        mock_wb.__getitem__ = lambda self, key: mock_ws
        mock_ws.iter_rows.return_value = [_make_plan_row()]

        importer.import_plan_draft(excel_path=Path("/fake/path.xlsx"), db_path=tmp_db_path)

        conn = get_connection(tmp_db_path)
        rows = conn.execute("SELECT contract_no FROM plan_draft").fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0][0] == "C001"


class TestImportBudgetExec:
    """Test import_budget_exec with mocked openpyxl."""

    @patch("revenue_recognition.v1.importer.openpyxl")
    def test_imports_rows(self, mock_openpyxl, tmp_db_path):
        from revenue_recognition.v1.db import init_db
        init_db(tmp_db_path)

        mock_wb = MagicMock()
        mock_ws = MagicMock()
        mock_openpyxl.load_workbook.return_value = mock_wb
        mock_wb.__getitem__ = lambda self, key: mock_ws

        mock_ws.iter_rows.return_value = [_make_budget_row()]

        count = importer.import_budget_exec(
            excel_path=Path("/fake/path.xlsx"),
            db_path=tmp_db_path
        )
        assert count == 1

    @patch("revenue_recognition.v1.importer.openpyxl")
    def test_skips_rows_without_contract_no(self, mock_openpyxl, tmp_db_path):
        from revenue_recognition.v1.db import init_db
        init_db(tmp_db_path)

        mock_wb = MagicMock()
        mock_ws = MagicMock()
        mock_openpyxl.load_workbook.return_value = mock_wb
        mock_wb.__getitem__ = lambda self, key: mock_ws

        row = [None] * 47
        row[0] = "新签"
        # row[1] = None → no contract_no

        mock_ws.iter_rows.return_value = [tuple(row)]

        count = importer.import_budget_exec(
            excel_path=Path("/fake/path.xlsx"),
            db_path=tmp_db_path
        )
        assert count == 0

    @patch("revenue_recognition.v1.importer.openpyxl")
    def test_clears_old_data(self, mock_openpyxl, tmp_db_path):
        from revenue_recognition.v1.db import init_db, get_connection
        init_db(tmp_db_path)

        conn = get_connection(tmp_db_path)
        conn.execute("""
            INSERT INTO budget_exec (category, contract_no) VALUES ('新签', 'OLD')
        """)
        conn.commit()
        conn.close()

        mock_wb = MagicMock()
        mock_ws = MagicMock()
        mock_openpyxl.load_workbook.return_value = mock_wb
        mock_wb.__getitem__ = lambda self, key: mock_ws

        mock_ws.iter_rows.return_value = [_make_budget_row()]

        importer.import_budget_exec(excel_path=Path("/fake/path.xlsx"), db_path=tmp_db_path)

        conn = get_connection(tmp_db_path)
        rows = conn.execute("SELECT contract_no FROM budget_exec").fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0][0] == "C001"


class TestImportAll:
    """Test import_all orchestrator."""

    @patch("revenue_recognition.v1.importer.import_performance_summary")
    @patch("revenue_recognition.v1.importer.import_monthly_summary")
    @patch("revenue_recognition.v1.importer.import_budget_exec")
    @patch("revenue_recognition.v1.importer.import_plan_draft")
    def test_returns_counts(self, mock_plan, mock_budget, mock_monthly, mock_perf, tmp_db_path):
        mock_plan.return_value = 10
        mock_budget.return_value = 20
        mock_monthly.return_value = 30
        mock_perf.return_value = 40
        result = importer.import_all(db_path=tmp_db_path)
        assert result == {"plan_draft": 10, "budget_exec": 20, "monthly_summary": 30, "performance_summary": 40}
