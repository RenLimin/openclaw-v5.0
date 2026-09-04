"""FIN-L4 数据库 + Repository 测试"""

import os
import sys
import unittest
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fin_l4.db import init_db, get_db
from fin_l4.db.repositories import (
    FamilyRepository, AccountRepository, TransactionRepository,
    CategoryRepository, LoanRepository, InsuranceRepository,
    PortfolioRepository, HoldingRepository, RateSnapshotRepository,
    IntegrationRepository, SecurityConfigRepository, AuditLogRepository,
)


class TestDatabase(unittest.TestCase):
    """数据库初始化测试"""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.addCleanup(os.close, self.db_fd)
        self.addCleanup(os.unlink, self.db_path)
        self.conn = init_db(self.db_path)

    def test_init_creates_tables(self):
        """测试初始化创建所有表"""
        tables = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'fin4_%'"
        ).fetchall()
        table_names = [t['name'] for t in tables]
        
        expected = [
            'fin4_family', 'fin4_accounts', 'fin4_categories',
            'fin4_transactions', 'fin4_budgets', 'fin4_loans',
            'fin4_insurance_policies', 'fin4_portfolios', 'fin4_holdings',
            'fin4_rate_snapshots', 'fin4_import_rules', 'fin4_integrations',
            'fin4_security_config', 'fin4_audit_log',
        ]
        for table in expected:
            self.assertIn(table, table_names, f"缺少表: {table}")


class TestFamilyRepository(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.addCleanup(os.close, self.db_fd)
        self.addCleanup(os.unlink, self.db_path)
        self.conn = init_db(self.db_path)
        self.repo = FamilyRepository(self.conn)

    def test_create_family(self):
        fid = self.repo.create("Rex 家庭", "CNY")
        self.assertIsNotNone(fid)
        
        family = self.repo.get(fid)
        self.assertEqual(family['name'], "Rex 家庭")
        self.assertEqual(family['currency'], "CNY")

    def test_list_families(self):
        self.repo.create("家庭A")
        self.repo.create("家庭B")
        families = self.repo.list_all()
        self.assertEqual(len(families), 2)


class TestAccountRepository(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.addCleanup(os.close, self.db_fd)
        self.addCleanup(os.unlink, self.db_path)
        self.conn = init_db(self.db_path)
        self.family_id = FamilyRepository(self.conn).create("测试家庭")
        self.repo = AccountRepository(self.conn)

    def test_create_account(self):
        aid = self.repo.create(
            family_id=self.family_id,
            code="1001",
            name="库存现金",
            type="ASSET",
            opening_balance="5000.00",
        )
        self.assertIsNotNone(aid)
        
        account = self.repo.get(aid)
        self.assertEqual(account['name'], "库存现金")
        self.assertEqual(account['type'], "ASSET")

    def test_balance_with_opening(self):
        aid = self.repo.create(
            family_id=self.family_id,
            code="1001",
            name="库存现金",
            type="ASSET",
            opening_balance="1000.00",
        )
        balance = self.repo.get_balance(aid)
        self.assertEqual(balance, 1000.00)

    def test_balance_asset_debit_increase(self):
        """资产类：借增贷减"""
        cash = self.repo.create(self.family_id, "1001", "现金", "ASSET", opening_balance="1000")
        expense = self.repo.create(self.family_id, "5001", "餐费", "EXPENSE", opening_balance="0")
        
        # 记一笔：借 餐费 100 / 贷 现金 100（花钱）
        txn_repo = TransactionRepository(self.conn)
        txn_repo.create(self.family_id, "2026-09-01", "100", expense, cash, "午餐")
        
        # 现金余额 = 1000 - 100 = 900（资产类贷减）
        self.assertEqual(self.repo.get_balance(cash), 900)
        # 费用余额 = 0 + 100 = 100（费用类借增）
        self.assertEqual(self.repo.get_balance(expense), 100)

    def test_balance_liability_credit_increase(self):
        """负债类：贷增借减"""
        loan = self.repo.create(self.family_id, "2501", "房贷", "LIABILITY", opening_balance="0")
        cash = self.repo.create(self.family_id, "1001", "现金", "ASSET", opening_balance="0")
        
        # 借 现金 100万 / 贷 房贷 100万
        txn_repo = TransactionRepository(self.conn)
        txn_repo.create(self.family_id, "2026-09-01", "1000000", cash, loan, "放贷")
        
        # 房贷余额 = 0 + 1000000 = 1000000
        self.assertEqual(self.repo.get_balance(loan), 1000000)


class TestTransactionRepository(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.addCleanup(os.close, self.db_fd)
        self.addCleanup(os.unlink, self.db_path)
        self.conn = init_db(self.db_path)
        self.family_id = FamilyRepository(self.conn).create("测试家庭")
        self.repo = TransactionRepository(self.conn)

    def test_create_transaction(self):
        # 创建真实账户用于外键
        acc_repo = AccountRepository(self.conn)
        acc1 = acc_repo.create(self.family_id, "1001", "现金", "ASSET")
        acc2 = acc_repo.create(self.family_id, "5001", "费用", "EXPENSE")
        aid = self.repo.create(self.family_id, "2026-09-01", "100.00", acc1, acc2, "测试")
        txn = self.conn.execute("SELECT * FROM fin4_transactions WHERE id = ?", (aid,)).fetchone()
        self.assertIsNotNone(txn)
        self.assertEqual(txn['amount'], "100.00")

    def test_list_by_family(self):
        acc_repo = AccountRepository(self.conn)
        acc1 = acc_repo.create(self.family_id, "1001", "现金", "ASSET")
        acc2 = acc_repo.create(self.family_id, "5001", "费用", "EXPENSE")
        self.repo.create(self.family_id, "2026-09-01", "100", acc1, acc2)
        self.repo.create(self.family_id, "2026-09-02", "200", acc2, acc1)
        results = self.repo.list_by_family(self.family_id)
        self.assertEqual(len(results), 2)


class TestRateSnapshotRepository(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.addCleanup(os.close, self.db_fd)
        self.addCleanup(os.unlink, self.db_path)
        self.conn = init_db(self.db_path)
        self.repo = RateSnapshotRepository(self.conn)

    def test_save_and_get_latest(self):
        self.repo.save("LPR", "0.035", "5y", "2026-09-01", "PBOC")
        result = self.repo.get_latest("LPR", "5y")
        self.assertIsNotNone(result)
        self.assertEqual(result['rate'], "0.035")

    def test_history(self):
        self.repo.save("LPR", "0.036", "5y", "2026-08-01", "PBOC")
        self.repo.save("LPR", "0.035", "5y", "2026-09-01", "PBOC")
        history = self.repo.get_history("LPR", "5y")
        self.assertEqual(len(history), 2)
        # 最新的在前
        self.assertEqual(history[0]['rate'], "0.035")


class TestIntegrationRepository(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.addCleanup(os.close, self.db_fd)
        self.addCleanup(os.unlink, self.db_path)
        self.conn = init_db(self.db_path)
        self.family_id = FamilyRepository(self.conn).create("测试家庭")
        self.repo = IntegrationRepository(self.conn)

    def test_create_and_list(self):
        iid = self.repo.create(self.family_id, "招商银行", "bank", "https://cmbchina.com")
        self.assertIsNotNone(iid)
        
        links = self.repo.list_by_family(self.family_id)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]['name'], "招商银行")

    def test_delete(self):
        iid = self.repo.create(self.family_id, "招商银行", "bank", "https://cmbchina.com")
        self.repo.delete(iid)
        links = self.repo.list_by_family(self.family_id)
        self.assertEqual(len(links), 0)


class TestAuditLogRepository(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.addCleanup(os.close, self.db_fd)
        self.addCleanup(os.unlink, self.db_path)
        self.conn = init_db(self.db_path)
        self.family_id = FamilyRepository(self.conn).create("测试家庭")
        self.repo = AuditLogRepository(self.conn)

    def test_log_and_list(self):
        self.repo.log(self.family_id, "test_user", "create", "account", "acc_001")
        logs = self.repo.list_by_family(self.family_id)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]['action'], "create")


if __name__ == '__main__':
    unittest.main()
