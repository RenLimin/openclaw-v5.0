"""BDMS Web API — MVP Dashboard 路由。"""

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/dashboard/mvp", tags=["dashboard-mvp"])


@router.get("/{month}")
async def get_mvp_dashboard(month: str, refresh: bool = False):
    """获取 MVP 8 个核心指标。"""
    try:
        from bdms.modules.dashboard.service import DashboardService
        svc = DashboardService()
        if refresh:
            svc.refresh_snapshot(month)
        return svc.get_mvp_dashboard(month)
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/refresh")
async def refresh_mvp_snapshot(month: str):
    """强制刷新 MVP 快照。"""
    try:
        from bdms.modules.dashboard.service import DashboardService
        svc = DashboardService()
        return svc.refresh_snapshot(month)
    except Exception as e:
        raise HTTPException(500, str(e))
