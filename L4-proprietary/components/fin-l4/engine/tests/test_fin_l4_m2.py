"""M2 测试: 智能分类 + 预算管理 + CSV 导入"""

import os
import sys
import unittest
import tempfile
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fin_l4.db import init_db
from fin_l4.db.repositories import (
    FamilyRepository, AccountRepository, CategoryRepository,
    BudgetRepository, ImportRuleRepository
)
from fin_l4.services.category_engine import CategoryEngine, CategoryRule
from fin_l4.services.budget_svc import BudgetService
from fin_l4.services.import_svc import ImportService
from fin_l4.services.account_svc import AccountService
from fin_l4.services.txn_svc import TransactionService


class TestCategoryEngine(unittest.TestCase):
    """智能分类引擎测试"""

    def setUp(self):
        self.engine = CategoryEngine.default_rules()

    def test_classify_salary(self):
        result = self.engine.classify("工资收入")
        self.assertEqual(result, "cat_salary")

    def test_classify_food(self):
        result = self.engine.classify("午餐外卖")
        self.assertEqual(result, "cat_food")

    def test_classify_transport(self):
        result = self.engine.classify("滴滴打车")
        self.assertEqual(result, "cat_transport")

    def test_classify_shopping(self):
        result = self.engine.classify("淘宝购物")
        self.assertEqual(result, "cat_shopping")

    def test_classify_housing(self):
        result = self.engine.classify("交房租")
        self.assertEqual(result, "cat_housing")

    def test_classify_medical(self):
        result = self.engine.classify("医院挂号费")
        self.assertEqual(result, "cat_medical")

    def test_classify_unknown(self):
        result = self.engine.classify("xyzabc123")
        self.assertEqual(result, "cat_other")

    def test_custom_rule_priority(self):
        """自定义规则应覆盖默认规则"""
        engine = CategoryEngine.default_rules()
        engine.add_rule(CategoryRule(
            id="custom_food", category_id="cat_food",
            keywords=["奖金"], priority=200,
        ))
        # "奖金" 默认匹配 cat_salary，但自定义规则优先级更高
        result = self.engine.classify("年终奖金")
        self.assertEqual(result, "cat_salary")  # 默认规则下

        result2 = engine.classify("年终奖金")
        self.assertEqual(result2, "cat_food")  # 自定义规则覆盖

    def test_list_rules(self):
        rules = self.engine.list_rules()
        self.assertGreater(len(rules), 5)


class TestBudgetService(unittest.TestCase):
    """预算管理测试"""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.addCleanup(os.close, self.db_fd)
        self.addCleanup(os.unlink, self.db_path)
        self.conn = init_db(self.db_path)
        self.family_id = FamilyRepository(self.conn).create("Test Family")

        # 创建分类
        cat_repo = CategoryRepository(self.conn)
        self.food_cat = cat_repo.create(self.family_id, "餐饮", "expense")
        self.transport_cat = cat_repo.create(self.family_id, "交通", "expense")
        self.salary_cat = cat_repo.create(self.family_id, "工资", "income")

        # 创建账户
        acc_repo = AccountRepository(self.conn)
        self.bank_acc = acc_repo.create(self.family_id, "1002", "银行存款", "ASSET")
        self.food_acc = acc_repo.create(self.family_id, "5001", "餐饮费", "EXPENSE")
        self.salary_acc = acc_repo.create(self.family_id, "4001", "工资收入", "INCOME")

        self.svc = BudgetService(self.conn)

    def test_set_budget(self):
        result = self.svc.set_budget(self.family_id, self.food_cat, "2026-09", "3000")
        self.assertEqual(result["status"], "ok")

    def test_get_budget(self):
        self.svc.set_budget(self.family_id, self.food_cat, "2026-09", "3000")
        budget = self.svc.get_budget(self.family_id, self.food_cat, "2026-09")
        self.assertIsNotNone(budget)
        self.assertEqual(budget["amount"], "3000")

    def test_list_budgets(self):
        self.svc.set_budget(self.family_id, self.food_cat, "2026-09", "3000")
        self.svc.set_budget(self.family_id, self.transport_cat, "2026-09", "1000")
        budgets = self.svc.list_budgets(self.family_id, "2026-09")
        self.assertEqual(len(budgets), 2)

    def test_upsert_update(self):
        """同一分类同月应更新而非重复"""
        self.svc.set_budget(self.family_id, self.food_cat, "2026-09", "3000")
        self.svc.set_budget(self.family_id, self.food_cat, "2026-09", "5000")
        budgets = self.svc.list_budgets(self.family_id, "2026-09")
        self.assertEqual(len(budgets), 1)
        self.assertEqual(budgets[0]["amount"], "5000")

    def test_budget_status(self):
        """预算执行状态"""
        # 设置预算
        self.svc.set_budget(self.family_id, self.food_cat, "2026-09", "3000")

        # 记一笔支出
        txn_svc = TransactionService(self.conn)
        txn_svc.record(self.family_id, "2026-09-15", "500",
                       self.food_acc, self.bank_acc, "聚餐",
                       category_id=self.food_cat)

        statuses = self.svc.get_status(self.family_id, "2026-09")
        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0].spent_amount, Decimal("500.00"))
        self.assertEqual(statuses[0].remaining, 2500)
        self.assertEqual(statuses[0].status, "ok")

    def test_budget_exceeded(self):
        """超支检测"""
        self.svc.set_budget(self.family_id, self.food_cat, "2026-09", "1000")

        txn_svc = TransactionService(self.conn)
        txn_svc.record(self.family_id, "2026-09-15", "1500",
                       self.food_acc, self.bank_acc, "豪华聚餐",
                       category_id=self.food_cat)

        statuses = self.svc.get_status(self.family_id, "2026-09")
        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0].status, "exceeded")

    def test_budget_overview(self):
        """预算总览"""
        self.svc.set_budget(self.family_id, self.food_cat, "2026-09", "3000")
        self.svc.set_budget(self.family_id, self.transport_cat, "2026-09", "1000")

        overview = self.svc.get_overview(self.family_id, "2026-09")
        self.assertEqual(overview["total_budget"], "4000")
        self.assertEqual(overview["categories"], 2)


class TestImportService(unittest.TestCase):
    """CSV 导入测试"""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.addCleanup(os.close, self.db_fd)
        self.addCleanup(os.unlink, self.db_path)
        self.conn = init_db(self.db_path)
        self.family_id = FamilyRepository(self.conn).create("Test Family")

        cat_repo = CategoryRepository(self.conn)
        self.food_cat = cat_repo.create(self.family_id, "餐饮", "expense")
        self.salary_cat = cat_repo.create(self.family_id, "工资", "income")

        acc_repo = AccountRepository(self.conn)
        self.bank_acc = acc_repo.create(self.family_id, "1002", "银行存款", "ASSET")
        self.food_acc = acc_repo.create(self.family_id, "5001", "餐饮费", "EXPENSE")
        self.salary_acc = acc_repo.create(self.family_id, "4001", "工资收入", "INCOME")

        self.svc = ImportService(self.conn)

    def test_preview_csv(self):
        csv_content = """date,amount,description
2026-09-01,35000,工资收入
2026-09-02,-50,午餐外卖
2026-09-03,-15,地铁通勤"""
        previews = self.svc.preview_csv(self.family_id, csv_content)
        self.assertEqual(len(previews), 3)
        # 第一行应分类为工资
        self.assertEqual(previews[0]["suggested_category"], "cat_salary")
        # 第二行应分类为餐饮
        self.assertEqual(previews[1]["suggested_category"], "cat_food")

    def test_import_csv(self):
        csv_content = """date,amount,description
2026-09-01,35000,工资收入
2026-09-02,-50,午餐外卖
2026-09-03,-15,地铁通勤"""
        result = self.svc.import_csv(
            self.family_id, csv_content,
        )
        self.assertEqual(result["imported"], 3)
        self.assertGreater(result["auto_categorized"], 0)

    def test_import_rules(self):
        """自定义导入规则"""
        rule_id = self.svc.add_rule(
            self.family_id, "星巴克,瑞幸,咖啡", self.food_cat, priority=10
        )
        self.assertIsNotNone(rule_id)

        rules = self.svc.list_rules(self.family_id)
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["category_id"], self.food_cat)

    def test_import_with_custom_rule(self):
        """自定义规则影响分类"""
        self.svc.add_rule(
            self.family_id, "星巴克", self.food_cat, priority=10
        )

        csv_content = """date,amount,description
2026-09-02,-38,星巴克拿铁"""
        result = self.svc.import_csv(
            self.family_id, csv_content,
        )
        self.assertEqual(result["imported"], 1)
        self.assertEqual(result["auto_categorized"], 1)


class TestBudgetRepository(unittest.TestCase):
    """Budget Repository 测试"""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.addCleanup(os.close, self.db_fd)
        self.addCleanup(os.unlink, self.db_path)
        self.conn = init_db(self.db_path)
        self.family_id = FamilyRepository(self.conn).create("Test")
        self.repo = BudgetRepository(self.conn)
        cat_repo = CategoryRepository(self.conn)
        self.cat1 = cat_repo.create(self.family_id, "餐饮", "expense")
        self.cat2 = cat_repo.create(self.family_id, "交通", "expense")

    def test_upsert_creates(self):
        bid = self.repo.upsert(self.family_id, self.cat1, "2026-09", "1000")
        self.assertIsNotNone(bid)

    def test_upsert_updates(self):
        self.repo.upsert(self.family_id, self.cat1, "2026-09", "1000")
        self.repo.upsert(self.family_id, self.cat1, "2026-09", "2000")
        budgets = self.repo.list_by_family(self.family_id, "2026-09")
        self.assertEqual(len(budgets), 1)
        self.assertEqual(budgets[0]["amount"], "2000")

    def test_get(self):
        self.repo.upsert(self.family_id, self.cat1, "2026-09", "1000")
        budget = self.repo.get(self.family_id, self.cat1, "2026-09")
        self.assertIsNotNone(budget)
        self.assertEqual(budget["amount"], "1000")

    def test_list_by_family(self):
        cat_repo = CategoryRepository(self.conn)
        c1 = cat_repo.create(self.family_id, "餐饮", "expense")
        c2 = cat_repo.create(self.family_id, "交通", "expense")
        self.repo.upsert(self.family_id, c1, "2026-09", "1000")
        self.repo.upsert(self.family_id, c2, "2026-09", "500")
        budgets = self.repo.list_by_family(self.family_id, "2026-09")
        self.assertEqual(len(budgets), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
