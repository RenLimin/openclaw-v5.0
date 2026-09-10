"""
学习路径规划引擎

功能：
  - 预设路径管理（入门/强化/冲刺）
  - 路径推荐（根据用户当前水平）
  - 每日学习计划生成
  - 进度追踪 + 里程碑解锁
  - 动态调整（根据答题情况）
"""

from __future__ import annotations

from datetime import date, timedelta
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import Integer
from sqlalchemy.orm import Session

from .models import (
    LearningPath, UserPathProgress, KnowledgePoint,
    DOMAIN_NAMES, Question, StudyRecord,
)
from .engine import pick_questions, get_domain_stats, get_weak_knowledge_points


# ── 预设路径定义 ───────────────────────────────────────────

PRESET_PATHS = [
    {
        "name": "CISSP 入门路径",
        "slug": "beginner",
        "description": "零基础入门，全面覆盖 8 大领域基础概念，建立知识框架",
        "goal": "掌握 CISSP 8 大领域核心概念，每领域正确率达到 60%",
        "estimated_days": 30,
        "daily_question_target": 10,
        "difficulty_min": 1,
        "difficulty_max": 3,
        "prerequisites": [],
        "milestones": [
            {"name": "安全基础入门", "domains": [1, 2], "mastery_threshold": 0.5,
             "description": "掌握安全与风险管理、资产安全基础"},
            {"name": "技术核心入门", "domains": [3, 4], "mastery_threshold": 0.5,
             "description": "掌握安全架构、网络安全基础"},
            {"name": "身份与运营入门", "domains": [5, 7], "mastery_threshold": 0.5,
             "description": "掌握 IAM、安全运营基础"},
            {"name": "测试与开发入门", "domains": [6, 8], "mastery_threshold": 0.5,
             "description": "掌握安全测试、软件开发安全基础"},
            {"name": "入门完成", "domains": list(range(1, 9)), "mastery_threshold": 0.6,
             "description": "全部 8 领域达到 60% 正确率"},
        ],
        "knowledge_point_sequence": [],  # 由引擎根据题库自动生成
    },
    {
        "name": "CISSP 强化路径",
        "slug": "advanced",
        "description": "重点领域深度学习 + 错题强化，冲刺高分",
        "goal": "8 大领域全面达到 80% 正确率，薄弱点全部消除",
        "estimated_days": 60,
        "daily_question_target": 20,
        "difficulty_min": 2,
        "difficulty_max": 5,
        "prerequisites": ["beginner"],
        "milestones": [
            {"name": "风险管理精通", "domains": [1], "mastery_threshold": 0.8,
             "description": "域1 达到 80% 掌握度"},
            {"name": "架构与网络精通", "domains": [3, 4], "mastery_threshold": 0.8,
             "description": "域3、域4 达到 80% 掌握度"},
            {"name": "身份与运营精通", "domains": [5, 7], "mastery_threshold": 0.8,
             "description": "域5、域7 达到 80% 掌握度"},
            {"name": "测试与开发精通", "domains": [6, 8], "mastery_threshold": 0.8,
             "description": "域6、域8 达到 80% 掌握度"},
            {"name": "全面精通", "domains": list(range(1, 9)), "mastery_threshold": 0.8,
             "description": "全部 8 领域达到 80% 掌握度"},
        ],
        "knowledge_point_sequence": [],
    },
    {
        "name": "CISSP 冲刺路径",
        "slug": "sprint",
        "description": "考前 14 天冲刺，模拟考试 + 薄弱点突击",
        "goal": "模拟考试稳定通过 70 分，消除所有薄弱知识点",
        "estimated_days": 14,
        "daily_question_target": 50,
        "difficulty_min": 3,
        "difficulty_max": 5,
        "prerequisites": ["advanced"],
        "milestones": [
            {"name": "首次模拟考", "domains": list(range(1, 9)), "mastery_threshold": 0.6,
             "description": "完成第一次完整模拟考试，达到 60 分"},
            {"name": "薄弱点扫荡", "domains": list(range(1, 9)), "mastery_threshold": 0.7,
             "description": "所有薄弱知识点掌握度提升至 70%"},
            {"name": "模拟考通关", "domains": list(range(1, 9)), "mastery_threshold": 0.7,
             "description": "模拟考试连续 2 次达到 70 分以上"},
            {"name": "冲刺完成", "domains": list(range(1, 9)), "mastery_threshold": 0.75,
             "description": "平均正确率 75%+，准备上考场"},
        ],
        "knowledge_point_sequence": [],
    },
]


# ── 路径管理 ──────────────────────────────────────────────

def init_preset_paths(session: Session) -> dict:
    """初始化预设路径（幂等：已存在则跳过）"""
    added = 0
    updated = 0
    skipped = 0

    for data in PRESET_PATHS:
        existing = session.query(LearningPath).filter_by(slug=data["slug"]).first()
        if existing:
            # 更新关键字段
            existing.name = data["name"]
            existing.description = data["description"]
            existing.goal = data["goal"]
            existing.estimated_days = data["estimated_days"]
            existing.daily_question_target = data["daily_question_target"]
            existing.difficulty_min = data["difficulty_min"]
            existing.difficulty_max = data["difficulty_max"]
            existing.prerequisites = data["prerequisites"]
            existing.milestones = data["milestones"]
            existing.knowledge_point_sequence = data["knowledge_point_sequence"]
            updated += 1
        else:
            lp = LearningPath(
                name=data["name"],
                slug=data["slug"],
                description=data["description"],
                goal=data["goal"],
                estimated_days=data["estimated_days"],
                daily_question_target=data["daily_question_target"],
                difficulty_min=data["difficulty_min"],
                difficulty_max=data["difficulty_max"],
                prerequisites=data["prerequisites"],
                milestones=data["milestones"],
                knowledge_point_sequence=data["knowledge_point_sequence"],
            )
            session.add(lp)
            added += 1

    session.flush()
    return {"added": added, "updated": updated, "skipped": skipped}


def list_paths(session: Session, active_only: bool = True) -> list[dict]:
    """列出所有可用学习路径"""
    query = session.query(LearningPath)
    if active_only:
        query = query.filter(LearningPath.is_active == True)
    paths = query.order_by(LearningPath.id.asc()).all()

    result = []
    for p in paths:
        result.append({
            "id": p.id,
            "name": p.name,
            "slug": p.slug,
            "description": p.description,
            "goal": p.goal,
            "estimated_days": p.estimated_days,
            "daily_question_target": p.daily_question_target,
            "difficulty_range": f"{p.difficulty_min}-{p.difficulty_max}",
            "milestone_count": len(p.milestones),
            "prerequisites": p.prerequisites,
        })
    return result


def get_path(session: Session, slug_or_id: str | int) -> LearningPath | None:
    """根据 slug 或 id 获取路径"""
    if isinstance(slug_or_id, int) or (isinstance(slug_or_id, str) and slug_or_id.isdigit()):
        return session.get(LearningPath, int(slug_or_id))
    return session.query(LearningPath).filter_by(slug=slug_or_id).first()


# ── 路径推荐 ──────────────────────────────────────────────

def recommend_path(session: Session, user_id: str = "default") -> dict:
    """
    根据用户当前水平推荐学习路径

    规则：
      - 总答题 < 50 题 → beginner
      - 正确率 < 60% → beginner
      - 正确率 60-80% → advanced
      - 正确率 > 80% 且 答题 > 200 → sprint
    """
    # 统计用户水平
    total_records = (
        session.query(StudyRecord)
        .filter(StudyRecord.study_date != None)  # 有答题记录就行
        .count()
    )
    total_correct = (
        session.query(StudyRecord)
        .filter(StudyRecord.is_correct == True)
        .count()
    )
    accuracy = total_correct / total_records if total_records > 0 else 0.0

    # 查已有路径进度
    progresses = (
        session.query(UserPathProgress)
        .filter_by(user_id=user_id)
        .all()
    )
    completed_slugs = set()
    for up in progresses:
        if up.status == "completed":
            lp = session.get(LearningPath, up.path_id)
            if lp:
                completed_slugs.add(lp.slug)

    # 推荐逻辑
    if total_records < 50 or accuracy < 0.6:
        recommended_slug = "beginner"
        reason = "答题量较少或正确率较低，建议从入门路径开始"
    elif accuracy < 0.8 or total_records < 200:
        recommended_slug = "advanced"
        reason = "已有一定基础，建议进入强化路径深度学习"
    else:
        recommended_slug = "sprint"
        reason = "基础扎实，建议进入冲刺路径考前突击"

    # 检查前置条件
    path = session.query(LearningPath).filter_by(slug=recommended_slug).first()
    can_start = True
    missing_prereqs = []
    if path:
        for pre in path.prerequisites:
            if pre not in completed_slugs:
                can_start = False
                missing_prereqs.append(pre)

    return {
        "recommended_slug": recommended_slug,
        "reason": reason,
        "can_start": can_start,
        "missing_prerequisites": missing_prereqs,
        "user_stats": {
            "total_questions_answered": total_records,
            "overall_accuracy": round(accuracy, 4),
            "completed_paths": list(completed_slugs),
        },
    }


# ── 启动与进度 ────────────────────────────────────────────

def start_path(session: Session, slug: str, user_id: str = "default") -> dict:
    """开始一条学习路径"""
    path = session.query(LearningPath).filter_by(slug=slug).first()
    if not path:
        return {"success": False, "error": f"路径不存在: {slug}"}

    # 检查是否已有进度
    existing = (
        session.query(UserPathProgress)
        .filter_by(user_id=user_id, path_id=path.id)
        .first()
    )
    if existing and existing.status == "completed":
        return {"success": False, "error": "该路径已完成，如需重新开始请先重置"}
    if existing and existing.status == "in_progress":
        return {"success": False, "error": "该路径已在进行中",
                "progress": _progress_to_dict(existing, path)}

    # 检查前置条件
    for pre_slug in path.prerequisites:
        pre_path = session.query(LearningPath).filter_by(slug=pre_slug).first()
        if pre_path:
            pre_progress = (
                session.query(UserPathProgress)
                .filter_by(user_id=user_id, path_id=pre_path.id)
                .first()
            )
            if not pre_progress or pre_progress.status != "completed":
                return {
                    "success": False,
                    "error": f"需要先完成前置路径: {pre_slug}",
                }

    today = date.today()
    expected_end = today + timedelta(days=path.estimated_days)

    if existing:
        # 重新激活
        existing.status = "in_progress"
        existing.updated_at = None
        progress = existing
    else:
        progress = UserPathProgress(
            path_id=path.id,
            user_id=user_id,
            status="in_progress",
            start_date=today,
            expected_end_date=expected_end,
        )
        session.add(progress)

    session.flush()
    return {"success": True, "path": _path_to_dict(path),
            "progress": _progress_to_dict(progress, path)}


def get_path_status(session: Session, user_id: str = "default") -> dict | None:
    """获取当前进行中的路径状态"""
    progress = (
        session.query(UserPathProgress)
        .filter_by(user_id=user_id, status="in_progress")
        .order_by(UserPathProgress.created_at.desc())
        .first()
    )
    if not progress:
        return None

    path = session.get(LearningPath, progress.path_id)
    if not path:
        return None

    # 更新实时进度
    _update_progress(session, progress, path)

    return {
        "path": _path_to_dict(path),
        "progress": _progress_to_dict(progress, path),
        "current_milestone": _get_current_milestone(progress, path),
        "milestone_status": _get_milestone_status(session, progress, path),
    }


def _update_progress(session: Session, progress: UserPathProgress, path: LearningPath):
    """更新用户路径进度（实时计算）"""
    # 计算各领域掌握度
    domain_stats = get_domain_stats(session)
    domain_mastery = {d["domain"]: d["accuracy"] for d in domain_stats}

    # 总体完成度：各领域掌握度的平均值 / 目标掌握度
    milestones = path.milestones or []
    if milestones:
        # 以最后一个里程碑的阈值作为最终目标
        final_threshold = milestones[-1].get("mastery_threshold", 0.8)
        avg_mastery = sum(domain_mastery.values()) / len(domain_mastery) if domain_mastery else 0
        progress.completion_percent = min(1.0, avg_mastery / final_threshold) * 100
    else:
        progress.completion_percent = 0.0

    # 更新当前里程碑
    for i, ms in enumerate(milestones):
        ms_domains = ms.get("domains", [])
        threshold = ms.get("mastery_threshold", 0.6)
        if ms_domains:
            domain_vals = [domain_mastery.get(d, 0.0) for d in ms_domains]
            ms_avg = sum(domain_vals) / len(domain_vals) if domain_vals else 0
        else:
            ms_avg = 0.0

        if ms_avg < threshold:
            progress.current_milestone_index = i
            break
    else:
        # 全部完成
        progress.current_milestone_index = len(milestones)
        progress.status = "completed"
        progress.completed_date = date.today()

    # 统计答题数
    total_records = session.query(StudyRecord).count()
    progress.total_questions_done = total_records
    correct = session.query(StudyRecord).filter(StudyRecord.is_correct == True).count()
    progress.total_correct = correct

    session.flush()


def _get_current_milestone(progress: UserPathProgress, path: LearningPath) -> dict | None:
    milestones = path.milestones or []
    idx = progress.current_milestone_index
    if idx < len(milestones):
        ms = milestones[idx]
        return {
            "index": idx,
            "name": ms.get("name", ""),
            "description": ms.get("description", ""),
            "domains": ms.get("domains", []),
            "threshold": ms.get("mastery_threshold", 0.0),
        }
    return None


def _get_milestone_status(session: Session, progress: UserPathProgress,
                          path: LearningPath) -> list[dict]:
    """获取所有里程碑的完成状态"""
    from .engine import get_domain_stats
    domain_stats = get_domain_stats(session)
    domain_mastery = {d["domain"]: d["accuracy"] for d in domain_stats}

    milestones = path.milestones or []
    result = []
    for i, ms in enumerate(milestones):
        ms_domains = ms.get("domains", [])
        threshold = ms.get("mastery_threshold", 0.6)
        if ms_domains:
            vals = [domain_mastery.get(d, 0.0) for d in ms_domains]
            avg = sum(vals) / len(vals) if vals else 0
            min_val = min(vals) if vals else 0
        else:
            avg = 0.0
            min_val = 0.0

        is_completed = i < progress.current_milestone_index or avg >= threshold
        result.append({
            "index": i,
            "name": ms.get("name", ""),
            "completed": is_completed,
            "avg_mastery": round(avg, 4),
            "min_mastery": round(min_val, 4),
            "threshold": threshold,
            "domains": ms.get("domains", []),
        })
    return result


# ── 每日计划 ──────────────────────────────────────────────

def generate_daily_plan(session: Session, user_id: str = "default",
                        plan_date: date | None = None) -> dict:
    """
    生成今日学习计划

    计划内容：
      - 今日目标题数
      - 推荐学习的知识点
      - 推荐练习模式
      - 今日里程碑进度
    """
    plan_date = plan_date or date.today()

    # 获取当前路径
    progress = (
        session.query(UserPathProgress)
        .filter_by(user_id=user_id, status="in_progress")
        .order_by(UserPathProgress.created_at.desc())
        .first()
    )

    if not progress:
        # 没有进行中的路径，给出通用建议
        return {
            "date": plan_date.isoformat(),
            "has_path": False,
            "suggestion": "暂无进行中的学习路径，建议先选择一条路径开始学习",
            "recommended_path": recommend_path(session, user_id),
        }

    path = session.get(LearningPath, progress.path_id)
    if not path:
        return {"date": plan_date.isoformat(), "has_path": False,
                "suggestion": "路径数据异常"}

    _update_progress(session, progress, path)

    # 当前里程碑
    milestones = path.milestones or []
    current_ms = None
    if progress.current_milestone_index < len(milestones):
        current_ms = milestones[progress.current_milestone_index]

    # 今日题数目标
    daily_target = path.daily_question_target

    # 薄弱知识点（优先学习）
    weak_domains = current_ms.get("domains") if current_ms else None
    weak_kps = get_weak_knowledge_points(session, top_n=10,
                                         domain=weak_domains[0] if weak_domains and len(weak_domains) == 1 else None)

    # 推荐模式
    if progress.completion_percent < 30:
        mode = "random"
        mode_desc = "全面学习"
    elif progress.completion_percent < 70:
        mode = "weak"
        mode_desc = "薄弱点强化"
    else:
        mode = "review"
        mode_desc = "间隔复习"

    # 预计还需天数
    if progress.completion_percent > 0:
        days_passed = (plan_date - progress.start_date).days + 1
        estimated_total = int(days_passed / progress.completion_percent * 100)
        days_remaining = max(0, estimated_total - days_passed)
    else:
        days_remaining = path.estimated_days

    return {
        "date": plan_date.isoformat(),
        "has_path": True,
        "path_name": path.name,
        "path_slug": path.slug,
        "daily_question_target": daily_target,
        "recommended_mode": mode,
        "recommended_mode_desc": mode_desc,
        "current_milestone": current_ms.get("name", "") if current_ms else "全部完成",
        "milestone_domains": current_ms.get("domains", []) if current_ms else [],
        "focus_knowledge_points": [kp.name for kp in weak_kps[:5]],
        "completion_percent": round(progress.completion_percent, 1),
        "days_remaining_estimate": days_remaining,
        "streak_days": progress.streak_days,
        "tip": _get_daily_tip(progress, current_ms),
    }


def _get_daily_tip(progress: UserPathProgress, current_ms: dict | None) -> str:
    """生成今日学习建议"""
    pct = progress.completion_percent
    if pct < 20:
        return "学习初期，重点是建立知识框架。先快速过一遍所有领域的基础概念。"
    elif pct < 50:
        if current_ms:
            return f"当前阶段：{current_ms.get('name', '')}。集中攻克当前里程碑的领域知识点。"
        return "学习中期，开始关注薄弱知识点，针对性强化。"
    elif pct < 80:
        return "学习后期，多做模拟考试，熟悉考试节奏和题型分布。"
    else:
        return "即将完成！查漏补缺，确保所有领域都达到目标掌握度。"


# ── 动态调整 ──────────────────────────────────────────────

def adjust_path(session: Session, user_id: str = "default") -> dict:
    """
    根据答题情况动态调整路径

    调整规则：
      - 连续 3 天正确率 > 85% → 提升难度 / 增加每日题量
      - 连续 3 天正确率 < 50% → 降低难度 / 减少每日题量
      - 薄弱知识点集中在某领域 → 追加该领域专项练习
    """
    from datetime import timedelta
    from sqlalchemy import func

    progress = (
        session.query(UserPathProgress)
        .filter_by(user_id=user_id, status="in_progress")
        .first()
    )
    if not progress:
        return {"adjusted": False, "reason": "没有进行中的路径"}

    path = session.get(LearningPath, progress.path_id)
    if not path:
        return {"adjusted": False, "reason": "路径不存在"}

    # 最近 7 天数据
    today = date.today()
    start = today - timedelta(days=6)

    # 按天统计正确率
    daily_stats = (
        session.query(
            StudyRecord.study_date,
            func.count(StudyRecord.id).label("total"),
            func.sum(func.cast(StudyRecord.is_correct, Integer)).label("correct"),
        )
        .filter(StudyRecord.study_date >= start)
        .group_by(StudyRecord.study_date)
        .order_by(StudyRecord.study_date.desc())
        .limit(7)
        .all()
    )

    if len(daily_stats) < 3:
        return {"adjusted": False, "reason": "数据不足，需要至少 3 天答题记录"}

    # 最近 3 天的正确率
    recent_3 = daily_stats[:3]
    accs = [(r.correct or 0) / r.total for r in recent_3 if r.total > 0]

    if not accs:
        return {"adjusted": False, "reason": "近期答题数据不足"}

    avg_acc = sum(accs) / len(accs)

    adjustments = []
    current_daily = path.daily_question_target
    current_min = path.difficulty_min
    current_max = path.difficulty_max

    if all(a > 0.85 for a in accs):
        # 表现好：提升难度上限 + 增加题量
        if current_max < 5:
            path.difficulty_max = min(5, current_max + 1)
            adjustments.append(f"难度上限 {current_max} → {path.difficulty_max}")
        if current_daily < 50:
            path.daily_question_target = min(50, current_daily + 5)
            adjustments.append(f"每日题量 {current_daily} → {path.daily_question_target}")

    elif all(a < 0.5 for a in accs):
        # 表现差：降低难度 + 减少题量
        if current_min > 1:
            path.difficulty_min = max(1, current_min - 1)
            adjustments.append(f"难度下限 {current_min} → {path.difficulty_min}")
        if current_daily > 5:
            path.daily_question_target = max(5, current_daily - 3)
            adjustments.append(f"每日题量 {current_daily} → {path.daily_question_target}")

    # 薄弱领域检查
    from .engine import get_domain_stats
    ds = get_domain_stats(session)
    weak_domains = [d for d in ds if d["study_count"] >= 5 and d["accuracy"] < 0.5]
    if weak_domains:
        weak_names = [f"域{d['domain']}({d['domain_name']})" for d in weak_domains[:3]]
        adjustments.append(f"薄弱领域：{', '.join(weak_names)}，建议专项强化")

    session.flush()

    return {
        "adjusted": len(adjustments) > 0,
        "recent_accuracy": round(avg_acc, 4),
        "adjustments": adjustments,
    }


# ── 辅助函数 ──────────────────────────────────────────────

def _path_to_dict(path: LearningPath) -> dict:
    return {
        "id": path.id,
        "name": path.name,
        "slug": path.slug,
        "description": path.description,
        "goal": path.goal,
        "estimated_days": path.estimated_days,
        "daily_question_target": path.daily_question_target,
        "difficulty_min": path.difficulty_min,
        "difficulty_max": path.difficulty_max,
        "milestone_count": len(path.milestones),
    }


def _progress_to_dict(progress: UserPathProgress, path: LearningPath) -> dict:
    return {
        "status": progress.status,
        "completion_percent": round(progress.completion_percent, 1),
        "current_milestone_index": progress.current_milestone_index,
        "start_date": progress.start_date.isoformat() if progress.start_date else None,
        "expected_end_date": progress.expected_end_date.isoformat() if progress.expected_end_date else None,
        "total_questions_done": progress.total_questions_done,
        "streak_days": progress.streak_days,
        "path_name": path.name,
    }
