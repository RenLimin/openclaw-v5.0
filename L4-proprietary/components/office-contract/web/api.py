"""
合同审批 Web API — FastAPI 路由
基于 Service 层封装，不重复业务逻辑。
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import sys
import os

# 导入 service 层
_WEB_DIR = os.path.dirname(os.path.abspath(__file__))
_MODULE_DIR = os.path.dirname(_WEB_DIR)
if _MODULE_DIR not in sys.path:
    sys.path.insert(0, _MODULE_DIR)

from services import (
    init_db,
    create_contract,
    get_contract,
    list_contracts,
    list_contracts_paged,
    submit_for_approval,
    approve,
    reject,
    update_contract,
    risk_scan,
    get_stats,
    get_history,
    get_approval_level,
)
import config

router = APIRouter(prefix="/api", tags=["contracts"])


# ============================================================
# Pydantic Schemas
# ============================================================

class ContractCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    party_b: str = Field(..., min_length=1, max_length=200)
    amount: float = Field(..., gt=0)
    contract_type: str = "tech_service"
    effective_date: Optional[str] = None
    expiry_date: Optional[str] = None
    party_a: Optional[str] = None
    operator: str = "web-user"


class ContractUpdate(BaseModel):
    title: Optional[str] = None
    party_b: Optional[str] = None
    amount: Optional[float] = None
    contract_type: Optional[str] = None
    effective_date: Optional[str] = None
    expiry_date: Optional[str] = None
    party_a: Optional[str] = None


class ApproveRequest(BaseModel):
    approver_name: str = Field(..., min_length=1)
    approver_role: str = Field(..., min_length=1)
    comment: str = ""


class RejectRequest(BaseModel):
    approver_name: str = Field(..., min_length=1)
    approver_role: str = Field(..., min_length=1)
    comment: str = Field(..., min_length=1)


# ============================================================
# API Endpoints
# ============================================================

@router.get("/stats")
async def api_stats():
    """统计数据"""
    try:
        return get_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contracts")
async def api_list_contracts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    party_b: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
):
    """合同列表（分页+筛选）"""
    try:
        return list_contracts_paged(
            page=page, page_size=page_size,
            status=status, party_b=party_b,
            min_amount=min_amount, max_amount=max_amount,
            date_from=date_from, date_to=date_to,
            sort_by=sort_by, sort_order=sort_order,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/contracts", status_code=201)
async def api_create_contract(data: ContractCreate):
    """创建合同"""
    try:
        result = create_contract(
            title=data.title,
            party_b=data.party_b,
            amount=data.amount,
            contract_type=data.contract_type,
            effective_date=data.effective_date,
            expiry_date=data.expiry_date,
            operator=data.operator,
            party_a=data.party_a,
        )
        return {"id": result["id"], **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contracts/{contract_id}")
async def api_get_contract(contract_id: int):
    """合同详情"""
    try:
        result = get_contract(contract_id)
        if not result:
            raise HTTPException(status_code=404, detail="合同不存在")
        # 添加审批层级信息
        amount = result["contract"]["amount"]
        level = get_approval_level(amount)
        result["approval_level"] = level
        from config import OFFICE_APPROVAL_ROLES, APPROVAL_SLA_DAYS
        result["approval_roles"] = OFFICE_APPROVAL_ROLES.get(level, [])
        result["sla_days"] = APPROVAL_SLA_DAYS.get(level, 0)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/contracts/{contract_id}")
async def api_update_contract(contract_id: int, data: ContractUpdate):
    """更新合同"""
    try:
        result = update_contract(contract_id, **data.model_dump(exclude_none=True))
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/contracts/{contract_id}/submit")
async def api_submit(contract_id: int):
    """提交审批"""
    try:
        result = submit_for_approval(contract_id, operator="web-user")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/contracts/{contract_id}/approve")
async def api_approve(contract_id: int, data: ApproveRequest):
    """审批通过"""
    try:
        result = approve(
            contract_id,
            approver_name=data.approver_name,
            approver_role=data.approver_role,
            comment=data.comment,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/contracts/{contract_id}/reject")
async def api_reject(contract_id: int, data: RejectRequest):
    """审批驳回"""
    try:
        result = reject(
            contract_id,
            approver_name=data.approver_name,
            approver_role=data.approver_role,
            comment=data.comment,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contracts/{contract_id}/history")
async def api_history(contract_id: int):
    """审批历史"""
    try:
        result = get_history(contract_id)
        if not result:
            raise HTTPException(status_code=404, detail="合同不存在")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contracts/{contract_id}/risk-scan")
async def api_risk_scan(contract_id: int):
    """风险扫描结果"""
    try:
        result = risk_scan(contract_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def api_health():
    """健康检查"""
    return {"status": "ok", "component": "office-contract-web", "db": config.DB_PATH}
