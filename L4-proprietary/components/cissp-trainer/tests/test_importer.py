"""
测试题库导入器
"""

import json
import tempfile
import pytest
from pathlib import Path
import yaml

from cissp_trainer.importer import import_questions, import_from_file, load_yaml_questions
from cissp_trainer.models import Question, KnowledgePoint


class TestImporter:
    """导入器测试"""

    def test_import_single_question(self, db_session):
        """导入单道题"""
        qs = [{
            "id": "import-001",
            "domain": 1,
            "difficulty": 3,
            "question_type": "single",
            "stem": "测试题干",
            "options": {"A": "选项A", "B": "选项B"},
            "correct_answer": "A",
            "explanation": "测试解析",
            "tags": ["测试标签"],
        }]
        result = import_questions(db_session, qs, source="test")
        assert result["added"] == 1
        assert result["updated"] == 0
        assert result["skipped"] == 0

        q = db_session.query(Question).filter_by(external_id="import-001").first()
        assert q is not None
        assert q.domain == 1
        assert q.difficulty == 3
        assert q.stem == "测试题干"
        assert q.correct_answer == "A"
        assert q.tags == ["测试标签"]

    def test_import_with_knowledge_points(self, db_session):
        """导入时自动创建知识点"""
        qs = [{
            "id": "import-kp-001",
            "domain": 1,
            "difficulty": 2,
            "question_type": "single",
            "stem": "KP测试",
            "options": {"A": "对", "B": "错"},
            "correct_answer": "A",
            "tags": ["标签A", "标签B"],
        }]
        result = import_questions(db_session, qs, source="test")
        assert result["added"] == 1

        # 知识点被创建
        kp1 = db_session.query(KnowledgePoint).filter_by(name="标签A", domain=1).first()
        kp2 = db_session.query(KnowledgePoint).filter_by(name="标签B", domain=1).first()
        assert kp1 is not None
        assert kp2 is not None
        assert kp1.total_questions == 1

    def test_skip_existing(self, db_session):
        """已存在的题目默认跳过"""
        qs = [{
            "id": "dup-001",
            "domain": 1,
            "difficulty": 2,
            "question_type": "single",
            "stem": "原题干",
            "options": {"A": "对", "B": "错"},
            "correct_answer": "A",
        }]
        result1 = import_questions(db_session, qs, source="test")
        assert result1["added"] == 1

        # 再导入一次，应该跳过
        qs2 = [{
            "id": "dup-001",
            "domain": 1,
            "difficulty": 3,  # 改了难度
            "question_type": "single",
            "stem": "新题干",
            "options": {"A": "对", "B": "错"},
            "correct_answer": "B",
        }]
        result2 = import_questions(db_session, qs2, source="test", skip_existing=True)
        assert result2["added"] == 0
        assert result2["skipped"] == 1

        # 数据不变
        q = db_session.query(Question).filter_by(external_id="dup-001").first()
        assert q.stem == "原题干"
        assert q.difficulty == 2

    def test_force_update(self, db_session):
        """强制更新已存在的题目"""
        qs = [{
            "id": "upd-001",
            "domain": 1,
            "difficulty": 2,
            "question_type": "single",
            "stem": "原题干",
            "options": {"A": "对", "B": "错"},
            "correct_answer": "A",
        }]
        import_questions(db_session, qs, source="test")

        qs2 = [{
            "id": "upd-001",
            "domain": 2,
            "difficulty": 4,
            "question_type": "single",
            "stem": "新题干",
            "options": {"A": "对", "B": "错"},
            "correct_answer": "B",
        }]
        result = import_questions(db_session, qs2, source="test", skip_existing=False)
        assert result["updated"] == 1

        q = db_session.query(Question).filter_by(external_id="upd-001").first()
        assert q.stem == "新题干"
        assert q.difficulty == 4
        assert q.domain == 2

    def test_import_invalid_question(self, db_session):
        """无效题目跳过并记录错误"""
        qs = [
            {"domain": 1, "stem": "缺答案", "options": {"A": "x"}},  # 缺 correct_answer
            {"id": "valid-001", "domain": 1, "difficulty": 2, "question_type": "single",
             "stem": "有效题", "options": {"A": "对"}, "correct_answer": "A"},
        ]
        result = import_questions(db_session, qs, source="test")
        assert result["added"] == 1
        assert len(result["errors"]) == 1

    def test_yaml_file_import(self, db_session, tmp_path):
        """从 YAML 文件导入"""
        yaml_content = """
questions:
  - id: yaml-001
    domain: 3
    difficulty: 3
    question_type: single
    stem: YAML导入测试
    options:
      A: 选项A
      B: 选项B
      C: 选项C
      D: 选项D
    correct_answer: C
    explanation: YAML解析正确
    tags: ["YAML", "导入测试"]
    source: yaml-test
        """
        yaml_file = tmp_path / "test_questions.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        result = import_from_file(db_session, yaml_file, source="yaml-test")
        assert result["added"] == 1

        q = db_session.query(Question).filter_by(external_id="yaml-001").first()
        assert q is not None
        assert q.domain == 3
        assert q.stem == "YAML导入测试"
        assert len(q.tags) == 2

    def test_json_file_import(self, db_session, tmp_path):
        """从 JSON 文件导入"""
        data = [{
            "id": "json-001",
            "domain": 5,
            "difficulty": 2,
            "question_type": "single",
            "question": "JSON导入测试",
            "options": {"A": "对", "B": "错"},
            "answer": "A",
            "explanation": "JSON兼容格式",
            "tags": ["JSON"],
        }]
        json_file = tmp_path / "test.json"
        json_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        result = import_from_file(db_session, json_file, source="json-test")
        assert result["added"] == 1

        q = db_session.query(Question).filter_by(external_id="json-001").first()
        assert q is not None
        assert q.stem == "JSON导入测试"  # question → stem 映射
        assert q.correct_answer == "A"  # answer → correct_answer 映射

    def test_field_aliases(self, db_session):
        """字段别名兼容测试"""
        # 用中文命名字段
        qs = [{
            "id": "alias-001",
            "领域": 4,
            "难度": 3,
            "题型": "single",
            "题干": "中文命名字段测试",
            "选项": {"A": "选项一", "B": "选项二"},
            "正确答案": "B",
            "解析": "字段别名映射正确",
            "知识点": ["别名", "中文"],
        }]
        result = import_questions(db_session, qs, source="test")
        assert result["added"] == 1

        q = db_session.query(Question).filter_by(external_id="alias-001").first()
        assert q is not None
        assert q.domain == 4
        assert q.difficulty == 3
        assert q.stem == "中文命名字段测试"
        assert q.correct_answer == "B"
        assert q.tags == ["别名", "中文"]
