"""
Office Contract 页面视觉回归测试用例
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.abspath('/Users/bangcle/.openclaw/workspace/L2-infra/components/web-common/tests/visual'))
from base import VisualTestBase


class TestOCDashboard(VisualTestBase):
    """Office Contract 仪表盘页面测试"""
    url = "http://127.0.0.1:18804/"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_dashboard(self, page):
        self.assert_visual_match(page, "dashboard")


class TestOCList(VisualTestBase):
    """Office Contract 列表页面测试"""
    url = "http://127.0.0.1:18804/contracts"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_list(self, page):
        self.assert_visual_match(page, "list")


class TestOCNew(VisualTestBase):
    """Office Contract 新建合同页面测试"""
    url = "http://127.0.0.1:18804/contracts/new"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_new(self, page):
        self.assert_visual_match(page, "new")


class TestOCRiskRules(VisualTestBase):
    """Office Contract 风险规则页面测试"""
    url = "http://127.0.0.1:18804/risk-rules"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_risk_rules(self, page):
        self.assert_visual_match(page, "riskrules")
