"""确收模块 v2.1 — RevenueValidator 单元测试。

对齐 DESIGN-DETAIL-REVENUE-v2.1.md §1.5.2（12 条规则 + 存疑流程）。
"""

import sys
import pytest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from bdms.core import db as _db
from bdms.modules.revenue.validator import RevenueValidator


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    _db.init_db(path)
    return path


@pytest.fixture
def validator(db_path):
    return RevenueValidator(db_path=db_path)


# ─── 单行规则 ───

class TestRowRules:

    def test_r1_empty_contract(self, validator):
        issues = validator.validate_row("计划确收底稿", {"合同编号": "", "履约ID": "P1"}, 0)
        assert any(i["rule"] == "R1" and i["level"] == "error" for i in issues)

    def test_r2_empty_perf_id(self, validator):
        issues = validator.validate_row("计划确收底稿", {"合同编号": "C1", "履约ID": ""}, 0)
        assert any(i["rule"] == "R2" for i in issues)

    def test_r3_negative_amount(self, validator):
        issues = validator.validate_row("x", {"合同编号": "C", "履约ID": "P",
                                              "确收金额": "-100"}, 0)
        assert any(i["rule"] == "R3" for i in issues)

    def test_r3_non_numeric_amount(self, validator):
        issues = validator.validate_row("x", {"合同编号": "C", "履约ID": "P",
                                              "确收金额": "abc"}, 0)
        assert any(i["rule"] == "R3" for i in issues)

    def test_r4_bad_month(self, validator):
        issues = validator.validate_row("x", {"合同编号": "C", "履约ID": "P",
                                              "月份": "2026-06"}, 0)
        assert any(i["rule"] == "R4" and i["level"] == "warning" for i in issues)

    def test_r7_bad_category(self, validator):
        issues = validator.validate_row("x", {"合同编号": "C", "履约ID": "P",
                                              "分类": "其他"}, 0)
        assert any(i["rule"] == "R7" and i["level"] == "error" for i in issues)

    def test_r8_bad_method(self, validator):
        issues = validator.validate_row("x", {"合同编号": "C", "履约ID": "P",
                                              "收入确认方法": "完工百分比"}, 0)
        assert any(i["rule"] == "R8" and i["level"] == "warning" for i in issues)

    def test_clean_row_no_issues(self, validator):
        issues = validator.validate_row("x", {
            "合同编号": "C1", "履约ID": "P1", "分类": "新签",
            "收入确认方法": "时点法", "确收金额": "1000", "月份": "202606",
        }, 0)
        assert issues == []


# ─── 批量规则 ───

class TestBatchRules:

    def test_r11_duplicate(self, validator):
        rows = [
            {"合同编号": "C1", "履约ID": "P1", "分类": "新签"},
            {"合同编号": "C1", "履约ID": "P1", "分类": "新签"},
        ]
        result = validator.validate_batch("x", rows, "202606")
        assert any(e["rule"] == "R11" for e in result["errors"])

    def test_summary_counts(self, validator):
        rows = [
            {"合同编号": "C1", "履约ID": "P1", "分类": "新签"},   # clean
            {"合同编号": "", "履约ID": "P2", "分类": "新签"},     # error row
            {"合同编号": "C3", "履约ID": "P3", "分类": "递延",
             "收入确认方法": "其他"},  # warning row
        ]
        result = validator.validate_batch("x", rows, "202606")
        s = result["summary"]
        assert s["total"] == 3
        assert s["error_rows"] >= 1
        assert s["warning_rows"] >= 1
        assert s["clean_rows"] >= 1


# ─── 存疑流程（落盘 + 校正）───

class TestSuspiciousFlow:

    def test_persist_and_list_pending(self, db_path, validator):
        results = {
            "errors": [{"row": 1, "rule": "R1", "level": "error",
                        "col": "合同编号", "message": "空", "value": ""}],
            "warnings": [{"row": 2, "rule": "R8", "level": "warning",
                          "col": "收入确认方法", "message": "非法", "value": "x"}],
        }
        n = validator.persist_validation_results("202606", results)
        assert n == 2

        pending = validator.list_pending("202606")
        assert len(pending) == 2
        # ERROR 排前
        assert pending[0]["severity"] == "ERROR"

    def test_apply_correction(self, db_path, validator):
        results = {
            "errors": [],
            "warnings": [{"row": 5, "rule": "R4", "level": "warning",
                          "col": "月份", "message": "格式", "value": "bad"}],
        }
        validator.persist_validation_results("202606", results)
        pending = validator.list_pending("202606")
        vid = pending[0]["id"]

        r = validator.apply_manual_correction(vid, "202606", "rex")
        assert r["ok"]

        # 已处理后不再出现在 pending
        assert len(validator.list_pending("202606")) == 0

        # 留痕在 rr_edit_history
        conn = _db.get_connection(db_path)
        rows = conn.execute(
            "SELECT * FROM rr_edit_history WHERE month='202606'"
        ).fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0]["new_value"] == "202606"
        assert rows[0]["operator"] == "rex"

    def test_correction_idempotent(self, db_path, validator):
        results = {"errors": [], "warnings": [
            {"row": 1, "rule": "R4", "level": "warning",
             "col": "月份", "message": "x", "value": "y"}]}
        validator.persist_validation_results("202606", results)
        vid = validator.list_pending("202606")[0]["id"]
        assert validator.apply_manual_correction(vid, "v", "rex")["ok"]
        # 二次校正应拒绝
        r2 = validator.apply_manual_correction(vid, "v2", "rex")
        assert not r2["ok"]


# ─── ASC 606 自动填充 ───

class TestAutoFill:

    def test_asc606_suggestions(self, db_path, validator):
        import json
        conn = _db.get_connection(db_path)
        # 造两行：一行无方法（软件→建议时点法），一行已有方法
        for i, data in enumerate([
            {"产品": "移动安全软件", "收入确认方法": "", "合同编号": "C1"},
            {"产品": "安全服务", "收入确认方法": "时段法", "合同编号": "C2"},
        ]):
            conn.execute(
                "INSERT INTO rr_sheet_row (period, sheet, row_index, data) "
                "VALUES (?, '计划确收底稿', ?, ?)",
                ("202606", i, json.dumps(data, ensure_ascii=False)),
            )
        conn.commit()
        conn.close()

        suggestions = validator.auto_fill_suggestions("202606")
        # 只有缺方法的行给建议
        assert len(suggestions) == 1
        assert suggestions[0]["suggested_method"] == "时点法"
        assert "ASC 606" in suggestions[0]["basis"]
