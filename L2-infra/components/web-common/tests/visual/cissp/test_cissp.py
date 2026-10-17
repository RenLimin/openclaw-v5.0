"""
CISSP Trainer 页面视觉回归测试用例
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.abspath('/Users/bangcle/.openclaw/workspace/L2-infra/components/web-common/tests/visual'))
from base import VisualTestBase


class TestCISSPDashboard(VisualTestBase):
    """CISSP Trainer 仪表盘页面测试"""
    url = "http://127.0.0.1:18802/"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_dashboard(self, page):
        self.assert_visual_match(page, "dashboard")


class TestCISSPExam(VisualTestBase):
    """CISSP Trainer 考试页面测试"""
    url = "http://127.0.0.1:18802/exam"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_exam(self, page):
        self.assert_visual_match(page, "exam")


class TestCISSPKnowledgeGraph(VisualTestBase):
    """CISSP Trainer 知识图谱页面测试"""
    url = "http://127.0.0.1:18802/knowledge-graph"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_knowledge_graph(self, page):
        self.assert_visual_match(page, "knowledgegraph")


class TestCISSPLearningPath(VisualTestBase):
    """CISSP Trainer 学习路径页面测试"""
    url = "http://127.0.0.1:18802/learning-path"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_learning_path(self, page):
        self.assert_visual_match(page, "learningpath")


class TestCISSPQuestions(VisualTestBase):
    """CISSP Trainer 题目页面测试"""
    url = "http://127.0.0.1:18802/questions"
    viewport = (1440, 900)
    threshold = 0.001
    wait_for_selector = "body"

    def test_questions(self, page):
        self.assert_visual_match(page, "questions")
