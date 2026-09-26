"""BDMS Web API — 合同管理路由。"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/contract", tags=["contract"])


class ContractCreateRequest(BaseModel):
    title: str
    party_a: str = ""
    party_b: str = ""
    amount: float = 0.0
    contract_type: str = ""
    effective_date: str = ""
    expiry_date: str = ""
    operator: str = ""


class ApproveRequest(BaseModel):
    operator: str = ""
    role: str = ""
    comment: str = ""


@router.get("/list")
async def list_contracts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    keyword: Optional[str] = None,
):
    try:
        from bdms.modules.contract_management.service import ContractManagementService
        svc = ContractManagementService()
        filters = {}
        if status:
            filters["status"] = status
        if keyword:
            filters["keyword"] = keyword
        result = svc.list_contracts(filters, page=page, page_size=page_size)
        return result
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/{contract_id}")
async def get_contract(contract_id: int):
    try:
        from bdms.modules.contract_management.service import ContractManagementService
        svc = ContractManagementService()
        detail = svc.get_contract(contract_id)
        if not detail:
            raise HTTPException(404, f"合同 {contract_id} 不存在")
        return detail
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/create")
async def create_contract(req: ContractCreateRequest):
    try:
        from bdms.modules.contract_management.service import ContractManagementService
        svc = ContractManagementService()
        result = svc.create_contract(
            data={
                "title": req.title,
                "party_a": req.party_a,
                "party_b": req.party_b,
                "amount": req.amount,
                "contract_type": req.contract_type,
                "effective_date": req.effective_date,
                "expiry_date": req.expiry_date,
            },
            operator=req.operator,
        )
        return result
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/{contract_id}/submit")
async def submit_contract(contract_id: int, req: ApproveRequest):
    try:
        from bdms.modules.contract_management.service import ContractManagementService
        svc = ContractManagementService()
        return svc.submit_approval(contract_id, operator=req.operator)
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/{contract_id}/approve")
async def approve_contract(contract_id: int, req: ApproveRequest):
    try:
        from bdms.modules.contract_management.service import ContractManagementService
        svc = ContractManagementService()
        return svc.approve(contract_id, operator=req.operator, role=req.role, comment=req.comment)
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/{contract_id}/reject")
async def reject_contract(contract_id: int, req: ApproveRequest):
    try:
        from bdms.modules.contract_management.service import ContractManagementService
        svc = ContractManagementService()
        return svc.reject(contract_id, operator=req.operator, role=req.role, comment=req.comment)
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/{contract_id}/sign")
async def sign_contract(contract_id: int, req: ApproveRequest):
    try:
        from bdms.modules.contract_management.service import ContractManagementService
        svc = ContractManagementService()
        return svc.sign(contract_id, operator=req.operator)
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/{contract_id}/archive")
async def archive_contract(contract_id: int, req: ApproveRequest):
    try:
        from bdms.modules.contract_management.service import ContractManagementService
        svc = ContractManagementService()
        return svc.archive(contract_id, operator=req.operator)
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/{contract_id}/risks")
async def get_risks(contract_id: int):
    try:
        from bdms.modules.contract_management.service import ContractManagementService
        svc = ContractManagementService()
        return svc.scan_risks(contract_id)
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/{contract_id}/audit-log")
async def get_audit_log(contract_id: int):
    try:
        from bdms.modules.contract_management.service import ContractManagementService
        svc = ContractManagementService()
        return svc.audit_log(contract_id)
    except Exception as e:
        raise HTTPException(500, str(e))
