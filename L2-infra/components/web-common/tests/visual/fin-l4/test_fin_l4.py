"""
FIN-L4 家庭理财页面视觉回归测试用例
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.abspath('/Users/bangcle/.openclaw/workspace/L2-infra/components/web-common/tests/visual'))
from base import VisualTestBase


class TestFindashboard(VisualTestBase):
    """FIN-L4 仪表盘页面测试"""
    url = "http://127.0.0.1:18801/"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"
    mask_selectors = [".hero-greeting"]

    def test_dashboard(self, page):
        self.assert_visual_match(page, "dashboard")


class TestFinaccounts(VisualTestBase):
    """FIN-L4 账户页面测试"""
    url = "http://127.0.0.1:18801/accounts"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_accounts(self, page):
        self.assert_visual_match(page, "accounts")


class TestFinadvise(VisualTestBase):
    """FIN-L4 建议页面测试"""
    url = "http://127.0.0.1:18801/advise"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_advise(self, page):
        self.assert_visual_match(page, "advise")


class TestFinbudget(VisualTestBase):
    """FIN-L4 预算页面测试"""
    url = "http://127.0.0.1:18801/budget"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_budget(self, page):
        self.assert_visual_match(page, "budget")


class TestFincoveragegap(VisualTestBase):
    """FIN-L4 保障缺口页面测试"""
    url = "http://127.0.0.1:18801/insurance/coverage-gap"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_coveragegap(self, page):
        self.assert_visual_match(page, "coveragegap")


class TestFinimport(VisualTestBase):
    """FIN-L4 导入页面测试"""
    url = "http://127.0.0.1:18801/import"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_import(self, page):
        self.assert_visual_match(page, "import")


class TestFininsurance(VisualTestBase):
    """FIN-L4 保险页面测试"""
    url = "http://127.0.0.1:18801/insurance"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_insurance(self, page):
        self.assert_visual_match(page, "insurance")


class TestFinloans(VisualTestBase):
    """FIN-L4 贷款页面测试"""
    url = "http://127.0.0.1:18801/loans"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_loans(self, page):
        self.assert_visual_match(page, "loans")


class TestFinportfolio(VisualTestBase):
    """FIN-L4 投资组合页面测试"""
    url = "http://127.0.0.1:18801/portfolio"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_portfolio(self, page):
        self.assert_visual_match(page, "portfolio")


class TestFinrates(VisualTestBase):
    """FIN-L4 利率页面测试"""
    url = "http://127.0.0.1:18801/rates"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_rates(self, page):
        self.assert_visual_match(page, "rates")


class TestFinreports(VisualTestBase):
    """FIN-L4 报表页面测试"""
    url = "http://127.0.0.1:18801/reports"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_reports(self, page):
        self.assert_visual_match(page, "reports")


class TestFinrules(VisualTestBase):
    """FIN-L4 规则页面测试"""
    url = "http://127.0.0.1:18801/rules"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_rules(self, page):
        self.assert_visual_match(page, "rules")


class TestFinsettings(VisualTestBase):
    """FIN-L4 设置页面测试"""
    url = "http://127.0.0.1:18801/settings"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_settings(self, page):
        self.assert_visual_match(page, "settings")


class TestFintransactions(VisualTestBase):
    """FIN-L4 交易页面测试"""
    url = "http://127.0.0.1:18801/transactions"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_transactions(self, page):
        self.assert_visual_match(page, "transactions")
