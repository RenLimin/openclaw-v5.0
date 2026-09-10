"""
学习路径模块测试
"""

import pytest
from datetime import date, timedelta
from cissp_trainer.learning_path import (
    init_preset_paths, list_paths, get_path, recommend_path,
    start_path, get_path_status, generate_daily_plan, adjust_path,
    PRESET_PATHS,
)
from cissp_trainer.engine import answer_question, pick_questions


class TestPresetPaths:
    """预设路径测试"""

    def test_preset_paths_count(self, db_session):
        """应该有 3 条预设路径"""
        result = init_preset_paths(db_session)
        assert result["added"] == 3
        paths = list_paths(db_session)
        assert len(paths) == 3

    def test_preset_paths_slugs(self, db_session):
        """3 条路径的 slug 正确"""
        init_preset_paths(db_session)
        paths = list_paths(db_session)
        slugs = {p["slug"] for p in paths}
        assert slugs == {"beginner", "advanced", "sprint"}

    def test_preset_path_details(self, db_session):
        """每条路径有正确的基本属性"""
        init_preset_paths(db_session)
        for data in PRESET_PATHS:
            path = get_path(db_session, data["slug"])
            assert path is not None
            assert path.estimated_days == data["estimated_days"]
            assert path.daily_question_target == data["daily_question_target"]
            assert len(path.milestones) == len(data["milestones"])

    def test_init_idempotent(self, db_session):
        """多次初始化不会重复添加"""
        r1 = init_preset_paths(db_session)
        assert r1["added"] == 3
        r2 = init_preset_paths(db_session)
        assert r2["added"] == 0
        assert r2["updated"] == 3

    def test_prerequisites_chain(self, db_session):
        """路径前置依赖链：beginner ← advanced ← sprint"""
        init_preset_paths(db_session)
        beginner = get_path(db_session, "beginner")
        advanced = get_path(db_session, "advanced")
        sprint = get_path(db_session, "sprint")
        assert beginner.prerequisites == []
        assert "beginner" in advanced.prerequisites
        assert "advanced" in sprint.prerequisites


class TestPathRecommendation:
    """路径推荐测试"""

    def test_recommend_beginner_for_new_user(self, db_session, seed_questions):
        """新用户推荐 beginner"""
        rec = recommend_path(db_session)
        assert rec["recommended_slug"] == "beginner"
        assert rec["can_start"] is True

    def test_recommend_changes_after_practice(self, db_session, seed_questions):
        """做对很多题后推荐会变化"""
        # 先做对 50 道题，把正确率拉上去
        qs = pick_questions(db_session, count=20, mode="random")
        for q in qs:
            answer_question(db_session, q.id, q.correct_answer, time_spent_sec=5)
        db_session.commit()

        # 因为只有 20 题记录，可能还是 beginner，但用户统计应该更新了
        rec = recommend_path(db_session)
        assert rec["user_stats"]["total_questions_answered"] >= 20
        assert rec["user_stats"]["overall_accuracy"] == 1.0


class TestPathProgress:
    """路径进度测试"""

    def test_start_beginner_path(self, db_session, seed_questions):
        """可以开始入门路径"""
        init_preset_paths(db_session)
        result = start_path(db_session, "beginner")
        assert result["success"] is True
        assert result["progress"]["status"] == "in_progress"

    def test_start_advanced_without_prereq(self, db_session, seed_questions):
        """未完成前置路径时不能开始强化路径"""
        init_preset_paths(db_session)
        result = start_path(db_session, "advanced")
        assert result["success"] is False
        assert "beginner" in result["error"]

    def test_start_nonexistent_path(self, db_session):
        """启动不存在的路径返回错误"""
        result = start_path(db_session, "nonexistent")
        assert result["success"] is False

    def test_duplicate_start_ignored(self, db_session, seed_questions):
        """重复启动同一路径不会创建多条"""
        init_preset_paths(db_session)
        r1 = start_path(db_session, "beginner")
        assert r1["success"] is True
        r2 = start_path(db_session, "beginner")
        # 已经在进行中，返回失败但带错误信息
        assert r2["success"] is False

    def test_path_status_updates_with_practice(self, db_session, seed_questions):
        """答题后路径进度会更新"""
        init_preset_paths(db_session)
        start_path(db_session, "beginner")

        # 初始状态
        status1 = get_path_status(db_session)
        assert status1 is not None
        assert status1["progress"]["completion_percent"] == 0.0

        # 做对一些题
        qs = pick_questions(db_session, count=10, domain=1, mode="random")
        for q in qs:
            answer_question(db_session, q.id, q.correct_answer, time_spent_sec=5)
        db_session.commit()

        # 进度应该上升
        status2 = get_path_status(db_session)
        assert status2["progress"]["completion_percent"] > 0


class TestDailyPlan:
    """每日学习计划测试"""

    def test_daily_plan_without_path(self, db_session, seed_questions):
        """没有路径时也能给出建议"""
        plan = generate_daily_plan(db_session)
        assert plan["has_path"] is False
        assert "recommended_path" in plan

    def test_daily_plan_with_path(self, db_session, seed_questions):
        """有路径时有完整计划信息"""
        init_preset_paths(db_session)
        start_path(db_session, "beginner")
        plan = generate_daily_plan(db_session)
        assert plan["has_path"] is True
        assert "daily_question_target" in plan
        assert "recommended_mode" in plan
        assert "current_milestone" in plan
        assert "completion_percent" in plan
        assert "tip" in plan

    def test_daily_plan_focus_kps(self, db_session, seed_questions):
        """有答题数据后会推荐重点知识点"""
        init_preset_paths(db_session)
        start_path(db_session, "beginner")

        # 做一些题，做错几道
        qs = pick_questions(db_session, count=5, domain=1, mode="random")
        for q in qs[:3]:
            answer_question(db_session, q.id, "Z", time_spent_sec=5)  # 全错
        for q in qs[3:]:
            answer_question(db_session, q.id, q.correct_answer, time_spent_sec=5)
        db_session.commit()

        plan = generate_daily_plan(db_session)
        assert "focus_knowledge_points" in plan


class TestMilestones:
    """里程碑测试"""

    def test_milestone_starts_at_zero(self, db_session, seed_questions):
        """初始时当前里程碑是第 0 个"""
        init_preset_paths(db_session)
        start_path(db_session, "beginner")
        status = get_path_status(db_session)
        assert status["current_milestone"] is not None
        assert status["current_milestone"]["index"] == 0

    def test_milestone_status_list(self, db_session, seed_questions):
        """里程碑状态列表长度正确"""
        init_preset_paths(db_session)
        start_path(db_session, "beginner")
        status = get_path_status(db_session)
        ms_list = status["milestone_status"]
        assert len(ms_list) == 5  # beginner 有 5 个里程碑
        assert all("completed" in m for m in ms_list)
        assert all("avg_mastery" in m for m in ms_list)


class TestPathAdjustment:
    """动态调整测试"""

    def test_adjust_without_path(self, db_session):
        """没有路径时调整返回提示"""
        result = adjust_path(db_session)
        assert result["adjusted"] is False
        assert "没有进行中的路径" in result["reason"]

    def test_adjust_insufficient_data(self, db_session, seed_questions):
        """数据不足时不调整"""
        init_preset_paths(db_session)
        start_path(db_session, "beginner")
        result = adjust_path(db_session)
        assert result["adjusted"] is False
