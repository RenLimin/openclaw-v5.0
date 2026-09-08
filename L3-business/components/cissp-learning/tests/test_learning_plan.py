"""学习计划测试。"""

from datetime import date, timedelta

from models.learning_plan import (
    LearningPlan,
    PlanStatus,
    PlanMilestone,
    PlanObjective,
)
from repositories.learning_plan_repo import LearningPlanRepository


class TestLearningPlanModel:
    def test_create_plan(self):
        plan = LearningPlan(
            plan_name="CISSP 备考计划",
            description="6个月通过 CISSP 认证",
            category="certification",
            certification="CISSP",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=180),
            owner_id="user-001",
            total_hours_planned=300.0,
            status=PlanStatus.DRAFT,
        )
        assert plan.plan_name == "CISSP 备考计划"
        assert plan.owner_id == "user-001"
        assert plan.status == PlanStatus.DRAFT
        assert plan.total_hours_planned == 300.0
        assert plan.total_hours_spent == 0.0
        assert plan.progress_percent == 0.0

    def test_status_transitions_valid(self):
        plan = LearningPlan(
            plan_name="测试计划",
            start_date=date.today(),
            owner_id="u1",
            status=PlanStatus.DRAFT,
        )
        # DRAFT → ACTIVE
        plan.start()
        assert plan.status == PlanStatus.ACTIVE
        # ACTIVE → PAUSED
        plan.pause()
        assert plan.status == PlanStatus.PAUSED
        # PAUSED → ACTIVE
        plan.resume()
        assert plan.status == PlanStatus.ACTIVE
        # ACTIVE → COMPLETED
        plan.complete()
        assert plan.status == PlanStatus.COMPLETED
        # COMPLETED → ARCHIVED
        plan.archive()
        assert plan.status == PlanStatus.ARCHIVED

    def test_status_transition_invalid(self):
        plan = LearningPlan(
            plan_name="测试计划",
            start_date=date.today(),
            owner_id="u1",
            status=PlanStatus.DRAFT,
        )
        import pytest
        with pytest.raises(ValueError, match="Invalid status transition"):
            plan.complete()  # DRAFT → COMPLETED 非法

    def test_cancel_from_draft(self):
        plan = LearningPlan(
            plan_name="测试计划",
            start_date=date.today(),
            owner_id="u1",
            status=PlanStatus.DRAFT,
        )
        plan.cancel()
        assert plan.status == PlanStatus.CANCELLED

    def test_days_elapsed_and_remaining(self):
        today = date.today()
        plan = LearningPlan(
            plan_name="测试计划",
            start_date=today - timedelta(days=10),
            end_date=today + timedelta(days=20),
            owner_id="u1",
        )
        assert plan.days_elapsed == 11  # 含今天
        assert plan.days_remaining == 20

    def test_progress_percent(self):
        plan = LearningPlan(
            plan_name="测试计划",
            start_date=date.today(),
            owner_id="u1",
            total_hours_planned=100.0,
            total_hours_spent=25.0,
        )
        assert plan.progress_percent == 25.0

    def test_progress_zero_hours_planned(self):
        plan = LearningPlan(
            plan_name="测试计划",
            start_date=date.today(),
            owner_id="u1",
        )
        assert plan.progress_percent == 0.0

    def test_add_milestone_and_objective(self):
        plan = LearningPlan(
            plan_name="测试计划",
            start_date=date.today(),
            owner_id="u1",
        )
        plan.add_milestone(PlanMilestone(
            title="完成第一域",
            target_date=date.today() + timedelta(days=30),
        ))
        plan.add_objective(PlanObjective(
            title="通过模拟考",
            description="模拟考分数 >= 70%",
        ))
        assert plan.total_milestones_count == 1
        assert plan.total_objectives_count == 1
        assert plan.achieved_milestones_count == 0
        assert plan.achieved_objectives_count == 0

    def test_add_milestone_auto_generates_id(self):
        plan = LearningPlan(
            plan_name="测试计划",
            start_date=date.today(),
            owner_id="u1",
        )
        plan.add_milestone(PlanMilestone(
            title="无ID里程碑",
            target_date=date.today(),
        ))
        assert plan.milestones[0].milestone_id != ""

    def test_add_hours(self):
        plan = LearningPlan(
            plan_name="测试计划",
            start_date=date.today(),
            owner_id="u1",
            total_hours_planned=100.0,
        )
        plan.add_hours(5.5)
        assert plan.total_hours_spent == 5.5
        plan.add_hours(2.0)
        assert plan.total_hours_spent == 7.5

        import pytest
        with pytest.raises(ValueError, match="non-negative"):
            plan.add_hours(-1.0)

    def test_get_milestone(self):
        plan = LearningPlan(
            plan_name="测试计划",
            start_date=date.today(),
            owner_id="u1",
        )
        plan.add_milestone(PlanMilestone(
            milestone_id="m1",
            title="里程碑1",
            target_date=date.today(),
        ))
        m = plan.get_milestone("m1")
        assert m is not None
        assert m.title == "里程碑1"
        assert plan.get_milestone("nonexist") is None


class TestLearningPlanRepository:
    def test_create_and_get(self):
        plan = LearningPlanRepository.create(
            plan_name="CISSP 备考",
            start_date=date.today(),
            owner_id="u1",
            category="certification",
            certification="CISSP",
        )
        fetched = LearningPlanRepository.get_by_id(plan.id)
        assert fetched is not None
        assert fetched.plan_name == "CISSP 备考"
        assert fetched.tenant_id == "tenant-a-001"

    def test_list_by_owner(self):
        LearningPlanRepository.create(
            plan_name="计划A", start_date=date.today(), owner_id="u1",
        )
        LearningPlanRepository.create(
            plan_name="计划B", start_date=date.today(), owner_id="u2",
        )
        LearningPlanRepository.create(
            plan_name="计划C", start_date=date.today(), owner_id="u1",
        )
        assert len(LearningPlanRepository.list_by_owner("u1")) == 2
        assert len(LearningPlanRepository.list_by_owner("u2")) == 1

    def test_list_active(self):
        today = date.today()
        LearningPlanRepository.create(
            plan_name="进行中",
            start_date=today - timedelta(days=5),
            end_date=today + timedelta(days=30),
            owner_id="u1",
            status=PlanStatus.ACTIVE,
        )
        LearningPlanRepository.create(
            plan_name="草稿",
            start_date=today,
            owner_id="u1",
            status=PlanStatus.DRAFT,
        )
        active = LearningPlanRepository.list_active("u1")
        assert len(active) == 1
        assert active[0].plan_name == "进行中"

    def test_status_transitions_via_repository(self):
        p = LearningPlanRepository.create(
            plan_name="状态测试",
            start_date=date.today(),
            owner_id="u1",
            status=PlanStatus.DRAFT,
        )
        p = LearningPlanRepository.start_plan(p.id)
        assert p.status == PlanStatus.ACTIVE

        p = LearningPlanRepository.pause_plan(p.id)
        assert p.status == PlanStatus.PAUSED

        p = LearningPlanRepository.resume_plan(p.id)
        assert p.status == PlanStatus.ACTIVE

        p = LearningPlanRepository.complete_plan(p.id)
        assert p.status == PlanStatus.COMPLETED

        p = LearningPlanRepository.archive_plan(p.id)
        assert p.status == PlanStatus.ARCHIVED

    def test_cancel_plan(self):
        p = LearningPlanRepository.create(
            plan_name="取消测试",
            start_date=date.today(),
            owner_id="u1",
            status=PlanStatus.DRAFT,
        )
        p = LearningPlanRepository.cancel_plan(p.id)
        assert p.status == PlanStatus.CANCELLED

    def test_current_plan(self):
        today = date.today()
        LearningPlanRepository.create(
            plan_name="当前CISSP计划",
            start_date=today,
            end_date=today + timedelta(days=90),
            owner_id="u1",
            category="certification",
            status=PlanStatus.ACTIVE,
        )
        current = LearningPlanRepository.current_plan("u1", "certification")
        assert current is not None
        assert current.plan_name == "当前CISSP计划"
        assert LearningPlanRepository.current_plan("u1", "language") is None
