"""
BDMS 仪表盘页面视觉回归测试
"""

import sys
import os
sys.path.insert(0, os.path.abspath('/Users/bangcle/.openclaw/workspace/L2-infra/components/web-common/tests/visual'))
from base import VisualTestBase


class TestBDMSDashboard(VisualTestBase):
    """BDMS 仪表盘页面视觉测试"""

    url = "http://127.0.0.1:8000/"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_dashboard_page(self, page):
        """测试仪表盘页面视觉一致性"""
        self.assert_visual_match(page, "dashboard")
