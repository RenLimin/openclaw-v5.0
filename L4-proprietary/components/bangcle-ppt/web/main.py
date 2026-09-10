"""
Bangcle PPT Web UI — FastAPI 主入口
启动: uvicorn main:app --host 0.0.0.0 --port 8082
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse

# 模块路径
_WEB_DIR = os.path.dirname(os.path.abspath(__file__))
_PKG_ROOT = os.path.dirname(_WEB_DIR)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from web.api import router as api_router

# 路径
STATIC_DIR = os.path.join(_WEB_DIR, "static")
TEMPLATES_DIR = os.path.join(_WEB_DIR, "templates")

app = FastAPI(
    title="Bangcle PPT 模板生成器",
    version="1.0.0",
    description="梆梆安全 PPT 模板系统 Web UI (CPT-012)",
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
        {"request": request, "error": str(exc), "active_page": ""},
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
        {"request": request, "error": exc.detail, "active_page": ""},
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
        {"request": request, "error": msg, "active_page": ""},
        status_code=500,
    )


# ============================================================
# 页面路由
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def page_index(request: Request):
    """首页 — 模板库浏览"""
    return templates.TemplateResponse(request, "index.html", {
        "request": request,
        "active_page": "templates",
        "page_title": "模板库",
    })


@app.get("/templates/{template_name}", response_class=HTMLResponse)
async def page_template_detail(request: Request, template_name: str):
    """模板详情页"""
    return templates.TemplateResponse(request, "template_detail.html", {
        "request": request,
        "active_page": "templates",
        "page_title": f"模板详情 - {template_name}",
        "template_name": template_name,
    })


@app.get("/generator", response_class=HTMLResponse)
async def page_generator(request: Request):
    """在线生成页"""
    return templates.TemplateResponse(request, "generator.html", {
        "request": request,
        "active_page": "generator",
        "page_title": "在线生成",
    })


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok", "version": "1.0.0", "component": "bangcle-ppt-web"}


# 注册 API 路由
app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8082)
