"""
core/webui.py — Jinja2 Web UI
提供看板 + 项目视图 + 模块列表页面。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# 模板目录
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
STATIC_DIR = Path(__file__).parent.parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _get_registry(request: Request):
    """从 app state 获取 registry。"""
    return request.app.state.registry if hasattr(request.app.state, "registry") else None


def _get_db(request: Request):
    """从 app state 获取 db。"""
    return request.app.state.db if hasattr(request.app.state, "db") else None


def register_webui_routes(app, registry, db) -> None:
    """注册 Web UI 路由。"""

    # 挂载静态文件
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # 将 registry/db 存入 app.state
    app.state.registry = registry
    app.state.db = db

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def page_dashboard(request: Request):
        """看板主页。"""
        modules = []
        try:
            modules = [
                {"name": m.name, "version": m.version, "description": m.description}
                for m in registry.list_modules()
            ]
        except Exception:
            pass
        return templates.TemplateResponse(request=request, name="dashboard.html", context={
            "request": request,
            "modules": modules,
            "module_count": len(modules),
        })

    @app.get("/projects", response_class=HTMLResponse, include_in_schema=False)
    async def page_projects(request: Request):
        """项目列表页。"""
        projects = []
        try:
            mod = registry.get("project")
            if mod:
                projects = mod.list_projects()
        except Exception:
            pass
        return templates.TemplateResponse(request=request, name="projects.html", context={
            "request": request,
            "projects": projects,
        })

    @app.get("/projects/{project_id}", response_class=HTMLResponse, include_in_schema=False)
    async def page_project_detail(request: Request, project_id: str):
        """项目详情页（管理视图：跨 tenant 查询）。"""
        project = None
        tasks = []
        milestones = []
        deliverables = []
        risks = []
        try:
            from core.saas import TenantContext as _tc
            _old = _tc.current()
            _tc.set("system")
            try:
                p_mod = registry.get("project")
                if p_mod and hasattr(p_mod, '_repo'):
                    project = p_mod._repo.get_by_id_ignore_tenant(project_id)
                t_mod = registry.get("task")
                if t_mod:
                    tasks = [t for t in t_mod.list_tasks() if getattr(t, "project_id", "") == project_id]
                m_mod = registry.get("milestone")
                if m_mod:
                    milestones = [m for m in m_mod.list_milestones() if getattr(m, "project_id", "") == project_id]
                d_mod = registry.get("deliverable")
                if d_mod:
                    deliverables = [d for d in d_mod.list_deliverables() if getattr(d, "project_id", "") == project_id]
                r_mod = registry.get("risk")
                if r_mod:
                    risks = [r for r in r_mod.list_risks() if getattr(r, "project_id", "") == project_id]
            finally:
                _tc.set(_old)
        except Exception:
            pass
        return templates.TemplateResponse(request=request, name="project_detail.html", context={
            "request": request,
            "project": project,
            "tasks": tasks,
            "milestones": milestones,
            "deliverables": deliverables,
            "risks": risks,
        })

    @app.get("/modules", response_class=HTMLResponse, include_in_schema=False)
    async def page_modules(request: Request):
        """模块管理页。"""
        modules = []
        try:
            modules = [
                {"name": m.name, "version": m.version, "description": m.description,
                 "tables": m.tables, "dependencies": m.dependencies}
                for m in registry.list_modules()
            ]
        except Exception:
            pass
        return templates.TemplateResponse(request=request, name="modules.html", context={
            "request": request,
            "modules": modules,
        })
