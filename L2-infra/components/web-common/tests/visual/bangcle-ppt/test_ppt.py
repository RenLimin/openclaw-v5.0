"""
Bangcle PPT 页面视觉回归测试用例
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.abspath('/Users/bangcle/.openclaw/workspace/L2-infra/components/web-common/tests/visual'))
from base import VisualTestBase


class TestPPTIndex(VisualTestBase):
    """Bangcle PPT 首页测试"""
    url = "http://127.0.0.1:18805/"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_index(self, page):
        self.assert_visual_match(page, "index")


class TestPPTGenerator(VisualTestBase):
    """Bangcle PPT 生成页面测试"""
    url = "http://127.0.0.1:18805/generate"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_generator(self, page):
        self.assert_visual_match(page, "generator")


class TestPPTDetail(VisualTestBase):
    """Bangcle PPT 详情页面测试"""
    url = "http://127.0.0.1:18805/detail/1"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_detail(self, page):
        self.assert_visual_match(page, "detail")
