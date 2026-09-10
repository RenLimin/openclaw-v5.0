"""
Office Contract Web UI — FastAPI 主入口
基于 L2 web-common 组件库构建
"""

import os
import sys
import importlib.util
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import FileSystemLoader

# 模块路径
_WEB_DIR = os.path.dirname(os.path.abspath(__file__))
_MODULE_DIR = os.path.dirname(_WEB_DIR)
if _MODULE_DIR not in sys.path:
    sys.path.insert(0, _MODULE_DIR)

from office_contract.web.api import router as api_router
from office_contract.services import init_db
from office_contract import config

# 路径
STATIC_DIR = os.path.join(_WEB_DIR, "static")
TEMPLATES_DIR = os.path.join(_WEB_DIR, "templates")

# ── L2 web-common 组件库 ──
# 从 openclaw-v5.0 根目录定位 web-common
_PROJECT_ROOT = Path(_WEB_DIR).resolve().parents[5]  # openclaw-v5.0/
_WEB_COMMON_DIR = _PROJECT_ROOT / "L2-infra" / "components" / "web-common"
_WEB_COMMON_MACROS = _WEB_COMMON_DIR / "macros"
_WEB_COMMON_STATIC = _WEB_COMMON_DIR / "static"

app = FastAPI(
    title="合同审批管理系统",
    version="1.0.0",
    description="销售合同审批工作流 Web UI",
)

# ── 静态资源 ──
# 业务特有静态资源
app.mount("/static/app", StaticFiles(directory=STATIC_DIR), name="static-app")
# web-common 通用静态资源
app.mount("/static/web-common", StaticFiles(directory=str(_WEB_COMMON_STATIC)), name="web-common-static")

# ── Jinja2 模板：业务模板 + web-common 宏 ──
templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.loader = FileSystemLoader([TEMPLATES_DIR, str(_WEB_COMMON_MACROS)])

# 全局模板变量（所有页面共用）
templates.env.globals.update({
    "brand_name": "合同审批",
    "brand_icon": "📋",
    "storage_key": "contract-ui-theme",
    "sidebar_items": [
        {
            "title": "概览",
            "items": [
                {"id": "dashboard", "label": "仪表盘", "url": "/", "icon": "📊"},
            ]
        },
        {
            "title": "合同管理",
            "items": [
                {"id": "contracts", "label": "合同列表", "url": "/contracts", "icon": "📄"},
                {"id": "new", "label": "新建合同", "url": "/new", "icon": "➕"},
            ]
        },
        {
            "title": "风险管理",
            "items": [
                {"id": "risk_rules", "label": "风险规则", "url": "/risk-rules", "icon": "⚠️"},
            ]
        },
    ],
})


# ============================================================
# 启动事件
# ============================================================
@app.on_event("startup")
async def startup_event():
    try:
        init_db()
    except Exception as e:
        print(f"[WARN] DB init: {e}")


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


# ============================================================
# 页面路由
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def page_dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", {
        "request": request,
        "active_page": "dashboard",
    })


@app.get("/contracts", response_class=HTMLResponse)
async def page_contracts(request: Request):
    return templates.TemplateResponse(request, "contract_list.html", {
        "request": request,
        "active_page": "contracts",
    })


@app.get("/contracts/{contract_id}", response_class=HTMLResponse)
async def page_contract_detail(request: Request, contract_id: int):
    return templates.TemplateResponse(request, "contract_detail.html", {
        "request": request,
        "active_page": "contracts",
        "contract_id": contract_id,
    })


@app.get("/new", response_class=HTMLResponse)
@app.get("/contracts/new", response_class=HTMLResponse)
async def page_new_contract(request: Request):
    return templates.TemplateResponse(request, "contract_new.html", {
        "request": request,
        "active_page": "new",
    })


@app.get("/risk-rules", response_class=HTMLResponse)
async def page_risk_rules(request: Request):
    return templates.TemplateResponse(request, "risk_rules.html", {
        "request": request,
        "active_page": "risk_rules",
    })


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0", "db": config.DB_PATH}


app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)
