"""FIN-L4 服务层测试"""

import os
import sys
import unittest
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fin_l4.db import init_db, get_db
from fin_l4.db.repositories import FamilyRepository, AccountRepository
from fin_l4.services.account_svc import AccountService
from fin_l4.services.txn_svc import TransactionService
from fin_l4.services.loan_svc import LoanService
from fin_l4.services.insurance_svc import InsuranceService
from fin_l4.services.portfolio_svc import PortfolioService
from fin_l4.services.report_svc import ReportService
from fin_l4.services.rate_svc import RateService


class TestAccountService(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.addCleanup(os.close, self.db_fd)
        self.addCleanup(os.unlink, self.db_path)
        self.conn = init_db(self.db_path)
        self.family_id = FamilyRepository(self.conn).create("测试家庭")
        self.svc = AccountService(self.conn)

    def test_create_account(self):
        result = self.svc.create_account(
            family_id=self.family_id,
            code="1001",
            name="库存现金",
            type="ASSET",
            opening_balance="5000",
        )
        self.assertEqual(result['name'], "库存现金")
        self.assertEqual(result['type'], "ASSET")

    def test_create_account_invalid_type(self):
        with self.assertRaises(ValueError):
            self.svc.create_account(self.family_id, "9999", "测试", "INVALID")

    def test_list_accounts(self):
        self.svc.create_account(self.family_id, "1001", "现金", "ASSET")
        self.svc.create_account(self.family_id, "1002", "银行", "ASSET")
        accounts = self.svc.list_accounts(self.family_id)
        self.assertEqual(len(accounts), 2)

    def test_trial_balance_balanced(self):
        """试算平衡：有借必有贷"""
        self.svc.create_account(self.family_id, "1001", "现金", "ASSET", opening_balance="10000")
        self.svc.create_account(self.family_id, "3001", "权益", "EQUITY", opening_balance="10000")
        result = self.svc.get_trial_balance(self.family_id)
        self.assertTrue(result['is_balanced'])

    def test_trial_balance_unbalanced(self):
        """试算平衡：不平衡应检测"""
        self.svc.create_account(self.family_id, "1001", "现金", "ASSET", opening_balance="10000")
        self.svc.create_account(self.family_id, "3001", "权益", "EQUITY", opening_balance="5000")
        result = self.svc.get_trial_balance(self.family_id)
        self.assertFalse(result['is_balanced'])


class TestTransactionService(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.addCleanup(os.close, self.db_fd)
        self.addCleanup(os.unlink, self.db_path)
        self.conn = init_db(self.db_path)
        self.family_id = FamilyRepository(self.conn).create("测试家庭")
        self.svc = TransactionService(self.conn)
        
        # 创建基础账户
        acc_repo = AccountRepository(self.conn)
        self.cash_id = acc_repo.create(self.family_id, "1001", "现金", "ASSET", opening_balance="10000")
        self.expense_id = acc_repo.create(self.family_id, "5001", "餐费", "EXPENSE", opening_balance="0")

    def test_record_valid(self):
        result = self.svc.record(
            family_id=self.family_id,
            date_str="2026-09-01",
            amount="50",
            debit_account_id=self.expense_id,
            credit_account_id=self.cash_id,
            note="午餐",
        )
        self.assertEqual(result['status'], "ok")

    def test_record_invalid_amount(self):
        with self.assertRaises(ValueError):
            self.svc.record(self.family_id, "2026-09-01", "-50", self.expense_id, self.cash_id)

    def test_list_transactions(self):
        self.svc.record(self.family_id, "2026-09-01", "50", self.expense_id, self.cash_id, "午餐")
        self.svc.record(self.family_id, "2026-09-02", "30", self.expense_id, self.cash_id, "早餐")
        txns = self.svc.list_transactions(self.family_id)
        self.assertEqual(len(txns), 2)


class TestLoanService(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.addCleanup(os.close, self.db_fd)
        self.addCleanup(os.unlink, self.db_path)
        self.conn = init_db(self.db_path)
        self.family_id = FamilyRepository(self.conn).create("测试家庭")
        self.svc = LoanService(self.conn)

    def test_create_loan(self):
        result = self.svc.create_loan(
            family_id=self.family_id,
            name="房贷",
            principal="1000000",
            annual_rate="0.035",
            term_months=360,
        )
        self.assertEqual(result['name'], "房贷")
        self.assertEqual(result['status'], "active")

    def test_get_schedule(self):
        loan = self.svc.create_loan(
            family_id=self.family_id,
            name="房贷",
            principal="1000000",
            annual_rate="0.035",
            term_months=360,
        )
        schedule = self.svc.get_schedule(loan['id'])
        self.assertEqual(len(schedule), 360)
        # 最后一期剩余本金应为 0
        self.assertEqual(schedule[-1]['remaining_balance'], "0.00")

    def test_get_summary(self):
        loan = self.svc.create_loan(
            family_id=self.family_id,
            name="房贷",
            principal="1000000",
            annual_rate="0.035",
            term_months=360,
        )
        summary = self.svc.get_summary(loan['id'])
        self.assertIn('monthly_payment', summary)
        self.assertIn('total_interest', summary)


class TestInsuranceService(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.addCleanup(os.close, self.db_fd)
        self.addCleanup(os.unlink, self.db_path)
        self.conn = init_db(self.db_path)
        self.family_id = FamilyRepository(self.conn).create("测试家庭")
        self.svc = InsuranceService(self.conn)

    def test_add_policy(self):
        result = self.svc.add_policy(
            family_id=self.family_id,
            product_name="重疾险",
            policy_type="critical_illness",
            sum_assured="300000",
            annual_premium="8000",
            term_years=30,
            payment_years=20,
            insured_name="Rex",
            insured_age=28,
        )
        self.assertEqual(result['product_name'], "重疾险")

    def test_invalid_type(self):
        with self.assertRaises(ValueError):
            self.svc.add_policy(
                family_id=self.family_id,
                product_name="测试",
                policy_type="invalid_type",
                sum_assured="100000",
                annual_premium="5000",
                term_years=20,
                payment_years=10,
            )


class TestPortfolioService(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.addCleanup(os.close, self.db_fd)
        self.addCleanup(os.unlink, self.db_path)
        self.conn = init_db(self.db_path)
        self.family_id = FamilyRepository(self.conn).create("测试家庭")
        self.svc = PortfolioService(self.conn)

    def test_create_portfolio(self):
        result = self.svc.create_portfolio(self.family_id, "我的组合")
        self.assertEqual(result['name'], "我的组合")

    def test_buy_holding(self):
        portfolio = self.svc.create_portfolio(self.family_id, "我的组合")
        result = self.svc.buy(
            portfolio_id=portfolio['id'],
            asset_type="stock",
            asset_name="贵州茅台",
            asset_code="600519",
            shares="100",
            price="1600.00",
        )
        self.assertEqual(result['action'], "buy")

    def test_performance_empty(self):
        portfolio = self.svc.create_portfolio(self.family_id, "空组合")
        result = self.svc.get_performance(portfolio['id'])
        self.assertEqual(result['total_value'], "0")


class TestReportService(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.addCleanup(os.close, self.db_fd)
        self.addCleanup(os.unlink, self.db_path)
        self.conn = init_db(self.db_path)
        self.family_id = FamilyRepository(self.conn).create("测试家庭")
        self.svc = ReportService(self.conn)

    def test_balance_sheet(self):
        # 创建账户 + 期初余额
        AccountRepository(self.conn).create(self.family_id, "1001", "现金", "ASSET", opening_balance="50000")
        AccountRepository(self.conn).create(self.family_id, "3001", "权益", "EQUITY", opening_balance="50000")
        
        result = self.svc.balance_sheet(self.family_id)
        self.assertIn('assets', result)
        self.assertIn('equity', result)
        self.assertTrue(result['is_balanced'])

    def test_income_summary(self):
        result = self.svc.income_summary(self.family_id)
        self.assertIn('income', result)
        self.assertIn('expenses', result)


class TestRateService(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.addCleanup(os.close, self.db_fd)
        self.addCleanup(os.unlink, self.db_path)
        self.conn = init_db(self.db_path)
        self.svc = RateService(self.conn)

    def test_sync_and_query(self):
        result = self.svc.sync_rates()
        self.assertIn('lpr', result)
        
        latest = self.svc.get_latest("LPR", "5y")
        self.assertIsNotNone(latest)


if __name__ == '__main__':
    unittest.main()
