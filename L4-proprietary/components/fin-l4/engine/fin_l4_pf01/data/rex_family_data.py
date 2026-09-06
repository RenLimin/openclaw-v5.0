"""
Rex 家庭模拟数据

基于 DESIGN.md 中定义的家庭画像，生成完整的模拟财务数据。
所有数据为虚构，用于 L4 实例验证。
"""

from decimal import Decimal
from datetime import date


def get_family_profile():
    """Rex 家庭画像"""
    return {
        "name": "Rex 家庭",
        "members": [
            {"role": "户主", "name": "Rex", "age": 30, "occupation": "技术管理"},
            {"role": "配偶", "name": "Rex 配偶", "age": 28, "occupation": "设计师"},
        ],
        "monthly_income": Decimal("35000"),       # 月收入
        "monthly_expenses": Decimal("18000"),     # 月支出
        "total_assets": Decimal("850000"),        # 总资产
        "total_liabilities": Decimal("1050000"),  # 总负债（含房贷）
        "emergency_fund": Decimal("120000"),      # 应急资金
    }


def get_opening_balances():
    """期初余额（导入科目余额）"""
    return {
        "库存现金": Decimal("5000"),
        "银行存款": Decimal("215000"),
        "股票投资": Decimal("160000"),
        "基金投资": Decimal("50000"),
        "债券投资": Decimal("100000"),
        "保单现金价值": Decimal("30000"),
        "房产": Decimal("800000"),
        "信用卡欠款": Decimal("15000"),
        "消费贷": Decimal("35000"),
        "房贷": Decimal("1000000"),
        "初始权益": Decimal("310000"),  # 平衡项
    }


def get_loans():
    """贷款列表"""
    return [
        {
            "name": "房贷-自住房",
            "principal": Decimal("1000000"),
            "annual_rate": Decimal("0.035"),  # 3.5%（LPR 5Y+）
            "term_months": 360,
            "method": "equal_payment",
            "start_date": date(2024, 1, 1),
        },
        {
            "name": "消费贷-装修",
            "principal": Decimal("50000"),
            "annual_rate": Decimal("0.06"),  # 6%
            "term_months": 36,
            "method": "equal_payment",
            "start_date": date(2025, 6, 1),
        },
    ]


def get_insurances():
    """保险组合"""
    return [
        {
            "name": "终身寿险-户主",
            "policy_type": "whole_life",
            "premium": Decimal("12000"),       # 年缴保费
            "sum_assured": Decimal("500000"),  # 保额
            "term_years": 99,                   # 终身
            "payment_years": 20,
            "insured_age": 30,
            "insured_gender": "male",
        },
        {
            "name": "定期寿险-配偶",
            "policy_type": "term_life",
            "premium": Decimal("3000"),
            "sum_assured": Decimal("300000"),
            "term_years": 30,
            "payment_years": 20,
            "insured_age": 28,
            "insured_gender": "female",
        },
        {
            "name": "重疾险-户主",
            "policy_type": "critical_illness",
            "premium": Decimal("8000"),
            "sum_assured": Decimal("300000"),
            "term_years": 99,
            "payment_years": 20,
            "insured_age": 30,
            "insured_gender": "male",
        },
        {
            "name": "百万医疗险-家庭",
            "policy_type": "medical",
            "premium": Decimal("2000"),
            "sum_assured": Decimal("600000"),
            "term_years": 1,
            "payment_years": 1,
            "insured_age": 30,
            "insured_gender": "male",
        },
    ]


def get_investments():
    """投资组合"""
    return [
        {
            "asset_type": "stock",
            "asset_name": "贵州茅台",
            "asset_code": "600519",
            "shares": 100,
            "cost_basis_price": 1500,
            "current_price": 1650,
        },
        {
            "asset_type": "stock",
            "asset_name": "腾讯控股",
            "asset_code": "00700",
            "shares": 500,
            "cost_basis_price": 350,
            "current_price": 380,
        },
        {
            "asset_type": "fund",
            "asset_name": "易方达蓝筹精选",
            "asset_code": "005827",
            "shares": 20000,
            "cost_basis_price": 2.0,
            "current_price": 2.3,
        },
        {
            "asset_type": "fund",
            "asset_name": "中欧医疗健康",
            "asset_code": "003096",
            "shares": 10000,
            "cost_basis_price": 3.0,
            "current_price": 2.8,
        },
        {
            "asset_type": "bond",
            "asset_name": "10年期国债",
            "asset_code": "T10Y",
            "shares": 5000,
            "cost_basis_price": 100,
            "current_price": 101.5,
        },
        {
            "asset_type": "bond",
            "asset_name": "5年期国债",
            "asset_code": "T5Y",
            "shares": 3000,
            "cost_basis_price": 100,
            "current_price": 100.8,
        },
        {
            "asset_type": "cash",
            "asset_name": "招行活期",
            "asset_code": "CMB",
            "shares": 1,
            "cost_basis_price": 150000,
            "current_price": 150000,
        },
    ]
