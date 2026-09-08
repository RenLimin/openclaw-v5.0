"""健康计划模块测试。"""

from datetime import date, timedelta

from health_plan.models import (
    HealthPlan,
    PlanStatus,
    PlanType,
    PlanTask,
    TaskStatus,
    PlanMilestone,
)
from health_plan.repository import HealthPlanRepository


def test_create_plan_full():
    today = date.today()
    tasks = [
        PlanTask(
            task_id="t1",
            title="每日步行10000步",
            category="运动",
            frequency="daily",
            target_value=10000,
            target_unit="步",
            priority=2,
            status=TaskStatus.IN_PROGRESS,
            progress=50.0,
        ),
        PlanTask(
            task_id="t2",
            title="低盐饮食",
            category="饮食",
            frequency="daily",
            priority=1,
            status=TaskStatus.PENDING,
        ),
    ]
    milestones = [
        PlanMilestone(
            milestone_id="m1",
            title="第1周达标",
            target_date=today + timedelta(days=7),
            description="连续7天完成运动目标",
        ),
        PlanMilestone(
            milestone_id="m2",
            title="减重2kg",
            target_date=today + timedelta(days=30),
            description="体重从70kg降至68kg",
        ),
    ]
    plan = HealthPlanRepository.create(
        profile_id="P001",
        plan_name="3个月减重计划",
        plan_type=PlanType.WEIGHT_LOSS,
        start_date=today,
        end_date=today + timedelta(days=90),
        created_by="doctor",
        doctor_name="李医生",
        overall_goal="3个月减重5kg，BMI降至22",
        goals=["减重5kg", "体脂率下降3%", "腰围减少5cm"],
        status=PlanStatus.ACTIVE,
        tasks=tasks,
        milestones=milestones,
        baseline_metrics={"weight": 70.0, "bmi": 24.5, "body_fat": 22.0},
        target_metrics={"weight": 65.0, "bmi": 22.5, "body_fat": 19.0},
    )
    assert plan.plan_name == "3个月减重计划"
    assert plan.plan_type == PlanType.WEIGHT_LOSS
    assert plan.status == PlanStatus.ACTIVE
    assert plan.total_tasks_count == 2
    assert plan.completed_tasks_count == 0
    assert plan.achieved_milestones_count == 0
    assert plan.duration_days is None  # 未显式设
    assert plan.days_elapsed == 1


def test_overall_progress():
    plan = HealthPlan(
        profile_id="P001",
        plan_name="测试",
        plan_type=PlanType.CUSTOM,
        start_date=date.today(),
        tasks=[
            PlanTask(task_id="t1", title="a", progress=100.0, status=TaskStatus.COMPLETED),
            PlanTask(task_id="t2", title="b", progress=50.0, status=TaskStatus.IN_PROGRESS),
            PlanTask(task_id="t3", title="c", progress=0.0, status=TaskStatus.PENDING),
        ],
    )
    assert plan.overall_progress == 50.0  # (100+50+0)/3


def test_days_remaining():
    today = date.today()
    plan = HealthPlan(
        profile_id="P001",
        plan_name="测试",
        plan_type=PlanType.CUSTOM,
        start_date=today - timedelta(days=10),
        end_date=today + timedelta(days=20),
    )
    assert plan.days_remaining == 20
    assert plan.days_elapsed == 11  # 含今天


def test_update_task_progress():
    plan = HealthPlan(
        profile_id="P001",
        plan_name="测试",
        plan_type=PlanType.CUSTOM,
        start_date=date.today(),
    )
    task = PlanTask(task_id="t1", title="任务1")
    plan.add_task(task)
    assert plan.total_tasks_count == 1

    # 更新进度
    ok = plan.update_task_progress("t1", 75.0)
    assert ok is True
    t = plan.get_task("t1")
    assert t.progress == 75.0
    assert t.status == TaskStatus.IN_PROGRESS

    # 达到100%
    ok = plan.update_task_progress("t1", 100.0)
    assert ok is True
    t = plan.get_task("t1")
    assert t.status == TaskStatus.COMPLETED
    assert t.completion_date == date.today()

    # 不存在的任务
    ok = plan.update_task_progress("nonexist", 50)
    assert ok is False


def test_add_task_generates_id():
    plan = HealthPlan(
        profile_id="P001",
        plan_name="测试",
        plan_type=PlanType.CUSTOM,
        start_date=date.today(),
    )
    plan.add_task(PlanTask(title="自动生成ID的任务"))
    assert plan.tasks[0].task_id != ""


def test_repository_list_active():
    today = date.today()
    HealthPlanRepository.create(
        profile_id="P001",
        plan_name="进行中计划",
        plan_type=PlanType.FITNESS_IMPROVEMENT,
        start_date=today - timedelta(days=5),
        end_date=today + timedelta(days=25),
        status=PlanStatus.ACTIVE,
    )
    HealthPlanRepository.create(
        profile_id="P001",
        plan_name="草稿计划",
        plan_type=PlanType.CUSTOM,
        start_date=today,
        status=PlanStatus.DRAFT,
    )
    HealthPlanRepository.create(
        profile_id="P001",
        plan_name="已完成计划",
        plan_type=PlanType.WEIGHT_LOSS,
        start_date=today - timedelta(days=100),
        end_date=today - timedelta(days=10),
        status=PlanStatus.COMPLETED,
    )
    active = HealthPlanRepository.list_active("P001")
    assert len(active) == 1
    assert active[0].plan_name == "进行中计划"


def test_repository_current_plan():
    today = date.today()
    HealthPlanRepository.create(
        profile_id="P001",
        plan_name="当前减重计划",
        plan_type=PlanType.WEIGHT_LOSS,
        start_date=today,
        end_date=today + timedelta(days=90),
        status=PlanStatus.ACTIVE,
    )
    current = HealthPlanRepository.current_plan("P001", PlanType.WEIGHT_LOSS)
    assert current is not None
    assert current.plan_name == "当前减重计划"

    # 不存在的类型
    assert HealthPlanRepository.current_plan("P001", PlanType.BLOOD_SUGAR_CONTROL) is None


def test_repository_status_transitions():
    p = HealthPlanRepository.create(
        profile_id="P001",
        plan_name="状态测试",
        plan_type=PlanType.CUSTOM,
        start_date=date.today(),
        status=PlanStatus.DRAFT,
    )
    # 启动
    started = HealthPlanRepository.start_plan(p.id)
    assert started.status == PlanStatus.ACTIVE

    # 暂停
    paused = HealthPlanRepository.pause_plan(p.id)
    assert paused.status == PlanStatus.PAUSED

    # 完成
    done = HealthPlanRepository.complete_plan(p.id)
    assert done.status == PlanStatus.COMPLETED
