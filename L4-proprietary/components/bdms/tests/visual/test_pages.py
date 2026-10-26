"""
BDMS 9 页面视觉回归测试
页面路由: /, /report, /revenue, /revenue/compare, /master-data, /dashboard, /settings, /error, /api 相关
"""

import sys
import os
sys.path.insert(0, os.path.abspath('/Users/bangcle/.openclaw/workspace/L2-infra/components/web-common/tests/visual'))
from base import VisualTestBase


class TestBDMSDashboard(VisualTestBase):
    """BDMS 仪表盘/首页"""
    url = "http://127.0.0.1:8000/"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "index")


class TestBDMSDashView(VisualTestBase):
    """BDMS 交付统计看板"""
    url = "http://127.0.0.1:8000/dashboard"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "dashboard_view")


class TestBDMSError(VisualTestBase):
    """BDMS 错误页（404 是预期状态，允许截基准图）"""
    url = "http://127.0.0.1:8000/nonexistent-page"
    viewport = (1440, 900)
    wait_for_selector = "body"
    allowed_status_codes = {200, 404}

    def test_page(self, page):
        self.assert_visual_match(page, "error")


class TestBDMSReport(VisualTestBase):
    """BDMS 交付月报"""
    url = "http://127.0.0.1:8000/report"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "report")


class TestBDMSRevenue(VisualTestBase):
    """BDMS 确收汇总"""
    url = "http://127.0.0.1:8000/revenue"
    viewport = (1440, 900)
    threshold = 0.01  # 1% 容忍度：表格数据内容会变，允许一定差异
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "revenue")


class TestBDMSRevenueCompare(VisualTestBase):
    """BDMS 对比分析"""
    url = "http://127.0.0.1:8000/revenue/compare"
    viewport = (1440, 900)
    threshold = 0.01  # 1% 容忍度：对比内容会变，允许一定差异
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "revenue_compare")


class TestBDMSMasterData(VisualTestBase):
    """BDMS 图例基础数据"""
    url = "http://127.0.0.1:8000/master-data"
    viewport = (1440, 900)
    threshold = 0.01  # 1% 容忍度：表格数据内容会变，允许一定差异
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "master_data")


class TestBDMSSettings(VisualTestBase):
    """BDMS 系统设定"""
    url = "http://127.0.0.1:8000/settings"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "settings")
