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


@router.post("/report/generate")
async def report_generate(req: GenerateRequest):
    from bdms.modules.delivery_report.service import DeliveryReportService
    try:
        return DeliveryReportService().generate(req.month, req.mode)
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/report/export/{month}")
async def report_export(month: str):
    from bdms.modules.delivery_report.exporter import DeliveryReportExporter
    try:
        path = DeliveryReportExporter().export(month)
    except Exception as e:
        raise HTTPException(500, str(e))
    return FileResponse(path, filename=f"交付月报_{month}.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ========== 2. 确认收入 ==========

@router.get("/revenue/summary/{month}")
async def revenue_summary(month: str):
    from bdms.modules.revenue.summary_engine import SummaryEngine
    r = SummaryEngine().compute_summary(month)
    if "error" in r:
        raise HTTPException(400, r["error"])
    return r


@router.post("/revenue/import")
async def revenue_import(req: GenerateRequest):
    from bdms.modules.revenue.engine import RevenueEngineAdapter
    try:
        return RevenueEngineAdapter().import_source(req.month)
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/revenue/compare/{month}")
async def revenue_compare(month: str, manual: Optional[str] = None):
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
