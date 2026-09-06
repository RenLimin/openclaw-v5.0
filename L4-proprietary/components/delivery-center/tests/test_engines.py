"""业务逻辑引擎测试"""

import pytest
import pandas as pd
from datetime import datetime


def test_join_contract_oa():
    """测试 ONES-OA 关联"""
    from scripts.l4.delivery_center.engines.join_engine import join_contract_oa

    ones_df = pd.DataFrame({
        "销售合同编号": ["C001", "C002", "C003"],
        "项目名称": ["项目A", "项目B", "项目C"],
    })
    oa_df = pd.DataFrame({
        "合同编号": ["C001", "C002"],
        "客户名称": ["客户A", "客户B"],
    })

    result = join_contract_oa(ones_df, oa_df)
    assert len(result) == 3
    assert "客户名称" in result.columns


def test_status_determination():
    """测试状态判定"""
    from scripts.l4.delivery_center.engines.status_engine import determine_delivery_status

    row = pd.Series({
        "状态": "实施进行中",
        "交付邮件发送日期": None,
        "履约项异常/变更类型": "",
    })
    status = determine_delivery_status(row, datetime(2026, 6, 30))
    assert status == "1：正常交付"


def test_scoring():
    """测试考核扣分"""
    from scripts.l4.delivery_center.engines.scoring_engine import calculate_accuracy_score

    df = pd.DataFrame({
        "交付计划方向": ["一致", "延后", "提前"],
        "交付计划跨月": ["不统计", "否", "是"],
        "交付计划差异": [0, 10, 20],
    })
    result = calculate_accuracy_score(df)
    assert "交付计划扣分" in result.columns
    assert result.iloc[0]["交付计划扣分"] == 0  # 一致 → 0
    assert result.iloc[1]["交付计划扣分"] == 0.5  # 跨月否 + <15天 → 0.5
    assert result.iloc[2]["交付计划扣分"] == 1  # 跨月是 → 1


def test_variance():
    """测试差异计算"""
    from scripts.l4.delivery_center.engines.variance_engine import calculate_variance

    df = pd.DataFrame({
        "预算金额": [100, 200, 300],
        "实际金额": [90, 200, 350],
    })
    result = calculate_variance(df, "预算金额", "实际金额")
    assert result.iloc[0]["差异"] == 10
    assert result.iloc[1]["差异"] == 0
    assert result.iloc[2]["差异"] == -50
