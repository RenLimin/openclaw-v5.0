"""Tests for revenue_recognition.v1.engine module."""

import pytest
from revenue_recognition.v1.engine import RevenueEngine, _row_factory_dict


class TestRowFactoryDict:
    """Test _row_factory_dict helper."""

    def test_converts_row_to_dict(self):
        class FakeCursor:
            description = [("col1",), ("col2",), ("col3",)]
        row = (1, "hello", 3.14)
        result = _row_factory_dict(FakeCursor(), row)
        assert result == {"col1": 1, "col2": "hello", "col3": 3.14}

    def test_empty_row(self):
        class FakeCursor:
            description = []
        result = _row_factory_dict(FakeCursor(), ())
        assert result == {}


class TestRevenueEngineInit:
    """Test RevenueEngine initialization."""

    def test_default_db_path(self):
        engine = RevenueEngine()
        assert engine.db_path is None

    def test_custom_db_path(self, tmp_db_path):
        engine = RevenueEngine(db_path=tmp_db_path)
        assert engine.db_path == tmp_db_path


class TestComputeSummary:
    """Test compute_summary method."""

    def test_returns_new_and_deferred(self, engine_with_data):
        result = engine_with_data.compute_summary()
        assert "new" in result
        assert "deferred" in result

    def test_new_contracts_data(self, engine_with_data):
        result = engine_with_data.compute_summary()
        new = result["new"]
        assert len(new) > 0
        # Check first period
        first = new[0]
        assert "period" in first
        assert "total_amount" in first
        assert "plan_rev" in first
        assert "actual_rev" in first

    def test_deferred_contracts_data(self, engine_with_data):
        result = engine_with_data.compute_summary()
        deferred = result["deferred"]
        assert len(deferred) > 0
        first = deferred[0]
        assert "period" in first

    def test_periods_are_sorted(self, engine_with_data):
        result = engine_with_data.compute_summary()
        new_periods = [r["period"] for r in result["new"]]
        assert new_periods == sorted(new_periods)

    def test_empty_db(self, tmp_db_path):
        from revenue_recognition.v1.db import init_db
        init_db(tmp_db_path)
        engine = RevenueEngine(db_path=tmp_db_path)
        result = engine.compute_summary()
        assert result["new"] == []
        assert result["deferred"] == []

    def test_custom_period_param(self, engine_with_data):
        """Period param is accepted (used for output labeling)."""
        result = engine_with_data.compute_summary(period="202612")
        assert "new" in result


class TestComputeMonthlyDetail:
    """Test compute_monthly_detail method."""

    def test_returns_list(self, engine_with_data):
        result = engine_with_data.compute_monthly_detail()
        assert isinstance(result, list)

    def test_each_entry_has_required_keys(self, engine_with_data):
        result = engine_with_data.compute_monthly_detail()
        required_keys = {
            "period", "contract_period", "new_amount", "new_plan_rev",
            "new_actual_rev", "def_plan_rev", "def_actual_rev",
            "total_plan_rev", "total_actual_rev"
        }
        for entry in result:
            assert required_keys.issubset(entry.keys())

    def test_total_is_sum_of_new_and_deferred(self, engine_with_data):
        result = engine_with_data.compute_monthly_detail()
        for entry in result:
            assert abs(entry["total_plan_rev"] - (entry["new_plan_rev"] + entry["def_plan_rev"])) < 0.01
            assert abs(entry["total_actual_rev"] - (entry["new_actual_rev"] + entry["def_actual_rev"])) < 0.01

    def test_period_field_is_int(self, engine_with_data):
        result = engine_with_data.compute_monthly_detail()
        for entry in result:
            assert isinstance(entry["period"], int)

    def test_empty_db(self, tmp_db_path):
        from revenue_recognition.v1.db import init_db
        init_db(tmp_db_path)
        engine = RevenueEngine(db_path=tmp_db_path)
        result = engine.compute_monthly_detail()
        # 空数据库也返回12个月（202601-202612），值为0
        assert len(result) == 12
        for entry in result:
            assert entry["new_amount"] == 0
            assert entry["new_plan_rev"] == 0
            assert entry["new_actual_rev"] == 0
            assert entry["def_plan_rev"] == 0
            assert entry["def_actual_rev"] == 0


class TestComputePerformanceSummary:
    """Test compute_performance_summary method."""

    def test_returns_three_sections(self, engine_with_data):
        result = engine_with_data.compute_performance_summary()
        assert "new" in result
        assert "deferred" in result
        assert "total" in result

    def test_new_has_required_keys(self, engine_with_data):
        result = engine_with_data.compute_performance_summary()
        required = {"budget", "actual", "diff", "ahead", "behind", "disappear"}
        assert required.issubset(result["new"].keys())

    def test_total_is_sum(self, engine_with_data):
        result = engine_with_data.compute_performance_summary()
        n = result["new"]
        d = result["deferred"]
        t = result["total"]
        assert abs(t["budget"] - (n["budget"] + d["budget"])) < 0.01
        assert abs(t["actual"] - (n["actual"] + d["actual"])) < 0.01
        assert abs(t["ahead"] - (n["ahead"] + d["ahead"])) < 0.01
        assert abs(t["behind"] - (n["behind"] + d["behind"])) < 0.01

    def test_diff_is_budget_minus_actual(self, engine_with_data):
        result = engine_with_data.compute_performance_summary()
        for section in ("new", "deferred", "total"):
            expected = result[section]["budget"] - result[section]["actual"]
            assert abs(result[section]["diff"] - expected) < 0.01

    def test_empty_db(self, tmp_db_path):
        from revenue_recognition.v1.db import init_db
        init_db(tmp_db_path)
        engine = RevenueEngine(db_path=tmp_db_path)
        result = engine.compute_performance_summary()
        for section in ("new", "deferred", "total"):
            for key in ("budget", "actual", "diff", "ahead", "behind", "disappear"):
                assert result[section][key] == 0


class TestComputeRebuildPerf:
    """Test compute_rebuild_perf method."""

    def test_returns_list(self, engine_with_data):
        result = engine_with_data.compute_rebuild_perf()
        assert isinstance(result, list)

    def test_entries_have_contract_no(self, engine_with_data):
        result = engine_with_data.compute_rebuild_perf()
        for entry in result:
            assert "contract_no" in entry
            assert "ahead" in entry
            assert "behind" in entry

    def test_empty_db(self, tmp_db_path):
        from revenue_recognition.v1.db import init_db
        init_db(tmp_db_path)
        engine = RevenueEngine(db_path=tmp_db_path)
        result = engine.compute_rebuild_perf()
        assert result == []
