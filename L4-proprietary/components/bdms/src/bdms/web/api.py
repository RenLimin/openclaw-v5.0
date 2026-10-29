"""BDMS Web API 路由。

按模块分组：
  /api/report/*       交付月报
  /api/revenue/*      确认收入
  /api/master-data/*  基础数据
  /api/dashboard/*    统计看板
  /api/settings/*     系统设定
"""

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from bdms.core import db as _db
from bdms.core.db import normalize_month

router = APIRouter(prefix="/api")


# ========== 请求模型 ==========

class GenerateRequest(BaseModel):
    month: str
    mode: str = "auto"


class SettingUpdate(BaseModel):
    key: str
    value: Any


class DriftQuery(BaseModel):
    month: str
    dimension: str
    value: str
    sheet: str = "签约"


# ========== 1. 交付月报 ==========

@router.get("/report/months")
async def report_months():
    from bdms.modules.delivery_report.service import DeliveryReportService
    return {"months": DeliveryReportService().list_months()}


@router.get("/report/generate-progress/{job_id}")
async def report_generate_progress(job_id: int):
    from bdms.core import db as _db
    from bdms.core.db import get_connection
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM job WHERE id = ?", (job_id,)
        ).fetchone()
        if row:
            return dict(row)
        return {"id": job_id, "status": "not_found"}
    finally:
        conn.close()


class GenerateRequest(BaseModel):
    month: str
    mode: str = "auto"  # auto | read | regenerate
    refetch_sources: bool = True  # 默认从源系统重新拉取原始数据


@router.post("/report/generate")
async def report_generate(req: GenerateRequest):
    """生成月报（异步）— 立即返回 job_id，后台执行，前端轮询进度。

    进度条铁律：>10s 的操作必须有实时进度条。
    """
    import threading
    from bdms.modules.delivery_report.service import DeliveryReportService
    from bdms.core import db as _db

    month = normalize_month(req.month)
    mode = req.mode
    refetch = req.refetch_sources

    # 先创建 job，立即返回 job_id（让前端马上能轮询进度）
    conn = _db.get_connection()
    try:
        job_id = _db.create_job(conn, "delivery_report", month, mode)
        conn.commit()
    finally:
        conn.close()

    # 后台线程执行生成
    def _run():
        try:
            svc = DeliveryReportService()
            svc.generate_with_job(job_id, month, mode, refetch_sources=refetch)
        except Exception as e:
            conn2 = _db.get_connection()
            try:
                _db.update_job_status(conn2, job_id, "failed", 0,
                                      message=str(e)[:500],
                                      finished_at="datetime('now','localtime')")
                # 手动设置 finished_at 用 SQL 函数有坑，这里重新更新一下
                conn2.execute(
                    "UPDATE job SET status='failed', progress=0, message=?, "
                    "finished_at=datetime('now','localtime') WHERE id=?",
                    (str(e)[:500], job_id))
                conn2.commit()
            finally:
                conn2.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    return {"job_id": job_id, "month": month, "mode": mode,
            "status": "running", "progress": 0, "message": "已提交，准备生成..."}


@router.get("/report/export/{month}")
async def report_export(month: str):
    month = normalize_month(month)
    from bdms.modules.delivery_report.exporter import DeliveryReportExporter
    try:
        path = DeliveryReportExporter().export(month)
    except Exception as e:
        raise HTTPException(500, str(e))
    return FileResponse(path, filename=f"交付月报_{month}.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.get("/report/export-sheet/{month}/{sheet}")
async def report_export_sheet(month: str, sheet: str, search: str = ""):
    """导出单个 Sheet 为 CSV（支持搜索过滤）。"""
    import io
    import csv
    month = normalize_month(month)
    from bdms.modules.delivery_report.engine import DeliveryReportEngine
    from bdms.modules.delivery_report.calibration import CalibrationService
    engine = DeliveryReportEngine()
    raw = engine.load(month)
    if sheet not in raw:
        raise HTTPException(404, f"{month} 无 {sheet} 数据")
    # BR-07：导出与浏览同口径，统一经校准解析层
    eff_all = CalibrationService().apply_overlays(month, raw)
    data = {k: v for k, v in eff_all.items()
            if not str(k).startswith("__")}
    df = data[sheet]
    
    # 搜索过滤
    if search and search.strip():
        keyword = search.strip()
        mask = df.apply(
            lambda row: any(keyword.lower() in str(v).lower() for v in row.values),
            axis=1
        )
        df = df[mask]
    
    # 导出 CSV
    output = io.StringIO()
    df.fillna("").to_csv(output, index=False, quoting=csv.QUOTE_ALL)
    content = output.getvalue().encode('utf-8-sig')
    
    from fastapi.responses import Response
    filename = f"{month}_{sheet}{'_筛选' if search else ''}.csv"
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""}
    )




# ========== 人机协作审核 API ==========

class ReviewApproveRequest(BaseModel):
    reviewer: str = ""

class ReviewRejectRequest(BaseModel):
    reason: str = ""
    reviewer: str = ""


@router.get("/report/review-status/{month}")
async def report_review_status(month: str):
    """获取某月审核状态。"""
    month = normalize_month(month)
    from bdms.modules.delivery_report.service import DeliveryReportService
    return DeliveryReportService().get_review_status(month)


@router.get("/report/review-months")
async def report_review_months():
    """列出所有已生成月份的审核状态。"""
    from bdms.modules.delivery_report.service import DeliveryReportService
    return {"months": DeliveryReportService().list_review_months()}


@router.get("/report/review-issues/{month}")
async def report_review_issues(month: str, status_filter: str = None):
    """列出某月的校验问题。"""
    month = normalize_month(month)
    from bdms.modules.delivery_report.service import DeliveryReportService
    return DeliveryReportService().list_review_issues(month, status_filter)


@router.post("/report/review-approve/{month}")
async def report_review_approve(month: str, req: ReviewApproveRequest):
    """人工审批通过。"""
    month = normalize_month(month)
    from bdms.modules.delivery_report.service import DeliveryReportService
    try:
        return DeliveryReportService().approve_review(month, req.reviewer)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/report/review-reject/{month}")
async def report_review_reject(month: str, req: ReviewRejectRequest):
    """人工驳回。"""
    month = normalize_month(month)
    from bdms.modules.delivery_report.service import DeliveryReportService
    try:
        return DeliveryReportService().reject_review(month, req.reason, req.reviewer)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/report/revalidate/{month}")
async def report_revalidate(month: str):
    """人工触发重新校验。"""
    month = normalize_month(month)
    from bdms.modules.delivery_report.service import DeliveryReportService
    return DeliveryReportService().revalidate(month)


@router.get("/report/compare/{month}")
async def report_compare(month: str):
    """与手工报表逐项对比。"""
    month = normalize_month(month)
    from bdms.modules.delivery_report.service import DeliveryReportService
    try:
        return DeliveryReportService().compare_with_manual(month)
    except Exception as e:
        raise HTTPException(500, str(e))


class IssueResolveRequest(BaseModel):
    action: str  # confirm | reject
    operator: str = ""


class IssueBatchResolveRequest(BaseModel):
    issue_ids: list[int]
    action: str  # confirm | reject
    operator: str = ""


@router.post("/report/review-issues/{month}/{issue_id}/resolve")
async def report_resolve_issue(month: str, issue_id: int, req: IssueResolveRequest):
    """单条 issue 状态流转：confirm（确认）或 reject（驳回/误报）。"""
    month = normalize_month(month)
    from bdms.modules.delivery_report.service import DeliveryReportService
    try:
        return DeliveryReportService().resolve_issue(
            month, issue_id, req.action, req.operator)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/report/review-issues/{month}/batch-resolve")
async def report_batch_resolve_issues(month: str, req: IssueBatchResolveRequest):
    """批量处理 issue。"""
    month = normalize_month(month)
    from bdms.modules.delivery_report.service import DeliveryReportService
    try:
        return DeliveryReportService().batch_resolve_issues(
            month, req.issue_ids, req.action, req.operator)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ========== 人工校准 API（v1.0）==========

class CalibrationRequest(BaseModel):
    sheet: str
    row_index: int
    column_name: str
    corrected_value: str
    reason: str
    operator: str = "gateway-owner"
    issue_id: Optional[int] = None


class CalibrationRevokeRequest(BaseModel):
    sheet: str
    row_index: int
    column_name: str
    operator: str = "gateway-owner"


@router.post("/report/calibrations/{month}")
async def report_calibration_submit(month: str, req: CalibrationRequest):
    """提交/修改校准；小批量同步重校验，大批量返回 job_id 走轮询。"""
    month = normalize_month(month)
    from bdms.modules.delivery_report.calibration import (
        CalibrationService, CalibrationError)
    from bdms.modules.delivery_report.service import (
        DeliveryReportService, SYNC_LIMIT)
    try:
        result = CalibrationService().upsert(
            month, req.sheet, req.row_index, req.column_name,
            req.corrected_value, req.reason, req.operator, req.issue_id)
    except CalibrationError as e:
        # to_dict() 返回 {"detail": {...}}；HTTPException 会再包一层，
        # 这里取内层保证响应体为 {"detail": {"code", "message"}}（对齐 §4.9）
        raise HTTPException(400, detail=e.to_dict()["detail"]
                            if hasattr(e, "to_dict") else str(e))

    affected = [(req.sheet, req.row_index)]
    if len(affected) <= SYNC_LIMIT:
        recalc = DeliveryReportService().recalculate_after_calibration(
            month, affected, operator=req.operator)
        return {"ok": True, "calibration": result, "recalculation": recalc}
    else:
        async_result = DeliveryReportService().recalculate_after_calibration_async(
            month, affected, operator=req.operator)
        return {"ok": True, "calibration": result, **async_result}


@router.post("/report/calibrations/{month}/revoke")
async def report_calibration_revoke(month: str, req: CalibrationRevokeRequest):
    """撤销校准（同步重校验）。"""
    month = normalize_month(month)
    from bdms.modules.delivery_report.calibration import (
        CalibrationService, CalibrationError)
    from bdms.modules.delivery_report.service import DeliveryReportService
    try:
        result = CalibrationService().revoke(
            month, req.sheet, req.row_index, req.column_name, req.operator)
    except CalibrationError as e:
        raise HTTPException(400, detail=str(e))
    recalc = DeliveryReportService().recalculate_after_calibration(
        month, [(req.sheet, req.row_index)], operator=req.operator)
    return {"ok": True, "calibration": result, "recalculation": recalc}


@router.get("/report/calibrations/{month}")
async def report_calibration_list(month: str, sheet: str = None,
                                  row_index: int = None, status: str = None):
    """查询校准记录（支持 sheet/row/status 过滤）。"""
    month = normalize_month(month)
    from bdms.modules.delivery_report.calibration import CalibrationService
    return CalibrationService().list_calibrations(
        month, sheet=sheet, row_index=row_index, status=status)


@router.get("/report/calibrations/{month}/overview")
async def report_calibration_overview(month: str):
    """校准总览/KPI。"""
    month = normalize_month(month)
    from bdms.modules.delivery_report.calibration import CalibrationService
    return CalibrationService().overview(month)


@router.get("/report/sheets/{month}")
async def report_sheets(month: str):
    """动态返回当月实际 Sheet 列表（补齐 15 个，供数据浏览下拉）。"""
    month = normalize_month(month)
    conn = _db.get_connection()
    try:
        rows = conn.execute(
            "SELECT sheet, row_count FROM dr_sheet_meta "
            "WHERE month = ? ORDER BY rowid", (month,)
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        raise HTTPException(404, f"{month} 无 Sheet 数据")
    return {"month": month,
            "sheets": [{"name": r["sheet"], "rows": r["row_count"]} for r in rows]}


@router.get("/report/enum-options/{month}/{sheet}/{column}")
async def report_enum_options(month: str, sheet: str, column: str):
    """枚举列合法值（校准对话框下拉数据源，DESIGN-DETAIL §4.6）。

    仅对 ENUM_COLS 映射列返回非空 options；非映射列返回空数组，
    前端据此渲染 <input> 而非 <select>。
    """
    month = normalize_month(month)
    from bdms.modules.delivery_report.validator import get_enum_options
    options = get_enum_options(None, sheet, column)  # None → 默认生产库路径
    return {"month": month, "sheet": sheet, "column": column,
            "options": options}


@router.get("/report/calibration-ledger/{month}")
async def report_calibration_ledger(month: str, format: str = "json"):
    """校准台账（JSON 预览 / xlsx 导出）。"""
    month = normalize_month(month)
    from bdms.modules.delivery_report.calibration import CalibrationService
    rows = CalibrationService().ledger_rows(month)
    columns = ["月份", "Sheet", "行号", "列名", "原始值", "校准值",
               "操作人", "校准时间", "校准原因", "状态"]
    if format == "xlsx":
        import io
        import pandas as pd
        from fastapi.responses import Response
        buf = io.BytesIO()
        df = pd.DataFrame(rows, columns=columns)
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="校准台账")
        buf.seek(0)
        filename = f"校准台账_{month}.xlsx"
        return Response(
            content=buf.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    return {"month": month, "columns": columns, "rows": rows}


@router.get("/report/data/{month}/{sheet}")
async def report_data(month: str, sheet: str, page: int = 1, page_size: int = 50, search: str = ""):
    """获取某月某 Sheet 的数据（分页 + 搜索）。"""
    month = normalize_month(month)
    from bdms.modules.delivery_report.engine import DeliveryReportEngine
    from bdms.modules.delivery_report.calibration import CalibrationService
    engine = DeliveryReportEngine()
    raw = engine.load(month)
    if sheet not in raw:
        raise HTTPException(404, f"{month} 无 {sheet} 数据")
    # 统一走校准解析层（数据浏览展示校准后值，口径与导出一致）
    eff_all = CalibrationService().apply_overlays(month, raw)
    data = {k: v for k, v in eff_all.items()
            if not str(k).startswith("__")}
    df = data[sheet]
    
    # 搜索过滤（全字段模糊匹配）
    if search and search.strip():
        keyword = search.strip()
        mask = df.apply(
            lambda row: any(keyword.lower() in str(v).lower() for v in row.values),
            axis=1
        )
        df = df[mask]
    
    total = len(df)
    start = (page - 1) * page_size
    end = start + page_size
    page_df = df.iloc[start:end]
    # 暴露原始行号（0-based，定位校准单元格用；搜索过滤后 index 仍指向原始位置）
    page_rows = page_df.fillna("").to_dict(orient="records")
    for rec, idx in zip(page_rows, page_df.index):
        rec["row_index"] = int(idx)
    return {
        "month": month,
        "sheet": sheet,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
        "columns": list(page_df.columns) + ["row_index"],
        "rows": page_rows,
    }


# ========== 2. 确认收入 ==========

@router.get("/revenue/summary/{month}")
async def revenue_summary(month: str):
    month = normalize_month(month)
    from bdms.modules.revenue.summary_engine import SummaryEngine
    r = SummaryEngine().compute_summary(month)
    if "error" in r:
        raise HTTPException(400, r["error"])
    return r


@router.get("/revenue/export/{month}")
async def revenue_export(month: str):
    """导出确收汇总为 Excel。"""
    month = normalize_month(month)
    from bdms.modules.revenue.exporter import RevenueReportExporter, RevenueSummaryError
    try:
        path = RevenueReportExporter().export(month)
    except RevenueSummaryError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"导出失败: {e}")
    return FileResponse(path, filename=f"确收汇总_{month}.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@router.post("/revenue/generate")
async def revenue_generate(req: GenerateRequest):
    """生成/读取确认收入（幂等，受 mode 控制）。"""
    from bdms.modules.revenue.service import RevenueService
    svc = RevenueService()
    try:
        return svc.generate(normalize_month(req.month), getattr(req, "mode", "auto") or "auto")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/revenue/import")
async def revenue_import(req: GenerateRequest):
    from bdms.modules.revenue.service import RevenueService
    try:
        return RevenueService().import_source(normalize_month(req.month))
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/revenue/compare/{month}")
async def revenue_compare(month: str, manual: Optional[str] = None):
    month = normalize_month(month)
    from pathlib import Path
    from bdms.core import paths
    from bdms.modules.revenue.summary_engine import SummaryEngine
    s = SummaryEngine()
    mine = s.compute_summary(month)
    if "error" in mine:
        raise HTTPException(400, mine["error"])
    manual_path = Path(manual) if manual else None
    if manual_path is None:
        # 在团队报告目录下查找该月的差异分析表
        mdir = paths.month_dir(month)
        if mdir.exists():
            hits = sorted(mdir.glob("*差异分析*.xlsx"))
            manual_path = hits[0] if hits else None
    if not manual_path or not Path(manual_path).exists():
        return {"mine": mine, "manual": None,
                "note": f"未找到 {month} 手工报表，仅返回本方计算"}
    manual = s.read_manual_summary(manual_path)
    mrows = {r.get("period"): r for r in manual.get("rows", []) if r.get("period")}
    compare = []
    for row in mine["rows"]:
        m = mrows.get(row["period"])
        in_scope = row["period"] <= month  # 同口径：手工报表月份及之前
        entry = {"period": row["period"], "categories": {}, "in_scope": in_scope}
        for cat, mkey in [("递延", "deferred"), ("新签", "new_sign"), ("合计", "total")]:
            op = row["categories"][cat]["plan"]
            oa = row["categories"][cat]["actual"]
            if m and in_scope:
                mp = (m[mkey]["plan"] or 0) * 10000
                ma = (m[mkey]["actual"] or 0) * 10000
                entry["categories"][cat] = {
                    "ours": {"plan": op, "actual": oa},
                    "manual": {"plan": mp, "actual": ma},
                    "match": abs(op - mp) < 1 and abs(oa - ma) < 1,
                }
            else:
                entry["categories"][cat] = {"ours": {"plan": op, "actual": oa}, "manual": None}
        compare.append(entry)
    ok = sum(1 for e in compare if e["in_scope"]
             for c in e["categories"].values() if c.get("match"))
    total = sum(1 for e in compare if e["in_scope"]
                for c in e["categories"].values() if c.get("manual") is not None)
    return {"mine": mine, "compare": compare, "matched": ok, "comparable": total,
            "all_match": ok == total and total > 0, "scope_month": month}


# ========== 3. 基础数据 ==========

@router.get("/master-data/types")
async def master_types():
    try:
        from bdms.modules.master_data.service import MasterDataService
        svc = MasterDataService()
        return {"types": svc.list_types()}
    except ImportError:
        raise HTTPException(503, "模块3（基础数据）尚未完成")


@router.get("/master-data/list/{data_type}")
async def master_list(data_type: str, include_disabled: bool = False):
    try:
        from bdms.modules.master_data.service import MasterDataService
        svc = MasterDataService()
        # 兼容不同命名：优先 list_items，回退 list_reference
        fn = getattr(svc, "list_items", None) or getattr(svc, "list_reference", None)
        if fn is None:
            raise HTTPException(500, "MasterDataService 缺少列表方法")
        try:
            items = fn(data_type, include_disabled=include_disabled)
        except TypeError:
            items = fn(data_type)
        return {"data_type": data_type, "items": items}
    except ImportError:
        raise HTTPException(503, "模块3（基础数据）尚未完成")


# ========== 4. 统计看板 ==========

@router.get("/dashboard/{month}")
async def dashboard(month: str, refresh: bool = False):
    try:
        from bdms.modules.dashboard.service import DashboardService
    except ImportError:
        raise HTTPException(503, "模块4（统计看板）尚未完成")
    svc = DashboardService()
    try:
        if refresh:
            svc.refresh_snapshot(month)
        return svc.get_dashboard(month)
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/dashboard/drill-down")
async def dashboard_drill(req: DriftQuery):
    try:
        from bdms.modules.dashboard.service import DashboardService
    except ImportError:
        raise HTTPException(503, "模块4（统计看板）尚未完成")
    try:
        return DashboardService().drill_down(req.month, req.dimension, req.value,
                                             sheet=req.sheet)
    except Exception as e:
        raise HTTPException(500, str(e))


# ========== 5. 系统设定 ==========

@router.get("/settings")
async def settings_get():
    try:
        from bdms.modules.settings.service import SettingsService
        return SettingsService().get_all()
    except ImportError:
        # 降级：直接用 core
        return _db.get_all_settings()


@router.post("/settings")
async def settings_set(req: SettingUpdate):
    try:
        from bdms.modules.settings.service import SettingsService
        return SettingsService().set(req.key, req.value)
    except ImportError:
        _db.upsert_settings({req.key: req.value})
        return {"ok": True, "key": req.key, "value": req.value}


# ========== 健康检查 ==========

@router.get("/health")
async def health():
    return {"status": "ok", "component": "bdms-web"}
