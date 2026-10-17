"""
Delivery Center 5 页面视觉回归测试
页面: /, /generate, /reports/{id}
"""

import sys
import os
sys.path.insert(0, os.path.abspath('/Users/bangcle/.openclaw/workspace/L2-infra/components/web-common/tests/visual'))
from base import VisualTestBase

BASE = "http://127.0.0.1:18804"


class TestDCDashboard(VisualTestBase):
    """Delivery Center 首页/报告列表"""
    url = f"{BASE}/"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "dashboard")


class TestDCGenerate(VisualTestBase):
    """Delivery Center 生成月报"""
    url = f"{BASE}/generate"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "generate")


class TestDCReportDetail(VisualTestBase):
    """Delivery Center 报告详情"""
    url = f"{BASE}/reports/1"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "report_detail")
