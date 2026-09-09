"""
CISSP 学习引擎核心

三大模块：
  - 出题模块 (pick_questions): 按领域/难度/模式抽题
  - 答题模块 (answer_question): 记录答题 + 更新 SM-2 + 更新掌握度
  - 统计模块 (get_stats): 总体/分域/薄弱知识点统计
"""

from __future__ import annotations

import random
from datetime import date, datetime
from collections import defaultdict
from typing import Literal

from sqlalchemy import func, select, and_, or_, Integer
from sqlalchemy.orm import Session

from .models import Question, StudyRecord, KnowledgePoint, DOMAIN_NAMES
from .spaced_repetition import sm2_update, due_priority


# ── 出题模块 ──────────────────────────────────────────────

PickMode = Literal["random", "review", "weak", "exam"]


def pick_questions(
    session: Session,
    count: int = 10,
    domain: int | None = None,
    difficulty: int | None = None,
    mode: PickMode = "random",
    weak_tags: list[str] | None = None,
) -> list[Question]:
    """
    智能出题

    参数：
      session: 数据库 session
      count: 题目数量
      domain: 按域筛选（1-8，None=全部）
      difficulty: 按难度筛选（1-5，None=全部）
      mode: 出题模式
        - random: 完全随机
        - review: 到期复习优先（间隔重复）
        - weak: 薄弱知识点优先
        - exam: 模拟考试（按域权重分布）
      weak_tags: 薄弱知识点标签列表（weak 模式下使用）

    返回：Question 列表
    """
    # 基础查询
    query = select(Question)
    filters = []
    if domain is not None:
        filters.append(Question.domain == domain)
    if difficulty is not None:
        filters.append(Question.difficulty == difficulty)
    if filters:
        query = query.where(and_(*filters))

    all_questions = list(session.scalars(query).all())

    if not all_questions:
        return []

    count = min(count, len(all_questions))

    if mode == "random":
        return random.sample(all_questions, count)

    elif mode == "review":
        # 到期复习优先：获取每题最新的 study_record
        return _pick_by_review_priority(session, all_questions, count)

    elif mode == "weak":
        # 薄弱知识点优先
        return _pick_by_weak_kp(session, all_questions, count, weak_tags)

    elif mode == "exam":
        # 模拟考试：按域权重分布
        return _pick_by_domain_weight(session, all_questions, count)

    else:
        return random.sample(all_questions, count)


def _pick_by_review_priority(
    session: Session, pool: list[Question], count: int
) -> list[Question]:
    """按到期复习优先级抽题"""
    today = date.today()
    q_with_priority = []

    for q in pool:
        # 取最新一条记录
        latest = (
            session.query(StudyRecord)
            .filter(StudyRecord.question_id == q.id)
            .order_by(StudyRecord.created_at.desc())
            .first()
        )
        if latest is None:
            # 从未做过，高优先级
            priority = 999.0
        else:
            priority = due_priority(latest.next_review_date, latest.efactor, today)
        q_with_priority.append((q, priority))

    # 按优先级降序，取前 N 个；优先级相同的打乱
    q_with_priority.sort(key=lambda x: (-x[1], random.random()))
    return [q for q, _ in q_with_priority[:count]]


def _pick_by_weak_kp(
    session: Session, pool: list[Question], count: int,
    weak_tags: list[str] | None = None,
) -> list[Question]:
    """按薄弱知识点优先级抽题"""
    # 如果没传 weak_tags，从知识库取最薄弱的 10 个
    if weak_tags is None:
        weak_kps = get_weak_knowledge_points(session, top_n=10)
        weak_tags = [kp.name for kp in weak_kps]

    weak_set = set(weak_tags)

    scored = []
    for q in pool:
        tags = q.tags or []
        # 命中薄弱知识点的数量
        hit_count = len(set(tags) & weak_set)
        # 正确率越低分越高
        if q.times_shown > 0:
            wrong_rate = 1 - q.times_correct / q.times_shown
        else:
            wrong_rate = 0.5  # 没做过的中等优先
        score = hit_count * 10 + wrong_rate * 5
        scored.append((q, score))

    scored.sort(key=lambda x: (-x[1], random.random()))
    return [q for q, _ in scored[:count]]


def _pick_by_domain_weight(
    session: Session, pool: list[Question], count: int
) -> list[Question]:
    """按域权重分布抽题（模拟考试）"""
    # CISSP 8 域大致权重（参考 (ISC)2 官方考试大纲权重）
    weights = {
        1: 15,  # 安全与风险管理
        2: 10,  # 资产安全
        3: 13,  # 安全架构与工程
        4: 13,  # 通信与网络安全
        5: 13,  # 身份与访问管理
        6: 12,  # 安全评估与测试
        7: 13,  # 安全运营
        8: 11,  # 软件开发安全
    }

    # 按域分组
    by_domain: dict[int, list[Question]] = defaultdict(list)
    for q in pool:
        by_domain[q.domain].append(q)

    total_weight = sum(w for d, w in weights.items() if by_domain.get(d))
    result = []
    remaining = count

    for domain_id in sorted(weights.keys(), key=lambda d: -weights[d]):
        if domain_id not in by_domain:
            continue
        domain_count = max(1, round(count * weights[domain_id] / total_weight))
        domain_count = min(domain_count, remaining, len(by_domain[domain_id]))
        result.extend(random.sample(by_domain[domain_id], domain_count))
        remaining -= domain_count
        if remaining <= 0:
            break

    # 不够的从剩余题补
    if remaining > 0:
        used_ids = {q.id for q in result}
        leftover = [q for q in pool if q.id not in used_ids]
        if leftover:
            result.extend(random.sample(leftover, min(remaining, len(leftover))))

    random.shuffle(result)
    return result


# ── 答题模块 ──────────────────────────────────────────────

def answer_question(
    session: Session,
    question_id: int,
    user_answer: str,
    time_spent_sec: int = 0,
    study_date: date | None = None,
) -> dict:
    """
    记录一次答题

    做的事：
      1. 校验答案正确性
      2. 写入 StudyRecord
      3. 更新 Question 统计字段
      4. 更新相关 KnowledgePoint 掌握度
      5. 计算 SM-2 下次复习时间

    返回：结果字典
    """
    study_date = study_date or date.today()
    q = session.get(Question, question_id)
    if q is None:
        raise ValueError(f"Question {question_id} not found")

    # 判断正确
    correct = _check_answer(q, user_answer)

    # 获取上一次记录（用于 SM-2 连续计算）
    last_record = (
        session.query(StudyRecord)
        .filter(StudyRecord.question_id == question_id)
        .order_by(StudyRecord.created_at.desc())
        .first()
    )

    if last_record:
        prev_ef = last_record.efactor
        prev_interval = last_record.interval
        prev_rep = last_record.repetition
    else:
        prev_ef = 2.5
        prev_interval = 0
        prev_rep = 0

    # SM-2 计算
    sr = sm2_update(
        is_correct=correct,
        current_efactor=prev_ef,
        current_interval=prev_interval,
        current_repetition=prev_rep,
        today=study_date,
        difficulty=q.difficulty,
        time_spent_sec=time_spent_sec,
    )

    # 写学习记录
    record = StudyRecord(
        question_id=question_id,
        study_date=study_date,
        user_answer=user_answer,
        is_correct=correct,
        time_spent_sec=time_spent_sec,
        quality=sr.quality,
        efactor=sr.efactor,
        interval=sr.interval,
        repetition=sr.repetition,
        next_review_date=sr.next_review_date,
    )
    session.add(record)

    # 更新题目统计
    q.times_shown += 1
    if correct:
        q.times_correct += 1

    # 更新知识点掌握度
    _update_knowledge_points(session, q, correct)

    session.flush()

    return {
        "question_id": question_id,
        "is_correct": correct,
        "correct_answer": q.correct_answer,
        "explanation": q.explanation,
        "quality": sr.quality,
        "efactor": sr.efactor,
        "next_review_date": sr.next_review_date.isoformat(),
        "interval_days": sr.interval,
    }


def _check_answer(q: Question, user_answer: str) -> bool:
    """校验答案正确性"""
    ua = user_answer.strip().upper()
    ca = q.correct_answer.strip().upper()

    if q.question_type == "single":
        return ua == ca

    elif q.question_type == "multiple":
        # 多选：排序后比较
        user_set = set(x.strip() for x in ua.split(",") if x.strip())
        correct_set = set(x.strip() for x in ca.split(",") if x.strip())
        return user_set == correct_set

    elif q.question_type == "truefalse":
        # 判断题：用户输入的是选项字母(A/B)，需要从 options 中取出实际值再比较
        # 同时兼容直接输入 True/False/对/错 的情况
        true_keywords = {"T", "TRUE", "对", "正确", "Y", "YES", "1"}
        false_keywords = {"F", "FALSE", "错", "错误", "N", "NO", "0"}
        
        # 解析用户答案
        if ua in true_keywords:
            user_is_true = True
        elif ua in false_keywords:
            user_is_true = False
        elif ua in q.options:
            # 用户输入的是选项 key，从 options 中取值
            opt_val = str(q.options[ua]).strip()
            user_is_true = opt_val in ("正确", "对", "True", "true", "TRUE", "是")
        else:
            user_is_true = ua in true_keywords  # 默认判断
        
        # 解析正确答案
        if ca in true_keywords:
            correct_is_true = True
        elif ca in false_keywords:
            correct_is_true = False
        elif ca in q.options:
            opt_val = str(q.options[ca]).strip()
            correct_is_true = opt_val in ("正确", "对", "True", "true", "TRUE", "是")
        else:
            # ca 可能是选项的 value，如 "正确"/"错误"
            correct_is_true = str(ca) in ("正确", "对", "True", "true", "TRUE", "是")
        
        return user_is_true == correct_is_true

    else:
        return ua == ca


def _update_knowledge_points(session: Session, q: Question, is_correct: bool):
    """更新题目标签对应的知识点掌握度"""
    tags = q.tags or []
    for tag_name in tags:
        kp = (
            session.query(KnowledgePoint)
            .filter(
                KnowledgePoint.name == tag_name,
                KnowledgePoint.domain == q.domain,
            )
            .first()
        )
        if kp is None:
            # 自动创建知识点
            kp = KnowledgePoint(
                name=tag_name,
                domain=q.domain,
                mastery_level=0.0,
                total_questions=1,
            )
            session.add(kp)
            session.flush()

        kp.review_count += 1
        if is_correct:
            kp.correct_count += 1
        else:
            kp.wrong_count += 1
        kp.last_reviewed_at = datetime.utcnow()

        # 计算掌握度（指数移动平均，答错影响更大）
        # 新掌握度 = 旧掌握度 * 0.7 + 本次结果 * 0.3
        # 答对 = 1.0，答错 = 0.0
        delta = 1.0 if is_correct else 0.0
        kp.mastery_level = kp.mastery_level * 0.7 + delta * 0.3
        kp.mastery_level = max(0.0, min(1.0, kp.mastery_level))


# ── 统计模块 ──────────────────────────────────────────────

def get_overall_stats(session: Session) -> dict:
    """总体统计"""
    total_questions = session.query(func.count(Question.id)).scalar() or 0
    total_records = session.query(func.count(StudyRecord.id)).scalar() or 0
    total_correct = (
        session.query(func.count(StudyRecord.id))
        .filter(StudyRecord.is_correct == True)
        .scalar() or 0
    )
    total_kps = session.query(func.count(KnowledgePoint.id)).scalar() or 0

    accuracy = total_correct / total_records if total_records > 0 else 0.0

    # 今日学习情况
    today = date.today()
    today_records = (
        session.query(func.count(StudyRecord.id))
        .filter(StudyRecord.study_date == today)
        .scalar() or 0
    )
    today_correct = (
        session.query(func.count(StudyRecord.id))
        .filter(
            StudyRecord.study_date == today,
            StudyRecord.is_correct == True,
        )
        .scalar() or 0
    )

    # 待复习题数
    due_count = (
        session.query(func.count(StudyRecord.id))
        .filter(
            StudyRecord.next_review_date <= today,
        )
        .scalar() or 0
    )

    return {
        "total_questions": total_questions,
        "total_study_records": total_records,
        "total_correct": total_correct,
        "overall_accuracy": round(accuracy, 4),
        "total_knowledge_points": total_kps,
        "today_studied": today_records,
        "today_accuracy": round(today_correct / today_records, 4) if today_records > 0 else 0.0,
        "due_review_count": due_count,
    }


def get_domain_stats(session: Session) -> list[dict]:
    """各领域统计"""
    results = []
    for domain_id in range(1, 9):
        # 题数
        q_count = (
            session.query(func.count(Question.id))
            .filter(Question.domain == domain_id)
            .scalar() or 0
        )
        # 答题记录数和正确数
        record_count = (
            session.query(func.count(StudyRecord.id))
            .join(Question, StudyRecord.question_id == Question.id)
            .filter(Question.domain == domain_id)
            .scalar() or 0
        )
        correct_count = (
            session.query(func.count(StudyRecord.id))
            .join(Question, StudyRecord.question_id == Question.id)
            .filter(
                Question.domain == domain_id,
                StudyRecord.is_correct == True,
            )
            .scalar() or 0
        )
        # 知识点数
        kp_count = (
            session.query(func.count(KnowledgePoint.id))
            .filter(KnowledgePoint.domain == domain_id)
            .scalar() or 0
        )

        accuracy = correct_count / record_count if record_count > 0 else 0.0

        results.append({
            "domain": domain_id,
            "domain_name": DOMAIN_NAMES[domain_id],
            "question_count": q_count,
            "study_count": record_count,
            "correct_count": correct_count,
            "accuracy": round(accuracy, 4),
            "knowledge_point_count": kp_count,
        })

    return results


def get_weak_knowledge_points(
    session: Session, top_n: int = 10, domain: int | None = None
) -> list[KnowledgePoint]:
    """获取最薄弱的知识点（掌握度最低 + 至少做过 2 次）"""
    query = session.query(KnowledgePoint).filter(KnowledgePoint.review_count >= 2)
    if domain is not None:
        query = query.filter(KnowledgePoint.domain == domain)

    kps = query.order_by(KnowledgePoint.mastery_level.asc()).limit(top_n).all()
    return list(kps)


def get_progress_curve(session: Session, days: int = 30) -> list[dict]:
    """获取学习进度曲线（最近 N 天，每天学习量和正确率）"""
    from datetime import timedelta
    start = date.today() - timedelta(days=days - 1)

    records = (
        session.query(
            StudyRecord.study_date,
            func.count(StudyRecord.id).label("total"),
            func.sum(func.cast(StudyRecord.is_correct, Integer)).label("correct"),
        )
        .filter(StudyRecord.study_date >= start)
        .group_by(StudyRecord.study_date)
        .order_by(StudyRecord.study_date)
        .all()
    )

    # 转 dict
    date_map = {}
    for r in records:
        date_map[r.study_date.isoformat()] = {
            "date": r.study_date.isoformat(),
            "total": r.total,
            "correct": r.correct or 0,
            "accuracy": round((r.correct or 0) / r.total, 4) if r.total > 0 else 0.0,
        }

    # 补全没有数据的天
    result = []
    for i in range(days):
        d = start + timedelta(days=i)
        ds = d.isoformat()
        if ds in date_map:
            result.append(date_map[ds])
        else:
            result.append({
                "date": ds,
                "total": 0,
                "correct": 0,
                "accuracy": 0.0,
            })

    return result
