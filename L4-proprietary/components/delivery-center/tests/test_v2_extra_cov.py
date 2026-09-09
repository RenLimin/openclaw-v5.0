"""
BDMS v2 — 额外覆盖率补全测试

补充 DataLoader fallback 路径 + contract_engine Excel 加载 + 其他边缘分支
目标：把覆盖率推过 80%
"""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path
import sys
import tempfile

V2_DIR = Path(__file__).parent.parent / "v2"
sys.path.insert(0, str(V2_DIR))
sys.path.insert(0, str(V2_DIR / "engines"))
sys.path.insert(0, str(V2_DIR / "generators"))
sys.path.insert(0, str(V2_DIR / "config"))


# ============================================================
# DataLoader fallback 路径测试
# ============================================================

class TestDataLoaderFallbacks:
    """DataLoader 备用文件名 fallback 测试"""

    def test_load_sign_contracts_fallback(self):
        """签约表：带月份的文件名不存在时，回退到通用文件名"""
        from build_v2_report import ReportConfig, DataLoader

        with tempfile.TemporaryDirectory() as tmp:
            ones_dir = Path(tmp)
            df = pd.DataFrame({
                "销售合同编号": ["HT-001", "HT-002"],
                "负责人": ["张三", "李四"],
                "履约项异常/变更备注": ["", "异常"],
            })
            df.to_csv(ones_dir / "签约项目统计.csv", index=False, encoding="utf-8")

            cfg = ReportConfig(report_month="202606", ones_dir=ones_dir)
            loader = DataLoader(cfg)
            result = loader.load_sign_contracts()
            assert len(result) == 2
            # 验证列名规范化生效
            assert "履约项异常/变更类型" in result.columns

    def test_load_poc_fallback(self):
        """POC表：带月份的文件名不存在时，回退到通用文件名"""
        from build_v2_report import ReportConfig, DataLoader

        with tempfile.TemporaryDirectory() as tmp:
            ones_dir = Path(tmp)
            df = pd.DataFrame({
                "销售合同编号": ["HT-P01"],
                "负责人": ["张三"],
                "履约项异常/变更备注": [""],
                "项目类型(概览)": ["POC"],
            })
            df.to_csv(ones_dir / "poc_提前实施.csv", index=False, encoding="utf-8")

            cfg = ReportConfig(report_month="202606", ones_dir=ones_dir)
            loader = DataLoader(cfg)
            result = loader.load_poc()
            assert len(result) == 1

    def test_load_exceptions_fallback(self):
        """异常表：带月份的文件名不存在时，回退到通用文件名"""
        from build_v2_report import ReportConfig, DataLoader

        with tempfile.TemporaryDirectory() as tmp:
            ones_dir = Path(tmp)
            df = pd.DataFrame({
                "销售合同编号": ["HT-001"],
                "履约项异常/变更类型": ["交付异常"],
                "标题": ["异常1"],
            })
            df.to_csv(ones_dir / "异常处置.csv", index=False, encoding="utf-8")

            cfg = ReportConfig(report_month="202606", ones_dir=ones_dir)
            loader = DataLoader(cfg)
            result = loader.load_exceptions()
            assert len(result) == 1


# ============================================================
# contract_engine Excel 加载测试
# ============================================================

class TestContractEngineExcel:
    """合同引擎 OA 台账 Excel 加载测试"""

    def test_load_oa_contracts_full_pipeline(self):
        """完整 Excel 加载流程：列名规范化 + 校准 + 金额转换 + 日期解析 + 去重"""
        from contract_engine import load_oa_contracts

        with tempfile.TemporaryDirectory() as tmp:
            xlsx_path = Path(tmp) / "oa_test.xlsx"

            # 模拟 OA 导出台账的列名特色
            df = pd.DataFrame({
                "合同编号！": ["ht-001", "HT-001", "ht-002"],
                "签约金额（元）": ["100000", "200000", "150000"],
                "客户名称（浏览框）": ["客户A", "客户A", "客户B"],
                "合同归档日期": ["2026-01-15", "2026-01-16", "2026-02-20"],
                "合同起始日期": ["2026-01-01", "", "2026-02-01"],
                "合同结束日期": ["2026-12-31", "", "2027-01-31"],
                "客户名称": ["客户A公司", "客户A公司", "客户B公司"],
            })
            df.to_excel(xlsx_path, index=False)

            result = load_oa_contracts(xlsx_path)

            # 列名规范化：合同编号！→ 合同编号
            assert "合同编号" in result.columns
            assert "签约金额" in result.columns
            assert "客户名称浏览框" in result.columns
            # 原始合同编号被保存
            assert "原始合同编号" in result.columns

            # 合同编号已校准为大写
            assert result.iloc[0]["合同编号"] == "HT-001"

            # 去重：HT-001 两条 → 保留第一条
            assert len(result) == 2
            assert (result["合同编号"] == "HT-001").sum() == 1

            # 金额转为数值类型
            assert pd.api.types.is_numeric_dtype(result["签约金额"])
            assert result.iloc[0]["签约金额"] == 100000

            # 日期列已解析（非空字符串）
            assert pd.notna(result.iloc[0]["合同归档日期"])
            assert pd.notna(result.iloc[0]["合同起始日期"])

    def test_load_oa_contracts_minimal_columns(self):
        """最小列集：只有合同编号列也能加载"""
        from contract_engine import load_oa_contracts

        with tempfile.TemporaryDirectory() as tmp:
            xlsx_path = Path(tmp) / "oa_minimal.xlsx"
            df = pd.DataFrame({
                "合同编号！": ["HT-001", "HT-002"],
            })
            df.to_excel(xlsx_path, index=False)

            result = load_oa_contracts(xlsx_path)
            assert len(result) == 2
            assert "合同编号" in result.columns
            # 没有金额列也 OK（不会报错）
            assert "签约金额" not in result.columns

    def test_load_oa_contracts_no_contract_col(self):
        """无合同编号列：也不报错，返回原始结构"""
        from contract_engine import load_oa_contracts

        with tempfile.TemporaryDirectory() as tmp:
            xlsx_path = Path(tmp) / "oa_nocontract.xlsx"
            df = pd.DataFrame({
                "客户名称": ["客户A", "客户B"],
                "签约金额（元）": ["1000", "2000"],
            })
            df.to_excel(xlsx_path, index=False)

            result = load_oa_contracts(xlsx_path)
            assert len(result) == 2
            # 金额列被重命名
            assert "签约金额" in result.columns




if __name__ == "__main__":
    pytest.main([__file__, "-v"])
