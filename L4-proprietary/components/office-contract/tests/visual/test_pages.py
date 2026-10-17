"""
Office Contract 6 页面视觉回归测试
页面: /, /contracts, /contracts/new, /risk-rules
"""

import sys
import os
sys.path.insert(0, os.path.abspath('/Users/bangcle/.openclaw/workspace/L2-infra/components/web-common/tests/visual'))
from base import VisualTestBase

BASE = "http://127.0.0.1:18803"


class TestOCDashboard(VisualTestBase):
    """Office Contract 首页/看板"""
    url = f"{BASE}/"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "dashboard")


class TestOCList(VisualTestBase):
    """Office Contract 合同列表"""
    url = f"{BASE}/contracts"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "contract_list")


class TestOCNew(VisualTestBase):
    """Office Contract 新建合同"""
    url = f"{BASE}/contracts/new"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "contract_new")


class TestOCRiskRules(VisualTestBase):
    """Office Contract 风控规则"""
    url = f"{BASE}/risk-rules"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "risk_rules")
