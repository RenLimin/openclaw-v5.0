"""
Bangcle PPT Web UI — FastAPI 主入口
启动: uvicorn main:app --host 0.0.0.0 --port 8082
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import FileSystemLoader

# 模块路径
_WEB_DIR = Path(__file__).resolve().parent
_PKG_DIR = _WEB_DIR.parent
_SRC_DIR = _PKG_DIR.parent
_PROJECT_ROOT = _WEB_DIR.parents[5]
for _p in [_SRC_DIR, _WEB_DIR]:
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from bangcle_ppt.web.api import router as api_router

# 路径
STATIC_DIR = _WEB_DIR / "static"
TEMPLATES_DIR = _WEB_DIR / "templates"
_WEB_COMMON_MACROS = _PROJECT_ROOT / "L2-infra" / "components" / "web-common" / "macros"
_WEB_COMMON_STATIC = _PROJECT_ROOT / "L2-infra" / "components" / "web-common" / "static"


def setup_web_common(app: FastAPI, templates: Jinja2Templates, brand_name: str = "Bangcle PPT",
                     brand_icon: str = "📊", storage_key: str = "bangcle_ppt_sidebar",
                     sidebar_items: list | None = None):
    """挂载 web-common 静态资源 + 注册模板加载器 + 注入全局变量"""
    app.mount("/static/web-common", StaticFiles(directory=str(_WEB_COMMON_STATIC)), name="web-common-static")
    templates.env.loader = FileSystemLoader([str(TEMPLATES_DIR), str(_WEB_COMMON_MACROS)])
    templates.env.globals["brand_name"] = brand_name
    templates.env.globals["brand_icon"] = brand_icon
    templates.env.globals["storage_key"] = storage_key
    templates.env.globals["sidebar_items"] = sidebar_items or []


app = FastAPI(
    title="Bangcle PPT 模板生成器",
    version="1.0.0",
    description="梆梆安全 PPT 模板系统 Web UI (CPT-012)",
)

# 静态文件（业务）
app.mount("/static/app", StaticFiles(directory=str(STATIC_DIR)), name="app-static")

# 模板
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# 侧边栏配置
_SIDEBAR_ITEMS = [
    {
        "title": "模板库",
        "items": [
            {"id": "templates", "label": "模板浏览", "url": "/", "icon": "📁"},
        ]
    },
    {
        "title": "工具",
        "items": [
            {"id": "generator", "label": "在线生成", "url": "/generator", "icon": "⚡"},
        ]
    },
]

# 集成 web-common
setup_web_common(
    app, templates,
    brand_name="Bangcle PPT",
    brand_icon="📊",
    storage_key="bangcle_ppt_sidebar",
    sidebar_items=_SIDEBAR_ITEMS,
)


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
    })


@app.get("/templates/{template_name}", response_class=HTMLResponse)
async def page_template_detail(request: Request, template_name: str):
    """模板详情页"""
    return templates.TemplateResponse(request, "template_detail.html", {
        "request": request,
        "active_page": "templates",
        "template_name": template_name,
    })


@app.get("/generator", response_class=HTMLResponse)
async def page_generator(request: Request):
    """在线生成页"""
    return templates.TemplateResponse(request, "generator.html", {
        "request": request,
        "active_page": "generator",
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
