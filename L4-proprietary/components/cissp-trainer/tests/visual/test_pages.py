"""
CISSP Trainer 9 页面视觉回归测试
页面: /, /questions, /exam, /learning-path, /knowledge-graph
"""

import sys
import os
sys.path.insert(0, os.path.abspath('/Users/bangcle/.openclaw/workspace/L2-infra/components/web-common/tests/visual'))
from base import VisualTestBase

BASE = "http://127.0.0.1:8083"


class TestCisspDashboard(VisualTestBase):
    """CISSP 首页"""
    url = f"{BASE}/"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "dashboard")


class TestCisspQuestions(VisualTestBase):
    """CISSP 题库"""
    url = f"{BASE}/questions"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "questions")


class TestCisspExam(VisualTestBase):
    """CISSP 考试列表"""
    url = f"{BASE}/exam"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "exam")


class TestCisspLearningPath(VisualTestBase):
    """CISSP 学习路径"""
    url = f"{BASE}/learning-path"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "learning_path")


class TestCisspKnowledgeGraph(VisualTestBase):
    """CISSP 知识图谱"""
    url = f"{BASE}/knowledge-graph"
    viewport = (1440, 900)
    wait_for_selector = "body"

    def test_page(self, page):
        self.assert_visual_match(page, "knowledge_graph")
