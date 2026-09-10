"""
CISSP Trainer Web UI — FastAPI 主入口
启动: cd cissp-trainer && python -m web.main
      uvicorn web.main:app --host 0.0.0.0 --port 8082
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse

# 路径设置
_WEB_DIR = os.path.dirname(os.path.abspath(__file__))
_MODULE_DIR = os.path.dirname(_WEB_DIR)
_SRC_DIR = os.path.join(_MODULE_DIR, "src")
for _p in [_SRC_DIR, _MODULE_DIR, _WEB_DIR]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from web.api import router as api_router
from cissp_trainer.database import init_db
from cissp_trainer.learning_path import init_preset_paths

STATIC_DIR = os.path.join(_WEB_DIR, "static")
TEMPLATES_DIR = os.path.join(_WEB_DIR, "templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化数据库（幂等）"""
    try:
        init_db()
        # 初始化预设学习路径
        from cissp_trainer.database import session_scope
        with session_scope() as session:
            init_preset_paths(session)
    except Exception as e:
        print(f"[WARN] DB init: {e}")
    yield
    # shutdown: 暂无需清理


app = FastAPI(
    title="CISSP 训练平台",
    version="1.0.0",
    description="CISSP 认证备考训练系统 — 题库 / 学习路径 / 模拟考试 / 知识图谱",
    lifespan=lifespan,
)

# 静态文件
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# 模板
templates = Jinja2Templates(directory=TEMPLATES_DIR)


# ============================================================
# 异常处理
# ============================================================
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    path = request.url.path
    if path.startswith("/api/"):
        return JSONResponse(status_code=400, content={"error": str(exc)})
    return templates.TemplateResponse(
        request, "error.html",
        {"error": str(exc), "active_page": ""},
        status_code=400,
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    path = request.url.path
    if path.startswith("/api/"):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail},
        )
    return templates.TemplateResponse(
        request, "error.html",
        {"error": exc.detail, "active_page": ""},
        status_code=exc.status_code,
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    path = request.url.path
    msg = str(exc) if __debug__ else "Internal Server Error"
    if path.startswith("/api/"):
        return JSONResponse(status_code=500, content={"error": msg})
    return templates.TemplateResponse(
        request, "error.html",
        {"error": msg, "active_page": ""},
        status_code=500,
    )


# ============================================================
# 页面路由
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def page_dashboard(request: Request):
    """首页仪表盘"""
    return templates.TemplateResponse(request, "dashboard.html", {
        "request": request,
        "active_page": "dashboard",
        "page_title": "学习仪表盘",
    })


@app.get("/questions", response_class=HTMLResponse)
async def page_questions(request: Request):
    """题库浏览页"""
    return templates.TemplateResponse(request, "question_bank.html", {
        "request": request,
        "active_page": "questions",
        "page_title": "题库浏览",
    })


@app.get("/exam", response_class=HTMLResponse)
async def page_exam_list(request: Request):
    """模考列表页"""
    return templates.TemplateResponse(request, "exam_list.html", {
        "request": request,
        "active_page": "exam",
        "page_title": "模拟考试",
    })


@app.get("/exam/{exam_id}", response_class=HTMLResponse)
async def page_exam_take(request: Request, exam_id: int):
    """模考答题页"""
    return templates.TemplateResponse(request, "exam_take.html", {
        "request": request,
        "active_page": "exam",
        "page_title": "模拟考试",
        "exam_id": exam_id,
    })


@app.get("/exam/{exam_id}/result", response_class=HTMLResponse)
async def page_exam_result(request: Request, exam_id: int):
    """模考成绩页"""
    return templates.TemplateResponse(request, "exam_result.html", {
        "request": request,
        "active_page": "exam",
        "page_title": "考试成绩",
        "exam_id": exam_id,
    })


@app.get("/learning-path", response_class=HTMLResponse)
async def page_learning_path(request: Request):
    """学习路径页"""
    return templates.TemplateResponse(request, "learning_path.html", {
        "request": request,
        "active_page": "path",
        "page_title": "学习路径",
    })


@app.get("/knowledge-graph", response_class=HTMLResponse)
async def page_knowledge_graph(request: Request):
    """知识图谱页"""
    return templates.TemplateResponse(request, "knowledge_graph.html", {
        "request": request,
        "active_page": "kg",
        "page_title": "知识图谱",
    })


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok", "version": "1.0.0", "component": "cissp-trainer"}


# 注册 API 路由
app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8082)
