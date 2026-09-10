"""BDMS v2 Web UI — FastAPI 主应用"""

import sys
from pathlib import Path
from datetime import date

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

sys.path.insert(0, str(BASE_DIR.parent))
from services.report_service import list_reports, get_report_status

app = FastAPI(
    title="BDMS v2 — 交付月报管理系统",
    version="2.0.0",
    description="Bangcle 交付管理系统 v2 — 月报生成与管理",
)

# 静态文件
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 模板
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ========== 页面路由 ==========

@app.get("/", response_class=HTMLResponse)
async def report_list_page(request: Request):
    """月报列表页（首页）"""
    reports = list_reports(limit=50)
    # 格式化日期
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
