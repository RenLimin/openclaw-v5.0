"""
BDMS 页面视觉回归测试用例
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.abspath('/Users/bangcle/.openclaw/workspace/L2-infra/components/web-common/tests/visual'))
from base import VisualTestBase


class TestBDMSDashboard(VisualTestBase):
    """BDMS 仪表盘页面测试"""
    url = "http://127.0.0.1:8000/"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_dashboard(self, page):
        self.assert_visual_match(page, "dashboard")


class TestBDMSDashView(VisualTestBase):
    """BDMS 明细查看页面测试"""
    url = "http://127.0.0.1:8000/masterdata/dashview"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_dashview(self, page):
        self.assert_visual_match(page, "dashview")


class TestBDMSError(VisualTestBase):
    """BDMS 错误页面测试"""
    url = "http://127.0.0.1:8000/error"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_error(self, page):
        self.assert_visual_match(page, "error")


class TestBDMSMasterData(VisualTestBase):
    """BDMS 主数据页面测试"""
    url = "http://127.0.0.1:8000/masterdata"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_masterdata(self, page):
        self.assert_visual_match(page, "masterdata")


class TestBDMSReport(VisualTestBase):
    """BDMS 报表页面测试"""
    url = "http://127.0.0.1:8000/report"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_report(self, page):
        self.assert_visual_match(page, "report")


class TestBDMSRevenue(VisualTestBase):
    """BDMS 收入页面测试"""
    url = "http://127.0.0.1:8000/revenue"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"
    settle_time = 1.5  # 等待 Chart.js 动画完成

    def test_revenue(self, page):
        self.assert_visual_match(page, "revenue")


class TestBDMSRevenueCompare(VisualTestBase):
    """BDMS 收入对比页面测试"""
    url = "http://127.0.0.1:8000/revenue/compare"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_revenue_compare(self, page):
        self.assert_visual_match(page, "revenuecompare")


class TestBDMSSettings(VisualTestBase):
    """BDMS 设置页面测试"""
    url = "http://127.0.0.1:8000/settings"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_settings(self, page):
        self.assert_visual_match(page, "settings")
