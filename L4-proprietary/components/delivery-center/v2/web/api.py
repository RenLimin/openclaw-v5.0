"""BDMS v2 Web API 路由"""

import sys
from pathlib import Path
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from services.report_service import (
    generate_report_async, get_report_status, list_reports,
    get_report_file_path, get_report_summary, get_report_download_name,
)

router = APIRouter(prefix="/api")


# ========== 请求模型 ==========

class GenerateRequest(BaseModel):
    month: str  # YYYYMM 格式


class ReportJobResponse(BaseModel):
    id: int
    month: str
    status: str
    progress: int = 0
    file_path: Optional[str] = None
    error_msg: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


# ========== API 接口 ==========

@router.get("/reports", response_model=List[ReportJobResponse])
async def get_report_list(limit: int = 20):
    """月报列表 - 按创建时间倒序"""
    jobs = list_reports(limit=limit)
    return jobs


@router.post("/reports/generate")
async def generate_report(req: GenerateRequest):
    """触发生成月报（异步任务）

    返回 job_id，用 /api/reports/{id}/status 轮询进度
    """
    # 校验月份格式
    if not req.month or len(req.month) != 6 or not req.month.isdigit():
        raise HTTPException(status_code=400, detail="月份格式错误，应为 YYYYMM，如 202606")

    year = int(req.month[:4])
    month = int(req.month[4:])
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="月份范围错误，应为 01-12")
    if year < 2020 or year > 2100:
        raise HTTPException(status_code=400, detail="年份范围不合理")

    try:
        job_id = generate_report_async(req.month)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成任务创建失败: {e}")

    return {
        "job_id": job_id,
        "month": req.month,
        "status": "pending",
        "message": "报告生成任务已提交",
    }


@router.get("/reports/{report_id}/status")
async def get_status(report_id: int):
    """查询生成状态"""
    job = get_report_status(report_id)
    if not job:
        raise HTTPException(status_code=404, detail="报告任务不存在")
    return job


@router.get("/reports/{report_id}/download")
async def download_report(report_id: int):
    """下载月报 Excel 文件"""
    file_path = get_report_file_path(report_id)
    if not file_path:
        job = get_report_status(report_id)
        if not job:
            raise HTTPException(status_code=404, detail="报告任务不存在")
        if job["status"] != "completed":
            raise HTTPException(status_code=400, detail=f"报告尚未生成完成，当前状态: {job['status']}")
        raise HTTPException(status_code=404, detail="报告文件不存在")

    filename = get_report_download_name(report_id)
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/reports/{report_id}/summary")
async def get_summary(report_id: int):
    """月报概要数据（用于预览页）"""
    summary = get_report_summary(report_id)
    if not summary:
        raise HTTPException(status_code=404, detail="报告任务不存在")
    return summary
