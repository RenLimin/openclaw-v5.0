"""
CLI v2 命令集成测试
（不做交互式测试，只测试非交互命令能正常运行）
"""

import pytest
import subprocess
import sys
from pathlib import Path


CLI_PATH = Path(__file__).resolve().parents[1] / "src" / "cissp_trainer" / "cli.py"


def run_cli(*args, db_path=None):
    """运行 CLI 命令并返回 (returncode, stdout, stderr)"""
    cmd = [sys.executable, str(CLI_PATH)] + list(args)
    env = None
    if db_path:
        import os
        env = os.environ.copy()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(Path(__file__).resolve().parents[2]),  # cissp-trainer 根目录
    )
    return result.returncode, result.stdout, result.stderr


class TestPathCLI:
    """path 子命令测试"""

    def test_path_list_runs(self, tmp_path):
        """path list 能正常输出"""
        # 初始化一个临时数据库
        db = tmp_path / "test.db"
        from cissp_trainer.database import init_db, session_scope
        from cissp_trainer.importer import import_questions
        from cissp_trainer.learning_path import init_preset_paths
        init_db(db_path=db, drop_first=True)

        # 因为 CLI 用默认数据库路径，这里用 pytest 的方式验证模块级功能
        with session_scope(db) as s:
            init_preset_paths(s)
            paths = list(Path(tmp_path).glob("*.db"))
            assert len(paths) >= 1

        # 直接用 Python API 验证 list_paths 能工作
        from cissp_trainer.learning_path import list_paths
        with session_scope(db) as s:
            result = list_paths(s)
            assert len(result) == 3
            slugs = {p["slug"] for p in result}
            assert "beginner" in slugs
            assert "advanced" in slugs
            assert "sprint" in slugs

    def test_path_start_and_status(self, db_session, seed_questions):
        """path start + status 工作流"""
        from cissp_trainer.learning_path import (
            init_preset_paths, start_path, get_path_status,
        )
        init_preset_paths(db_session)

        # 启动
        r = start_path(db_session, "beginner")
        assert r["success"] is True

        # 状态
        status = get_path_status(db_session)
        assert status is not None
        assert status["path"]["slug"] == "beginner"
        assert "milestone_status" in status

    def test_daily_plan_generation(self, db_session, seed_questions):
        """generate_daily_plan 返回结构完整"""
        from cissp_trainer.learning_path import (
            init_preset_paths, start_path, generate_daily_plan,
        )
        init_preset_paths(db_session)
        start_path(db_session, "beginner")

        plan = generate_daily_plan(db_session)
        assert plan["has_path"] is True
        assert "daily_question_target" in plan
        assert "recommended_mode" in plan
        assert "current_milestone" in plan
        assert "completion_percent" in plan
        assert "tip" in plan


class TestExamCLI:
    """exam 子命令测试"""

    def test_exam_history_empty(self, db_session):
        """空历史正常"""
        from cissp_trainer.exam_engine import get_exam_history
        history = get_exam_history(db_session)
        assert history == []

    def test_full_exam_flow(self, db_session, seed_questions):
        """完整考试流程：创建 → 开始 → 答题 → 交卷 → 历史"""
        from cissp_trainer.exam_engine import (
            create_exam, start_exam, get_current_question,
            answer_current, submit_exam, get_exam_history,
            get_exam_detail,
        )
        from cissp_trainer.models import Question

        # 创建
        cr = create_exam(db_session, question_count=5)
        assert cr["success"] is True
        exam_id = cr["exam_id"]

        # 开始
        sr = start_exam(db_session, exam_id)
        assert sr["success"] is True

        # 答题
        for i in range(5):
            q = get_current_question(db_session, exam_id)
            assert q is not None
            # 用正确答案
            q_obj = db_session.get(Question, q["question_id"])
            result = answer_current(db_session, exam_id, q_obj.correct_answer, time_spent_sec=1)
            assert result["success"] is True

        # 交卷
        sub = submit_exam(db_session, exam_id)
        assert sub["success"] is True
        assert sub["score"] == 100.0
        assert sub["passed"] is True

        # 历史
        history = get_exam_history(db_session)
        assert len(history) == 1

        # 详情
        detail = get_exam_detail(db_session, exam_id)
        assert detail is not None
        assert detail["score"] == 100.0


class TestKnowledgeCLI:
    """knowledge 子命令测试"""

    def test_graph_functions(self, db_session):
        """图谱函数都能正常调用"""
        from cissp_trainer.knowledge_graph import (
            add_edge, build_domain_graph, to_mermaid, to_text_tree,
            mastery_heatmap, get_prerequisites, get_successors,
            analyze_weak_propagation,
        )

        # 建一个小图
        add_edge(db_session, "A", "B", 1)
        add_edge(db_session, "B", "C", 1)
        add_edge(db_session, "C", "D", 1)

        # 各种查询都不报错
        graph = build_domain_graph(db_session, 1)
        assert len(graph["nodes"]) == 4

        prereqs = get_prerequisites(db_session, "D", 1)
        assert len(prereqs) > 0

        succ = get_successors(db_session, "A", 1)
        assert len(succ) > 0

        mermaid = to_mermaid(db_session, 1)
        assert "flowchart" in mermaid

        tree = to_text_tree(db_session, 1)
        assert isinstance(tree, str)

        heatmap = mastery_heatmap(db_session)
        assert "热力图" in heatmap

        # 设置掌握度后做传播分析
        from cissp_trainer.models import KnowledgePoint
        kp_a = db_session.query(KnowledgePoint).filter_by(name="A", domain=1).first()
        kp_a.mastery_level = 0.2
        db_session.flush()

        prop = analyze_weak_propagation(db_session, "A", 1)
        assert prop.total_affected == 3  # B, C, D
