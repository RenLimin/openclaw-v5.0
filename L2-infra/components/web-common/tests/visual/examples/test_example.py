"""
示例：视觉回归测试用例
运行: pytest tests/visual/examples/test_example.py -v
"""

import sys
import os
import pytest
sys.path.insert(0, os.path.abspath('/Users/bangcle/.openclaw/workspace/L2-infra/components/web-common/tests/visual'))
from base import VisualTestBase


class TestExamplePage(VisualTestBase):
    """示例测试：测试一个本地 HTML 文件"""

    # 这里用本地文件测试，file:// URL
    url = "file:///Users/bangcle/.openclaw/workspace/L2-infra/components/web-common/examples/demo.html"
    viewport = (1440, 900)
    threshold = 0.001  # 0.1% 差异容忍
    # mask_selectors = [".dynamic-content"]  # 如果有动态内容，在这里加选择器
    wait_for_selector = "body"

    def test_example_page(self, page):
        """测试示例页面视觉一致性"""
        self.assert_visual_match(page, "demo")
