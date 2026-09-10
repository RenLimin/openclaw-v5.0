"""
CISSP Trainer Web API — FastAPI 路由
5 大类 API：题库 / 学习进度 / 模考 / 知识图谱 / 学习路径
"""

from __future__ import annotations

import sys
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

# 将 src 加入路径
_WEB_DIR = os.path.dirname(os.path.abspath(__file__))
_MODULE_DIR = os.path.dirname(_WEB_DIR)
_SRC_DIR = os.path.join(_MODULE_DIR, "src")
for _p in [_SRC_DIR, _MODULE_DIR]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from cissp_trainer.database import get_session, session_scope
from cissp_trainer import engine as study_engine
from cissp_trainer import exam_engine
from cissp_trainer import learning_path as lp_engine
from cissp_trainer import knowledge_graph as kg_engine
from cissp_trainer.models import DOMAIN_NAMES, Question

router = APIRouter(prefix="/api", tags=["cissp-trainer"])

USER_ID = "default"


# ============================================================
# Pydantic Schemas
# ============================================================

class AnswerRequest(BaseModel):
    question_id: int
    user_answer: str
    time_spent_sec: int = 0


class ExamCreateRequest(BaseModel):
    title: str = "CISSP 模拟考试"
    question_count: int = Field(default=20, ge=2, le=500)
    duration_minutes: int = Field(default=60, ge=10, le=480)
    domain_filter: Optional[list[int]] = Field(default=None)
    difficulty_min: int = Field(default=1, ge=1, le=5)
    difficulty_max: int = Field(default=5, ge=1, le=5)


class ExamAnswerRequest(BaseModel):
    user_answer: str
    time_spent_sec: int = 0


class PathStartRequest(BaseModel):
    slug: str


# ============================================================
# 1. 题库 API
# ============================================================

@router.get("/questions")
async def api_list_questions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    domain: Optional[int] = Query(None, ge=1, le=8),
    difficulty: Optional[int] = Query(None, ge=1, le=5),
    question_type: Optional[str] = None,
    keyword: Optional[str] = None,
    sort_by: str = "id",
    sort_order: str = "asc",
):
    """题目列表（分页 + 筛选）"""
    with session_scope() as session:
        query = session.query(Question)

        if domain is not None:
            query = query.filter(Question.domain == domain)
        if difficulty is not None:
            query = query.filter(Question.difficulty == difficulty)
        if question_type:
            query = query.filter(Question.question_type == question_type)
        if keyword:
            query = query.filter(Question.stem.ilike(f"%{keyword}%"))

        total = query.count()

        # 排序
        if sort_by == "difficulty":
            col = Question.difficulty
        elif sort_by == "domain":
            col = Question.domain
        else:
            col = Question.id
        if sort_order == "desc":
            query = query.order_by(col.desc())
        else:
            query = query.order_by(col.asc())

        offset = (page - 1) * page_size
        items = query.offset(offset).limit(page_size).all()

        results = [
            {
                "id": q.id,
                "domain": q.domain,
                "domain_name": q.domain_name,
                "difficulty": q.difficulty,
                "question_type": q.question_type,
                "stem": q.stem,
                "options": q.options,
                "correct_answer": q.correct_answer,
                "explanation": q.explanation,
                "tags": q.tags,
                "times_shown": q.times_shown,
                "times_correct": q.times_correct,
                "correct_rate": round(q.correct_rate, 4),
            }
            for q in items
        ]

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
            "items": results,
        }


@router.get("/questions/{question_id}")
async def api_get_question(question_id: int):
    """题目详情"""
    with session_scope() as session:
        q = session.get(Question, question_id)
        if not q:
            raise HTTPException(status_code=404, detail="题目不存在")
        return {
            "id": q.id,
            "domain": q.domain,
            "domain_name": q.domain_name,
            "difficulty": q.difficulty,
            "question_type": q.question_type,
            "stem": q.stem,
            "options": q.options,
            "correct_answer": q.correct_answer,
            "explanation": q.explanation,
            "tags": q.tags,
            "source": q.source,
            "times_shown": q.times_shown,
            "times_correct": q.times_correct,
            "correct_rate": round(q.correct_rate, 4),
        }


@router.get("/questions/random/pick")
async def api_pick_questions(
    count: int = Query(10, ge=1, le=100),
    domain: Optional[int] = Query(None, ge=1, le=8),
    difficulty: Optional[int] = Query(None, ge=1, le=5),
    mode: str = Query("random", pattern="^(random|review|weak|exam)$"),
):
    """智能抽题"""
    with session_scope() as session:
        qs = study_engine.pick_questions(
            session, count=count, domain=domain,
            difficulty=difficulty, mode=mode,
        )
        return {
            "count": len(qs),
            "mode": mode,
            "questions": [
                {
                    "id": q.id,
                    "domain": q.domain,
                    "domain_name": q.domain_name,
                    "difficulty": q.difficulty,
                    "question_type": q.question_type,
                    "stem": q.stem,
                    "options": q.options,
                    "tags": q.tags,
                }
                for q in qs
            ],
        }


@router.post("/questions/answer")
async def api_answer_question(data: AnswerRequest):
    """回答一道题（练习模式，更新掌握度 + SM-2）"""
    with session_scope() as session:
        try:
            result = study_engine.answer_question(
                session,
                question_id=data.question_id,
                user_answer=data.user_answer,
                time_spent_sec=data.time_spent_sec,
            )
            return result
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))


# ============================================================
# 2. 学习进度 API
# ============================================================

@router.get("/stats/overall")
async def api_overall_stats():
    """总体统计"""
    with session_scope() as session:
        return study_engine.get_overall_stats(session)


@router.get("/stats/domains")
async def api_domain_stats():
    """各领域统计"""
    with session_scope() as session:
        return study_engine.get_domain_stats(session)


@router.get("/stats/weak-kps")
async def api_weak_kps(
    top_n: int = Query(10, ge=1, le=50),
    domain: Optional[int] = Query(None, ge=1, le=8),
):
    """最薄弱知识点"""
    with session_scope() as session:
        kps = study_engine.get_weak_knowledge_points(session, top_n=top_n, domain=domain)
        return [
            {
                "id": kp.id,
                "name": kp.name,
                "domain": kp.domain,
                "domain_name": DOMAIN_NAMES.get(kp.domain, ""),
                "mastery_level": round(kp.mastery_level, 4),
                "review_count": kp.review_count,
                "correct_count": kp.correct_count,
                "wrong_count": kp.wrong_count,
            }
            for kp in kps
        ]


@router.get("/stats/progress-curve")
async def api_progress_curve(days: int = Query(30, ge=1, le=365)):
    """学习进度曲线"""
    with session_scope() as session:
        return study_engine.get_progress_curve(session, days=days)


# ============================================================
# 3. 模考 API
# ============================================================

@router.post("/exams")
async def api_create_exam(data: ExamCreateRequest):
    """创建模拟考试"""
    with session_scope() as session:
        result = exam_engine.create_exam(
            session,
            title=data.title,
            question_count=data.question_count,
            duration_minutes=data.duration_minutes,
            domain_filter=data.domain_filter,
            difficulty_min=data.difficulty_min,
            difficulty_max=data.difficulty_max,
            user_id=USER_ID,
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "创建失败"))
        return result


@router.post("/exams/{exam_id}/start")
async def api_start_exam(exam_id: int):
    """开始考试"""
    with session_scope() as session:
        result = exam_engine.start_exam(session, exam_id)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "开始失败"))
        return result


@router.get("/exams/{exam_id}/current")
async def api_exam_current_question(exam_id: int):
    """获取当前题目"""
    with session_scope() as session:
        result = exam_engine.get_current_question(session, exam_id)
        if result is None:
            raise HTTPException(status_code=404, detail="考试不存在或已结束")
        return result


@router.post("/exams/{exam_id}/answer")
async def api_exam_answer(exam_id: int, data: ExamAnswerRequest):
    """回答当前题目"""
    with session_scope() as session:
        result = exam_engine.answer_current(
            session, exam_id,
            user_answer=data.user_answer,
            time_spent_sec=data.time_spent_sec,
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "答题失败"))
        return result


@router.post("/exams/{exam_id}/goto")
async def api_exam_goto(exam_id: int, index: int = Query(..., ge=0)):
    """跳转到指定题目"""
    with session_scope() as session:
        result = exam_engine.goto_question(session, exam_id, index)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "跳转失败"))
        return result


@router.post("/exams/{exam_id}/flag")
async def api_exam_flag(exam_id: int, question_index: Optional[int] = None):
    """标记/取消标记题目"""
    with session_scope() as session:
        result = exam_engine.flag_question(session, exam_id, question_index)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "标记失败"))
        return result


@router.post("/exams/{exam_id}/pause")
async def api_exam_pause(exam_id: int):
    """暂停考试"""
    with session_scope() as session:
        result = exam_engine.pause_exam(session, exam_id)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "暂停失败"))
        return result


@router.post("/exams/{exam_id}/resume")
async def api_exam_resume(exam_id: int):
    """继续考试"""
    with session_scope() as session:
        result = exam_engine.resume_exam(session, exam_id)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "继续失败"))
        return result


@router.post("/exams/{exam_id}/submit")
async def api_exam_submit(exam_id: int):
    """交卷"""
    with session_scope() as session:
        result = exam_engine.submit_exam(session, exam_id)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "交卷失败"))
        return result


@router.get("/exams/history")
async def api_exam_history(limit: int = Query(20, ge=1, le=100)):
    """考试历史记录"""
    with session_scope() as session:
        return exam_engine.get_exam_history(session, user_id=USER_ID, limit=limit)


@router.get("/exams/{exam_id}/result")
async def api_exam_result(exam_id: int):
    """考试详细结果"""
    with session_scope() as session:
        result = exam_engine.get_exam_detail(session, exam_id)
        if result is None:
            raise HTTPException(status_code=404, detail="考试不存在")
        return result


@router.get("/exams/score-curve")
async def api_score_curve():
    """成绩曲线"""
    with session_scope() as session:
        return exam_engine.get_score_curve(session, user_id=USER_ID)


# ============================================================
# 4. 知识图谱 API
# ============================================================

@router.get("/kg/domains/{domain_id}")
async def api_kg_domain(domain_id: int):
    """获取某领域知识图谱"""
    if domain_id < 1 or domain_id > 8:
        raise HTTPException(status_code=400, detail="领域ID必须在1-8之间")
    with session_scope() as session:
        return kg_engine.build_domain_graph(session, domain_id)


@router.get("/kg/prerequisites")
async def api_kg_prerequisites(
    kp_name: str,
    domain: Optional[int] = Query(None, ge=1, le=8),
    depth: int = Query(3, ge=1, le=10),
):
    """查询知识点前置依赖"""
    with session_scope() as session:
        return kg_engine.get_prerequisites(session, kp_name, domain=domain, depth=depth)


@router.get("/kg/successors")
async def api_kg_successors(
    kp_name: str,
    domain: Optional[int] = Query(None, ge=1, le=8),
    depth: int = Query(3, ge=1, le=10),
):
    """查询知识点后继"""
    with session_scope() as session:
        return kg_engine.get_successors(session, kp_name, domain=domain, depth=depth)


@router.get("/kg/suggest-next")
async def api_kg_suggest_next(
    kp_name: str,
    domain: Optional[int] = Query(None, ge=1, le=8),
    top_n: int = Query(5, ge=1, le=20),
):
    """推荐下一步学习的知识点"""
    with session_scope() as session:
        return kg_engine.suggest_next_kps(session, kp_name, domain=domain, top_n=top_n)


@router.get("/kg/weak-propagation")
async def api_kg_weak_propagation(
    kp_name: str,
    domain: Optional[int] = Query(None, ge=1, le=8),
    max_depth: int = Query(5, ge=1, le=10),
):
    """薄弱点传播分析"""
    with session_scope() as session:
        result = kg_engine.analyze_weak_propagation(
            session, kp_name, domain=domain, max_depth=max_depth,
        )
        return {
            "source_kp": result.source_kp,
            "total_affected": result.total_affected,
            "affected_kps": result.affected_kps,
        }


# ============================================================
# 5. 学习路径 API
# ============================================================

@router.get("/paths")
async def api_list_paths():
    """列出所有学习路径"""
    with session_scope() as session:
        lp_engine.init_preset_paths(session)
        return lp_engine.list_paths(session)


@router.get("/paths/recommend")
async def api_recommend_path():
    """推荐学习路径"""
    with session_scope() as session:
        lp_engine.init_preset_paths(session)
        return lp_engine.recommend_path(session, user_id=USER_ID)


@router.post("/paths/start")
async def api_start_path(data: PathStartRequest):
    """开始一条学习路径"""
    with session_scope() as session:
        lp_engine.init_preset_paths(session)
        result = lp_engine.start_path(session, slug=data.slug, user_id=USER_ID)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "启动失败"))
        return result


@router.get("/paths/current")
async def api_current_path():
    """当前进行中的路径状态"""
    with session_scope() as session:
        result = lp_engine.get_path_status(session, user_id=USER_ID)
        if result is None:
            return {"has_path": False, "message": "暂无进行中的路径"}
        return {"has_path": True, **result}


@router.get("/paths/daily-plan")
async def api_daily_plan():
    """今日学习计划"""
    with session_scope() as session:
        return lp_engine.generate_daily_plan(session, user_id=USER_ID)


@router.post("/paths/adjust")
async def api_adjust_path():
    """动态调整路径"""
    with session_scope() as session:
        return lp_engine.adjust_path(session, user_id=USER_ID)


# ============================================================
# Health
# ============================================================

@router.get("/health")
async def api_health():
    """健康检查"""
    return {"status": "ok", "component": "cissp-trainer-web", "domains": len(DOMAIN_NAMES)}
