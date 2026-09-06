"""FIN-L4 端到端集成测试"""

import os
import sys
import unittest
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fin_l4.db import init_db, get_db
from fin_l4.db.repositories import FamilyRepository
from fin_l4.services.account_svc import AccountService
from fin_l4.services.txn_svc import TransactionService
from fin_l4.services.loan_svc import LoanService
from fin_l4.services.insurance_svc import InsuranceService
from fin_l4.services.portfolio_svc import PortfolioService
from fin_l4.services.report_svc import ReportService
from fin_l4.services.advise_svc import AdviseService
from fin_l4.services.rate_svc import RateService


class TestE2EFamilyFinance(unittest.TestCase):
    """端到端家庭理财流程测试"""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.addCleanup(os.close, self.db_fd)
        self.addCleanup(os.unlink, self.db_path)
        self.conn = init_db(self.db_path)
        self.family_id = FamilyRepository(self.conn).create("Rex 家庭")

    def test_full_workflow(self):
        """完整工作流：创建家庭 → 建立科目 → 记账 → 贷款 → 保险 → 投资 → 报表"""
        account_svc = AccountService(self.conn)
        txn_svc = TransactionService(self.conn)
        loan_svc = LoanService(self.conn)
        insurance_svc = InsuranceService(self.conn)
        portfolio_svc = PortfolioService(self.conn)
        report_svc = ReportService(self.conn)

        # 1. 建立科目表
        cash = account_svc.create_account(self.family_id, "1001", "库存现金", "ASSET", opening_balance="50000")
        bank = account_svc.create_account(self.family_id, "1002", "银行存款", "ASSET", opening_balance="300000")
        equity = account_svc.create_account(self.family_id, "3001", "初始权益", "EQUITY", opening_balance="350000")
        salary = account_svc.create_account(self.family_id, "4001", "工资收入", "INCOME")
        food_exp = account_svc.create_account(self.family_id, "5001", "餐饮费", "EXPENSE")
        loan_pay = account_svc.create_account(self.family_id, "5002", "还贷支出", "EXPENSE")

        # 验证试算平衡（期初：资产 350000 = 权益 350000）
        tb = account_svc.get_trial_balance(self.family_id)
        self.assertTrue(tb['is_balanced'], "期初试算平衡")

        # 2. 记账：月工资收入
        txn_svc.record(self.family_id, "2026-09-01", "35000", bank['id'], salary['id'], "9月工资")
        # 记账：餐饮支出
        txn_svc.record(self.family_id, "2026-09-02", "500", food_exp['id'], cash['id'], "午餐")

        # 验证余额
        cash_balance = account_svc.get_balance(cash['id'])
        self.assertEqual(cash_balance, 50000 - 500)  # 期初 50000 - 支出 500

        bank_balance = account_svc.get_balance(bank['id'])
        self.assertEqual(bank_balance, 300000 + 35000)  # 期初 300000 + 收入 35000

        # 3. 添加贷款
        loan = loan_svc.create_loan(
            self.family_id, "房贷", "1000000", "0.035", 360
        )
        self.assertEqual(loan['status'], "active")

        schedule = loan_svc.get_schedule(loan['id'])
        self.assertEqual(len(schedule), 360)
        self.assertEqual(schedule[-1]['remaining_balance'], "0.00")

        summary = loan_svc.get_summary(loan['id'])
        self.assertIn('monthly_payment', summary)
        self.assertIn('total_interest', summary)

        # 4. 添加保险
        policy = insurance_svc.add_policy(
            self.family_id, "重疾险", "critical_illness",
            "300000", "8000", 30, 20,
            insured_name="Rex", insured_age=28,
        )
        self.assertEqual(policy['product_name'], "重疾险")

        # 5. 投资
        portfolio = portfolio_svc.create_portfolio(self.family_id, "Rex 组合")
        self.assertEqual(portfolio['name'], "Rex 组合")

        holding = portfolio_svc.buy(
            portfolio['id'], "stock", "贵州茅台", "600519", "100", "1600.00"
        )
        self.assertEqual(holding['action'], "buy")

        perf = portfolio_svc.get_performance(portfolio['id'])
        self.assertIn('total_value', perf)

        alloc = portfolio_svc.get_allocation(portfolio['id'])
        self.assertIn('allocation', alloc)

        # 6. 报表
        bs = report_svc.balance_sheet(self.family_id)
        self.assertIn('assets', bs)
        self.assertIn('net_worth', bs)

        income = report_svc.income_summary(self.family_id)
        self.assertIn('income', income)
        self.assertIn('expenses', income)

        cashflow = report_svc.cashflow_monthly(self.family_id)
        self.assertIsInstance(cashflow, list)

        print(f"\n=== 端到端测试结果 ===")
        print(f"家庭: Rex 家庭")
        print(f"现金余额: ¥{cash_balance}")
        print(f"银行余额: ¥{bank_balance}")
        print(f"贷款: {summary['name']}, 月供: ¥{summary['monthly_payment']}")
        print(f"投资: {perf['total_value']}")
        print(f"净值: ¥{bs['net_worth']}")
        print(f"=====================\n")

    def test_rate_sync(self):
        """利率同步测试"""
        rate_svc = RateService(self.conn)
        result = rate_svc.sync_rates()
        self.assertIn('lpr', result)

        latest = rate_svc.get_latest("LPR", "5y")
        self.assertIsNotNone(latest)

    def test_external_data_sources(self):
        """外部数据源注册测试"""
        from fin_l4.external.base import DataSourceRegistry
        from fin_l4.external.rate_source import RateSource

        source = RateSource()
        DataSourceRegistry.register(source)

        sources = DataSourceRegistry.list_all()
        self.assertGreater(len(sources), 0)
        self.assertEqual(sources[0]['name'], 'rate_lpr')

    def test_integration_links(self):
        """外部系统链接测试"""
        from fin_l4.db.repositories import IntegrationRepository
        repo = IntegrationRepository(self.conn)

        iid = repo.create(self.family_id, "招商银行", "bank", "https://cmbchina.com", "Rex")
        links = repo.list_by_family(self.family_id)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]['name'], "招商银行")

    def test_audit_trail(self):
        """审计日志测试"""
        from fin_l4.db.repositories import AuditLogRepository
        audit = AuditLogRepository(self.conn)

        # 创建账户会自动记录审计日志
        account_svc = AccountService(self.conn)
        account_svc.create_account(self.family_id, "1001", "现金", "ASSET")

        logs = audit.list_by_family(self.family_id)
        self.assertGreater(len(logs), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
