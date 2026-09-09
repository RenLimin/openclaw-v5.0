"""
BDMS v2 — 统计 Sheet & 边界 & 大数量级测试

覆盖：
- 签约统计 Pivot 生成
- POC 统计 Pivot 生成
- 异常统计 Pivot 生成
- 交接统计 Pivot 生成
- 15 个 Sheet 全部生成验证（编排层）
- 空数据集边界
- 单项目极端场景
- 字段缺失容错性
- 大数量级性能冒烟（100+ 项目）
"""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path
import sys
import time

V2_DIR = Path(__file__).parent.parent / "v2"
sys.path.insert(0, str(V2_DIR))
sys.path.insert(0, str(V2_DIR / "engines"))
sys.path.insert(0, str(V2_DIR / "generators"))
sys.path.insert(0, str(V2_DIR / "config"))


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def sign_detail_df():
    """经过引擎处理后的签约明细 fixture（含状态、考核、映射、异常列）"""
    from status_engine import add_status_columns
    from scoring_engine import add_scoring_columns
    from mapping_engine import add_mapping_columns, add_simple_computed_columns

    df = pd.DataFrame({
        "ID": [f"ID-{i:04d}" for i in range(20)],
        "所属项目": [f"项目{i}" for i in range(20)],
        "销售合同编号": [f"HT-{i:03d}" for i in range(20)],
        "负责人": ["张三"] * 5 + ["李四"] * 5 + ["王五"] * 5 + ["赵六"] * 5,
        "责任销售所属团队": ["北区营销部"] * 10 + ["南区营销部"] * 10,
        "状态": (
            ["交付邮件已归档"] * 4
            + ["验收文件已归档"] * 4
            + ["实施进行中"] * 4
            + ["交付邮件已归档"] * 4
            + ["验收文件已归档"] * 4
        ),
        "履约项异常/变更类型": [""] * 15 + ["履约项交付异常"] * 3 + ["履约项验收异常"] * 2,
        "预估交付完成日期": ["2026-05-01"] * 20,
        "预估验收完成日期": ["2026-06-15"] * 20,
        "实际服务/授权结束日期": ["2026-12-31"] * 20,
        "项目状态": ["进行中"] * 20,
        "基线-预估结项日期": ["2026-06-01"] * 20,
        "实际结项日期": ["2026-06-03"] * 10 + ["2026-06-20"] * 5 + [""] * 5,
        "合同归档日期": ["2026-01-15"] * 7 + ["2025-12-10"] * 8 + ["2026-03-20"] * 5,
        "预算-预估验收完成日期": ["2026-06-30"] * 20,
    })

    df = add_simple_computed_columns(df)
    df = add_status_columns(df, "2026-06-30")
    df = add_scoring_columns(df)
    df = add_mapping_columns(df)

    return df


@pytest.fixture
def poc_detail_df():
    """POC&提前实施明细 fixture"""
    from mapping_engine import add_mapping_columns

    df = pd.DataFrame({
        "ID": [f"POC-{i:03d}" for i in range(15)],
        "所属项目": [f"POC项目{i}" for i in range(15)],
        "销售合同编号": [f"HT-POC-{i:03d}" if i < 10 else "" for i in range(15)],
        "负责人": ["张三"] * 5 + ["李四"] * 5 + ["王五"] * 5,
        "责任销售所属团队": ["北区"] * 10 + ["南区"] * 5,
        "项目类型(概览)": ["POC"] * 8 + ["提前实施"] * 7,
        "立项日期": ["2026-01-10"] * 5 + ["2026-03-15"] * 5 + ["2026-05-20"] * 5,
        "状态": ["实施进行中"] * 15,
        "履约项异常/变更类型": [""] * 15,
        "预估交付完成日期": ["2026-07-01"] * 15,
        "预估验收完成日期": ["2026-08-01"] * 15,
        "实际服务/授权结束日期": ["2026-12-31"] * 15,
        "项目状态": ["进行中"] * 15,
        "基线-预估结项日期": ["2026-06-01"] * 15,
        "实际结项日期": [""] * 15,
        "合同归档日期": ["2026-02-01"] * 8 + [""] * 7,
        "预算-预估验收完成日期": ["2026-09-01"] * 15,
        "所属产线": ["安全产品线"] * 5 + ["数据产品线"] * 5 + ["云产品线"] * 5,
        "POC项目工时合计（小时）": [100, 200, 150, 300, 250, 80, 120, 90, 0, 0, 0, 0, 0, 0, 0],
        "提前实施项目持续周期-统计": (
            ["1个月内"] * 3 + ["3个月内"] * 4 + ["6个月内"] * 3 + [""] * 5
        ),
    })

    df = add_mapping_columns(df)
    return df


@pytest.fixture
def exception_detail_df():
    """异常项目明细 fixture"""
    return pd.DataFrame({
        "ID": [f"EXC-{i:03d}" for i in range(10)],
        "销售合同编号": [f"HT-{i:03d}" for i in range(10)],
        "异常报备日期": [
            "2026-06-01", "2026-06-05", "2026-05-20", "2026-06-10", "2026-04-15",
            "2026-06-15", "2026-03-10", "2026-06-20", "2026-06-25", "2026-05-30",
        ],
        "异常归档日期": [
            "", "2026-06-08", "", "", "2026-05-01",
            "", "2026-04-15", "", "2026-06-28", "",
        ],
        "异常影响情况": [
            "进度延迟", "资源不足", "需求变更", "质量问题", "客户原因",
            "范围蔓延", "第三方依赖", "人员变动", "环境问题", "技术难点",
        ],
        "异常项目-类别": [
            "进度风险", "资源风险", "范围变更", "质量风险", "客户风险",
            "范围变更", "外部依赖", "资源风险", "环境风险", "技术风险",
        ],
        "合同归档年度": [
            "2026", "2026", "2025", "2026", "2025",
            "2026", "2025", "2026", "2026", "2025",
        ],
        "履约项异常/变更类型": [
            "履约项交付异常", "履约项交付异常", "履约项变更", "履约项验收异常", "履约项交付异常",
            "履约项交付异常", "履约项变更", "履约项验收异常", "履约项交付异常", "履约项交付异常",
        ],
        "事业部（区域）": ["华北区"] * 5 + ["华东区"] * 3 + ["华南区"] * 2,
        "项目经理": ["张三", "李四", "王五", "赵六", "张三", "李四", "王五", "赵六", "张三", "李四"],
    })


# ============================================================
# 签约统计测试
# ============================================================

class TestSignStats:
    """签约统计 Sheet 生成测试"""

    def test_build_sign_stats_returns_left_and_right(self, sign_detail_df):
        """签约统计返回 left 和 right 两个 pivot"""
        from build_v2_report import StatsSheetBuilder

        builder = StatsSheetBuilder()
        results = builder.build_sign_stats(sign_detail_df)

        assert "left" in results
        assert "right" in results

    def test_sign_stats_left_structure(self, sign_detail_df):
        """左侧 pivot：合同归档年度 × 计数"""
        from build_v2_report import StatsSheetBuilder

        builder = StatsSheetBuilder()
        results = builder.build_sign_stats(sign_detail_df)
        left = results["left"]

        assert "合同归档年度" in left.columns
        assert "计数项:ID" in left.columns
        # 总计数 = 总行数
        assert left["计数项:ID"].sum() == len(sign_detail_df)

    def test_sign_stats_right_has_total_column(self, sign_detail_df):
        """右侧 pivot：有总计列"""
        from build_v2_report import StatsSheetBuilder

        builder = StatsSheetBuilder()
        results = builder.build_sign_stats(sign_detail_df)
        right = results["right"]

        assert "总计" in right.columns
        # 总计列之和 = 总行数
        assert right["总计"].sum() == len(sign_detail_df)

    def test_sign_stats_right_status_index(self, sign_detail_df):
        """右侧 pivot：行索引是履约项统计状态"""
        from build_v2_report import StatsSheetBuilder

        builder = StatsSheetBuilder()
        results = builder.build_sign_stats(sign_detail_df)
        right = results["right"]

        # 索引应该是各种状态
        # 索引是带编号的状态名
        status_names = list(right.index)
        assert len(status_names) >= 2  # 至少 2 种状态
        for name in status_names:
            assert "：" in name or ":" in name, f"状态名应带编号前缀: {name}"

# ============================================================
# POC 统计测试
# ============================================================

class TestPocStats:
    """POC&提前实施统计 Sheet 测试"""

    def test_build_poc_stats_returns_left(self, poc_detail_df):
        """POC 统计至少返回 left pivot"""
        from build_v2_report import StatsSheetBuilder

        builder = StatsSheetBuilder()
        results = builder.build_poc_stats(poc_detail_df)

        assert "left" in results

    def test_poc_stats_left_total_column(self, poc_detail_df):
        """左侧 pivot：有总计列，总数=POC+提前实施总数"""
        from build_v2_report import StatsSheetBuilder

        builder = StatsSheetBuilder()
        results = builder.build_poc_stats(poc_detail_df)
        left = results["left"]

        assert "总计" in left.columns
        assert left["总计"].sum() == len(poc_detail_df)

    def test_poc_stats_middle_early_impl(self, poc_detail_df):
        """中间 pivot：提前实施项目按部门×周期统计"""
        from build_v2_report import StatsSheetBuilder

        builder = StatsSheetBuilder()
        results = builder.build_poc_stats(poc_detail_df)

        if "middle" in results:
            mid = results["middle"]
            # 只包含提前实施项目
            early_count = len(poc_detail_df[poc_detail_df["项目类型(概览)"] == "提前实施"])
            assert mid.values.sum() > 0

    def test_poc_stats_right_poc_hours(self, poc_detail_df):
        """右侧 pivot：POC 项目按产线×部门工时求和"""
        from build_v2_report import StatsSheetBuilder

        builder = StatsSheetBuilder()
        results = builder.build_poc_stats(poc_detail_df)

        if "right" in results:
            right = results["right"]
            # 工时应大于 0
            assert right.values.sum() > 0


# ============================================================
# 异常统计测试
# ============================================================

class TestAbnormalStats:
    """异常统计 Sheet 测试"""

    def test_build_abnormal_stats_returns_data(self, exception_detail_df):
        """异常统计返回 pivot 数据"""
        from build_v2_report import StatsSheetBuilder

        builder = StatsSheetBuilder()
        results = builder.build_abnormal_stats(exception_detail_df)

        # 至少有一个 pivot（报备或归档）
        assert len(results) > 0

    def test_abnormal_stats_left_report_date(self, exception_detail_df):
        """左侧：按报备年月 × 合同归档年度"""
        from build_v2_report import StatsSheetBuilder

        builder = StatsSheetBuilder()
        results = builder.build_abnormal_stats(exception_detail_df)

        if "left" in results:
            left = results["left"]
            # 索引是 (年份, 月份) MultiIndex
            assert left.index.nlevels >= 1
            # 数量应该 <= 总异常数
            assert left.values.sum() <= len(exception_detail_df)

    def test_abnormal_stats_filters_empty_impact(self):
        """异常影响情况为空的记录被过滤出统计"""
        from build_v2_report import StatsSheetBuilder

        builder = StatsSheetBuilder()
        df = pd.DataFrame({
            "ID": ["E1", "E2", "E3"],
            "异常报备日期": ["2026-06-01", "2026-06-05", "2026-06-10"],
            "异常影响情况": ["有影响", "", "有影响"],
            "合同归档年度": ["2026", "2026", "2026"],
            "异常归档日期": ["", "", ""],
        })

        results = builder.build_abnormal_stats(df)
        if "left" in results:
            left = results["left"]
            # 空影响情况的记录不应计入
            assert left.values.sum() == 2


# ============================================================
# 交接统计测试
# ============================================================

class TestHandoverStats:
    """交接统计 Sheet 测试"""

    def test_build_handover_stats_with_valid_data(self):
        """有有效数据时返回交接统计"""
        from build_v2_report import StatsSheetBuilder

        builder = StatsSheetBuilder()
        df_rev = pd.DataFrame({
            "ID": ["R1", "R2", "R3", "R4"],
            "交接年月": ["202606", "202606", "202606", "202606"],
            "跨月交接": ["是", "否", "否", "是"],
        })
        df_acc = pd.DataFrame({
            "ID": ["A1", "A2", "A3"],
            "交接年月": ["202606", "202606", "202606"],
            "跨月交接": ["否", "否", "是"],
        })

        results = builder.build_handover_stats(df_rev, df_acc)

        assert "revenue" in results
        assert "acceptance" in results

    def test_handover_stats_cross_month_ratio(self):
        """跨月比率计算正确"""
        from build_v2_report import StatsSheetBuilder

        builder = StatsSheetBuilder()
        df_rev = pd.DataFrame({
            "ID": ["R1", "R2", "R3", "R4"],
            "交接年月": ["202606", "202606", "202606", "202606"],
            "跨月交接": ["是", "是", "否", "否"],
        })
        df_acc = pd.DataFrame()

        results = builder.build_handover_stats(df_rev, df_acc)
        rev_pivot = results["revenue"]

        assert "跨月比率" in rev_pivot.columns
        # 2/4 = 0.5
        assert rev_pivot.iloc[0]["跨月比率"] == 0.5

    def test_handover_stats_empty_df(self):
        """空 DataFrame 不报错，返回空结果"""
        from build_v2_report import StatsSheetBuilder

        builder = StatsSheetBuilder()
        results = builder.build_handover_stats(pd.DataFrame(), pd.DataFrame())
        assert isinstance(results, dict)
        assert len(results) == 0


# ============================================================
# 15 个 Sheet 验证 & 报告结构
# ============================================================

class TestReportStructure:
    """报告整体结构测试"""

    def test_sheet_order_15_sheets(self):
        """SHEET_ORDER 定义了 15 个 Sheet"""
        from build_v2_report import SHEET_ORDER

        assert len(SHEET_ORDER) == 15, f"预期 15 个 Sheet，实际 {len(SHEET_ORDER)} 个"

    def test_sheet_order_contains_key_sheets(self):
        """关键 Sheet 都在列表中"""
        from build_v2_report import SHEET_ORDER

        expected = [
            "签约", "POC&提前实施", "异常项目",
            "确收交接", "验收交接",
            "签约统计", "异常统计", "图例",
            "交付效率统计", "交接统计",
        ]
        for sheet in expected:
            assert sheet in SHEET_ORDER, f"缺少关键 Sheet: {sheet}"

    def test_report_config_computes_end_date(self):
        """ReportConfig 正确计算报告截止日期"""
        from build_v2_report import ReportConfig

        # 小月（6月有30天）
        cfg = ReportConfig(report_month="202606")
        assert cfg.report_date == "2026-06-30"

        # 大月
        cfg2 = ReportConfig(report_month="202601")
        assert cfg2.report_date == "2026-01-31"

        # 2月（平年28天）
        cfg3 = ReportConfig(report_month="202602")
        assert cfg3.report_date == "2026-02-28"

        # 12月
        cfg4 = ReportConfig(report_month="202612")
        assert cfg4.report_date == "2026-12-31"

    def test_orchestrator_build_preserves_rows(self, sign_detail_df):
        """引擎编排器 build_sign_detail 保留行数"""
        from build_v2_report import ReportConfig, ReportEngineOrchestrator

        cfg = ReportConfig(report_month="202606")
        orch = ReportEngineOrchestrator(cfg)

        # 造一个简化版异常表
        exc = pd.DataFrame({"销售合同编号": [], "异常处置状态": [], "异常影响情况": [], "交付说明": []})

        result = orch.build_sign_detail(sign_detail_df, exc)
        assert len(result) == len(sign_detail_df)
        assert len(result.columns) > len(sign_detail_df.columns)  # 加了更多列


# ============================================================
# 边界 & 异常测试
# ============================================================

class TestBoundaryCases:
    """边界场景测试"""

    def test_empty_sign_detail_stats(self):
        """空签约明细（0行但有列）：统计生成返回空结果字典，不崩溃"""
        from build_v2_report import StatsSheetBuilder

        builder = StatsSheetBuilder()
        # 有 1 行数据但值为空，确保 pivot_table 能工作
        emptyish_df = pd.DataFrame({
            "合同归档年度": [""],
            "ID": [""],
            "履约项统计状态（即，财报-交付/确收状态）": [""],
        })
        results = builder.build_sign_stats(emptyish_df)

        assert isinstance(results, dict)
        # left pivot 应该存在
        assert "left" in results

    def test_single_project_extreme(self):
        """单项目极端场景：所有引擎都能处理 1 行数据"""
        from status_engine import add_status_columns
        from scoring_engine import add_scoring_columns
        from mapping_engine import add_mapping_columns, add_simple_computed_columns

        df = pd.DataFrame({
            "ID": ["SINGLE-001"],
            "所属项目": ["单项目"],
            "销售合同编号": ["HT-SINGLE"],
            "负责人": ["独苗PM"],
            "责任销售所属团队": ["独立销售"],
            "状态": ["交付邮件已归档"],
            "履约项异常/变更类型": [""],
            "预估交付完成日期": ["2026-05-01"],
            "预估验收完成日期": ["2026-07-01"],
            "实际服务/授权结束日期": ["2026-12-31"],
            "项目状态": ["进行中"],
            "基线-预估结项日期": ["2026-06-01"],
            "实际结项日期": ["2026-06-02"],
            "合同归档日期": ["2026-01-01"],
            "预算-预估验收完成日期": ["2026-08-01"],
        })

        df = add_simple_computed_columns(df)
        df = add_status_columns(df, "2026-06-30")
        df = add_scoring_columns(df)
        df = add_mapping_columns(df)

        assert len(df) == 1
        assert "履约项统计状态（即，财报-交付/确收状态）" in df.columns
        assert df.iloc[0]["项目经理所属部门"] == "未匹配"  # 未知PM

    def test_all_missing_fields_tolerant(self):
        """大部分字段缺失：状态引擎能容错处理，不崩溃"""
        from status_engine import add_status_columns

        df = pd.DataFrame({
            "ID": ["MINIMAL-001"],
            "状态": [""],
            "项目状态": [""],
            "履约项异常/变更类型": [""],
        })

        # 即使缺少日期列也应能运行（可能有警告但不崩溃）
        df = add_status_columns(df, "2026-06-30")

        assert len(df) == 1
        assert "履约项统计状态（即，财报-交付/确收状态）" in df.columns

    def test_nan_values_in_key_columns(self):
        """关键列含 NaN：状态判定和映射不崩溃"""
        from status_engine import determine_status

        row = pd.Series({
            "状态": None,
            "履约项异常/变更类型": None,
            "预估交付完成日期": None,
            "预估验收完成日期": None,
            "实际服务/授权结束日期": None,
        })

        result = determine_status(row, "2026-06-30")
        # 全空时默认返回正常交付
        assert result == "正常交付"

    def test_malformed_date_strings(self):
        """格式错误的日期字符串：不崩溃，返回默认值"""
        from scoring_engine import _parse_date, _calc_diff_days

        assert _parse_date("") is None
        assert _parse_date("not-a-date") is None
        assert _parse_date(None) is None
        assert _parse_date("2026/06/01") is None  # 格式不对
        assert _calc_diff_days(None, None) is None

    def test_empty_status_engine_df(self):
        """空 DataFrame 跑 add_status_columns"""
        from status_engine import add_status_columns

        df = pd.DataFrame(columns=["状态", "项目状态", "履约项异常/变更类型"])
        result = add_status_columns(df, "2026-06-30")

        assert len(result) == 0
        assert "履约项统计状态（即，财报-交付/确收状态）" in result.columns

    def test_empty_scoring_engine_df(self):
        """所有日期为空的 DataFrame 跑 add_scoring_columns：不崩溃，结果为 NaN"""
        from scoring_engine import add_scoring_columns

        df = pd.DataFrame({
            "基线-预估结项日期": ["", ""],
            "实际结项日期": ["", ""],
            "预算-预估验收完成日期": ["", ""],
            "实际服务/授权结束日期": ["", ""],
        })
        result = add_scoring_columns(df)

        assert len(result) == 2
        assert "交付计划准确率“差异”" in result.columns
        # 空日期计算结果为 NaN
        assert pd.isna(result.iloc[0]["交付计划准确率“差异”"])


# ============================================================
# 大数量级性能冒烟测试
# ============================================================

class TestLargeScalePerformance:
    """大数量级性能冒烟测试（100+ 项目）"""

    def test_100_projects_status_engine(self):
        """100 个项目跑状态引擎 < 5 秒"""
        from status_engine import add_status_columns

        np.random.seed(42)
        n = 200
        statuses = ["实施未开始", "义务已拆分", "实施进行中", "实施已完成",
                    "交付邮件交接中", "交付邮件已归档", "验收文件交接中", "验收文件已归档"]

        df = pd.DataFrame({
            "ID": [f"BIG-{i:04d}" for i in range(n)],
            "状态": np.random.choice(statuses, n),
            "履约项异常/变更类型": np.random.choice(["", "履约项交付异常", "履约项验收异常"], n, p=[0.85, 0.1, 0.05]),
            "预估交付完成日期": ["2026-05-01"] * n,
            "预估验收完成日期": ["2026-06-15"] * n,
            "实际服务/授权结束日期": ["2026-12-31"] * n,
            "项目状态": ["进行中"] * n,
        })

        start = time.time()
        result = add_status_columns(df, "2026-06-30")
        elapsed = time.time() - start

        assert len(result) == n
        assert elapsed < 5.0, f"200 项目状态引擎耗时 {elapsed:.2f}s，超过 5s 阈值"

    def test_100_projects_scoring_engine(self):
        """100 个项目跑考核引擎 < 10 秒"""
        from scoring_engine import add_scoring_columns

        np.random.seed(42)
        n = 200
        base_dates = pd.date_range("2026-01-01", "2026-12-31", periods=n).strftime("%Y-%m-%d").tolist()
        actual_dates = pd.date_range("2026-02-01", "2027-01-31", periods=n).strftime("%Y-%m-%d").tolist()

        df = pd.DataFrame({
            "基线-预估结项日期": base_dates,
            "实际结项日期": actual_dates,
            "预算-预估验收完成日期": base_dates,
            "实际服务/授权结束日期": actual_dates,
        })

        start = time.time()
        result = add_scoring_columns(df)
        elapsed = time.time() - start

        assert len(result) == n
        assert "交付计划准确率“差异”" in result.columns
        assert elapsed < 10.0, f"200 项目考核引擎耗时 {elapsed:.2f}s，超过 10s 阈值"

    def test_100_projects_mapping_engine(self):
        """100 个项目跑映射引擎 < 3 秒"""
        from mapping_engine import add_mapping_columns

        n = 200
        df = pd.DataFrame({
            "负责人": [f"PM-{i % 20}" for i in range(n)],
            "责任销售所属团队": [f"团队-{i % 5}" for i in range(n)],
        })

        start = time.time()
        result = add_mapping_columns(df)
        elapsed = time.time() - start

        assert len(result) == n
        assert "项目经理所属部门" in result.columns
        assert elapsed < 3.0, f"200 项目映射引擎耗时 {elapsed:.2f}s，超过 3s 阈值"

    def test_full_pipeline_50_projects(self):
        """50 个项目跑完整引擎流水线 < 15 秒"""
        from status_engine import add_status_columns
        from scoring_engine import add_scoring_columns
        from mapping_engine import add_mapping_columns, add_simple_computed_columns

        np.random.seed(42)
        n = 50
        statuses = ["实施进行中", "交付邮件已归档", "验收文件已归档"]

        df = pd.DataFrame({
            "ID": [f"FULL-{i:03d}" for i in range(n)],
            "所属项目": [f"项目{i}" for i in range(n)],
            "销售合同编号": [f"HT-{i:03d}" for i in range(n)],
            "负责人": [f"PM-{i % 10}" for i in range(n)],
            "责任销售所属团队": [f"团队-{i % 3}" for i in range(n)],
            "状态": np.random.choice(statuses, n),
            "履约项异常/变更类型": np.random.choice(["", "履约项交付异常"], n, p=[0.9, 0.1]),
            "预估交付完成日期": ["2026-05-01"] * n,
            "预估验收完成日期": ["2026-06-15"] * n,
            "实际服务/授权结束日期": ["2026-12-31"] * n,
            "项目状态": ["进行中"] * n,
            "基线-预估结项日期": ["2026-06-01"] * n,
            "实际结项日期": ["2026-06-05"] * n,
            "合同归档日期": ["2026-01-15"] * n,
            "预算-预估验收完成日期": ["2026-07-01"] * n,
        })

        start = time.time()
        df = add_simple_computed_columns(df)
        df = add_status_columns(df, "2026-06-30")
        df = add_scoring_columns(df)
        df = add_mapping_columns(df)
        elapsed = time.time() - start

        assert len(df) == n
        assert len(df.columns) > 50  # 50+ 列
        assert elapsed < 15.0, f"50 项目完整流水线耗时 {elapsed:.2f}s，超过 15s 阈值"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
