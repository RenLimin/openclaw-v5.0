"""数据采集层测试"""

import pytest
import pandas as pd
from pathlib import Path

# 测试数据路径
TEST_DATA_DIR = Path.home() / "Bangcle Workspace/01. Management/2026/2026团队报告/202606"


def test_contract_no_calibration():
    """测试合同编号校准"""
    from scripts.l4.delivery_center.collectors.data_cleaner import calibrate_contract_no

    assert calibrate_contract_no("ABC-001&DEF-002") == "ABC-001"
    assert calibrate_contract_no("ABC-001") == "ABC-001"
    assert calibrate_contract_no("") == ""
    assert calibrate_contract_no(None) is None


def test_clean_ones_contract_file_exists():
    """测试签约数据文件存在"""
    csv_file = TEST_DATA_DIR / "202606周报-签约项目统计.csv"
    assert csv_file.exists(), f"测试数据不存在: {csv_file}"


def test_clean_ones_contract():
    """测试签约数据清洗"""
    from scripts.l4.delivery_center.collectors.data_cleaner import clean_ones_contract

    csv_file = TEST_DATA_DIR / "202606周报-签约项目统计.csv"
    if not csv_file.exists():
        pytest.skip("测试数据不存在")

    df = clean_ones_contract(str(csv_file))
    assert len(df) > 0
    assert "合同编号（校准）" in df.columns


def test_clean_ones_poc():
    """测试 POC 数据清洗"""
    from scripts.l4.delivery_center.collectors.data_cleaner import clean_ones_poc

    csv_file = TEST_DATA_DIR / "202606周报-POC&提前实施统计.csv"
    if not csv_file.exists():
        pytest.skip("测试数据不存在")

    df = clean_ones_poc(str(csv_file))
    assert len(df) > 0


def test_clean_workhour():
    """测试工时数据清洗"""
    from scripts.l4.delivery_center.collectors.data_cleaner import clean_workhour

    xlsx_file = TEST_DATA_DIR / "202606工时填报.xlsx"
    if not xlsx_file.exists():
        pytest.skip("测试数据不存在")

    df = clean_workhour(str(xlsx_file))
    assert len(df) > 0
