"""
Office Contract Web UI — FastAPI 主入口
启动: uvicorn main:app --host 0.0.0.0 --port 8081
"""

import os
import sys
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

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

app = FastAPI(
    title="合同审批管理系统",
    version="1.0.0",
    description="销售合同审批工作流 Web UI",
)

# 静态文件
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# 模板
templates = Jinja2Templates(directory=TEMPLATES_DIR)


# ============================================================
# 启动事件：确保数据库存在
# ============================================================
@app.on_event("startup")
async def startup_event():
    """启动时初始化数据库（幂等）"""
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
    """仪表盘首页"""
    return templates.TemplateResponse(request, "dashboard.html", {
        "request": request,
        "active_page": "dashboard",
        "page_title": "仪表盘",
    })


@app.get("/contracts", response_class=HTMLResponse)
async def page_contracts(request: Request):
    """合同列表页"""
    return templates.TemplateResponse(request, "contract_list.html", {
        "request": request,
        "active_page": "contracts",
        "page_title": "合同列表",
    })


@app.get("/contracts/{contract_id}", response_class=HTMLResponse)
async def page_contract_detail(request: Request, contract_id: int):
    """合同详情页"""
    return templates.TemplateResponse(request, "contract_detail.html", {
        "request": request,
        "active_page": "contracts",
        "page_title": "合同详情",
        "contract_id": contract_id,
    })


@app.get("/new", response_class=HTMLResponse)
@app.get("/contracts/new", response_class=HTMLResponse)
async def page_new_contract(request: Request):
    """新建合同页"""
    return templates.TemplateResponse(request, "contract_new.html", {
        "request": request,
        "active_page": "new",
        "page_title": "新建合同",
    })


@app.get("/risk-rules", response_class=HTMLResponse)
async def page_risk_rules(request: Request):
    """风险规则页（可选）"""
    return templates.TemplateResponse(request, "risk_rules.html", {
        "request": request,
        "active_page": "risk_rules",
        "page_title": "风险规则",
    })


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok", "version": "1.0.0", "db": config.DB_PATH}


# 注册 API 路由
app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)
