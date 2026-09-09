"""
BDMS v2 — 异常项目模块测试

覆盖：
- 异常项目与主项目的关联关系
- 异常状态流转（发现→跟进→关闭）
- 异常分类统计
- 边界：空异常列表、单项目多异常、跨事业部异常
"""

import pytest
import pandas as pd
from pathlib import Path
import sys

V2_DIR = Path(__file__).parent.parent / "v2"
sys.path.insert(0, str(V2_DIR))
sys.path.insert(0, str(V2_DIR / "engines"))


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def sign_df():
    """签约主表 fixture（3 个项目，跨 2 个事业部）"""
    return pd.DataFrame({
        "销售合同编号": ["HT-001", "HT-002", "HT-003", "HT-004"],
        "项目经理": ["张三", "李四", "王五", "赵六"],
        "项目经理所属部门": ["政企一部", "政企二部", "政企一部", "金融事业部"],
        "项目验收状态（即，财报-验收状态）": ["未验收", "正常验收", "未验收", "正常验收"],
        "客户名称": ["客户A", "客户B", "客户C", "客户D"],
        "状态": ["实施进行中", "验收文件已归档", "交付邮件已归档", "验收文件已归档"],
    })


@pytest.fixture
def exception_df():
    """异常项目 fixture（4 条异常，覆盖不同状态和分类）"""
    return pd.DataFrame({
        "销售合同编号": ["HT-001", "HT-001", "HT-003", "HT-999"],
        "标题": ["异常-交付延迟", "异常-需求变更", "异常-验收争议", "异常-资源不足"],
        "项目类型(概览)": ["交付类", "变更类", "验收类", "交付类"],
        "项目状态": ["处理中", "已关闭", "跟进中", "已关闭"],
        "履约项异常/变更类型": ["履约项交付异常", "履约项变更", "履约项验收异常", "履约项交付异常"],
        "异常项目-类别": ["进度风险", "范围变更", "验收风险", "资源风险"],
        "异常处置状态": ["跟进中", "已关闭", "处理中", "已关闭"],
        "异常影响情况": ["交付延期 2 周", "金额增加 10%", "验收退回", "启动延期"],
        "交付说明（异常履约项统计类别）": ["交付延迟", "变更确认", "验收争议", "资源问题"],
        "事业部（区域）": ["华北区", "华北区", "华东区", "华南区"],
        "异常报备日期": ["2026-06-01", "2026-05-15", "2026-06-10", "2026-06-20"],
        "异常归档日期": ["", "2026-06-20", "", "2026-06-25"],
        "备注": ["需重点关注", "已闭环", "客户不满", "已补充人力"],
        "ID": ["EXC-001", "EXC-002", "EXC-003", "EXC-004"],
        "BI履约ID": ["BI-001", "BI-002", "BI-003", "BI-999"],
        "最终用户名称": ["用户A", "用户A", "用户C", "用户X"],
        "责任销售（履约项）": ["销售甲", "销售甲", "销售乙", "销售丙"],
        "负责人": ["张三", "张三", "王五", "钱七"],
        "所属项目": ["项目A", "项目A", "项目C", "项目X"],
    })


# ============================================================
# build_exception_df 核心测试
# ============================================================

class TestBuildExceptionDf:
    """异常项目 DataFrame 构建测试"""

    def test_join_pm_from_sign_table(self, sign_df, exception_df):
        """异常表关联签约表：项目经理正确回填"""
        from exception_engine import build_exception_df

        df = build_exception_df(exception_df, sign_df)

        assert "项目经理" in df.columns
        # HT-001 的项目经理是张三
        mask = df["销售合同编号"] == "HT-001"
        assert df.loc[mask, "项目经理"].iloc[0] == "张三"
        # HT-003 的项目经理是王五
        mask = df["销售合同编号"] == "HT-003"
        assert df.loc[mask, "项目经理"].iloc[0] == "王五"

    def test_join_pm_team_from_sign_table(self, sign_df, exception_df):
        """异常表关联签约表：项目经理团队正确回填"""
        from exception_engine import build_exception_df

        df = build_exception_df(exception_df, sign_df)

        assert "项目经理团队" in df.columns
        mask = df["销售合同编号"] == "HT-001"
        assert df.loc[mask, "项目经理团队"].iloc[0] == "政企一部"

    def test_join_acceptance_status_from_sign_table(self, sign_df, exception_df):
        """异常表关联签约表：项目验收状态正确回填"""
        from exception_engine import build_exception_df

        df = build_exception_df(exception_df, sign_df)

        assert "项目验收状态" in df.columns
        # HT-001 未验收
        mask = df["销售合同编号"] == "HT-001"
        assert df.loc[mask, "项目验收状态"].iloc[0] == "未验收"
        # HT-003 未验收
        mask = df["销售合同编号"] == "HT-003"
        assert df.loc[mask, "项目验收状态"].iloc[0] == "未验收"

    def test_unknown_contract_na(self, sign_df, exception_df):
        """签约表里不存在的合同号，关联字段为空/NaN"""
        from exception_engine import build_exception_df

        df = build_exception_df(exception_df, sign_df)

        # HT-999 不在签约表里
        mask = df["销售合同编号"] == "HT-999"
        pm_val = df.loc[mask, "项目经理"].iloc[0]
        assert pd.isna(pm_val) or pm_val == "" or pm_val is None

    def test_preserves_all_exception_rows(self, sign_df, exception_df):
        """build_exception_df 保留所有异常行（左连接语义）"""
        from exception_engine import build_exception_df

        df = build_exception_df(exception_df, sign_df)
        assert len(df) == len(exception_df), "异常行数不应减少"

    def test_column_order_and_core_columns_exist(self, sign_df, exception_df):
        """输出包含预期的核心列（build_exception_df 按白名单过滤后仍存在的列）"""
        from exception_engine import build_exception_df

        df = build_exception_df(exception_df, sign_df)

        # 必须存在的核心列（在 expected_cols 白名单中的列）
        core_cols = [
            "销售合同编号", "标题", "履约项异常/变更类型",
            "异常项目-类别", "异常影响情况",
            "项目经理", "项目经理团队", "项目验收状态",
            "事业部（区域）", "异常报备日期",
        ]
        for col in core_cols:
            assert col in df.columns, f"缺少核心列: {col}"


# ============================================================
# 异常状态流转测试
# ============================================================

class TestExceptionStatusFlow:
    """异常状态流转 & 分类统计"""

    def test_exception_status_distribution(self, exception_df):
        """异常状态分布统计：跟进中/处理中/已关闭"""
        status_counts = exception_df["异常处置状态"].value_counts()

        assert status_counts.get("已关闭", 0) == 2
        assert status_counts.get("跟进中", 0) == 1
        assert status_counts.get("处理中", 0) == 1

    def test_exception_category_distribution(self, exception_df):
        """异常分类统计：按异常项目-类别分组"""
        cat_counts = exception_df["异常项目-类别"].value_counts()

        assert "进度风险" in cat_counts.index
        assert "验收风险" in cat_counts.index
        assert "范围变更" in cat_counts.index

    def test_exception_by_abnormal_type(self, exception_df):
        """按履约项异常/变更类型分类统计"""
        type_counts = exception_df["履约项异常/变更类型"].value_counts()

        delivery_count = type_counts.get("履约项交付异常", 0)
        acceptance_count = type_counts.get("履约项验收异常", 0)
        assert delivery_count == 2
        assert acceptance_count == 1

    def test_open_exception_count(self, exception_df):
        """未关闭异常数量统计"""
        open_mask = exception_df["异常处置状态"].isin(["跟进中", "处理中"])
        open_count = open_mask.sum()

        assert open_count == 2, f"预期 2 个未关闭异常，实际 {open_count}"

    def test_cross_dept_exception(self, sign_df, exception_df):
        """跨事业部异常：异常项目分布在不同事业部"""
        dept_counts = exception_df["事业部（区域）"].value_counts()

        assert len(dept_counts) >= 2, "异常应分布在多个事业部"
        assert "华北区" in dept_counts.index
        assert "华东区" in dept_counts.index


# ============================================================
# 异常关联（签约侧 lookup）测试
# ============================================================

class TestExceptionLookupOnSign:
    """签约明细表上的异常关联列测试（mapping_engine）"""

    def test_mark_has_exception(self, sign_df, exception_df):
        """有异常的合同标记为'有'"""
        from mapping_engine import add_exception_lookup_columns

        df = add_exception_lookup_columns(sign_df, exception_df)

        assert df.iloc[0]["异常项目对比"] == "有"   # HT-001
        assert df.iloc[2]["异常项目对比"] == "有"   # HT-003

    def test_mark_no_exception(self, sign_df, exception_df):
        """无异常的合同标记为空"""
        from mapping_engine import add_exception_lookup_columns

        df = add_exception_lookup_columns(sign_df, exception_df)

        assert df.iloc[1]["异常项目对比"] == ""    # HT-002 无异常
        assert df.iloc[3]["异常项目对比"] == ""    # HT-004 无异常

    def test_lookup_exception_status(self, sign_df, exception_df):
        """异常处置状态 lookup：取第一条匹配"""
        from mapping_engine import add_exception_lookup_columns

        df = add_exception_lookup_columns(sign_df, exception_df)

        # HT-001 有 2 条异常，取第一条（跟进中）
        assert df.iloc[0]["异常处置状态"] == "跟进中"

    def test_lookup_exception_impact(self, sign_df, exception_df):
        """异常影响情况 lookup"""
        from mapping_engine import add_exception_lookup_columns

        df = add_exception_lookup_columns(sign_df, exception_df)

        assert "交付延期" in df.iloc[0]["异常影响情况"]
        # HT-002 无异常，影响为空
        assert df.iloc[1]["异常影响情况"] == ""

    def test_multiple_exceptions_same_contract(self, sign_df, exception_df):
        """单项目多异常：lookup 只取第一条，不重复行"""
        from mapping_engine import add_exception_lookup_columns

        df = add_exception_lookup_columns(sign_df, exception_df)

        # 签约表行数不变
        assert len(df) == len(sign_df)
        # HT-001 有多条异常，但只有一条记录
        assert (df["销售合同编号"] == "HT-001").sum() == 1


# ============================================================
# 边界测试
# ============================================================

class TestExceptionBoundary:
    """异常模块边界测试"""

    def test_empty_exception_list(self, sign_df):
        """空异常列表：所有项目异常标记为空"""
        from mapping_engine import add_exception_lookup_columns

        empty_exc = pd.DataFrame(columns=["销售合同编号", "异常处置状态", "异常影响情况", "交付说明"])
        df = add_exception_lookup_columns(sign_df, empty_exc)

        assert (df["异常项目对比"] == "").all()
        assert (df["异常处置状态"] == "").all()

    def test_empty_sign_table(self):
        """空签约表 + 有异常：返回空 DataFrame，但列存在"""
        from mapping_engine import add_exception_lookup_columns

        empty_sign = pd.DataFrame(columns=["销售合同编号"])
        exc = pd.DataFrame({
            "销售合同编号": ["HT-001"],
            "异常处置状态": ["处理中"],
            "异常影响情况": ["测试"],
            "交付说明": ["测试"],
        })
        df = add_exception_lookup_columns(empty_sign, exc)

        assert len(df) == 0
        assert "异常项目对比" in df.columns

    def test_build_exception_empty_raw(self, sign_df):
        """build_exception_df 输入空异常表"""
        from exception_engine import build_exception_df

        empty_exc = pd.DataFrame(columns=["销售合同编号"])
        df = build_exception_df(empty_exc, sign_df)

        assert len(df) == 0
        # 仍应包含核心列
        assert "销售合同编号" in df.columns

    def test_exception_with_nan_contract_id(self, sign_df):
        """异常表含空合同号：不影响其他正常行"""
        from mapping_engine import add_exception_lookup_columns

        exc = pd.DataFrame({
            "销售合同编号": ["HT-001", None, "HT-003"],
            "异常处置状态": ["处理中", "已关闭", "跟进中"],
            "异常影响情况": ["问题A", "问题B", "问题C"],
            "交付说明": ["说明A", "说明B", "说明C"],
        })
        df = add_exception_lookup_columns(sign_df, exc)

        # HT-001 和 HT-003 正常标记
        assert df.iloc[0]["异常项目对比"] == "有"
        assert df.iloc[2]["异常项目对比"] == "有"
        # HT-002 无异常
        assert df.iloc[1]["异常项目对比"] == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
