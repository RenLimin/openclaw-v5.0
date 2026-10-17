"""
FIN-L4 19 页面视觉回归测试
页面: /, /budget, /import, /loans, /insurance, /insurance/coverage-gap,
      /portfolio, /accounts, /transactions, /rates, /rules, /settings,
      /reports, /advise
"""

import sys
import os
sys.path.insert(0, os.path.abspath('/Users/bangcle/.openclaw/workspace/L2-infra/components/web-common/tests/visual'))
from base import VisualTestBase

BASE = "http://127.0.0.1:18801"


class TestFinDashboard(VisualTestBase):
    """FIN-L4 仪表盘"""
    url = f"{BASE}/"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "dashboard")


class TestFinBudget(VisualTestBase):
    """FIN-L4 预算"""
    url = f"{BASE}/budget"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "budget")


class TestFinImport(VisualTestBase):
    """FIN-L4 导入"""
    url = f"{BASE}/import"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "import")


class TestFinLoans(VisualTestBase):
    """FIN-L4 贷款列表"""
    url = f"{BASE}/loans"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "loans")


class TestFinInsurance(VisualTestBase):
    """FIN-L4 保险列表"""
    url = f"{BASE}/insurance"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "insurance")


class TestFinCoverageGap(VisualTestBase):
    """FIN-L4 保障缺口"""
    url = f"{BASE}/insurance/coverage-gap"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "coverage_gap")


class TestFinPortfolio(VisualTestBase):
    """FIN-L4 投资组合"""
    url = f"{BASE}/portfolio"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "portfolio")


class TestFinAccounts(VisualTestBase):
    """FIN-L4 账户"""
    url = f"{BASE}/accounts"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "accounts")


class TestFinTransactions(VisualTestBase):
    """FIN-L4 交易流水"""
    url = f"{BASE}/transactions"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "transactions")


class TestFinRates(VisualTestBase):
    """FIN-L4 汇率"""
    url = f"{BASE}/rates"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "rates")


class TestFinRules(VisualTestBase):
    """FIN-L4 规则"""
    url = f"{BASE}/rules"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "rules")


class TestFinSettings(VisualTestBase):
    """FIN-L4 设置"""
    url = f"{BASE}/settings"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "settings")


class TestFinReports(VisualTestBase):
    """FIN-L4 报表"""
    url = f"{BASE}/reports"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "reports")


class TestFinAdvise(VisualTestBase):
    """FIN-L4 理财建议"""
    url = f"{BASE}/advise"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "advise")
