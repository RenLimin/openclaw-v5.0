"""
Bangcle PPT 5 页面视觉回归测试
页面: /, /generator, /templates/{name}
"""

import sys
import os
sys.path.insert(0, os.path.abspath('/Users/bangcle/.openclaw/workspace/L2-infra/components/web-common/tests/visual'))
from base import VisualTestBase

BASE = "http://127.0.0.1:18806"


class TestPPTIndex(VisualTestBase):
    """Bangcle PPT 首页"""
    url = f"{BASE}/"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "index")


class TestPPTGenerator(VisualTestBase):
    """Bangcle PPT 生成器"""
    url = f"{BASE}/generator"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "generator")


class TestPPTDetail(VisualTestBase):
    """Bangcle PPT 模板详情"""
    url = f"{BASE}/templates/cover-light"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "template_detail")
