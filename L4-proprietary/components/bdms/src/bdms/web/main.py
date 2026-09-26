"""BDMS Web UI — FastAPI 主应用。

基于 L2 web-common 组件库构建，与 delivery-center 保持一致的 UI 规范。
五大模块：
  1. 交付月度管理（月报生成/导出）
  2. 确认收入管理（导入/计算/汇总/对比）
  3. 交付管理基础数据（图例等）
  4. 交付统计看板（图表 + 下钻）
  5. 交付管理系统设定
"""

import sys
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import FileSystemLoader

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# ── L2 web-common 组件库 ──
def _find_web_common() -> Path | None:
    """从当前文件向上查找 L2-infra/components/web-common。"""
    for p in [BASE_DIR.resolve(), *BASE_DIR.resolve().parents]:
        cand = p / "L2-infra" / "components" / "web-common"
        if cand.is_dir():
            return cand
    return None

_WEB_COMMON_DIR = _find_web_common()
_WEB_COMMON_MACROS = (_WEB_COMMON_DIR / "macros") if _WEB_COMMON_DIR else None
_WEB_COMMON_STATIC = (_WEB_COMMON_DIR / "static") if _WEB_COMMON_DIR else None

sys.path.insert(0, str(BASE_DIR.parent))

app = FastAPI(
    title="BDMS — 交付管理系统",
    version="1.0.0",
    description="BDMS 交付管理系统：交付月报 / 确认收入 / 基础数据 / 统计看板 / 系统设定",
)

if STATIC_DIR.exists():
    app.mount("/static/app", StaticFiles(directory=str(STATIC_DIR)), name="static-app")
if _WEB_COMMON_STATIC and _WEB_COMMON_STATIC.exists():
    app.mount("/static/web-common", StaticFiles(directory=str(_WEB_COMMON_STATIC)),
              name="web-common-static")

# 模板搜索路径：本地 templates 优先，其次 web-common macros
template_dirs = [str(TEMPLATES_DIR)]
if _WEB_COMMON_MACROS and _WEB_COMMON_MACROS.is_dir():
    template_dirs.append(str(_WEB_COMMON_MACROS))

templates = Jinja2Templates(directory=template_dirs[0])
templates.env.loader = FileSystemLoader(template_dirs)

templates.env.globals.update({
    "brand_name": "BDMS",
    "brand_desc": "交付管理系统",
    "brand_icon": "📦",
    "storage_key": "bdms-theme",
    "sidebar_items": [
        {
            "title": "交付月度管理",
            "items": [
                {"id": "report", "label": "交付月报", "url": "/report", "icon": "📋"},
            ],
        },
        {
            "title": "确认收入管理",
            "items": [
                {"id": "revenue", "label": "确收汇总", "url": "/revenue", "icon": "💰"},
                {"id": "revenue-compare", "label": "对比分析", "url": "/revenue/compare", "icon": "🔍"},
            ],
        },
        {
            "title": "基础数据",
            "items": [
                {"id": "master", "label": "图例基础数据", "url": "/master-data", "icon": "📖"},
            ],
        },
        {
            "title": "统计看板",
            "items": [
                {"id": "dashboard", "label": "交付统计看板", "url": "/dashboard", "icon": "📊"},
            ],
        },
        {
            "title": "系统",
            "items": [
                {"id": "settings", "label": "系统设定", "url": "/settings", "icon": "⚙️"},
            ],
        },
    ],
})


def _render(request: Request, name: str, ctx: dict | None = None) -> HTMLResponse:
    ctx = dict(ctx or {})
    ctx.setdefault("active_page", "")
    return templates.TemplateResponse(request, name, ctx)


# ========== 页面路由 ==========

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return _render(request, "index.html", {"active_page": "dashboard"})


@app.get("/report", response_class=HTMLResponse)
async def page_report(request: Request):
    return _render(request, "report.html", {"active_page": "report"})


@app.get("/revenue", response_class=HTMLResponse)
async def page_revenue(request: Request):
    return _render(request, "revenue.html", {"active_page": "revenue"})


@app.get("/revenue/compare", response_class=HTMLResponse)
async def page_revenue_compare(request: Request):
    return _render(request, "revenue_compare.html", {"active_page": "revenue-compare"})


@app.get("/master-data", response_class=HTMLResponse)
async def page_master_data(request: Request):
    return _render(request, "master_data.html", {"active_page": "master"})


@app.get("/dashboard", response_class=HTMLResponse)
async def page_dashboard(request: Request):
    return _render(request, "dashboard.html", {"active_page": "dashboard"})


@app.get("/settings", response_class=HTMLResponse)
async def page_settings(request: Request):
    return _render(request, "settings.html", {"active_page": "settings"})


# ========== 异常处理 ==========

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=400, content={"error": str(exc)})
    return _render(request, "error.html", {"error": str(exc)})


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
    return _render(request, "error.html", {"error": exc.detail})


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    msg = str(exc) if __debug__ else "Internal Server Error"
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=500, content={"error": msg})
    return _render(request, "error.html", {"error": msg})


# ========== API 路由 ==========

from .api import router as api_router  # noqa: E402
from .api_v2 import router as api_v2_router  # noqa: E402

app.include_router(api_router)
app.include_router(api_v2_router)
