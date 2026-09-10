"""
BDMS v2 Web UI — FastAPI 主应用
基于 L2 web-common 组件库构建
"""

import sys
from pathlib import Path
from datetime import date

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import FileSystemLoader

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# ── L2 web-common 组件库 ──
_PROJECT_ROOT = BASE_DIR.resolve().parents[6]  # openclaw-v5.0/
_WEB_COMMON_DIR = _PROJECT_ROOT / "L2-infra" / "components" / "web-common"
_WEB_COMMON_MACROS = _WEB_COMMON_DIR / "macros"
_WEB_COMMON_STATIC = _WEB_COMMON_DIR / "static"

sys.path.insert(0, str(BASE_DIR.parent))
from services.report_service import list_reports, get_report_status

app = FastAPI(
    title="BDMS v2 — 交付月报管理系统",
    version="2.0.0",
    description="Bangcle 交付管理系统 v2 — 月报生成与管理",
)

# ── 静态资源 ──
app.mount("/static/app", StaticFiles(directory=str(STATIC_DIR)), name="static-app")
app.mount("/static/web-common", StaticFiles(directory=str(_WEB_COMMON_STATIC)), name="web-common-static")

# ── Jinja2 模板 ──
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.loader = FileSystemLoader([str(TEMPLATES_DIR), str(_WEB_COMMON_MACROS)])

# 全局模板变量
templates.env.globals.update({
    "brand_name": "BDMS v2",
    "brand_icon": "📊",
    "storage_key": "bdms-v2-theme",
    "sidebar_items": [
        {
            "title": "交付月报",
            "items": [
                {"id": "list", "label": "月报列表", "url": "/", "icon": "📋"},
                {"id": "generate", "label": "生成月报", "url": "/generate", "icon": "✨"},
            ]
        },
    ],
})


# ========== 异常处理 ==========
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
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
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


# ========== 页面路由 ==========

@app.get("/", response_class=HTMLResponse)
async def report_list_page(request: Request):
    """月报列表页（首页）"""
    reports = list_reports(limit=50)
    for r in reports:
        if r.get("created_at"):
            r["created_at_display"] = r["created_at"].replace("T", " ")[:19] if "T" in str(r["created_at"]) else str(r["created_at"])[:19]
        else:
            r["created_at_display"] = "--"

    return templates.TemplateResponse(request, "report_list.html", {
        "request": request,
        "active_page": "list",
        "reports": reports,
    })


@app.get("/generate", response_class=HTMLResponse)
async def generate_page(request: Request):
    """月报生成页"""
    today = date.today()
    default_month = today.strftime("%Y%m")
    return templates.TemplateResponse(request, "generate.html", {
        "request": request,
        "active_page": "generate",
        "default_month": default_month,
    })


@app.get("/reports/{report_id}", response_class=HTMLResponse)
async def report_detail_page(request: Request, report_id: int):
    """月报预览页"""
    job = get_report_status(report_id)
    if not job:
        return templates.TemplateResponse(request, "error.html", {
            "request": request,
            "active_page": "",
            "error": f"报告 #{report_id} 不存在",
        })
    return templates.TemplateResponse(request, "report_detail.html", {
        "request": request,
        "active_page": "list",
        "report_id": report_id,
        "job": job,
    })


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok", "version": "2.0.0", "module": "bdms-v2"}


# ========== 注册 API 路由 ==========
from api import router as api_router
app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
