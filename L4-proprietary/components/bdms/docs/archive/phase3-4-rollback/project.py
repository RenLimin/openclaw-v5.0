"""BDMS Web API — 项目管理路由。"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/project", tags=["project"])


class ProjectCreateRequest(BaseModel):
    project_name: str
    project_type: str = ""
    dept: str = ""
    pm: str = ""
    budget: float = 0.0
    start_date: str = ""
    end_date: str = ""
    created_by: str = ""


class OperatorRequest(BaseModel):
    operator: str = ""
    role: str = ""
    comment: str = ""


class MemberRequest(BaseModel):
    member_name: str
    role: str = ""
    allocation: float = 1.0


class RiskRequest(BaseModel):
    title: str
    description: str = ""
    risk_type: str = ""
    probability: str = "medium"
    impact: str = "medium"
    reporter: str = ""
    owner: str = ""


@router.get("/list")
async def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    pm: Optional[str] = None,
    keyword: Optional[str] = None,
):
    try:
        from bdms.modules.project_management.service import ProjectManagementService
        svc = ProjectManagementService()
        items, total = svc.list_projects(
            status=status, pm=pm, keyword=keyword,
            page=page, page_size=page_size,
        )
        return {"items": items, "total": total, "page": page, "page_size": page_size}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/{project_id}")
async def get_project(project_id: int):
    try:
        from bdms.modules.project_management.service import ProjectManagementService
        svc = ProjectManagementService()
        detail = svc.get_project_detail(project_id)
        if not detail or not detail.get("project"):
            raise HTTPException(404, f"项目 {project_id} 不存在")
        return detail
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/create")
async def create_project(req: ProjectCreateRequest):
    try:
        from bdms.modules.project_management.service import ProjectManagementService
        svc = ProjectManagementService()
        project_id = svc.create_project(
            project_name=req.project_name,
            project_type=req.project_type,
            dept=req.dept,
            pm=req.pm,
            budget=req.budget,
            start_date=req.start_date,
            end_date=req.end_date,
            created_by=req.created_by,
        )
        return {"id": project_id}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/{project_id}/start")
async def start_project(project_id: int, req: OperatorRequest):
    try:
        from bdms.modules.project_management.service import ProjectManagementService
        svc = ProjectManagementService()
        svc.start_project(project_id, operator=req.operator)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/{project_id}/submit-delivery")
async def submit_delivery(project_id: int, req: OperatorRequest):
    try:
        from bdms.modules.project_management.service import ProjectManagementService
        svc = ProjectManagementService()
        report_id = svc.submit_delivery(
            project_id, "monthly", req.comment or "交付报告", created_by=req.operator,
        )
        return {"report_id": report_id}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/{project_id}/accept")
async def accept_project(project_id: int, req: OperatorRequest):
    try:
        from bdms.modules.project_management.service import ProjectManagementService
        svc = ProjectManagementService()
        svc.accept_project(project_id, operator=req.operator, acceptance_report=req.comment)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/{project_id}/close")
async def close_project(project_id: int, req: OperatorRequest):
    try:
        from bdms.modules.project_management.service import ProjectManagementService
        svc = ProjectManagementService()
        svc.close_project(project_id, operator=req.operator, summary=req.comment)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/{project_id}/cancel")
async def cancel_project(project_id: int, req: OperatorRequest):
    try:
        from bdms.modules.project_management.service import ProjectManagementService
        svc = ProjectManagementService()
        svc.cancel_project(project_id, reason=req.comment, operator=req.operator)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/{project_id}/reactivate")
async def reactivate_project(project_id: int, req: OperatorRequest):
    try:
        from bdms.modules.project_management.service import ProjectManagementService
        svc = ProjectManagementService()
        svc.reactivate_project(project_id, operator=req.operator)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/{project_id}/add-member")
async def add_member(project_id: int, req: MemberRequest):
    try:
        from bdms.modules.project_management.engine import ProjectEngine
        engine = ProjectEngine()
        member_id = engine.add_team_member(
            project_id, req.member_name, req.role, req.allocation,
        )
        return {"member_id": member_id}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/{project_id}/report-risk")
async def report_risk(project_id: int, req: RiskRequest):
    try:
        from bdms.modules.project_management.risk.engine import RiskEngine
        engine = RiskEngine()
        risk_id = engine.report_risk(
            project_id, req.title, description=req.description,
            risk_type=req.risk_type, probability=req.probability,
            impact=req.impact, reporter=req.reporter, owner=req.owner,
        )
        return {"risk_id": risk_id}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/{project_id}/dashboard")
async def project_dashboard(project_id: int):
    try:
        from bdms.modules.project_management.service import ProjectManagementService
        svc = ProjectManagementService()
        return svc.get_project_dashboard(project_id)
    except Exception as e:
        raise HTTPException(500, str(e))
