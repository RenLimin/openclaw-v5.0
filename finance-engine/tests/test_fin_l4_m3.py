"""M3 测试: 贷款详情 + 保险详情 + 投资详情 + 导出"""

import os
import sys
import io
import unittest
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fin_l4.db import init_db
from fin_l4.db.repositories import (
    FamilyRepository, AccountRepository, CategoryRepository,
    LoanRepository, InsuranceRepository, PortfolioRepository, HoldingRepository
)
from fin_l4.services.loan_svc import LoanService
from fin_l4.services.insurance_svc import InsuranceService
from fin_l4.services.portfolio_svc import PortfolioService
from fin_l4.services.export_svc import ExportService


class TestLoanDetail(unittest.TestCase):
    """贷款详情 + 提前还款 + 结清"""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.addCleanup(os.close, self.db_fd)
        self.addCleanup(os.unlink, self.db_path)
        self.conn = init_db(self.db_path)
        self.family_id = FamilyRepository(self.conn).create("Test")
        self.svc = LoanService(self.conn)

    def test_get_schedule(self):
        loan = self.svc.create_loan(self.family_id, "房贷", "1000000", "0.0390", 360)
        loan_id = loan["id"]
        schedule = self.svc.get_schedule(loan_id)
        self.assertEqual(len(schedule), 360)
        self.assertEqual(schedule[0]["period"], 1)

    def test_get_summary(self):
        loan = self.svc.create_loan(self.family_id, "房贷", "1000000", "0.0390", 360)
        loan_id = loan["id"]
        summary = self.svc.get_summary(loan_id)
        self.assertIn("monthly_payment", summary)
        self.assertIn("total_interest", summary)
        self.assertIn("remaining_balance", summary)

    def test_execute_prepay(self):
        loan = self.svc.create_loan(self.family_id, "房贷", "1000000", "0.0390", 360)
        loan_id = loan["id"]
        result = self.svc.execute_prepay(loan_id, "100000")
        self.assertEqual(result["prepay_amount"], "100000")
        self.assertIn("interest_saved", result)
        # 验证本金减少
        loan = self.svc.repo.get(loan_id)
        self.assertEqual(loan["principal"], "900000")

    def test_close_loan(self):
        loan = self.svc.create_loan(self.family_id, "房贷", "1000000", "0.0390", 360)
        loan_id = loan["id"]
        result = self.svc.close_loan(loan_id)
        self.assertEqual(result["status"], "closed")
        loan = self.svc.repo.get(loan_id)
        self.assertEqual(loan["status"], "closed")


class TestInsuranceDetail(unittest.TestCase):
    """保险详情 + 退保 + 保障缺口"""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.addCleanup(os.close, self.db_fd)
        self.addCleanup(os.unlink, self.db_path)
        self.conn = init_db(self.db_path)
        self.family_id = FamilyRepository(self.conn).create("Test")
        self.svc = InsuranceService(self.conn)

    def test_get_policy_detail(self):
        policy = self.svc.add_policy(self.family_id, "重疾险", "critical_illness", "500000", "12000", 30, 20)
        pid = policy["id"]
        detail = self.svc.get_policy_detail(pid)
        self.assertEqual(detail["product_name"], "重疾险")
        self.assertIn("cash_value_table", detail)

    def test_surrender_policy(self):
        policy = self.svc.add_policy(self.family_id, "重疾险", "critical_illness", "500000", "12000", 30, 20)
        pid = policy["id"]
        result = self.svc.surrender_policy(pid)
        self.assertIn("cash_value", result)
        self.assertEqual(result["status"], "surrendered")

    def test_coverage_gap(self):
        # 创建一个保单
        self.svc.add_policy(self.family_id, "重疾险", "critical_illness", "500000", "12000", 30, 20)
        gaps = self.svc.get_coverage_gap(self.family_id)
        self.assertGreater(len(gaps), 0)
        # 找到重疾险
        ci_gap = [g for g in gaps if g["type"] == "critical_illness"]
        self.assertEqual(len(ci_gap), 1)


class TestPortfolioDetail(unittest.TestCase):
    """投资详情 + 盈亏 + 配置 + 再平衡"""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.addCleanup(os.close, self.db_fd)
        self.addCleanup(os.unlink, self.db_path)
        self.conn = init_db(self.db_path)
        self.family_id = FamilyRepository(self.conn).create("Test")
        self.svc = PortfolioService(self.conn)

    def test_get_performance(self):
        portfolio = self.svc.create_portfolio(self.family_id, "我的组合")
        pid = portfolio["id"]
        self.svc.buy(pid, "stock", "腾讯", "00700", "100", "350")
        perf = self.svc.get_performance(pid)
        self.assertIn("total_value", perf)
        self.assertIn("total_cost", perf)
        self.assertIn("total_gain", perf)

    def test_get_allocation(self):
        portfolio = self.svc.create_portfolio(self.family_id, "我的组合")
        pid = portfolio["id"]
        self.svc.buy(pid, "stock", "腾讯", "00700", "100", "350")
        alloc = self.svc.get_allocation(pid)
        self.assertIn("allocation", alloc)

    def test_get_rebalance(self):
        portfolio = self.svc.create_portfolio(self.family_id, "我的组合")
        pid = portfolio["id"]
        self.svc.buy(pid, "stock", "腾讯", "00700", "100", "350")
        rebalance = self.svc.get_rebalance(pid)
        self.assertIn("suggestions", rebalance)

    def test_get_holdings(self):
        portfolio = self.svc.create_portfolio(self.family_id, "我的组合")
        pid = portfolio["id"]
        self.svc.buy(pid, "stock", "腾讯", "00700", "100", "350")
        holdings = self.svc.get_holdings(pid)
        self.assertEqual(len(holdings), 1)
        self.assertEqual(holdings[0]["asset_name"], "腾讯")

    def test_update_price(self):
        portfolio = self.svc.create_portfolio(self.family_id, "我的组合")
        pid = portfolio["id"]
        self.svc.buy(pid, "stock", "腾讯", "00700", "100", "350")
        holdings = self.svc.get_holdings(pid)
        self.svc.update_price(holdings[0]["id"], "400")
        perf = self.svc.get_performance(pid)
        self.assertEqual(perf["total_value"], "40000.00")


class TestExportService(unittest.TestCase):
    """导出服务测试"""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.addCleanup(os.close, self.db_fd)
        self.addCleanup(os.unlink, self.db_path)
        self.conn = init_db(self.db_path)
        self.family_id = FamilyRepository(self.conn).create("Test")
        self.svc = ExportService(self.conn)

        # 创建账户
        acc_repo = AccountRepository(self.conn)
        acc_repo.create(self.family_id, "1001", "现金", "ASSET")
        acc_repo.create(self.family_id, "1002", "银行存款", "ASSET")
        acc_repo.create(self.family_id, "2001", "房贷", "LIABILITY")

    def test_export_balance_sheet_excel(self):
        data = self.svc.export_balance_sheet_excel(self.family_id)
        self.assertGreater(len(data), 1000)
        # 验证是有效的 xlsx（PK header）
        self.assertTrue(data[:2] == b'PK')

    def test_export_transactions_excel(self):
        data = self.svc.export_transactions_excel(self.family_id)
        self.assertGreater(len(data), 1000)
        self.assertTrue(data[:2] == b'PK')

    def test_export_financial_report_word(self):
        data = self.svc.export_financial_report_word(self.family_id)
        self.assertGreater(len(data), 1000)
        # docx 也是 zip
        self.assertTrue(data[:2] == b'PK')


if __name__ == '__main__':
    unittest.main(verbosity=2)
