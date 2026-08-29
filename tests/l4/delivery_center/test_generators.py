"""报告生成器测试"""

import pytest
import pandas as pd
from pathlib import Path


def test_delivery_report_generation():
    """测试交付月报生成"""
    from scripts.l4.delivery_center.generators.delivery_report import generate_delivery_report

    # 创建测试数据
    contract_df = pd.DataFrame({
        "合同编号": ["C001"],
        "项目名称": ["测试项目"],
        "签约金额": [100000],
    })
    poc_df = pd.DataFrame({"合同编号": [], "项目名称": []})
    exception_df = pd.DataFrame({"合同编号": [], "项目名称": []})
    revenue_df = pd.DataFrame({"合同编号": [], "确收金额": []})
    acceptance_df = pd.DataFrame({"合同编号": [], "验收日期": []})

    output_dir = "/tmp/bdms_test"
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    result = generate_delivery_report(
        month="202606",
        contract_df=contract_df,
        poc_df=poc_df,
        exception_df=exception_df,
        revenue_df=revenue_df,
        acceptance_df=acceptance_df,
        output_dir=output_dir,
    )

    assert Path(result).exists()
    assert result.endswith(".xlsx")


def test_revenue_report_generation():
    """测试确收月报生成"""
    from scripts.l4.delivery_center.generators.revenue_report import generate_revenue_report

    budget_df = pd.DataFrame({
        "合同编号": ["C001"],
        "预算金额": [100000],
    })
    actual_df = pd.DataFrame({
        "合同编号": ["C001"],
        "实际金额": [90000],
    })
    contract_df = pd.DataFrame({
        "合同编号": ["C001"],
        "客户名称": ["测试客户"],
    })

    output_dir = "/tmp/bdms_test"
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    result = generate_revenue_report(
        month="202606",
        budget_df=budget_df,
        actual_df=actual_df,
        contract_df=contract_df,
        output_dir=output_dir,
    )

    assert Path(result).exists()
    assert result.endswith(".xlsx")
