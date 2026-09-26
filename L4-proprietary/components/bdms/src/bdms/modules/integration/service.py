# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""IntegrationService — 数据集成编排服务。

对齐 DESIGN-DETAIL-INTEGRATION-v2.1.md §4.1：
- 连接器状态查询 / 同步执行
- 暂存数据查询 / 提升到业务表
- 频率配置 / 失败重试 / 死信队列 / 同步历史
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from bdms.core.db import get_connection
from .base import BaseConnector, ConnectorRegistry, SyncResult

# 确保连接器注册
from . import connectors as _connectors  # noqa: F401
from . import local_import_connector as _lic  # noqa: F401


class IntegrationService:
    """数据集成编排服务。"""

    def __init__(self, db_path=None):
        self.db_path = db_path

    # ========================================================
    # 连接器状态
    # ========================================================

    def list_connectors(self) -> List[Dict]:
        """列出所有可用连接器及状态。"""
        result = []
        for name in ConnectorRegistry.list_names():
            cls = ConnectorRegistry._connectors[name]
            last = self._last_sync(name)
            result.append({
                "name": name,
                "data_source": cls.data_source,
                "target_modules": cls.target_modules,
                "auth_type": cls.auth_type,
                "default_frequency": cls.default_frequency,
                "status": "ready",
                "last_sync_at": last.get("started_at") if last else None,
                "last_sync_status": last.get("status") if last else None,
            })
        return result

    def get_connector_status(self, name: str) -> Dict:
        """获取指定连接器详细状态。"""
        connector = ConnectorRegistry.create(name, self.db_path)
        last = self._last_sync(name)
        freq = self.get_frequency_config(name)
        return {
            "name": name,
            "status": "ready",
            "authenticated": connector._authenticated,
            "last_sync_at": last.get("started_at") if last else None,
            "last_sync_status": last.get("status") if last else None,
            "last_sync_result": last,
            "frequency_config": freq,
            "error": None,
        }

    # ========================================================
    # 同步执行
    # ========================================================

    def sync(self, connector_name: str, **params) -> Dict:
        """执行同步（写入 int_sync_log）。"""
        connector = ConnectorRegistry.create(connector_name, self.db_path)
        result = connector.sync(**params)
        self._log_sync(result, params)
        return result.to_dict()

    def sync_all(self, **params) -> List[Dict]:
        """同步所有连接器。"""
        results = []
        for name in ConnectorRegistry.list_names():
            try:
                results.append(self.sync(name, **params))
            except Exception as e:
                results.append({
                    "connector_name": name, "status": "failed",
                    "errors": [{"error": str(e)[:200]}],
                })
        return results

    # ========================================================
    # 暂存数据
    # ========================================================

    def get_staging_data(self, connector_name: str, batch_id: str,
                         status: str = "pending", limit: int = 100,
                         offset: int = 0) -> List[Dict]:
        """查询暂存数据。"""
        conn = get_connection(self.db_path)
        try:
            where = "connector_name = ? AND batch_id = ?"
            params: list = [connector_name, batch_id]
            if status != "all":
                where += " AND status = ?"
                params.append(status)
            rows = conn.execute(
                f"SELECT * FROM int_staging WHERE {where} "
                f"ORDER BY id LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["source_data"] = json.loads(d["source_data"]) if d["source_data"] else {}
                d["normalized_data"] = json.loads(d["normalized_data"]) if d["normalized_data"] else {}
                out.append(d)
            return out
        finally:
            conn.close()

    def promote_staging(self, connector_name: str, batch_id: str,
                        target_module: str, target_table: str) -> Dict:
        """将暂存数据提升到业务表。

        通用提升：写目标表的 JSON 列（如 dr_sheet_row）或返回数据供模块处理。
        """
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                """SELECT * FROM int_staging
                   WHERE connector_name = ? AND batch_id = ?
                     AND status = 'pending'""",
                (connector_name, batch_id),
            ).fetchall()

            promoted = skipped = errors = 0
            now = datetime.now().isoformat()
            for r in rows:
                try:
                    # 通用提升逻辑：目标表有 data/normalized_data JSON 列时直接写
                    # 具体业务表结构由各模块定义，这里标记 processed + 事件
                    self._promote_one(conn, r, target_module, target_table)
                    conn.execute(
                        "UPDATE int_staging SET status = 'processed', "
                        "processed_at = ? WHERE id = ?",
                        (now, r["id"]),
                    )
                    promoted += 1
                except Exception as e:
                    conn.execute(
                        "UPDATE int_staging SET status = 'error', "
                        "error_msg = ? WHERE id = ?",
                        (str(e)[:200], r["id"]),
                    )
                    errors += 1
                    skipped += 1
            conn.commit()
            return {
                "batch_id": batch_id,
                "target_module": target_module,
                "target_table": target_table,
                "promoted_count": promoted,
                "skipped_count": skipped,
                "error_count": errors,
            }
        finally:
            conn.close()

    def _promote_one(self, conn, staging_row, target_module: str,
                     target_table: str) -> None:
        """单条提升（写 outbox 事件，由目标模块消费）。"""
        conn.execute(
            """INSERT INTO outbox_events
               (event_type, aggregate_type, aggregate_id, payload)
               VALUES (?, ?, ?, ?)""",
            (f"{target_module}.staging_promoted",
             target_table,
             str(staging_row["source_id"]),
             json.dumps({
                 "batch_id": staging_row["batch_id"],
                 "target_table": target_table,
                 "data": staging_row["normalized_data"],
             }, ensure_ascii=False, default=str)),
        )

    # ========================================================
    # 频率配置
    # ========================================================

    def configure_frequency(self, connector_name: str, schedule: str,
                            cron_expr: str = None,
                            event_triggers: List[str] = None) -> Dict:
        """配置同步频率。"""
        if schedule not in ("manual", "cron", "event"):
            raise ValueError(f"schedule 非法: {schedule}")
        if schedule == "cron" and not cron_expr:
            raise ValueError("schedule=cron 需要 cron_expr")
        if schedule == "event" and not event_triggers:
            raise ValueError("schedule=event 需要 event_triggers")

        conn = get_connection(self.db_path)
        try:
            conn.execute(
                """INSERT INTO int_frequency_config
                   (connector_name, schedule, cron_expr, event_triggers, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(connector_name) DO UPDATE SET
                     schedule = excluded.schedule,
                     cron_expr = excluded.cron_expr,
                     event_triggers = excluded.event_triggers,
                     updated_at = excluded.updated_at""",
                (connector_name, schedule, cron_expr,
                 json.dumps(event_triggers or []), datetime.now().isoformat()),
            )
            conn.commit()
            return {
                "connector_name": connector_name,
                "schedule": schedule,
                "cron_expr": cron_expr,
            }
        finally:
            conn.close()

    def get_frequency_config(self, connector_name: str) -> Dict:
        """获取频率配置。"""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM int_frequency_config WHERE connector_name = ?",
                (connector_name,),
            ).fetchone()
            if not row:
                return {"schedule": "manual", "cron_expr": None,
                        "event_triggers": []}
            d = dict(row)
            d["event_triggers"] = json.loads(d["event_triggers"] or "[]")
            return d
        finally:
            conn.close()

    # ========================================================
    # 重试 + 死信
    # ========================================================

    def retry_failed(self, connector_name: str, batch_id: str) -> Dict:
        """重试失败同步（指数退避由调用方/调度器控制间隔）。"""
        conn = get_connection(self.db_path)
        try:
            # 重置 error 状态的暂存行
            conn.execute(
                """UPDATE int_staging
                   SET status = 'pending', retry_count = retry_count + 1,
                       error_msg = NULL
                   WHERE connector_name = ? AND batch_id = ? AND status = 'error'""",
                (connector_name, batch_id),
            )
            conn.commit()
            # 重新执行同步
            return self.sync(connector_name)
        finally:
            conn.close()

    def get_dead_letters(self, status: str = "pending") -> List[Dict]:
        """查询死信队列。"""
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM int_dead_letter WHERE status = ? ORDER BY id DESC LIMIT 100",
                (status,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def move_to_dead_letter(self, connector_name: str, batch_id: str,
                            source_id: str, error_msg: str,
                            error_type: str = "system") -> None:
        """移入死信队列（重试超限后）。"""
        conn = get_connection(self.db_path)
        try:
            conn.execute(
                """INSERT INTO int_dead_letter
                   (connector_name, batch_id, source_id, error_msg, error_type)
                   VALUES (?, ?, ?, ?, ?)""",
                (connector_name, batch_id, source_id, error_msg[:500], error_type),
            )
            conn.commit()
        finally:
            conn.close()

    # ========================================================
    # 同步历史
    # ========================================================

    def get_sync_history(self, connector_name: Optional[str] = None,
                         limit: int = 20, offset: int = 0) -> List[Dict]:
        """查询同步历史。"""
        conn = get_connection(self.db_path)
        try:
            where = "WHERE connector_name = ?" if connector_name else ""
            params = [connector_name] if connector_name else []
            rows = conn.execute(
                f"""SELECT * FROM int_sync_log {where}
                    ORDER BY started_at DESC LIMIT ? OFFSET ?""",
                [*params, limit, offset],
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ========================================================
    # 内部
    # ========================================================

    def _last_sync(self, connector_name: str) -> Optional[Dict]:
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM int_sync_log WHERE connector_name = ? "
                "ORDER BY started_at DESC LIMIT 1",
                (connector_name,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _log_sync(self, result: SyncResult, params: Dict) -> None:
        conn = get_connection(self.db_path)
        try:
            conn.execute(
                """INSERT OR REPLACE INTO int_sync_log
                   (connector_name, batch_id, mode, status, total_fetched,
                    new_count, updated_count, unchanged_count, error_count,
                    params, started_at, completed_at)
                   VALUES (?, ?, 'sync', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (result.connector_name, result.batch_id, result.status,
                 result.total_fetched, result.new_count, result.updated_count,
                 result.unchanged_count, result.error_count,
                 json.dumps(params, ensure_ascii=False, default=str),
                 result.started_at, result.completed_at),
            )
            conn.commit()
        finally:
            conn.close()
