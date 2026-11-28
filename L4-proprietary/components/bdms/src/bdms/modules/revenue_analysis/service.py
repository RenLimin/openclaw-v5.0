"""service — 确收分析服务层（幂等编排）。

契约：DESIGN-DETAIL-REVENUE-ANALYSIS-v1.0 §9.2：
  - generate(period, mode) 三模式幂等（auto/read/regenerate）+ job 记录；
  - import_source / summary / caliber / trend / sources_available / list_periods；
  - caliber/trend 读 ra_caliber / ra_trend_row（结构化快照），无数据 fail-closed。

🔒 NO_TOKEN — 纯代码，零 AI 依赖。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from bdms.core import db as _db
from bdms.modules.base import BaseService, MODE_AUTO, MODE_READ, MODE_REGENERATE

from .engine import RevenueAnalysisEngine
from .exporter import RevenueAnalysisExporter


class RevenueAnalysisService(BaseService):
    """确收分析服务层。"""

    module_name = "revenue_analysis"

    def __init__(self, db_path: Optional[Path] = None):
        # 2026-11-24 修复：必须 env-aware。
        # 旧实现传 None → BaseEngine 回退到硬编码 DATA_DIR/"bdms.db"（忽略 BDMS_DB），
        # 而同进程内 _db.get_connection() 用的是 paths.DB_PATH（读 BDMS_DB）。
        # 后果：Web/定时任务设了 BDMS_DB 时，job 表落 tmp 库、引擎算生产库，
        # 两者分裂 —— 表现为 job 永远 running / fail-closed 误判有数据。
        from bdms.core.paths import DB_PATH as _ENV_DB_PATH
        resolved = Path(db_path) if db_path else _ENV_DB_PATH
        self.engine = RevenueAnalysisEngine(resolved)
        self._last_snapshot_backfill: dict = {}
        # BaseService 组合模式：显式传 engine，meta_db 与 engine 同库
        super().__init__(module_name=self.module_name, engine=self.engine,
                         meta_db_path=resolved)

    def generate(self, period: str, mode: str = MODE_AUTO) -> dict:
        """幂等生成/读取 + 快照兜底。

        BaseService 骨架的 auto/read 路径在 has_data=True 时只读宽表，
        不写 ra_caliber/ra_trend_row/ra_period 快照；这里在 read 分支后
        检查快照缺失并补一次 compute+persist，保证双口径/趋势始终可查。
        """
        r = super().generate(period, mode)
        self._ensure_snapshots(period)
        # Q6/Q7（§7.1）：生成后自动 upsert 当期台账快照（月度/履约汇总记录）
        try:
            data = self.engine.compute(period)
            self.engine.persist_ledger_snapshot(period, data)
            r["ledger_snapshot"] = {"period": period, "written": 2}
        except Exception as e:
            # 快照失败不阻断生成主流程，记 warning 供前端提示
            r["ledger_snapshot"] = {"period": period, "error": str(e)}
        return r

    def _ensure_snapshots(self, period: str) -> None:
        """快照兜底：ra_caliber / ra_attribution / ra_alert 任一缺失即补。

        Rex 2026-11-24 拍板（D3）：generate() 重新生成时必须刷新 Q1 归因与
        Q4 预警快照，不再只在 engine 主流程产生一次。
        三张表同时补齐，保证同一账期内口径一致（同一次 compute 产物）。
        """
        conn = _db.get_connection(self.engine.db_path)
        try:
            counts = {}
            for tbl in ("ra_caliber", "ra_attribution", "ra_alert"):
                try:
                    counts[tbl] = conn.execute(
                        f"SELECT COUNT(*) FROM {tbl} WHERE period = ?",
                        (period,),
                    ).fetchone()[0]
                except Exception:
                    counts[tbl] = 0
        finally:
            conn.close()
        if any(n == 0 for n in counts.values()):
            data = self.engine.compute(period)
            self.engine.persist(period, data, overwrite=True)
            self._last_snapshot_backfill = counts

    # ─── 数据源 ───

    def import_source(self, period: str,
                      excel_path: Optional[Path] = None) -> dict:
        """导入财报源文件（预算执行表 + 底稿），返回导入统计。"""
        return self.engine.import_source(period, excel_path)

    def sources_available(self, period: str) -> bool:
        return self.engine.sources_available(period)

    def list_periods(self) -> list[str]:
        """已登记账期（ra_period），按期间倒序。"""
        conn = _db.get_connection(self.engine.db_path)
        try:
            rows = conn.execute(
                "SELECT period FROM ra_period ORDER BY period DESC"
            ).fetchall()
            return [r["period"] for r in rows]
        finally:
            conn.close()

    # ─── 查询 ───

    def summary(self, period: str) -> dict:
        """双口径汇总：ra_caliber 两行 + 差异。"""
        conn = _db.get_connection(self.engine.db_path)
        try:
            rows = conn.execute(
                "SELECT caliber, total, by_group, by_month FROM ra_caliber "
                "WHERE period = ? ORDER BY caliber", (period,),
            ).fetchall()
            if not rows:
                raise ValueError(f"{period} 无双口径数据，请先 generate")
            out: dict[str, Any] = {"period": period}
            for r in rows:
                out[r["caliber"]] = {
                    "total": r["total"],
                    "by_group": json.loads(r["by_group"]),
                    "by_month": json.loads(r["by_month"]),
                }
            out["difference"] = round(
                out["dynamic"]["total"] - out["locked"]["total"], 2)
            return out
        finally:
            conn.close()

    def caliber(self, period: str) -> dict:
        """双口径（兼容 §9.2 语义，返回与 engine.compute_dual_caliber 同构）。"""
        cal = self.summary(period)
        dyn_group = cal["dynamic"]["by_group"]
        return {
            "period": period,
            "locked": {
                **cal["locked"]["by_group"], "合计": cal["locked"]["total"],
            },
            "dynamic": {
                "DUE_2026": dyn_group.get("DUE_2026", 0.0),
                "IN_PIPELINE": dyn_group.get("IN_PIPELINE", 0.0),
                "OTHER_2027plus": dyn_group.get("OTHER_2027plus", 0.0),
                "MISSING": dyn_group.get("MISSING", 0.0),
                "合计": cal["dynamic"]["total"],
            },
            "difference": cal["difference"],
        }

    def trend(self, period: str) -> list[dict]:
        """预算趋势分析 19 行（ra_trend_row + R19 单元格）。"""
        conn = _db.get_connection(self.engine.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM ra_trend_row WHERE period = ? "
                "ORDER BY row_index", (period,),
            ).fetchall()
            if not rows:
                raise ValueError(f"{period} 无趋势数据，请先 generate")
            cells = conn.execute(
                "SELECT row_index, col_index, value FROM ra_trend_cell "
                "WHERE period = ?", (period,),
            ).fetchall()
            cell_map = {(c["row_index"], c["col_index"]): c["value"]
                        for c in cells}
            out = []
            for r in rows:
                d = dict(r)
                d.pop("id", None)
                if r["row_index"] == 19:
                    rc = cell_map.get((19, 0))
                    if rc:
                        try:
                            d["recognize_rate_count"] = \
                                json.loads(rc).get("value")
                        except json.JSONDecodeError:
                            d["recognize_rate_count"] = None
                    ra = cell_map.get((19, 1))
                    if ra:
                        try:
                            d["recognize_rate_amount"] = \
                                json.loads(ra).get("value")
                        except json.JSONDecodeError:
                            d["recognize_rate_amount"] = None
                out.append(d)
            return out
        finally:
            conn.close()

    # ─── Q1 归因 / Q4 预警 ───

    def attribution(self, period: str) -> dict:
        """Q1 偏差归因结果（ra_attribution）+ 待人工清单。"""
        conn = _db.get_connection(self.engine.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM ra_attribution WHERE period = ? ORDER BY id",
                (period,),
            ).fetchall()
            if not rows:
                raise ValueError(f"{period} 无归因数据，请先 generate")
            out_rows = []
            for r in rows:
                d = dict(r)
                d.pop("id", None)
                d["context"] = json.loads(d["context"]) if d.get("context") else {}
                out_rows.append(d)
            auto = sum(1 for r in out_rows if r.get("auto_filled"))
            return {
                "period": period,
                "triggered": len(out_rows),
                "auto_filled": auto,
                "pending": len(out_rows) - auto,
                "rows": out_rows,
                "pending_rows": [r for r in out_rows if not r.get("auto_filled")],
            }
        finally:
            conn.close()

    def alerts(self, period: str) -> list[dict]:
        """Q4 预警清单（ra_alert）。

        契约沿用 P2 既定行为（test_service_fail_closed 冻结）：未生成/无预警均返回 []，
        由调用方结合 periods 列表判断账期是否已生成。此处刻意不抛错。
        """
        conn = _db.get_connection(self.engine.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM ra_alert WHERE period = ? ORDER BY id",
                (period,),
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d.pop("id", None)
                d["context"] = json.loads(d["context"]) if d.get("context") else {}
                out.append(d)
            return out
        finally:
            conn.close()

    def buckets(self, period: str) -> dict:
        """Q2/Q3 分桶结果（ra_bucket）。

        返回：total/inherited/overridden/blank + rules 分布 + 详细列表（分页前 200）。
        fail-closed：未生成/无数据 → 返回空结构（与 alerts 一致，便于前端渲染）。
        """
        conn = _db.get_connection(self.engine.db_path)
        try:
            rows = conn.execute(
                """SELECT perf_id, budget_fill, budget_trend, bucket_source,
                          budget_fill_source, matched_oa, matched_ones,
                          week_status, created_at
                   FROM ra_bucket WHERE period = ? ORDER BY perf_id""",
                (period,),
            ).fetchall()
        finally:
            conn.close()
        if not rows:
            return {"total": 0, "items": []}
        items = [dict(r) for r in rows]
        # 统计分布
        from collections import Counter
        bt = Counter(r["budget_trend"] or "(空)" for r in items)
        bf = Counter(r["budget_fill"] or "(空)" for r in items)
        src = Counter(r["bucket_source"] or "" for r in items)
        src_fill = Counter(r["budget_fill_source"] or "" for r in items)
        return {
            "total": len(items),
            "budget_trend_dist": dict(bt),
            "budget_fill_dist": dict(bf),
            "source_dist": dict(src),
            "fill_source_dist": dict(src_fill),
            "items": items[:200],  # 预览前 200 条
        }

    def forecast(self, period: str) -> dict:
        """P7 预测快照（DESIGN v1.1 §8.3）。

        fail-closed：宽表缺失 → ImportError_ 转空结构（不抛给前端，与 buckets 一致）。
        仅读既有单一事实源（CaliberBuilder / ra_bucket / 汇总分析 / 年度目标），
        不新增加总逻辑、不自造聚合。
        """
        from .forecast_engine import ForecastEngine
        from bdms.modules.base import ImportError_
        try:
            out = ForecastEngine(self.engine).forecast(period)
        except ImportError_:
            return {"period": period, "has_data": False, "risks": []}
        out["has_data"] = True
        return out

    def annual_targets(self) -> list[dict]:
        """Q8 年度目标列表（ra_annual_target）。"""
        return self.engine.list_annual_targets()

    def set_annual_target(self, year: int, amount_wan: float) -> dict:
        """Q8 设置年度目标（upsert）。"""
        return self.engine.set_annual_target(year, amount_wan)

    def ledger_snapshot(self, period: str) -> dict:
        """Q6/Q7 台账快照（月度汇总记录 + 履约汇总记录）。"""
        snap = self.engine.load_ledger_snapshot(period)
        if snap is None:
            return {"period": period, "has_snapshot": False,
                    "monthly_record": [], "perf_record": []}
        return {"period": period, "has_snapshot": True,
                "monthly_record": snap.get("monthly_record") or [],
                "perf_record": snap.get("perf_record") or []}

    def snapshot_periods(self) -> list[str]:
        """已登记台账快照的账期（Q6 连续性检查用）。"""
        return self.engine.list_snapshot_periods()

    # ─── 异步 job（Web UI 用） ───

    def generate_with_job(self, job_id: int, period: str,
                          mode: str = MODE_AUTO) -> dict:
        """在已有 job 上下文中生成/读取数据，分步上报进度。

        供 Web 异步调用：API 先 create_job 立即返回 job_id，后台线程调本方法。
        刻意不走 BaseService.generate()——那条路径会自建 job，导致双 job。

        进度条铁律（AGENTS.md）：导出/生成长任务必须分步上报。
        """
        from bdms.core import db as _db

        def _progress(pct: int, msg: str) -> None:
            c = _db.get_connection(self.meta_db_path)
            try:
                _db.update_job_status(c, job_id, "running", pct, msg)
                c.commit()
            finally:
                c.close()

        try:
            self._ensure_ready()
            has = self.engine.has_data(period)
            if mode == MODE_READ and not has:
                raise ValueError(
                    f"{period} 无数据可读，请先用 auto/regenerate 生成")
            if mode == MODE_REGENERATE:
                action = "generated"
            elif mode == MODE_READ:
                action = "read"
            else:
                action = "read" if has else "generated"

            if action == "read":
                _progress(20, "步骤 1/3：读取历史数据...")
                data = self.engine.load(period)
                counts = {k: len(v) for k, v in data.items()}
                _progress(85, "数据加载完成，补齐快照...")
            else:
                _progress(20, "步骤 1/3：加载源表...")
                _progress(40, "步骤 2/3：计算 10 Sheet + 快照...")
                computed = self.engine.compute(period)
                _progress(75, "步骤 3/3：落盘...")
                counts = self.engine.persist(
                    period, computed,
                    overwrite=(mode == MODE_REGENERATE or has))

            total = sum(v for v in counts.values() if isinstance(v, (int, float)))
            # D3 兜底：read 模式下若 ra_caliber/ra_attribution/ra_alert 缺失则补
            self._ensure_snapshots(period)
            self._finish_job(job_id, "done", 100, message=f"{action}: {total} 行")
            return {
                "month": period, "mode": mode, "action": action,
                "sheets": counts, "job_id": job_id, "total_rows": total,
            }
        except Exception as e:
            self._finish_job(job_id, "failed", 0, message=str(e)[:500])
            raise

    def export_with_job(self, job_id: int, period: str) -> Path:
        """异步导出 Excel，进度上报 + output_path 回写 job。"""
        from bdms.core import db as _db

        def _progress(pct: int, msg: str) -> None:
            c = _db.get_connection(self.meta_db_path)
            try:
                _db.update_job_status(c, job_id, "running", pct, msg)
                c.commit()
            finally:
                c.close()

        try:
            _progress(5, "步骤 1/2：准备导出...")
            target = self.export(period)
            _progress(95, "步骤 2/2：写出 Excel...")
            conn = _db.get_connection(self.meta_db_path)
            try:
                _db.update_job_status(conn, job_id, "done", 100,
                                      message="导出完成",
                                      output_path=str(target))
                conn.commit()
            finally:
                conn.close()
            return target
        except Exception as e:
            self._finish_job(job_id, "failed", 0, message=str(e)[:500])
            raise

    # ─── 导出 ───

    def export(self, period: str, out_path: Optional[Path] = None) -> Path:
        """导出 Excel（确认收入分析_{period}.xlsx）。"""
        return RevenueAnalysisExporter(self.engine.db_path).export(
            period, out_path)
