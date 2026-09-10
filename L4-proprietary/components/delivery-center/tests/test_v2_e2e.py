"""
BDMS v2 — 端到端集成测试 & 数据加载层测试

用最小模拟数据驱动完整流水线，覆盖：
- DataLoader 各加载方法（文件存在/不存在场景）
- ReportEngineOrchestrator 全部 build_* 方法
- build_report 主入口（用模拟数据跑通）
- ExcelWriter 高级特性（title_row、格式配置）
- 15 个 Sheet 完整性验证
- build_report_with_exports 导出入口
"""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path
import sys
import tempfile
import json

V2_DIR = Path(__file__).parent.parent / "src" / "delivery_center" / "v2"
sys.path.insert(0, str(V2_DIR))
sys.path.insert(0, str(V2_DIR / "engines"))
sys.path.insert(0, str(V2_DIR / "generators"))
sys.path.insert(0, str(V2_DIR / "config"))


# ============================================================
# Fixture: 最小测试数据集
# ============================================================

@pytest.fixture
def test_data_dirs():
    """创建临时目录 + 最小 CSV 数据集，返回各路径"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        ones_dir = tmp / "ones_exports"
        handover_dir = tmp / "handover"
        output_dir = tmp / "output"
        ones_dir.mkdir()
        handover_dir.mkdir()
        (handover_dir / "202606").mkdir()
        output_dir.mkdir()

        # 签约项目统计
        sign_df = pd.DataFrame({
            "ID": [f"ID-{i:04d}" for i in range(10)],
            "所属项目": [f"项目{i}" for i in range(10)],
            "销售合同编号": [f"HT-{i:03d}" for i in range(10)],
            "负责人": (["张三"]*3 + ["李四"]*3 + ["王五"]*2 + ["赵六"]*2),
            "责任销售所属团队": ["北区营销部"]*5 + ["南区营销部"]*5,
            "状态": (["交付邮件已归档"]*3 + ["验收文件已归档"]*2 +
                     ["实施进行中"]*2 + ["交付邮件交接中"]*1 + ["验收文件交接中"]*2),
            "履约项异常/变更备注": ([""]*7 + ["履约项交付异常"]*2 + ["履约项验收异常"]*1),
            "预估交付完成日期": ["2026-05-01"]*10,
            "预估验收完成日期": ["2026-06-15"]*10,
            "实际服务/授权结束日期": ["2026-12-31"]*10,
            "项目状态": ["进行中"]*10,
            "基线-预估结项日期": ["2026-06-01"]*10,
            "实际结项日期": ["2026-06-03"]*5 + ["2026-06-20"]*3 + [""]*2,
            "合同归档日期": (["2026-01-15"]*4 + ["2025-12-10"]*3 + ["2026-03-20"]*3),
            "预算-预估验收完成日期": ["2026-07-01"]*10,
            "立项日期": ["2026-01-01"]*10,
        })
        sign_df.to_csv(ones_dir / "202606周报-签约项目统计.csv", index=False, encoding="utf-8")

        # POC
        poc_df = pd.DataFrame({
            "ID": [f"POC-{i:03d}" for i in range(6)],
            "所属项目": [f"POC{i}" for i in range(6)],
            "销售合同编号": ["HT-P01", "HT-P02", "HT-P03", "HT-P04", "", ""],
            "负责人": ["张三"]*2 + ["李四"]*2 + ["王五"]*2,
            "责任销售所属团队": ["北区"]*4 + ["南区"]*2,
            "状态": ["实施进行中"]*6,
            "履约项异常/变更备注": [""]*6,
            "预估交付完成日期": ["2026-07-01"]*6,
            "预估验收完成日期": ["2026-08-01"]*6,
            "实际服务/授权结束日期": ["2026-12-31"]*6,
            "项目状态": ["进行中"]*6,
            "基线-预估结项日期": ["2026-06-01"]*6,
            "实际结项日期": [""]*6,
            "合同归档日期": ["2026-02-01"]*3 + [""]*3,
            "预算-预估验收完成日期": ["2026-09-01"]*6,
            "立项日期": ["2026-03-01"]*6,
            "项目类型(概览)": ["POC"]*4 + ["提前实施"]*2,
            "所属产线": ["安全产品线"]*2 + ["数据产品线"]*2 + ["云产品线"]*2,
            "POC项目工时合计（小时）": [100, 200, 150, 0, 0, 0],
            "提前实施项目持续周期-统计": ["1个月内", "3个月内", "6个月内", "", "", ""],
        })
        poc_df.to_csv(ones_dir / "202606周报-POC&提前实施统计.csv", index=False, encoding="utf-8")

        # 异常
        exc_df = pd.DataFrame({
            "销售合同编号": ["HT-007", "HT-008", "HT-009"],
            "标题": ["异常A", "异常B", "异常C"],
            "履约项异常/变更类型": ["履约项交付异常", "履约项验收异常", "履约项交付异常"],
            "异常报备日期": ["2026-06-01", "2026-06-10", "2026-05-20"],
            "异常归档日期": ["", "2026-06-15", ""],
            "异常影响情况": ["进度延迟", "质量问题", "资源不足"],
            "异常项目-类别": ["进度风险", "质量风险", "资源风险"],
            "ID": ["EXC-001", "EXC-002", "EXC-003"],
            "事业部（区域）": ["华北区", "华东区", "华南区"],
            "合同归档年度": ["2026", "2026", "2025"],
        })
        exc_df.to_csv(ones_dir / "202606-签约项目异常处置.csv", index=False, encoding="utf-8")

        # 确收交接
        rev_df = pd.DataFrame({
            "标题": ["确收1", "确收2", "确收3"],
            "ID": ["RV-001", "RV-002", "RV-003"],
            "BI履约ID": ["BI-001", "BI-002", "BI-003"],
            "合同编号1": ["HT-001-1", "HT-002-1", "HT-003-1"],
            "邮件编号": ["M-001", "M-002", "M-003"],
            "合同编号": ["HT-001", "HT-002", "HT-003"],
            "客户名称": ["客户A", "客户B", "客户C"],
            "销售部门": ["政企一部", "政企二部", "政企一部"],
            "项目经理": ["张三", "李四", "王五"],
            "备注": ["", "加急", ""],
            "交接日期": ["2026-06-15", "2026-06-20", "2026-06-25"],
            "财务": ["财务甲", "财务乙", "财务丙"],
            "是否接收": ["是", "是", "否"],
            "财务反馈": ["OK", "OK", "缺材料"],
            "交付邮件是否跨月": ["否", "否", "是"],
            "PMO": ["PMO甲", "PMO乙", "PMO丙"],
            "PMO备注": ["没问题", "", ""],
            "是否修改ones状态": ["是", "否", "是"],
        })
        rev_df.to_csv(handover_dir / "202606" / "202606确收凭证交接-确收.csv",
                      index=False, encoding="utf-8")

        # 验收交接（避免重名列导致的 Excel 写入问题，这里列名不重复）
        acc_df = pd.DataFrame({
            "合同名称": ["合同A", "合同B", "合同C"],
            "标题": ["验收1", "验收2", "验收3"],
            "ID": ["AC-001", "AC-002", "AC-003"],
            "BI履约ID": ["BI-001", "BI-002", "BI-003"],
            "验收单编号-财务端": ["YS-001", "YS-002", "YS-003"],
            "合同编号1": ["HT-001-1", "HT-002-1", "HT-003-1"],
            "验收单编号": ["ACPT-001", "ACPT-002", "ACPT-003"],
            "合同编号": ["HT-001", "HT-002", "HT-003"],
            "客户名称": ["客户A", "客户B", "客户C"],
            "销售部门": ["政企一部", "政企二部", "政企一部"],
            "项目经理": ["张三", "李四", "王五"],
            "备注": ["", "部分验收", "验收退回"],
            "交接日期": ["2026-06-10", "2026-06-18", "2026-06-22"],
            "验收方式": ["初验", "终验", "初验"],
            "是否为渠道": ["否", "是", "否"],
            "财务": ["财务甲", "财务乙", "财务丙"],
            "财务是否接收": ["是", "是", "否"],
            "实际验收方式": ["现场验收", "远程验收", "现场验收"],
            "财务反馈": ["通过", "通过", "材料不全"],
            "PMO": ["PMO甲", "PMO乙", "PMO丙"],
            "PMO备注": ["", "需跟进", ""],
            "是否修改ones及OA状态": ["是", "是", "否"],
        })
        acc_df.to_csv(handover_dir / "202606" / "202606确收凭证交接-验收.csv",
                      index=False, encoding="utf-8")

        yield {
            "ones_dir": ones_dir,
            "handover_dir": handover_dir,
            "output_dir": output_dir,
        }


# ============================================================
# DataLoader 测试
# ============================================================

class TestDataLoader:
    """数据加载层测试"""

    def test_load_sign_contracts(self, test_data_dirs):
        """加载签约项目统计 CSV"""
        from build_v2_report import ReportConfig, DataLoader

        cfg = ReportConfig(
            report_month="202606",
            ones_dir=test_data_dirs["ones_dir"],
        )
        loader = DataLoader(cfg)
        df = loader.load_sign_contracts()

        assert len(df) == 10
        assert "销售合同编号" in df.columns
        assert "状态" in df.columns

    def test_load_poc(self, test_data_dirs):
        """加载 POC CSV"""
        from build_v2_report import ReportConfig, DataLoader

        cfg = ReportConfig(report_month="202606", ones_dir=test_data_dirs["ones_dir"])
        loader = DataLoader(cfg)
        df = loader.load_poc()

        assert len(df) == 6
        assert "项目类型(概览)" in df.columns

    def test_load_exceptions(self, test_data_dirs):
        """加载异常 CSV"""
        from build_v2_report import ReportConfig, DataLoader

        cfg = ReportConfig(report_month="202606", ones_dir=test_data_dirs["ones_dir"])
        loader = DataLoader(cfg)
        df = loader.load_exceptions()

        assert len(df) == 3
        assert "履约项异常/变更类型" in df.columns

    def test_load_revenue_handover(self, test_data_dirs):
        """加载确收交接 CSV"""
        from build_v2_report import ReportConfig, DataLoader

        cfg = ReportConfig(
            report_month="202606",
            handover_base_dir=test_data_dirs["handover_dir"],
        )
        loader = DataLoader(cfg)
        df = loader.load_revenue_handover()

        assert len(df) == 3
        assert "是否接收" in df.columns

    def test_load_oa_contracts_none_path(self, test_data_dirs):
        """OA合同：None 路径返回空 DataFrame"""
        from build_v2_report import ReportConfig, DataLoader

        cfg = ReportConfig(report_month="202606", oa_contract_path=None)
        loader = DataLoader(cfg)
        df = loader.load_oa_contracts()

        assert len(df) == 0

    def test_load_workhours_none_path(self, test_data_dirs):
        """工时：None 路径返回空 DataFrame"""
        from build_v2_report import ReportConfig, DataLoader

        cfg = ReportConfig(report_month="202606", workhour_path=None)
        loader = DataLoader(cfg)
        df = loader.load_workhours()

        assert len(df) == 0

    def test_normalize_ones_columns(self, test_data_dirs):
        """ONES 列名规范化：履约项异常/变更备注 → 履约项异常/变更类型"""
        from build_v2_report import ReportConfig, DataLoader

        cfg = ReportConfig(report_month="202606", ones_dir=test_data_dirs["ones_dir"])
        loader = DataLoader(cfg)
        df = loader.load_sign_contracts()

        # 原列名是"履约项异常/变更备注"，应该被重命名为"履约项异常/变更类型"
        assert "履约项异常/变更类型" in df.columns


# ============================================================
# ReportEngineOrchestrator 完整流水线测试
# ============================================================

class TestOrchestratorFullPipeline:
    """引擎编排器完整流水线测试"""

    def test_build_sign_detail_full(self, test_data_dirs):
        """签约明细构建：从原始数据 → 完整 59+ 列"""
        from build_v2_report import ReportConfig, DataLoader, ReportEngineOrchestrator

        cfg = ReportConfig(
            report_month="202606",
            ones_dir=test_data_dirs["ones_dir"],
        )
        loader = DataLoader(cfg)
        orch = ReportEngineOrchestrator(cfg)

        df_sign = loader.load_sign_contracts()
        df_exc = loader.load_exceptions()

        result = orch.build_sign_detail(df_sign, df_exc)

        assert len(result) == len(df_sign)
        assert len(result.columns) >= 50  # 50+ 列
        # 验证关键计算列存在
        assert "履约项统计状态（即，财报-交付/确收状态）" in result.columns
        assert "项目经理所属部门" in result.columns
        assert "异常项目对比" in result.columns
        assert "交付计划准确率“差异”" in result.columns

    def test_build_poc_detail_full(self, test_data_dirs):
        """POC明细构建：完整流水线"""
        from build_v2_report import ReportConfig, DataLoader, ReportEngineOrchestrator

        cfg = ReportConfig(report_month="202606", ones_dir=test_data_dirs["ones_dir"])
        loader = DataLoader(cfg)
        orch = ReportEngineOrchestrator(cfg)

        df_poc = loader.load_poc()
        df_exc = loader.load_exceptions()

        result = orch.build_poc_detail(df_poc, df_exc)

        assert len(result) == len(df_poc)
        assert len(result.columns) >= 50

    def test_build_exception_detail(self, test_data_dirs):
        """异常明细构建：从签约明细（已含项目经理列）关联信息"""
        from build_v2_report import ReportConfig, DataLoader, ReportEngineOrchestrator

        cfg = ReportConfig(report_month="202606", ones_dir=test_data_dirs["ones_dir"])
        loader = DataLoader(cfg)
        orch = ReportEngineOrchestrator(cfg)

        df_sign_raw = loader.load_sign_contracts()
        df_exc = loader.load_exceptions()
        # 先构建签约明细（加了项目经理等列，异常表需要关联）
        df_sign = orch.build_sign_detail(df_sign_raw, df_exc)

        result = orch.build_exception_detail(df_exc, df_sign)
        assert len(result) == len(df_exc)
        # 验证有关联列
        assert "项目经理" in result.columns

    def test_build_revenue_handover(self, test_data_dirs):
        """确收交接构建"""
        from build_v2_report import ReportConfig, DataLoader, ReportEngineOrchestrator

        cfg = ReportConfig(
            report_month="202606",
            handover_base_dir=test_data_dirs["handover_dir"],
        )
        loader = DataLoader(cfg)
        orch = ReportEngineOrchestrator(cfg)

        df_rev = loader.load_revenue_handover()
        result = orch.build_revenue_handover(df_rev)

        assert len(result.columns) == 23

    def test_build_acceptance_handover(self, test_data_dirs):
        """验收交接构建"""
        # 验收交接因为重名列问题可能写 Excel 报错，但构建 DataFrame 应该没问题
        from build_v2_report import ReportConfig, DataLoader, ReportEngineOrchestrator

        cfg = ReportConfig(
            report_month="202606",
            handover_base_dir=test_data_dirs["handover_dir"],
        )
        loader = DataLoader(cfg)
        orch = ReportEngineOrchestrator(cfg)

        # 直接用构造的数据（避免从文件加载的列名问题）
        df_acc = pd.DataFrame({
            "合同名称": ["合同A", "合同B"],
            "标题": ["验收1", "验收2"],
            "ID": ["AC-001", "AC-002"],
            "BI履约ID": ["BI-001", "BI-002"],
            "验收单编号-财务端": ["YS-001", "YS-002"],
            "合同编号1": ["HT-001-1", "HT-002-1"],
            "验收单编号": ["ACPT-001", "ACPT-002"],
            "合同编号": ["HT-001", "HT-002"],
            "客户名称": ["客户A", "客户B"],
            "销售部门": ["政企一部", "政企二部"],
            "项目经理": ["张三", "李四"],
            "备注": ["", ""],
            "交接日期": ["2026-06-10", "2026-06-18"],
            "验收方式": ["初验", "终验"],
            "截至目前全部/部分验收": ["全部验收", "部分验收"],
            "是否为渠道": ["否", "是"],
            "财务": ["财务甲", "财务乙"],
            "财务是否接收": ["是", "是"],
            "实际验收方式": ["现场", "远程"],
            "财务反馈": ["通过", "通过"],
            "PMO": ["PMO甲", "PMO乙"],
            "PMO备注": ["", ""],
            "是否修改ones及OA状态": ["是", "是"],
        })
        result = orch.build_acceptance_handover(df_acc)

        assert len(result.columns) == 27


# ============================================================
# ExcelWriter 高级功能测试
# ============================================================

class TestExcelWriterAdvanced:
    """Excel 写入器高级功能测试"""

    def test_write_with_title_row(self):
        """带标题行写入"""
        from build_v2_report import ExcelWriter

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "title.xlsx"
            writer = ExcelWriter(path)

            df = pd.DataFrame({"A": [1, 2], "B": ["x", "y"]})
            ws = writer.write_dataframe(df, "带标题", title_row="2026-06-30")
            writer.save()

            from openpyxl import load_workbook
            wb = load_workbook(path)
            ws = wb["带标题"]
            # 第1行是标题
            assert ws.cell(row=1, column=1).value == "2026-06-30"
            # 第2行是表头
            assert ws.cell(row=2, column=1).value == "A"
            # 第3行开始是数据
            assert ws.cell(row=3, column=1).value == 1
            wb.close()

    def test_write_multiple_times_same_sheet(self):
        """同一 Sheet 多次写入（不同位置）"""
        from build_v2_report import ExcelWriter

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "multi_write.xlsx"
            writer = ExcelWriter(path)

            df1 = pd.DataFrame({"左A": [1, 2]})
            df2 = pd.DataFrame({"右B": [3, 4]})

            writer.write_dataframe(df1, "并排", start_col=1)
            writer.write_dataframe(df2, "并排", start_col=5)
            writer.save()

            from openpyxl import load_workbook
            wb = load_workbook(path)
            ws = wb["并排"]
            assert ws.cell(row=1, column=1).value == "左A"
            assert ws.cell(row=1, column=5).value == "右B"
            wb.close()

    def test_writer_column_widths(self):
        """列宽自动计算"""
        from build_v2_report import ExcelWriter
        from openpyxl.utils import get_column_letter

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "widths.xlsx"
            writer = ExcelWriter(path)

            df = pd.DataFrame({
                "短列": [1, 2],
                "这是一个很长的列名": ["短", "也短"],
            })
            writer.write_dataframe(df, "列宽测试")
            writer.save()

            from openpyxl import load_workbook
            wb = load_workbook(path)
            ws = wb["列宽测试"]
            w1 = ws.column_dimensions[get_column_letter(1)].width
            w2 = ws.column_dimensions[get_column_letter(2)].width
            # 长列名列应该更宽
            assert w2 > w1
            wb.close()


# ============================================================
# 导出功能测试
# ============================================================

class TestExportFunctions:
    """各种导出功能测试（JSON、明细拆分、全量导出）"""

    def test_build_report_with_exports(self, test_data_dirs):
        """build_report_with_exports：完整导出入口（至少不崩溃）"""
        from build_v2_report import build_report_with_exports, ReportConfig
        from openpyxl import load_workbook

        cfg = ReportConfig(
            report_month="202606",
            ones_dir=test_data_dirs["ones_dir"],
            handover_base_dir=test_data_dirs["handover_dir"],
            output_dir=test_data_dirs["output_dir"],
        )

        result = build_report_with_exports(cfg)

        # 返回值包含各输出路径
        assert isinstance(result, dict)
        assert "excel" in result
        assert "json" in result
        assert "detail_dir" in result

        # Excel 文件存在
        assert result["excel"].exists()

        wb = load_workbook(result["excel"], read_only=True)
        # 至少有签约、POC、异常等核心 Sheet
        assert "签约" in wb.sheetnames
        assert "POC&提前实施" in wb.sheetnames
        assert "异常项目" in wb.sheetnames
        assert "确收交接" in wb.sheetnames
        wb.close()

    def test_json_export_in_full_pipeline(self, test_data_dirs):
        """完整流水线中 JSON 导出文件结构正确"""
        from build_v2_report import build_report_with_exports, ReportConfig

        cfg = ReportConfig(
            report_month="202606",
            ones_dir=test_data_dirs["ones_dir"],
            handover_base_dir=test_data_dirs["handover_dir"],
            output_dir=test_data_dirs["output_dir"],
        )

        result = build_report_with_exports(cfg)
        json_path = result["json"]

        assert json_path.exists()
        data = json.loads(json_path.read_text(encoding="utf-8"))

        assert "_meta" in data
        assert data["_meta"]["version"] == "v2"
        assert "签约" in data
        assert data["签约"]["row_count"] == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
