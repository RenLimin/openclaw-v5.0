"""
模拟考试引擎

功能：
  - 创建考试会话（按域权重抽题）
  - 答题流程（逐题作答 / 标记 / 跳转）
  - 计时 + 暂停/继续
  - 自动交卷 / 手动交卷
  - 评分 + 领域分析 + 错题解析
  - 历史记录 + 成绩曲线
"""

from __future__ import annotations

import time
from datetime import datetime, date, timedelta
from dataclasses import dataclass
from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import (
    ExamSession, ExamAnswer, Question,
    DOMAIN_NAMES, StudyRecord,
)
from .engine import _pick_by_domain_weight, _check_answer, _update_knowledge_points


PASS_THRESHOLD = 0.70  # 70% 及格线
DEFAULT_DURATION_MIN = 180  # 3 小时
DEFAULT_QUESTION_COUNT = 100


# ── 创建考试 ──────────────────────────────────────────────

def create_exam(
    session: Session,
    title: str = "CISSP 模拟考试",
    question_count: int = DEFAULT_QUESTION_COUNT,
    duration_minutes: int = DEFAULT_DURATION_MIN,
    domain_filter: list[int] | None = None,
    difficulty_min: int = 1,
    difficulty_max: int = 5,
    user_id: str = "default",
) -> dict:
    """
    创建一场新的模拟考试

    参数：
      question_count: 题目数量（默认 100）
      duration_minutes: 考试时长（分钟，默认 180）
      domain_filter: 指定领域列表（None=全部 8 域）
      difficulty_min/max: 难度范围
    """
    # 抽题
    query = session.query(Question)
    if domain_filter:
        query = query.filter(Question.domain.in_(domain_filter))
    query = query.filter(Question.difficulty >= difficulty_min,
                         Question.difficulty <= difficulty_max)
    pool = list(query.all())

    if not pool:
        return {"success": False, "error": "题库中没有符合条件的题目"}

    if len(pool) < question_count:
        question_count = len(pool)
        # 不够题就全用

    # 按域权重抽题
    if domain_filter is None:
        questions = _pick_by_domain_weight(session, pool, question_count)
    else:
        # 指定领域的，平均分配
        questions = _pick_by_domain_balanced(session, pool, question_count, domain_filter)

    # 确保数量正确
    if len(questions) < question_count:
        from random import sample, shuffle
        used = {q.id for q in questions}
        remaining = [q for q in pool if q.id not in used]
        need = question_count - len(questions)
        if remaining and need > 0:
            questions.extend(sample(remaining, min(need, len(remaining))))
        shuffle(questions)

    exam = ExamSession(
        user_id=user_id,
        title=title,
        total_questions=len(questions),
        duration_minutes=duration_minutes,
        status="pending",
        question_ids=[q.id for q in questions],
        current_index=0,
        time_remaining_sec=duration_minutes * 60,
    )
    session.add(exam)
    session.flush()

    return {
        "success": True,
        "exam_id": exam.id,
        "title": exam.title,
        "total_questions": exam.total_questions,
        "duration_minutes": duration_minutes,
        "time_remaining_sec": exam.time_remaining_sec,
    }


def _pick_by_domain_balanced(session: Session, pool: list[Question],
                             count: int, domains: list[int]) -> list[Question]:
    """在指定领域内均衡抽题"""
    from random import sample, shuffle
    by_domain = defaultdict(list)
    for q in pool:
        by_domain[q.domain].append(q)

    if not by_domain:
        return []

    per_domain = max(1, count // len(by_domain))
    result = []
    for d in sorted(by_domain.keys()):
        n = min(per_domain, len(by_domain[d]))
        result.extend(sample(by_domain[d], n))

    # 不够的从剩余题补
    remaining_need = count - len(result)
    if remaining_need > 0:
        used = {q.id for q in result}
        leftover = [q for q in pool if q.id not in used]
        if leftover:
            result.extend(sample(leftover, min(remaining_need, len(leftover))))

    shuffle(result)
    return result


# ── 考试流程 ──────────────────────────────────────────────

def start_exam(session: Session, exam_id: int) -> dict:
    """开始考试（启动计时）"""
    exam = session.get(ExamSession, exam_id)
    if not exam:
        return {"success": False, "error": "考试不存在"}

    if exam.status not in ("pending", "paused"):
        return {"success": False, "error": f"考试状态 {exam.status} 无法开始"}

    exam.status = "in_progress"
    exam.started_at = datetime.utcnow()
    session.flush()

    return {
        "success": True,
        "exam_id": exam.id,
        "status": exam.status,
        "current_index": exam.current_index,
        "total_questions": exam.total_questions,
        "time_remaining_sec": exam.time_remaining_sec,
    }


def get_current_question(session: Session, exam_id: int) -> dict | None:
    """获取当前题目"""
    exam = session.get(ExamSession, exam_id)
    if not exam or exam.status != "in_progress":
        return None

    if exam.current_index >= len(exam.question_ids):
        return None

    qid = exam.question_ids[exam.current_index]
    q = session.get(Question, qid)
    if not q:
        return None

    # 检查是否已答
    existing = (
        session.query(ExamAnswer)
        .filter_by(exam_id=exam.id, question_id=q.id)
        .first()
    )

    return {
        "index": exam.current_index + 1,
        "total": exam.total_questions,
        "question_id": q.id,
        "domain": q.domain,
        "domain_name": q.domain_name,
        "difficulty": q.difficulty,
        "question_type": q.question_type,
        "stem": q.stem,
        "options": q.options,
        "user_answer": existing.user_answer if existing else "",
        "is_flagged": existing.is_flagged if existing else False,
        "time_remaining_sec": exam.time_remaining_sec,
    }


def answer_current(session: Session, exam_id: int, user_answer: str,
                   time_spent_sec: int = 0) -> dict:
    """
    回答当前题目（不立即判分，交卷时统一判）

    自动前进到下一题
    """
    exam = session.get(ExamSession, exam_id)
    if not exam or exam.status != "in_progress":
        return {"success": False, "error": "考试不在进行中"}

    if exam.current_index >= len(exam.question_ids):
        return {"success": False, "error": "已到最后一题"}

    qid = exam.question_ids[exam.current_index]

    # 写入/更新答案
    existing = (
        session.query(ExamAnswer)
        .filter_by(exam_id=exam.id, question_id=qid)
        .first()
    )
    if existing:
        existing.user_answer = user_answer
        existing.time_spent_sec += time_spent_sec
        existing.answered_at = datetime.utcnow()
    else:
        ans = ExamAnswer(
            exam_id=exam.id,
            question_id=qid,
            question_index=exam.current_index,
            user_answer=user_answer,
            time_spent_sec=time_spent_sec,
            answered_at=datetime.utcnow(),
        )
        session.add(ans)
        exam.total_answered += 1

    # 扣减时间
    if exam.time_remaining_sec is not None:
        exam.time_remaining_sec = max(0, exam.time_remaining_sec - time_spent_sec)
        if exam.time_remaining_sec <= 0:
            # 时间到，自动交卷
            return submit_exam(session, exam_id, reason="timeout")

    # 前进到下一题
    exam.current_index += 1
    session.flush()

    is_last = exam.current_index >= exam.total_questions

    return {
        "success": True,
        "answered_index": exam.current_index,  # 已答到第 N 题（1-based 就是 current_index）
        "total": exam.total_questions,
        "is_last": is_last,
        "time_remaining_sec": exam.time_remaining_sec,
    }


def goto_question(session: Session, exam_id: int, index: int) -> dict:
    """跳转到指定题目（0-based index）"""
    exam = session.get(ExamSession, exam_id)
    if not exam or exam.status != "in_progress":
        return {"success": False, "error": "考试不在进行中"}

    if index < 0 or index >= exam.total_questions:
        return {"success": False, "error": f"题号超出范围 (0-{exam.total_questions-1})"}

    exam.current_index = index
    session.flush()
    return {"success": True, "current_index": index}


def flag_question(session: Session, exam_id: int,
                  question_index: int | None = None) -> dict:
    """标记/取消标记当前题"""
    exam = session.get(ExamSession, exam_id)
    if not exam or exam.status != "in_progress":
        return {"success": False, "error": "考试不在进行中"}

    if question_index is None:
        question_index = exam.current_index

    if question_index < 0 or question_index >= exam.total_questions:
        return {"success": False, "error": "题号超出范围"}

    qid = exam.question_ids[question_index]
    ans = (
        session.query(ExamAnswer)
        .filter_by(exam_id=exam.id, question_id=qid)
        .first()
    )
    if ans:
        ans.is_flagged = not ans.is_flagged
        flagged = ans.is_flagged
    else:
        # 没答过也能标记（创建空记录）
        ans = ExamAnswer(
            exam_id=exam.id,
            question_id=qid,
            question_index=question_index,
            is_flagged=True,
        )
        session.add(ans)
        flagged = True

    session.flush()
    return {"success": True, "flagged": flagged, "question_index": question_index}


# ── 暂停 / 继续 ───────────────────────────────────────────

def pause_exam(session: Session, exam_id: int) -> dict:
    """暂停考试"""
    exam = session.get(ExamSession, exam_id)
    if not exam or exam.status != "in_progress":
        return {"success": False, "error": "考试不在进行中"}

    exam.status = "paused"
    exam.paused_at = datetime.utcnow()
    session.flush()

    return {
        "success": True,
        "exam_id": exam.id,
        "status": "paused",
        "time_remaining_sec": exam.time_remaining_sec,
        "answered": exam.total_answered,
        "total": exam.total_questions,
    }


def resume_exam(session: Session, exam_id: int) -> dict:
    """继续考试"""
    exam = session.get(ExamSession, exam_id)
    if not exam or exam.status != "paused":
        return {"success": False, "error": "考试未暂停"}

    exam.status = "in_progress"
    session.flush()

    return {
        "success": True,
        "exam_id": exam.id,
        "status": "in_progress",
        "current_index": exam.current_index,
        "time_remaining_sec": exam.time_remaining_sec,
    }


# ── 交卷 + 评分 ───────────────────────────────────────────

def submit_exam(session: Session, exam_id: int, reason: str = "manual") -> dict:
    """
    交卷并评分

    reason: manual / timeout / auto
    """
    exam = session.get(ExamSession, exam_id)
    if not exam:
        return {"success": False, "error": "考试不存在"}

    if exam.status in ("submitted", "timeout"):
        return {"success": False, "error": "考试已交卷"}

    # 获取所有答题记录
    answers = (
        session.query(ExamAnswer)
        .filter_by(exam_id=exam.id)
        .all()
    )
    ans_by_qid = {a.question_id: a for a in answers}

    total_correct = 0
    total_answered = 0
    domain_stats = defaultdict(lambda: {"correct": 0, "total": 0, "questions": []})
    wrong_questions = []

    for i, qid in enumerate(exam.question_ids):
        q = session.get(Question, qid)
        if not q:
            continue
        ans = ans_by_qid.get(qid)
        user_answer = ans.user_answer if ans else ""

        is_correct = False
        if user_answer:
            total_answered += 1
            is_correct = _check_answer(q, user_answer)
            if is_correct:
                total_correct += 1

        # 更新答题记录
        if ans:
            ans.is_correct = is_correct

        # 领域统计
        ds = domain_stats[q.domain]
        ds["total"] += 1
        if is_correct:
            ds["correct"] += 1
        ds["questions"].append(qid)

        # 错题收集
        if not is_correct:
            wrong_questions.append({
                "question_id": q.id,
                "domain": q.domain,
                "domain_name": q.domain_name,
                "stem": q.stem,
                "user_answer": user_answer,
                "correct_answer": q.correct_answer,
                "explanation": q.explanation,
            })

    # 计算分数
    total = exam.total_questions
    score = round(total_correct / total * 100, 2) if total > 0 else 0.0
    passed = score >= PASS_THRESHOLD * 100

    # 领域分数
    domain_scores = {}
    for d in sorted(domain_stats.keys()):
        ds = domain_stats[d]
        s = round(ds["correct"] / ds["total"] * 100, 1) if ds["total"] > 0 else 0.0
        domain_scores[str(d)] = {
            "domain": d,
            "domain_name": DOMAIN_NAMES.get(d, f"域{d}"),
            "correct": ds["correct"],
            "total": ds["total"],
            "score": s,
        }

    # 薄弱领域（正确率低于及格线的）
    weak_domains = [
        ds for ds in domain_scores.values()
        if ds["total"] >= 3 and ds["score"] < PASS_THRESHOLD * 100
    ]
    weak_domains.sort(key=lambda x: x["score"])

    # 更新考试记录
    exam.status = "timeout" if reason == "timeout" else "submitted"
    exam.score = score
    exam.passed = passed
    exam.domain_scores = domain_scores
    exam.total_correct = total_correct
    exam.total_answered = total_answered
    exam.submitted_at = datetime.utcnow()

    # 将考试答题结果同步到学习记录（更新掌握度 + SM-2）
    _sync_to_study_records(session, exam, ans_by_qid)

    session.flush()

    return {
        "success": True,
        "exam_id": exam.id,
        "status": exam.status,
        "score": score,
        "passed": passed,
        "pass_threshold": PASS_THRESHOLD * 100,
        "total_questions": total,
        "total_answered": total_answered,
        "total_correct": total_correct,
        "domain_scores": list(domain_scores.values()),
        "weak_domains": weak_domains,
        "wrong_count": len(wrong_questions),
        "wrong_questions": wrong_questions[:20],  # 只返回前 20 道错题概览
    }


def _sync_to_study_records(session: Session, exam: ExamSession,
                           ans_by_qid: dict[int, ExamAnswer]):
    """将考试答题同步到学习记录（更新掌握度）"""
    for qid in exam.question_ids:
        ans = ans_by_qid.get(qid)
        if not ans or not ans.user_answer:
            continue

        q = session.get(Question, qid)
        if not q:
            continue

        # 复用 engine 里的更新逻辑
        is_correct = ans.is_correct if ans.is_correct is not None else _check_answer(q, ans.user_answer)

        # 更新题目统计
        q.times_shown += 1
        if is_correct:
            q.times_correct += 1

        # 更新知识点掌握度
        _update_knowledge_points(session, q, is_correct)

        # 写 StudyRecord（简化版，不用 SM-2，用考试日期）
        from .models import StudyRecord
        from .spaced_repetition import sm2_update

        # 取上次记录
        last_record = (
            session.query(StudyRecord)
            .filter(StudyRecord.question_id == qid)
            .order_by(StudyRecord.created_at.desc())
            .first()
        )
        prev_ef = last_record.efactor if last_record else 2.5
        prev_interval = last_record.interval if last_record else 0
        prev_rep = last_record.repetition if last_record else 0

        study_date = exam.submitted_at.date() if exam.submitted_at else date.today()
        sr = sm2_update(
            is_correct=is_correct,
            current_efactor=prev_ef,
            current_interval=prev_interval,
            current_repetition=prev_rep,
            today=study_date,
            difficulty=q.difficulty,
            time_spent_sec=ans.time_spent_sec,
        )

        record = StudyRecord(
            question_id=qid,
            study_date=study_date,
            user_answer=ans.user_answer,
            is_correct=is_correct,
            time_spent_sec=ans.time_spent_sec,
            quality=sr.quality,
            efactor=sr.efactor,
            interval=sr.interval,
            repetition=sr.repetition,
            next_review_date=sr.next_review_date,
        )
        session.add(record)


# ── 考试记录查询 ───────────────────────────────────────────

def get_exam_history(session: Session, user_id: str = "default",
                     limit: int = 20) -> list[dict]:
    """获取考试历史记录"""
    exams = (
        session.query(ExamSession)
        .filter_by(user_id=user_id)
        .filter(ExamSession.status.in_(["submitted", "timeout"]))
        .order_by(ExamSession.submitted_at.desc())
        .limit(limit)
        .all()
    )

    result = []
    for e in exams:
        result.append({
            "exam_id": e.id,
            "title": e.title,
            "score": e.score,
            "passed": e.passed,
            "total_questions": e.total_questions,
            "total_correct": e.total_correct,
            "status": e.status,
            "submitted_at": e.submitted_at.isoformat() if e.submitted_at else None,
            "duration_minutes": e.duration_minutes,
        })
    return result


def get_score_curve(session: Session, user_id: str = "default") -> list[dict]:
    """获取成绩曲线（按时间排序的所有考试成绩）"""
    exams = (
        session.query(ExamSession)
        .filter_by(user_id=user_id)
        .filter(ExamSession.status.in_(["submitted", "timeout"]))
        .filter(ExamSession.score != None)
        .order_by(ExamSession.submitted_at.asc())
        .all()
    )

    result = []
    for e in exams:
        result.append({
            "exam_id": e.id,
            "date": e.submitted_at.date().isoformat() if e.submitted_at else "未知",
            "score": e.score,
            "passed": e.passed,
            "total_questions": e.total_questions,
        })
    return result


def get_exam_detail(session: Session, exam_id: int) -> dict | None:
    """获取考试详细信息（含错题解析）"""
    exam = session.get(ExamSession, exam_id)
    if not exam:
        return None

    answers = (
        session.query(ExamAnswer)
        .filter_by(exam_id=exam.id)
        .order_by(ExamAnswer.question_index.asc())
        .all()
    )

    wrong_list = []
    for ans in answers:
        if ans.is_correct == False:
            q = ans.question
            if q:
                wrong_list.append({
                    "index": ans.question_index + 1,
                    "question_id": q.id,
                    "domain": q.domain,
                    "domain_name": q.domain_name,
                    "stem": q.stem,
                    "options": q.options,
                    "user_answer": ans.user_answer,
                    "correct_answer": q.correct_answer,
                    "explanation": q.explanation,
                    "time_spent_sec": ans.time_spent_sec,
                    "tags": q.tags,
                })

    return {
        "exam_id": exam.id,
        "title": exam.title,
        "score": exam.score,
        "passed": exam.passed,
        "total_questions": exam.total_questions,
        "total_correct": exam.total_correct,
        "total_answered": exam.total_answered,
        "status": exam.status,
        "started_at": exam.started_at.isoformat() if exam.started_at else None,
        "submitted_at": exam.submitted_at.isoformat() if exam.submitted_at else None,
        "domain_scores": exam.domain_scores,
        "wrong_questions": wrong_list,
    }


def compare_with_previous(session: Session, exam_id: int,
                          user_id: str = "default") -> dict:
    """与上一次考试对比"""
    current = session.get(ExamSession, exam_id)
    if not current or current.score is None:
        return {"error": "当前考试不存在或未完成"}

    # 找前一次
    prev = (
        session.query(ExamSession)
        .filter(
            ExamSession.user_id == user_id,
            ExamSession.status.in_(["submitted", "timeout"]),
            ExamSession.score != None,
            ExamSession.id != exam_id,
            ExamSession.submitted_at < current.submitted_at if current.submitted_at else True,
        )
        .order_by(ExamSession.submitted_at.desc())
        .first()
    )

    if not prev:
        return {
            "previous": None,
            "current_score": current.score,
            "change": None,
            "message": "这是你的第一次考试，继续加油！",
        }

    score_diff = round(current.score - prev.score, 2)

    # 领域对比
    cur_ds = current.domain_scores or {}
    prev_ds = prev.domain_scores or {}
    domain_changes = []

    all_domains = set(list(cur_ds.keys()) + list(prev_ds.keys()))
    for d in sorted(all_domains, key=lambda x: int(x)):
        cur_s = cur_ds.get(d, {}).get("score", 0)
        prev_s = prev_ds.get(d, {}).get("score", 0)
        diff = round(cur_s - prev_s, 1)
        domain_changes.append({
            "domain": int(d),
            "domain_name": DOMAIN_NAMES.get(int(d), f"域{d}"),
            "previous_score": prev_s,
            "current_score": cur_s,
            "change": diff,
        })

    # 找出进步最大和退步最大的
    domain_changes.sort(key=lambda x: -x["change"])

    return {
        "previous": {
            "exam_id": prev.id,
            "score": prev.score,
            "date": prev.submitted_at.date().isoformat() if prev.submitted_at else "未知",
        },
        "current_score": current.score,
        "change": score_diff,
        "trend": "上升" if score_diff > 0 else ("下降" if score_diff < 0 else "持平"),
        "domain_changes": domain_changes,
        "most_improved": domain_changes[0] if domain_changes and domain_changes[0]["change"] > 0 else None,
        "most_declined": domain_changes[-1] if domain_changes and domain_changes[-1]["change"] < 0 else None,
    }
