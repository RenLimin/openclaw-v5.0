"""
加载 Rex 家庭模拟数据到 L4 数据库
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import date, timedelta
from decimal import Decimal
from fin_l4.db import get_db, init_db
from fin_l4.services.account_svc import AccountService
from fin_l4.services.txn_svc import TransactionService
from fin_l4.services.loan_svc import LoanService
from fin_l4.services.insurance_svc import InsuranceService
from fin_l4.services.portfolio_svc import PortfolioService
from fin_l4.services.budget_svc import BudgetService


FAMILY_ID = "default"


def clear_family_data(conn, family_id):
    """清除家庭已有数据"""
    tables = [
        "fin4_transactions", "fin4_loan_repayments", "fin4_loans",
        "fin4_insurance_policies", "fin4_portfolio_holdings", "fin4_portfolios",
        "fin4_budgets", "fin4_import_rules", "fin4_accounts",
    ]
    for table in tables:
        try:
            conn.execute(f"DELETE FROM {table} WHERE family_id = ?", (family_id,))
        except Exception:
            pass
    conn.commit()


def load_accounts(svc):
    """创建账户体系"""
    accounts = [
        # 资产类
        ("1001", "库存现金", "ASSET"),
        ("1002", "银行存款", "ASSET"),
        ("1003", "股票投资", "ASSET"),
        ("1004", "基金投资", "ASSET"),
        ("1005", "债券投资", "ASSET"),
        ("1006", "保单现金价值", "ASSET"),
        ("1007", "房产", "ASSET"),
        # 负债类
        ("2001", "信用卡欠款", "LIABILITY"),
        ("2002", "消费贷", "LIABILITY"),
        ("2003", "房贷", "LIABILITY"),
        # 权益类
        ("3001", "初始权益", "EQUITY"),
        # 收入类
        ("4001", "工资收入", "INCOME"),
        ("4002", "投资收益", "INCOME"),
        ("4003", "其他收入", "INCOME"),
        # 费用类
        ("5001", "餐饮费", "EXPENSE"),
        ("5002", "交通费", "EXPENSE"),
        ("5003", "住房支出", "EXPENSE"),
        ("5004", "保险费", "EXPENSE"),
        ("5005", "医疗费", "EXPENSE"),
        ("5006", "购物费", "EXPENSE"),
        ("5007", "教育费", "EXPENSE"),
        ("5008", "利息支出", "EXPENSE"),
    ]
    created = {}
    for code, name, acc_type in accounts:
        acc = svc.create_account(FAMILY_ID, code, name, acc_type)
        created[code] = acc["id"]
    return created


def load_opening_balances(txn_svc, accts):
    """录入期初余额（模拟 2026-01-01 开账）"""
    opening_date = "2026-01-01"
    balances = {
        "1001": "5000",       # 现金
        "1002": "215000",     # 银行存款
        "1003": "160000",     # 股票
        "1004": "50000",      # 基金
        "1005": "100000",     # 债券
        "1006": "30000",      # 保单现金价值
        "1007": "800000",     # 房产
        "2001": "15000",      # 信用卡
        "2002": "35000",      # 消费贷
        "2003": "1000000",    # 房贷
        "3001": "310000",     # 初始权益（平衡项）
    }
    # 资产类：借方增加
    for code in ["1001", "1002", "1003", "1004", "1005", "1006", "1007"]:
        if balances.get(code) and Decimal(balances[code]) > 0:
            txn_svc.record(FAMILY_ID, opening_date, balances[code],
                           accts[code], accts["3001"], f"期初余额-{code}")
    # 负债类：贷方增加（用负数借方表示）
    for code in ["2001", "2002", "2003"]:
        if balances.get(code) and Decimal(balances[code]) > 0:
            txn_svc.record(FAMILY_ID, opening_date, balances[code],
                           accts["3001"], accts[code], f"期初余额-{code}")


def load_recent_transactions(txn_svc, accts):
    """录入最近 3 个月的模拟交易"""
    today = date.today()
    transactions = [
        # 收入
        (today - timedelta(days=30), "35000", "工资收入", "1002", "4001"),
        (today - timedelta(days=60), "35000", "工资收入", "1002", "4001"),
        (today - timedelta(days=15), "2000", "股票分红", "1002", "4002"),
        # 支出
        (today - timedelta(days=3), "5000", "房租", "5003", "1002"),
        (today - timedelta(days=5), "300", "餐饮", "5001", "1002"),
        (today - timedelta(days=7), "200", "交通", "5002", "1002"),
        (today - timedelta(days=10), "1500", "购物", "5006", "1002"),
        (today - timedelta(days=12), "50", "餐饮", "5001", "1002"),
        (today - timedelta(days=15), "800", "加油", "5002", "1002"),
        (today - timedelta(days=20), "2000", "保险缴费", "5004", "1002"),
        (today - timedelta(days=25), "3000", "房贷还款", "2003", "1002"),
    ]
    for d, amt, note, debit, credit in transactions:
        txn_svc.record(FAMILY_ID, str(d), amt, accts[debit], accts[credit], note)


def load_loans(svc, accts):
    """创建贷款"""
    loan1 = svc.create_loan(FAMILY_ID, "房贷-自住房",
                            "1000000", "0.035", 360,
                            "equal_payment", "2024-01-01")
    loan2 = svc.create_loan(FAMILY_ID, "消费贷-装修",
                            "50000", "0.06", 36,
                            "equal_payment", "2025-06-01")
    return loan1, loan2


def load_insurance(svc, accts):
    """创建保险"""
    policy1 = svc.add_policy(FAMILY_ID, "重疾险-Rex", "critical_illness",
                                "500000", "20000", 40, 20,
                                insured_name="Rex", insured_age=30, insured_gender="M",
                                start_date="2026-01-01",
                                extra_terms={"policy_number": "P001"})
    policy2 = svc.add_policy(FAMILY_ID, "定期寿险-Rex", "term_life",
                                "1000000", "3000", 30, 20,
                                insured_name="Rex", insured_age=30, insured_gender="M",
                                start_date="2026-01-01",
                                extra_terms={"policy_number": "P002"})
    return policy1, policy2


def load_portfolio(svc, accts):
    """创建投资组合"""
    portfolio = svc.create_portfolio(FAMILY_ID, "主投资组合")
    return portfolio


def load_categories(conn):
    """创建分类体系"""
    from fin_l4.db.repositories import CategoryRepository
    cat_repo = CategoryRepository(conn)
    categories = [
        ("餐饮", "expense"),
        ("交通", "expense"),
        ("住房", "expense"),
        ("保险", "expense"),
        ("购物", "expense"),
        ("医疗", "expense"),
        ("教育", "expense"),
        ("工资", "income"),
        ("投资", "income"),
    ]
    created = {}
    for name, cat_type in categories:
        cid = cat_repo.create(FAMILY_ID, name, cat_type)
        created[name] = cid
    return created


def load_budgets(svc, cats):
    """设置月度预算"""
    budgets = [
        ("餐饮", "3000"),
        ("交通", "1500"),
        ("住房", "5000"),
        ("保险", "2000"),
        ("购物", "2000"),
        ("医疗", "1000"),
        ("教育", "1500"),
    ]
    today = date.today()
    month = today.strftime("%Y-%m")
    for cat_name, amount in budgets:
        svc.set_budget(FAMILY_ID, cats[cat_name], month, amount)


def main():
    print("🏠 加载 Rex 家庭模拟数据...")
    conn = get_db()
    init_db()

    # 清除旧数据
    clear_family_data(conn, FAMILY_ID)

    # 初始化服务
    account_svc = AccountService(conn)
    txn_svc = TransactionService(conn)
    loan_svc = LoanService(conn)
    insurance_svc = InsuranceService(conn)
    portfolio_svc = PortfolioService(conn)
    budget_svc = BudgetService(conn)

    # 1. 账户体系
    accts = load_accounts(account_svc)
    print(f"  ✅ 创建 {len(accts)} 个账户")

    # 2. 期初余额
    load_opening_balances(txn_svc, accts)
    print(f"  ✅ 录入期初余额")

    # 3. 近期交易
    load_recent_transactions(txn_svc, accts)
    print(f"  ✅ 录入近期交易")

    # 4. 贷款
    loans = load_loans(loan_svc, accts)
    print(f"  ✅ 创建 {len(loans)} 笔贷款")

    # 5. 保险
    policies = load_insurance(insurance_svc, accts)
    print(f"  ✅ 创建 {len(policies)} 张保单")

    # 6. 投资
    portfolio = load_portfolio(portfolio_svc, accts)
    print(f"  ✅ 创建投资组合")

    # 7. 分类
    cats = load_categories(conn)
    print(f"  ✅ 创建 {len(cats)} 个分类")

    # 8. 预算
    load_budgets(budget_svc, cats)
    print(f"  ✅ 设置月度预算")

    print(f"\n🎉 模拟数据加载完成！家庭 ID: {FAMILY_ID}")
    print(f"   访问 http://localhost:8500 查看效果")


if __name__ == "__main__":
    main()
