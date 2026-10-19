"""
Delivery Center 页面视觉回归测试用例
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.abspath('/Users/bangcle/.openclaw/workspace/L2-infra/components/web-common/tests/visual'))
from base import VisualTestBase


class TestDCDashboard(VisualTestBase):
    """Delivery Center 仪表盘页面测试"""
    url = "http://127.0.0.1:18803/"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_dashboard(self, page):
        self.assert_visual_match(page, "dashboard")


class TestDCGenerate(VisualTestBase):
    """Delivery Center 生成页面测试"""
    url = "http://127.0.0.1:18803/generate"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_generate(self, page):
        self.assert_visual_match(page, "generate")


class TestDCReportDetail(VisualTestBase):
    """Delivery Center 报表详情页面测试"""
    url = "http://127.0.0.1:18803/reports/1"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_report_detail(self, page):
        self.assert_visual_match(page, "reportdetail")
