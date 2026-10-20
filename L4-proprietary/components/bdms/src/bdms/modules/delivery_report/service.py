"""交付月报服务层 — 人机协作幂等编排。

模式：
  auto       默认：DB 有 → 读取；DB 无 → 生成
  read       强制从 DB 读取（不重算）
  regenerate 强制重算 + 覆盖 DB

人机协作状态机（审核状态）：
  generating → validating → reviewing → approved → exported
                   ↑________↓
                      rejected
"""

from pathlib import Path
from typing import Optional, List, Dict

from bdms.core import db as _db
from .engine import DeliveryReportEngine
from .validator import DeliveryReportValidator

MODE_AUTO = "auto"
MODE_READ = "read"
MODE_REGENERATE = "regenerate"


class DeliveryReportService:
    """交付月报编排服务（人机协作模式）。"""

    def __init__(self, db_path: Optional[Path] = None):
        self.engine = DeliveryReportEngine(db_path)
        self.db_path = db_path

    # ──────────────────────────────────────────────────────
    #  状态查询
    # ──────────────────────────────────────────────────────

    def get_review_status(self, month: str) -> dict:
        """获取某月的审核状态（人机协作流程位置）。"""
        conn = _db.get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM dr_review_status WHERE month = ?", (month,)
            ).fetchone()
            if row:
                return dict(row)
            return {
                "month": month, "status": "not_started",
                "total_errors": 0, "total_warnings": 0, "pending_fixes": 0,
            }
        finally:
            conn.close()

    def list_review_months(self) -> list[dict]:
        """列出所有已生成月份的审核状态（按月份倒序）。"""
        conn = _db.get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT month, status, total_errors, total_warnings, pending_fixes, "
                "generated_at, validated_at, reviewed_at, approved_at, reviewer "
                "FROM dr_review_status ORDER BY month DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def list_review_issues(self, month: str, status_filter: str = None) -> dict:
        """列出某月的所有校验问题。"""
        conn = _db.get_connection(self.db_path)
        try:
            sql = "SELECT * FROM dr_import_validation WHERE month = ?"
            params = [month]
            if status_filter:
                sql += " AND status = ?"
                params.append(status_filter)
            sql += " ORDER BY sheet, row_index"
            rows = conn.execute(sql, params).fetchall()
            return {
                "month": month,
                "issues": [dict(r) for r in rows],
                "total": len(rows),
                "pending": sum(1 for r in rows if r["status"] == "pending"),
                "confirmed": sum(1 for r in rows if r["status"] == "confirmed"),
                "rejected": sum(1 for r in rows if r["status"] == "rejected"),
            }
        finally:
            conn.close()

    # ──────────────────────────────────────────────────────
  #  人机协作审核操作
    # ──────────────────────────────────────────────────────

    def approve_review(self, month: str, reviewer: str = "") -> dict:
        """人工确认：审批通过，进入 approved 状态。"""
        conn = _db.get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT status FROM dr_review_status WHERE month = ?", (month,)
            ).fetchone()
            if not row:
                raise ValueError(f"{month} 无审核记录")
            if row["status"] == "approved":
                raise ValueError(f"{month} 已审核通过，无需重复操作")

            conn.execute(
                "UPDATE dr_review_status SET status='approved', approved_at=datetime('now','localtime'), "
                "reviewer=?, updated_at=datetime('now','localtime') WHERE month=?",
                (reviewer, month)
            )
            conn.commit()
            return {"month": month, "status": "approved", "reviewer": reviewer}
        finally:
            conn.close()

    def reject_review(self, month: str, reason: str = "", reviewer: str = "") -> dict:
        """人工驳回：打回 reviewing 状态等待修正。"""
        conn = _db.get_connection(self.db_path)
        try:
            conn.execute(
                "UPDATE dr_review_status SET status='reviewing', reviewer=?, "
                "updated_at=datetime('now','localtime') WHERE month=?",
                (reviewer, month)
            )
            conn.commit()
            return {"month": month, "status": "reviewing", "reason": reason}
        finally:
            conn.close()

    def resolve_issue(self, month: str, issue_id: int, action: str,
                      operator: str = "") -> dict:
        """单条 issue 状态流转：confirm（确认/确认错误无误）或 reject（驳回/误报）。

        同时重算 pending_fixes，保持 dr_review_status 与明细表一致。
        """
        if action not in ("confirm", "reject"):
            raise ValueError(f"未知 action: {action}，仅支持 confirm / reject")
        target_status = "confirmed" if action == "confirm" else "rejected"

        conn = _db.get_connection(self.db_path)
        try:
            # 检查 issue 是否存在且属于该 month
            row = conn.execute(
                "SELECT id, status FROM dr_import_validation "
                "WHERE id = ? AND month = ?",
                (issue_id, month)
            ).fetchone()
            if not row:
                raise ValueError(f"issue {issue_id} 不存在或不属于 {month}")

            # 已处理过的不再重复处理（幂等）
            if row["status"] == target_status:
                return {"id": issue_id, "status": target_status, "changed": False}

            # 更新状态
            conn.execute(
                "UPDATE dr_import_validation SET status=?, operator=?, "
                "resolved_at=datetime('now','localtime') WHERE id = ?",
                (target_status, operator, issue_id)
            )

            # 重算 pending_fixes
            pending_count = conn.execute(
                "SELECT COUNT(*) FROM dr_import_validation "
                "WHERE month = ? AND status = 'pending'",
                (month,)
            ).fetchone()[0]
            conn.execute(
                "UPDATE dr_review_status SET pending_fixes = ? WHERE month = ?",
                (pending_count, month)
            )
            conn.commit()
            return {"id": issue_id, "status": target_status,
                    "pending_fixes": pending_count, "changed": True}
        finally:
            conn.close()

    def batch_resolve_issues(self, month: str, issue_ids: List[int],
                             action: str, operator: str = "") -> dict:
        """批量处理 issue。"""
        if not issue_ids:
            return {"updated": 0, "pending_fixes": 0}
        if action not in ("confirm", "reject"):
            raise ValueError(f"未知 action: {action}")
        target_status = "confirmed" if action == "confirm" else "rejected"
        placeholders = ",".join("?" * len(issue_ids))

        conn = _db.get_connection(self.db_path)
        try:
            conn.execute(
                f"UPDATE dr_import_validation SET status=?, operator=?, "
                f"resolved_at=datetime('now','localtime') "
                f"WHERE month = ? AND id IN ({placeholders}) AND status != ?",
                [target_status, operator, month, *issue_ids, target_status]
            )
            updated = conn.total_changes

            pending_count = conn.execute(
                "SELECT COUNT(*) FROM dr_import_validation "
                "WHERE month = ? AND status = 'pending'",
                (month,)
            ).fetchone()[0]
            conn.execute(
                "UPDATE dr_review_status SET pending_fixes = ? WHERE month = ?",
                (pending_count, month)
            )
            conn.commit()
            return {"updated": updated, "pending_fixes": pending_count}
        finally:
            conn.close()

    def revalidate(self, month: str) -> dict:
        """人工触发：重新校验（修正后验证）。"""
        validator = DeliveryReportValidator(self.db_path)
        result = validator.collect_suspicious(month)

        conn = _db.get_connection(self.db_path)
        try:
            conn.execute(
                "UPDATE dr_review_status SET status='validating', "
                "total_errors=?, total_warnings=?, updated_at=datetime('now','localtime') "
                "WHERE month=?",
                (result["summary"]["total_errors"],
                 result["summary"]["total_warnings"],
                 month)
            )
            # 重算 pending_fixes（取明细表 pending 状态数）
            pending_count = conn.execute(
                "SELECT COUNT(*) FROM dr_import_validation "
                "WHERE month = ? AND status = 'pending'",
                (month,)
            ).fetchone()[0]
            conn.execute(
                "UPDATE dr_review_status SET pending_fixes = ? WHERE month = ?",
                (pending_count, month)
            )
            conn.commit()
        finally:
            conn.close()

        return {"month": month, "validation": result, "pending_fixes": pending_count}

    # ──────────────────────────────────────────────────────
    #  原有方法
    # ──────────────────────────────────────────────────────

    def generate(self, month: str, mode: str = MODE_AUTO,
                 refetch_sources: bool = False) -> dict:
        """生成/读取交付月报数据。

        Args:
            month: 月份 YYYYMM
            mode: auto | read | regenerate
            refetch_sources: 是否从源系统重新拉取原始数据（默认 False）
        """
        if mode not in (MODE_AUTO, MODE_READ, MODE_REGENERATE):
            raise ValueError(f"未知模式: {mode}")

        conn = _db.get_connection(self.db_path)
        try:
            job_id = _db.create_job(conn, "delivery_report", month, mode)
            conn.commit()
        finally:
            conn.close()

        def _progress(pct: int, msg: str):
            c = _db.get_connection(self.db_path)
            try:
                _db.update_job_status(c, job_id, "running", pct, msg)
                c.commit()
            finally:
                c.close()

        try:
            has_data = self.engine.has_data(month)

            if mode == MODE_READ:
                if not has_data:
                    raise ValueError(f"{month} 无数据可读，请先用 auto/regenerate 生成")
                action = "read"
            elif mode == MODE_REGENERATE:
                action = "generated"
            else:
                action = "read" if has_data else "generated"

            if action == "read":
                _progress(10, "读取历史数据...")
                data = self.engine.load(month)
                counts = {k: len(v) for k, v in data.items()}
                _progress(90, "数据加载完成")
            else:
                # ── 生成流程：分步进度 ──
                step = 0
                total_steps = 5 if refetch_sources else 4
                base_pct = 5

                if refetch_sources:
                    _progress(base_pct, "步骤 1/5：从源系统拉取原始数据...")
                    self._refetch_source_data(month)
                    step += 1
                    base_pct = 20

                _progress(base_pct, f"步骤 {step+1}/{total_steps}：加载源数据...")
                raw_data = self._extract_raw(month)
                step += 1

                _progress(base_pct + step * 15, f"步骤 {step+1}/{total_steps}：计算核心报表...")
                computed = self.engine.compute(month)
                step += 1

                _progress(base_pct + step * 15, f"步骤 {step+1}/{total_steps}：持久化到数据库...")
                counts = self.engine.persist(month, computed,
                                             overwrite=(mode == MODE_REGENERATE or has_data))
                step += 1

                _progress(base_pct + step * 15, f"步骤 {step+1}/{total_steps}：执行数据校验...")
                self._run_validation(month)

            _progress(100, "✅ 生成完成")
            self._finish_job(job_id, "done", 100,
                             message=f"{action}: {sum(counts.values())} 行")

            # 更新审核状态为 validating（等待人工审核）
            self._update_review_status(month, "validating", counts=counts)

            return {
                "month": month, "mode": mode, "action": action,
                "sheets": counts, "job_id": job_id,
                "total_rows": sum(counts.values()),
                "review_status": "validating",
                "refetch_sources": refetch_sources,
            }
        except Exception as e:
            self._finish_job(job_id, "failed", 0, message=str(e)[:500])
            raise

    def _extract_raw(self, month: str) -> dict:
        """提取原始数据（复用 pipeline）。"""
        from bdms.modules.integration.adapters.pipeline import DeliveryReportPipeline
        pipeline = DeliveryReportPipeline(self.db_path)
        return pipeline.extract_raw_data(month)

    def _refetch_source_data(self, month: str) -> dict:
        """从源系统重新拉取 ONES/OA 等原始数据到 workspace。

        先清空历史导出数据，再重新拉取。
        返回各数据源拉取结果。
        """
        import shutil
        from pathlib import Path
        from bdms.core import paths

        results = {}

        # 1. 清空 ONES 历史导出（当月）
        ones_base = paths.ones_dir()
        ones_base.mkdir(parents=True, exist_ok=True)
        patterns = [
            f"{month}周报-签约项目统计.csv",
            f"{month}周报-POC&提前实施统计.csv",
            f"{month}-签约项目异常处置.csv",
        ]
        cleared = 0
        for p in patterns:
            fp = ones_base / p
            if fp.exists():
                fp.unlink()
                cleared += 1
        results["ones_cleared"] = cleared

        # 2. 从 ONES 重新拉取（调用 ONES connector）
        try:
            from bdms.modules.integration.connectors.ones_connector import ONESConnector
            conn = ONESConnector()
            if conn.authenticate():
                # 签约
                sign_data = conn.fetch(filter_name="sign", month=month)
                results["sign_rows"] = len(sign_data) if sign_data else 0
                # POC
                poc_data = conn.fetch(filter_name="poc", month=month)
                results["poc_rows"] = len(poc_data) if poc_data else 0
                # 异常
                exc_data = conn.fetch(filter_name="exception", month=month)
                results["exception_rows"] = len(exc_data) if exc_data else 0
                results["ones_refetch"] = True
            else:
                results["ones_refetch"] = False
                results["ones_error"] = "认证失败"
        except Exception as e:
            results["ones_refetch"] = False
            results["ones_error"] = str(e)[:200]

        return results

    def _run_validation(self, month: str) -> dict:
        """执行校验，返回校验结果。"""
        from bdms.modules.delivery_report.validator import DeliveryReportValidator
        validator = DeliveryReportValidator(self.db_path)
        result = validator.collect_suspicious(month)
        # 同步 pending_fixes
        conn = _db.get_connection(self.db_path)
        try:
            pending_count = conn.execute(
                "SELECT COUNT(*) FROM dr_import_validation "
                "WHERE month = ? AND status = 'pending'",
                (month,)
            ).fetchone()[0]
            conn.execute(
                "UPDATE dr_review_status SET total_errors=?, total_warnings=?, pending_fixes=? "
                "WHERE month=?",
                (result["summary"]["total_errors"],
                 result["summary"]["total_warnings"],
                 pending_count, month)
            )
            conn.commit()
        finally:
            conn.close()
        return result

    def compare_with_manual(self, month: str) -> dict:
        """与手工报表逐项对比，返回各 Sheet 差异结果。

        使用 openpyxl read_only + values_only 模式，控制内存占用。
        带 job 进度上报，前端可轮询展示进度条（进度条铁律：>10s 必须有进度）。
        """
        from pathlib import Path
        import openpyxl
        import datetime as _dt
        from bdms.core import paths as _paths
        from bdms.core import db as _db

        # 创建对比 job（复用 job 表，module=compare_report）
        conn = _db.get_connection(self.db_path)
        try:
            job_id = _db.create_job(conn, "compare_report", month, "compare")
            conn.commit()
        finally:
            conn.close()

        def _progress(pct: int, msg: str):
            c = _db.get_connection(self.db_path)
            try:
                _db.update_job_status(c, job_id, "running", pct, msg)
                c.commit()
            finally:
                c.close()

        try:
            # 步骤 1/5：导出我方最新报表
            _progress(10, "步骤 1/5：导出我方月报...")
            from bdms.modules.delivery_report.exporter import DeliveryReportExporter
            exporter = DeliveryReportExporter(self.db_path)
            my_path = exporter.export(month)

            # 步骤 2/5：查找手工报表
            _progress(20, "步骤 2/5：定位手工报表...")
            man_dir = _paths.month_dir(month)
            man_path = None
            if man_dir.exists():
                for p in sorted(man_dir.glob("*交付月报*.xlsx")):
                    if p.name.startswith("~$"):
                        continue
                    man_path = p
                    break
            if not man_path:
                self._finish_job(job_id, "failed", 20, message=f"未找到 {month} 手工报表")
                return {"error": f"未找到 {month} 手工报表", "job_id": job_id}

            # 步骤 3/5：加载报表并准备对比
            _progress(30, "步骤 3/5：加载报表数据...")

            # 归一化函数（对齐 tools/compare_delivery_report.py）
            def _norm(v):
                if v is None:
                    return None
                if isinstance(v, _dt.time):
                    return 0 if (v.hour, v.minute, v.second, v.microsecond) == (0, 0, 0, 0) else v
                if isinstance(v, _dt.datetime):
                    return v.date() if (v.hour, v.minute, v.second, v.microsecond) == (0, 0, 0, 0) else v
                if isinstance(v, str):
                    s = v.strip()
                    if s == "00:00:00":
                        return 0
                    return None if s == "" else s
                return v

            def _eq(a, b):
                a, b = _norm(a), _norm(b)
                if a is None and b is None:
                    return True
                if a is None or b is None:
                    return False
                # 字符串 HH:MM:SS 与 time 对象互转
                if isinstance(a, str) and len(a) == 8 and ':' in a and isinstance(b, _dt.time):
                    return a == b.strftime('%H:%M:%S')
                if isinstance(a, _dt.time) and isinstance(b, str) and len(b) == 8 and ':' in b:
                    return a.strftime('%H:%M:%S') == b
                # 整数 YYYYMMDD 与 datetime/date 互转
                if isinstance(a, int) and isinstance(b, _dt.datetime):
                    a_dt = _dt.datetime.strptime(f'{a}', '%Y%m%d')
                    return a_dt.date() == b.date()
                if isinstance(a, int) and isinstance(b, _dt.date):
                    a_dt = _dt.datetime.strptime(f'{a}', '%Y%m%d').date()
                    return a_dt == b
                if isinstance(b, int) and isinstance(a, _dt.datetime):
                    b_dt = _dt.datetime.strptime(f'{b}', '%Y%m%d')
                    return a.date() == b_dt.date()
                if isinstance(b, int) and isinstance(a, _dt.date):
                    b_dt = _dt.datetime.strptime(f'{b}', '%Y%m%d').date()
                    return a == b_dt
                # 数字类数值容差
                if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                    return abs(a - b) <= 1e-6
                # 数字 vs 字符串
                if isinstance(a, (int, float)) and isinstance(b, str):
                    try:
                        return abs(a - float(b)) <= 1e-6
                    except Exception:
                        return False
                if isinstance(b, (int, float)) and isinstance(a, str):
                    try:
                        return abs(float(a) - b) <= 1e-6
                    except Exception:
                        return False
                return str(a) == str(b)

            # 步骤 4/5：逐 Sheet 对比
            _progress(40, "步骤 4/5：逐 Sheet 对比...")
            SHEETS = ["签约", "POC&提前实施", "异常项目", "确收交接", "验收交接"]
            results = {}
            total_diff = 0
            diff_limit = 200  # 每 Sheet 最多收集 200 条差异

            wb_mine = openpyxl.load_workbook(str(my_path), data_only=True, read_only=True)
            try:
                wb_man = openpyxl.load_workbook(str(man_path), data_only=True, read_only=True)
                try:
                    for idx, sheet in enumerate(SHEETS):
                        sheet_pct = 40 + int((idx / len(SHEETS)) * 50)
                        _progress(sheet_pct, f"步骤 4/5：对比 {sheet}...")
                        mine_sheet = wb_mine[sheet] if sheet in wb_mine.sheetnames else None
                        man_sheet = wb_man[sheet] if sheet in wb_man.sheetnames else None

                        if not mine_sheet and not man_sheet:
                            results[sheet] = {"status": "skip", "reason": "双方均无此 Sheet"}
                            continue
                        if not mine_sheet:
                            results[sheet] = {"status": "missing", "side": "mine", "reason": "我方缺少此 Sheet"}
                            total_diff += 1
                            continue
                        if not man_sheet:
                            results[sheet] = {"status": "missing", "side": "manual", "reason": "手工报表缺少此 Sheet"}
                            total_diff += 1
                            continue

                        diffs = []
                        mine_rows = 0
                        man_rows = 0
                        mine_cols = 0
                        man_cols = 0

                        it_m = mine_sheet.iter_rows(values_only=True)
                        it_a = man_sheet.iter_rows(values_only=True)

                        row_idx = 0
                        while True:
                            try:
                                rowm = next(it_m)
                            except StopIteration:
                                rowm = None
                            try:
                                rowa = next(it_a)
                            except StopIteration:
                                rowa = None

                            if rowm is None and rowa is None:
                                break

                            row_idx += 1
                            if rowm is not None:
                                mine_rows = row_idx
                                mine_cols = max(mine_cols, len(rowm))
                            if rowa is not None:
                                man_rows = row_idx
                                man_cols = max(man_cols, len(rowa))

                            max_col = max(
                                len(rowm) if rowm else 0,
                                len(rowa) if rowa else 0
                            )
                            for c in range(max_col):
                                mv = rowm[c] if (rowm and c < len(rowm)) else None
                                hv = rowa[c] if (rowa and c < len(rowa)) else None
                                if not _eq(mv, hv):
                                    diffs.append({
                                        "row": row_idx,
                                        "col": c + 1,
                                        "mine": str(mv) if mv is not None else "",
                                        "manual": str(hv) if hv is not None else ""
                                    })
                                    if len(diffs) >= diff_limit:
                                        break
                            if len(diffs) >= diff_limit:
                                pass  # 继续统计行数，但不收集更多差异

                        results[sheet] = {
                            "status": "match" if len(diffs) == 0 else "diff",
                            "mine_rows": mine_rows, "manual_rows": man_rows,
                            "mine_cols": mine_cols, "manual_cols": man_cols,
                            "diff_count": len(diffs),
                            "diffs": diffs,
                            "has_more": len(diffs) >= diff_limit,
                        }
                        total_diff += len(diffs)
                finally:
                    wb_man.close()
            finally:
                wb_mine.close()

            # 步骤 5/5：完成
            _progress(100, "✅ 对比完成")
            result = {
                "month": month,
                "job_id": job_id,
                "my_report": str(my_path),
                "manual_report": str(man_path),
                "total_diff_cells": total_diff,
                "all_match": total_diff == 0,
                "sheets": results,
            }
            self._finish_job(
                job_id, "done", 100,
                message=f"{'完全一致' if total_diff == 0 else str(total_diff) + ' 处差异'}",
                output_path=str(my_path)
            )
            return result

        except Exception as e:
            self._finish_job(job_id, "failed", 0, message=str(e)[:500])
            raise

    def _update_review_status(self, month: str, status: str, counts: dict = None):
        """更新审核状态。"""
        conn = _db.get_connection(self.db_path)
        try:
            existing = conn.execute(
                "SELECT id FROM dr_review_status WHERE month = ?", (month,)
            ).fetchone()

            set_parts = ["status=?", "updated_at=datetime('now','localtime')"]
            if status == "generating":
                set_parts.append("generated_at=datetime('now','localtime')")
            elif status == "validating":
                set_parts.append("validated_at=datetime('now','localtime')")

            if existing:
                set_clause = ", ".join(set_parts)
                conn.execute(
                    f"UPDATE dr_review_status SET {set_clause} WHERE month=?",
                    (status, month)
                )
            else:
                conn.execute(
                    "INSERT INTO dr_review_status (month, status, generated_at, updated_at) "
                    "VALUES (?, ?, datetime('now','localtime'), datetime('now','localtime'))",
                    (month, status)
                )

            # 同步校验统计 + 明细落盘
            if status == "validating":
                validator = DeliveryReportValidator(self.db_path)
                result = validator.collect_suspicious(month)
                conn.execute(
                    "UPDATE dr_review_status SET total_errors=?, total_warnings=?, pending_fixes=? "
                    "WHERE month=?",
                    (result["summary"]["total_errors"],
                     result["summary"]["total_warnings"],
                     result["summary"]["total_errors"],
                     month)
                )
                # 明细落盘 dr_import_validation（先清空再写入，保证幂等）
                conn.execute("DELETE FROM dr_import_validation WHERE month = ?", (month,))
                rows_to_insert = []
                for e in result["errors"]:
                    rows_to_insert.append((
                        month, e.get("sheet", ""), e.get("row", -1),
                        e.get("col", ""), e.get("issue", ""),
                        "error", e.get("issue", ""),
                        str(e.get("value", ""))[:500] if e.get("value") is not None else "",
                        "", "pending", "",
                    ))
                for w in result["warnings"]:
                    rows_to_insert.append((
                        month, w.get("sheet", ""), w.get("row", -1),
                        w.get("col", ""), w.get("issue", ""),
                        "warning", w.get("issue", ""),
                        "", "", "pending", "",
                    ))
                if rows_to_insert:
                    conn.executemany(
                        "INSERT INTO dr_import_validation "
                        "(month, sheet, row_index, column_name, rule_code, "
                        " severity, message, original_value, corrected_value, status, operator) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        rows_to_insert
                    )
                # 同步 pending_fixes 统计（取明细表 pending 状态数）
                pending_count = conn.execute(
                    "SELECT COUNT(*) FROM dr_import_validation WHERE month = ? AND status = 'pending'",
                    (month,)
                ).fetchone()[0]
                conn.execute(
                    "UPDATE dr_review_status SET pending_fixes = ? WHERE month = ?",
                    (pending_count, month)
                )

            conn.commit()
        finally:
            conn.close()

    def _finish_job(self, job_id: int, status: str, progress: int,
                    message: str = None, output_path: str = None) -> None:
        conn = _db.get_connection(self.db_path)
        try:
            _db.update_job_status(conn, job_id, status, progress, message, output_path)
            conn.commit()
        finally:
            conn.close()

    def has_data(self, month: str) -> bool:
        return self.engine.has_data(month)

    def list_months(self) -> list[dict]:
        conn = _db.get_connection(self.db_path)
        try:
            return _db.list_months(conn, "delivery_report")
        finally:
            conn.close()

    # ─── 分步生成（v2.1：Step 1-3 + 校验）───

    def generate_with_validation(self, month: str,
                                 fixes: List[Dict] = None) -> dict:
        """带校验的生成流程（Step 1 → 2 → 3）。"""
        validator = DeliveryReportValidator(self.db_path)

        if fixes:
            validator.apply_manual_fixes(month, fixes)

        if not self.engine.has_data(month):
            result = self.generate(month, mode=MODE_REGENERATE)
        else:
            result = {"month": month, "action": "read"}

        suspicious = validator.collect_suspicious(month)

        return {
            **result,
            "validation": suspicious,
            "pending_fixes": suspicious["summary"]["total_errors"] > 0,
        }

    def validate(self, month: str) -> dict:
        """单独执行 Step 2 校验。"""
        return DeliveryReportValidator(self.db_path).collect_suspicious(month)

    def apply_fixes(self, month: str, fixes: List[Dict]) -> dict:
        """单独应用人工调整。"""
        return DeliveryReportValidator(self.db_path).apply_manual_fixes(month, fixes)
