"""
BDMS V2 — POC 工时引擎单元测试

验证 hours_engine.py 核心功能：
  1. 工时数据加载（骨架模式）
  2. 按项目/合同分组汇总
  3. 人天换算
  4. POC 明细加工时列
  5. 一体化便捷函数
"""

import pytest
import pandas as pd
import sys
from pathlib import Path

# 路径设置
V2_DIR = Path(__file__).parent.parent / "v2"
sys.path.insert(0, str(V2_DIR / "engines"))

from hours_engine import (
    load_workhour_detail,
    load_workhour_pivot,
    aggregate_by_project,
    aggregate_by_contract,
    hours_to_person_days,
    add_poc_hours_column,
    add_person_days_column,
    get_poc_project_hours_by_contract,
    DEFAULT_HOURS_PER_DAY,
)


class TestLoadWorkhourDetail:
    """工时明细加载测试"""

    def test_empty_mode_returns_structure(self):
        """骨架模式（无文件）返回空结构"""
        df = load_workhour_detail(None)
        assert isinstance(df, pd.DataFrame)
        assert df.empty
        assert "项目名称" in df.columns
        assert "合同编号" in df.columns
        assert "登记工时" in df.columns

    def test_nonexistent_file_returns_empty(self):
        """不存在的文件返回空结构"""
        df = load_workhour_detail(Path("/nonexistent.xlsx"))
        assert df.empty


class TestLoadWorkhourPivot:
    """工时 pivot 加载测试"""

    def test_empty_mode_returns_structure(self):
        """骨架模式返回空结构"""
        df = load_workhour_pivot(None)
        assert df.empty
        assert "项目编号" in df.columns
        assert "工时合计" in df.columns


class TestAggregateByProject:
    """按项目汇总工时测试"""

    def _make_detail_df(self):
        return pd.DataFrame({
            "项目名称": ["项目A", "项目A", "项目B", "项目C", "项目B"],
            "合同编号": ["HT001", "HT001", "HT002", "HT003", "HT002"],
            "登记工时": ["8", "4", "6", "10", "2"],
            "填报人": ["张三", "李四", "王五", "赵六", "张三"],
        })

    def test_aggregate_by_project_basic(self):
        """按项目分组求和"""
        df = self._make_detail_df()
        result = aggregate_by_project(df)

        assert "项目编号" in result.columns
        assert "工时合计" in result.columns

        # 项目A: 8 + 4 = 12
        row_a = result[result["项目编号"] == "项目A"].iloc[0]
        assert row_a["工时合计"] == 12

        # 项目B: 6 + 2 = 8
        row_b = result[result["项目编号"] == "项目B"].iloc[0]
        assert row_b["工时合计"] == 8

    def test_aggregate_empty_df(self):
        """空 DataFrame 返回空结构"""
        result = aggregate_by_project(pd.DataFrame())
        assert result.empty
        assert "项目编号" in result.columns

    def test_aggregate_preserves_all_projects(self):
        """所有项目都在结果中"""
        df = self._make_detail_df()
        result = aggregate_by_project(df)

        assert len(result) == 3  # 项目A, 项目B, 项目C
        assert set(result["项目编号"]) == {"项目A", "项目B", "项目C"}


class TestAggregateByContract:
    """按合同汇总工时测试"""

    def _make_detail_df(self):
        return pd.DataFrame({
            "项目名称": ["项目A", "项目A-子项", "项目B", "项目C"],
            "合同编号": ["HT001", "HT001", "HT002", "HT003"],
            "登记工时": ["10", "5", "8", "20"],
        })

    def test_aggregate_by_contract_basic(self):
        """按合同编号分组求和"""
        df = self._make_detail_df()
        result = aggregate_by_contract(df)

        assert "合同编号" in result.columns
        assert "工时合计" in result.columns

        # HT001: 10 + 5 = 15
        row = result[result["合同编号"] == "HT001"].iloc[0]
        assert row["工时合计"] == 15

    def test_aggregate_sorted_desc(self):
        """结果按工时降序排列"""
        df = self._make_detail_df()
        result = aggregate_by_contract(df)

        # 项目C (HT003) 20 小时应该排第一
        assert result.iloc[0]["工时合计"] == 20

    def test_empty_df_returns_empty(self):
        """空 DataFrame 返回空结构"""
        result = aggregate_by_contract(pd.DataFrame())
        assert result.empty


class TestHoursToPersonDays:
    """人天换算测试"""

    def test_default_8_hours_per_day(self):
        """默认 8 小时/天"""
        assert hours_to_person_days(8) == 1.0
        assert hours_to_person_days(16) == 2.0

    def test_partial_day(self):
        """不足一天也按比例算"""
        assert hours_to_person_days(4) == 0.5
        assert hours_to_person_days(6) == 0.75

    def test_custom_hours_per_day(self):
        """自定义工时系数"""
        assert hours_to_person_days(10, hours_per_day=10) == 1.0
        assert hours_to_person_days(5, hours_per_day=10) == 0.5

    def test_zero_and_none(self):
        """零和空值处理"""
        assert hours_to_person_days(0) == 0.0
        assert hours_to_person_days(None) == 0.0
        import numpy as np
        assert hours_to_person_days(np.nan) == 0.0

    def test_round_to_2_decimals(self):
        """保留 2 位小数"""
        result = hours_to_person_days(10)  # 10/8 = 1.25
        assert result == 1.25
        assert isinstance(result, float)


class TestAddPocHoursColumn:
    """POC 明细加工时列测试"""

    def test_add_hours_column(self):
        """工时列正确写入 POC 明细"""
        df_poc = pd.DataFrame({
            "销售合同编号": ["HT001", "HT002", "HT003"],
            "项目名称": ["POC-A", "POC-B", "POC-C"],
        })
        df_hours = pd.DataFrame({
            "合同编号": ["HT001", "HT002", "HT003"],
            "工时合计": [40.0, 20.0, 0.0],
        })

        result = add_poc_hours_column(df_poc, df_hours)
        assert "POC项目工时合计（小时）" in result.columns

        # HT001 = 40 小时
        assert result.iloc[0]["POC项目工时合计（小时）"] == 40.0
        # HT003 = 0 小时
        assert result.iloc[2]["POC项目工时合计（小时）"] == 0.0

    def test_unmatched_contract_zero(self):
        """未匹配的合同工时为 0"""
        df_poc = pd.DataFrame({
            "销售合同编号": ["HT001", "HT999"],
            "项目名称": ["POC-A", "POC-Z"],
        })
        df_hours = pd.DataFrame({
            "合同编号": ["HT001"],
            "工时合计": [40.0],
        })

        result = add_poc_hours_column(df_poc, df_hours)
        # HT999 不在工时表中
        assert result.iloc[1]["POC项目工时合计（小时）"] == 0.0

    def test_empty_hours_returns_zero(self):
        """空工时表全部为 0"""
        df_poc = pd.DataFrame({
            "销售合同编号": ["HT001"],
            "项目名称": ["POC-A"],
        })
        df_empty = pd.DataFrame(columns=["合同编号", "工时合计"])

        result = add_poc_hours_column(df_poc, df_empty)
        assert result.iloc[0]["POC项目工时合计（小时）"] == 0.0


class TestAddPersonDaysColumn:
    """人天列测试"""

    def test_add_person_days(self):
        """工时列正确换算为人天"""
        df_poc = pd.DataFrame({
            "销售合同编号": ["HT001", "HT002"],
            "POC项目工时合计（小时）": [16.0, 4.0],
        })

        result = add_person_days_column(df_poc)

        assert "POC项目工时合计（人天）" in result.columns
        # 16 小时 = 2 人天
        assert result.iloc[0]["POC项目工时合计（人天）"] == 2.0
        # 4 小时 = 0.5 人天
        assert result.iloc[1]["POC项目工时合计（人天）"] == 0.5

    def test_missing_hours_column(self):
        """没有工时列时补 0"""
        df_poc = pd.DataFrame({
            "销售合同编号": ["HT001"],
        })
        result = add_person_days_column(df_poc)
        assert "POC项目工时合计（人天）" in result.columns
        assert result.iloc[0]["POC项目工时合计（人天）"] == 0.0


class TestGetPocProjectHoursByContract:
    """便捷函数测试"""

    def test_empty_source_returns_empty(self):
        """无数据源时返回空结构"""
        result = get_poc_project_hours_by_contract(None)
        assert result.empty
        assert "合同编号" in result.columns
        assert "POC项目工时合计（小时）" in result.columns
