"""
BDMS V2 — 合同信息引擎单元测试

验证 contract_engine.py 核心功能：
  1. 合同编号校准
  2. OA 合同加载与清洗
  3. 合同信息关联（join_contract_info）
  4. 合同统计汇总（summarize_contracts）
  5. 一体化 add_contract_columns
"""

import pytest
import pandas as pd
import sys
from pathlib import Path

# 路径设置
V2_DIR = Path(__file__).parent.parent / "src" / "delivery_center" / "v2"
sys.path.insert(0, str(V2_DIR / "engines"))

from contract_engine import (
    calibrate_contract_no,
    load_oa_contracts,
    join_contract_info,
    summarize_contracts,
    add_contract_columns,
)


class TestCalibrateContractNo:
    """合同编号校准测试"""

    def test_normal_contract_no(self):
        """正常合同号保持不变（转大写）"""
        assert calibrate_contract_no("HT20260001") == "HT20260001"

    def test_lowercase_to_upper(self):
        """小写转大写"""
        assert calibrate_contract_no("ht20260001") == "HT20260001"

    def test_strip_ampersand(self):
        """去除 & 后面内容"""
        assert calibrate_contract_no("HT20260001&补充协议1") == "HT20260001"

    def test_strip_spaces(self):
        """去除首尾空格"""
        assert calibrate_contract_no("  HT20260001  ") == "HT20260001"

    def test_empty_and_none(self):
        """空值处理"""
        assert calibrate_contract_no("") == ""
        assert calibrate_contract_no(None) == ""
        assert calibrate_contract_no(123) == ""


class TestLoadOAContracts:
    """OA 合同加载与清洗测试"""

    def test_empty_mode_returns_structure(self):
        """骨架模式（无文件）返回空结构，列齐全"""
        df = load_oa_contracts(None)
        assert isinstance(df, pd.DataFrame)
        assert df.empty
        expected_cols = [
            "合同编号", "原始合同编号", "签约金额", "合同归档日期",
            "合同起始日期", "合同结束日期", "客户名称",
            "责任销售", "责任销售所属部门", "合同类型", "产品分类"
        ]
        for col in expected_cols:
            assert col in df.columns, f"缺少列: {col}"

    def test_nonexistent_file_returns_empty(self):
        """不存在的文件返回空结构"""
        df = load_oa_contracts(Path("/nonexistent/path.xlsx"))
        assert df.empty


class TestJoinContractInfo:
    """合同信息关联测试"""

    def _make_projects_df(self):
        return pd.DataFrame({
            "销售合同编号": ["HT001", "HT002", "HT003", "HT004"],
            "项目名称": ["项目A", "项目B", "项目C", "项目D"],
            "负责人": ["张三", "李四", "王五", "赵六"],
        })

    def _make_contracts_df(self):
        return pd.DataFrame({
            "合同编号": ["HT001", "HT002", "HT003"],
            "签约金额": [100000, 200000, 300000],
            "合同起始日期": pd.to_datetime(["2026-01-01", "2026-02-01", "2026-03-01"]),
            "合同结束日期": pd.to_datetime(["2026-12-31", "2027-02-28", "2026-09-30"]),
            "客户名称": ["客户甲", "客户乙", "客户丙"],
            "责任销售": ["销售A", "销售B", "销售C"],
        })

    def test_join_adds_oa_columns(self):
        """关联后新增 oa_ 前缀列"""
        df_proj = self._make_projects_df()
        df_contracts = self._make_contracts_df()

        result = join_contract_info(df_proj, df_contracts)

        assert "oa_签约金额" in result.columns
        assert "oa_合同起始日期" in result.columns
        assert "oa_客户名称" in result.columns

    def test_join_preserves_all_rows(self):
        """左连接：保留所有项目行"""
        df_proj = self._make_projects_df()
        df_contracts = self._make_contracts_df()

        result = join_contract_info(df_proj, df_contracts)
        assert len(result) == len(df_proj)  # 4 行都保留

    def test_join_matched_values(self):
        """匹配的行值正确"""
        df_proj = self._make_projects_df()
        df_contracts = self._make_contracts_df()

        result = join_contract_info(df_proj, df_contracts)

        # HT001 应该匹配到 100000
        row_ht001 = result[result["销售合同编号"] == "HT001"].iloc[0]
        assert row_ht001["oa_签约金额"] == 100000
        assert row_ht001["oa_客户名称"] == "客户甲"

    def test_join_unmatched_has_empty(self):
        """未匹配的行 oa_ 列为空"""
        df_proj = self._make_projects_df()
        df_contracts = self._make_contracts_df()

        result = join_contract_info(df_proj, df_contracts)

        # HT004 不在合同表中
        row_ht004 = result[result["销售合同编号"] == "HT004"].iloc[0]
        assert pd.isna(row_ht004["oa_签约金额"]) or row_ht004["oa_签约金额"] == ""

    def test_empty_contracts_adds_empty_columns(self):
        """合同数据为空时，补空列保证结构一致"""
        df_proj = self._make_projects_df()
        df_empty = pd.DataFrame(columns=["合同编号", "签约金额"])

        result = join_contract_info(df_proj, df_empty)
        assert len(result) == 4
        assert "oa_签约金额" in result.columns

    def test_contract_no_case_insensitive(self):
        """合同编号大小写不敏感（已统一大写）"""
        df_proj = pd.DataFrame({
            "销售合同编号": ["ht001", "HT002"],
            "项目名称": ["项目A", "项目B"],
        })
        df_contracts = pd.DataFrame({
            "合同编号": ["HT001", "HT002"],
            "签约金额": [100, 200],
        })

        result = join_contract_info(df_proj, df_contracts)
        # ht001 校准后为 HT001，应该匹配
        row_a = result[result["销售合同编号"] == "ht001"].iloc[0]
        assert row_a["oa_签约金额"] == 100


class TestSummarizeContracts:
    """合同统计汇总测试"""

    def test_basic_summary(self):
        """按合同分组汇总履约项数量"""
        df = pd.DataFrame({
            "销售合同编号": ["HT001", "HT001", "HT002", "HT003"],
            "所属项目": ["项目A", "项目A", "项目B", "项目C"],
        })

        result = summarize_contracts(df)

        assert "合同编号" in result.columns
        assert "履约项数量" in result.columns
        # HT001 有 2 个履约项
        ht001_row = result[result["合同编号"] == "HT001"].iloc[0]
        assert ht001_row["履约项数量"] == 2

    def test_empty_df_returns_empty(self):
        """空 DataFrame 返回空"""
        result = summarize_contracts(pd.DataFrame())
        assert result.empty


class TestAddContractColumns:
    """一体化 add_contract_columns 测试"""

    def test_with_df_contracts(self):
        """传入已加载的合同 DataFrame"""
        df_proj = pd.DataFrame({
            "销售合同编号": ["HT001", "HT002"],
            "项目名称": ["项目A", "项目B"],
        })
        df_contracts = pd.DataFrame({
            "合同编号": ["HT001", "HT002"],
            "签约金额": [100000, 200000],
            "客户名称": ["客户甲", "客户乙"],
        })

        result = add_contract_columns(df_proj, df_contracts=df_contracts)
        assert "oa_签约金额" in result.columns
        assert len(result) == 2

    def test_without_any_source_returns_original(self):
        """不传任何数据源时，补空列"""
        df_proj = pd.DataFrame({
            "销售合同编号": ["HT001"],
            "项目名称": ["项目A"],
        })
        result = add_contract_columns(df_proj)
        # 应该有 oa_ 开头的列（空值）
        assert "oa_签约金额" in result.columns
        assert len(result) == 1
