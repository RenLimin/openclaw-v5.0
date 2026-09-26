# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""BDMS Web API v2.1 — 新模块路由（project / profit / integration / dashboard-v2）。

对齐各模块 DESIGN-DETAIL 的 Web API 定义。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from bdms.core import db as _db
from bdms.core.db import get_connection
from bdms.modules.base import BDMSBaseError, NotFoundError, ValidationError

router = APIRouter(prefix="/api/v2")


def _svc_project(db_path=None):
    from bdms.modules.project_management import ProjectManagementService
    return ProjectManagementService(db_path=db_path)


def _svc_profit(db_path=None):
    from bdms.modules.profit_management import ProfitService
    return ProfitService(db_path=db_path)


def _svc_integration(db_path=None):
    from bdms.modules.integration import IntegrationService
    return IntegrationService(db_path=db_path)


def _svc_dash_custom(db_path=None):
    from bdms.modules.dashboard import DashboardCustomizationService
    return DashboardCustomizationService(db_path=db_path)


# ============================================================
# 项目管理
# ============================================================

@router.get("/projects")
async def list_projects(
    status: Optional[str] = None,
    pm: Optional[str] = None,
    keyword: Optional[str] = None,
    impl_status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    svc = _svc_project()
    items, total = svc.engine.list_projects(
        status=status, pm=pm, keyword=keyword,
        impl_status=impl_status, page=page, page_size=page_size)
    return {"items": items, "total": total, "page": page}


@router.post("/projects")
async def create_project(body: dict):
    svc = _svc_project()
    try:
        pid = svc.create_project(**body)
        return {"id": pid}
    except ValidationError as e:
        raise HTTPException(400, str(e))
    except (TypeError, ValueError) as e:
        raise HTTPException(400, str(e))


@router.get("/projects/{project_id}")
async def get_project(project_id: int):
    svc = _svc_project()
    try:
        return svc.get_project_detail(project_id)
    except Exception as e:
        raise HTTPException(404, str(e))


@router.get("/projects/{project_id}/dashboard")
async def project_dashboard(project_id: int):
    svc = _svc_project()
    try:
        return svc.get_project_dashboard(project_id)
    except Exception as e:
        raise HTTPException(404, str(e))


@router.post("/projects/{project_id}/transition")
async def transition_project(project_id: int, body: dict):
    """状态推进。body: {"to_state": "...", "operator": "..."}"""
    svc = _svc_project()
    try:
        new_state = svc.engine.transition_state(
            project_id, body["to_state"],
            operator=body.get("operator", "web"))
        return {"status": new_state}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/projects/{project_id}/after-sales")
async def after_sales_summary(project_id: int):
    svc = _svc_project()
    try:
        return svc.get_after_sales_summary(project_id)
    except Exception as e:
        raise HTTPException(404, str(e))


# ============================================================
# 项目利润
# ============================================================

@router.get("/profit/report/{project_id}")
async def profit_report(project_id: int, period: str):
    svc = _svc_profit()
    try:
        return svc.get_profit_report(project_id, period)
    except Exception as e:
        raise HTTPException(404, str(e))


@router.get("/profit/projects")
async def profit_projects(
    period: str,
    dept: Optional[str] = None,
    sort_by: str = "profit_margin",
    page: int = 1,
    page_size: int = 50,
):
    svc = _svc_profit()
    return svc.list_projects_profit(
        period, dept=dept, sort_by=sort_by, page=page, page_size=page_size)


@router.get("/profit/alerts/{project_id}")
async def profit_alerts(project_id: int, threshold: float = 0.10):
    from bdms.modules.profit_management import ProfitEngine
    engine = ProfitEngine()
    try:
        return {"alerts": engine.check_budget_alert(project_id, threshold)}
    except Exception as e:
        raise HTTPException(404, str(e))


# ============================================================
# 数据集成
# ============================================================

@router.get("/integration/connectors")
async def integration_connectors():
    svc = _svc_integration()
    return {"connectors": svc.list_connectors()}


@router.get("/integration/connectors/{name}/status")
async def integration_connector_status(name: str):
    svc = _svc_integration()
    try:
        return svc.get_connector_status(name)
    except KeyError:
        raise HTTPException(404, f"未知连接器: {name}")


@router.post("/integration/sync/{connector_name}")
async def integration_sync(connector_name: str, body: dict = None):
    svc = _svc_integration()
    body = body or {}
    try:
        return svc.sync(connector_name, **body)
    except KeyError:
        raise HTTPException(404, f"未知连接器: {connector_name}")
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/integration/history")
async def integration_history(
    connector_name: Optional[str] = None,
    limit: int = 20,
):
    svc = _svc_integration()
    return {"history": svc.get_sync_history(connector_name, limit=limit)}


# ============================================================
# 驾驶舱 v2（视图管理）
# ============================================================

@router.get("/dashboard/views")
async def dashboard_views(user_id: str = "default"):
    svc = _svc_dash_custom()
    return {"views": svc.list_views(user_id)}


@router.post("/dashboard/views")
async def create_dashboard_view(body: dict):
    svc = _svc_dash_custom()
    try:
        return svc.create_view(
            body.get("user_id", "default"),
            body["view_name"],
            body.get("config", {}),
            set_default=body.get("set_default", False))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/dashboard/views/default")
async def dashboard_default_view(user_id: str = "default"):
    svc = _svc_dash_custom()
    return svc.get_default_view(user_id)


@router.get("/dashboard/views/{view_id}")
async def get_dashboard_view(view_id: str):
    svc = _svc_dash_custom()
    view = svc.get_view(view_id)
    if not view:
        raise HTTPException(404, f"视图 {view_id} 不存在")
    return view


@router.put("/dashboard/views/{view_id}")
async def update_dashboard_view(view_id: str, body: dict):
    svc = _svc_dash_custom()
    try:
        return svc.update_view(view_id, body.get("config", {}))
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/dashboard/views/{view_id}")
async def delete_dashboard_view(view_id: str):
    svc = _svc_dash_custom()
    try:
        return svc.delete_view(view_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/dashboard/views/{view_id}/set-default")
async def set_default_view(view_id: str, body: dict):
    svc = _svc_dash_custom()
    try:
        return svc.set_default_view(view_id, body.get("user_id", "default"))
    except ValueError as e:
        raise HTTPException(400, str(e))
