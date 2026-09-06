"""
FIN-001 账户体系测试
"""
import sys
sys.path.insert(0, '..')

from decimal import Decimal
from datetime import date
from fin001_account import (
    AccountingEngine, AccountType, DebitCredit,
    _to_decimal,
)


def test_create_account():
    """测试创建账户"""
    engine = AccountingEngine()
    acc = engine.create_account("现金", AccountType.ASSET, initial_balance=1000)
    assert acc.name == "现金"
    assert acc.type == AccountType.ASSET
    assert acc.balance == Decimal("1000.00")
    print("✅ test_create_account passed")


def test_record_transaction():
    """测试记录交易"""
    engine = AccountingEngine()

    cash = engine.create_account("现金", AccountType.ASSET, initial_balance=10000)
    income = engine.create_account("工资收入", AccountType.INCOME)

    txn = engine.record_transaction(
        debit_account_id=cash.id,
        credit_account_id=income.id,
        amount=5000,
        note="1月工资",
    )

    assert txn.amount == Decimal("5000.00")
    assert engine.get_account_balance(cash.id) == Decimal("15000.00")
    assert engine.get_account_balance(income.id) == Decimal("5000.00")
    print("✅ test_record_transaction passed")


def test_double_entry_balance():
    """测试复式记账平衡"""
    engine = AccountingEngine()

    asset = engine.create_account("资产", AccountType.ASSET, initial_balance=50000)
    liability = engine.create_account("负债", AccountType.LIABILITY, initial_balance=20000)
    equity = engine.create_account("权益", AccountType.EQUITY, initial_balance=30000)

    # 试算平衡
    tb = engine.get_trial_balance()
    assert tb.is_balanced, f"试算不平衡: 借方 {tb.debit_total} ≠ 贷方 {tb.credit_total}"
    print(f"✅ test_double_entry_balance passed (借方={tb.debit_total}, 贷方={tb.credit_total})")


def test_trial_balance_after_transactions():
    """测试交易后试算平衡"""
    engine = AccountingEngine()

    # 期初设置：资产(10000+50000) = 权益(60000)，满足会计恒等式
    cash = engine.create_account("现金", AccountType.ASSET, initial_balance=10000)
    bank = engine.create_account("银行存款", AccountType.ASSET, initial_balance=50000)
    capital = engine.create_account("实收资本", AccountType.EQUITY, initial_balance=60000)
    income = engine.create_account("收入", AccountType.INCOME)
    expense = engine.create_account("费用", AccountType.EXPENSE)

    # 期初试算平衡（确保基线正确）
    tb_init = engine.get_trial_balance()
    assert tb_init.is_balanced, f"期初试算不平衡: 借方 {tb_init.debit_total} ≠ 贷方 {tb_init.credit_total}"

    # 一系列交易
    engine.record_transaction(cash.id, income.id, 8000, note="工资")
    engine.record_transaction(bank.id, cash.id, 5000, note="取现")
    engine.record_transaction(expense.id, bank.id, 3000, note="交房租")

    tb = engine.get_trial_balance()
    assert tb.is_balanced, f"交易后试算不平衡: 借方 {tb.debit_total} ≠ 贷方 {tb.credit_total}"
    print(f"✅ test_trial_balance_after_transactions passed (借方={tb.debit_total}, 贷方={tb.credit_total})")


def test_account_tree():
    """测试账户树"""
    engine = AccountingEngine()

    root = engine.create_account("资产", AccountType.ASSET, account_id="root")
    child1 = engine.create_account("流动资产", AccountType.ASSET, parent_id="root", account_id="child1")
    child2 = engine.create_account("固定资产", AccountType.ASSET, parent_id="root", account_id="child2")
    grandchild = engine.create_account("银行存款", AccountType.ASSET, parent_id="child1", account_id="gc1")

    tree = engine.get_account_tree()
    assert len(tree["roots"]) == 1
    assert len(tree["roots"][0]["children"]) == 2
    print("✅ test_account_tree passed")


def test_reconcile():
    """测试对账（不含初始余额）"""
    engine = AccountingEngine()

    cash = engine.create_account("现金", AccountType.ASSET, initial_balance=0)
    income = engine.create_account("收入", AccountType.INCOME)

    engine.record_transaction(cash.id, income.id, 500, note="收入1")
    engine.record_transaction(cash.id, income.id, 300, note="收入2")

    # 外部对账单
    statement = [
        (date(2026, 1, 1), "收入1", Decimal("500")),
        (date(2026, 1, 2), "收入2", Decimal("300")),
    ]

    result = engine.reconcile_account(cash.id, statement)
    assert result.is_reconciled, f"对账不平: 差异 {result.difference}"
    print(f"✅ test_reconcile passed (余额={result.our_balance}, 差异={result.difference})")


def test_reconcile_with_difference():
    """测试有差异的对账"""
    engine = AccountingEngine()

    cash = engine.create_account("现金", AccountType.ASSET, initial_balance=0)
    income = engine.create_account("收入", AccountType.INCOME)

    engine.record_transaction(cash.id, income.id, 500, note="收入1")

    # 外部账单多一笔
    statement = [
        (date(2026, 1, 1), "收入1", Decimal("500")),
        (date(2026, 1, 2), "收入2", Decimal("200")),
    ]

    result = engine.reconcile_account(cash.id, statement)
    assert not result.is_reconciled
    assert result.difference == Decimal("-200.00")
    print(f"✅ test_reconcile_with_difference passed (差异={result.difference})")


def test_decimal_precision():
    """测试 Decimal 精度"""
    engine = AccountingEngine()

    cash = engine.create_account("现金", AccountType.ASSET)
    income = engine.create_account("收入", AccountType.INCOME)

    # 带小数的金额
    engine.record_transaction(cash.id, income.id, "1234.56", note="测试精度")
    balance = engine.get_account_balance(cash.id)
    assert balance == Decimal("1234.56"), f"精度丢失: {balance}"
    print(f"✅ test_decimal_precision passed (余额={balance})")


def test_invalid_transaction():
    """测试无效交易"""
    engine = AccountingEngine()

    cash = engine.create_account("现金", AccountType.ASSET)
    income = engine.create_account("收入", AccountType.INCOME)

    try:
        engine.record_transaction(cash.id, cash.id, 100)
        assert False, "应该抛出异常"
    except ValueError as e:
        assert "同一账户" in str(e)

    try:
        engine.record_transaction(cash.id, income.id, -100)
        assert False, "应该抛出异常"
    except ValueError as e:
        assert "金额必须 > 0" in str(e)

    print("✅ test_invalid_transaction passed")


def test_as_of_date():
    """测试按日期查询余额"""
    engine = AccountingEngine()

    cash = engine.create_account("现金", AccountType.ASSET, initial_balance=10000)
    income = engine.create_account("收入", AccountType.INCOME)

    engine.record_transaction(cash.id, income.id, 5000, txn_date=date(2026, 1, 15), note="1月")
    engine.record_transaction(cash.id, income.id, 3000, txn_date=date(2026, 2, 15), note="2月")
    engine.record_transaction(cash.id, income.id, 2000, txn_date=date(2026, 3, 15), note="3月")

    bal_jan = engine.get_account_balance(cash.id, date(2026, 1, 31))
    assert bal_jan == Decimal("15000.00"), f"1月底余额错误: {bal_jan}"

    bal_feb = engine.get_account_balance(cash.id, date(2026, 2, 28))
    assert bal_feb == Decimal("18000.00"), f"2月底余额错误: {bal_feb}"

    print("✅ test_as_of_date passed")


if __name__ == "__main__":
    test_create_account()
    test_record_transaction()
    test_double_entry_balance()
    test_trial_balance_after_transactions()
    test_account_tree()
    test_reconcile()
    test_reconcile_with_difference()
    test_decimal_precision()
    test_invalid_transaction()
    test_as_of_date()
    print("\n🎉 FIN-001 全部测试通过!")
