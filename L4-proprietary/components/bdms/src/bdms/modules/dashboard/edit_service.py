# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""DashboardEditService — 驾驶舱明细编辑（字段编辑 + 权限 + 历史 + 撤销）。

对齐 DESIGN-DETAIL-DASHBOARD-v2.1.md §6.3。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from bdms.core.db import get_connection


class DashboardEditService:
    """明细编辑服务。"""

    # 可编辑字段配置（按角色控制）
    EDITABLE_FIELDS = {
        "cr_contracts": {
            "remark": {"label": "备注", "type": "text",
                       "roles": ["admin", "pmo", "sales", "super_admin"]},
            "status": {"label": "状态", "type": "select",
                       "roles": ["admin", "pmo", "super_admin"]},
        },
        "pm_projects": {
            "remark": {"label": "备注", "type": "text",
                       "roles": ["admin", "pmo", "pm", "super_admin"]},
            "pm": {"label": "项目经理", "type": "text",
                   "roles": ["admin", "pmo", "super_admin"]},
        },
        "rk_risks": {
            "remark": {"label": "备注", "type": "text",
                       "roles": ["admin", "pmo", "pm", "super_admin"]},
            "status": {"label": "状态", "type": "select",
                       "roles": ["admin", "pmo", "pm", "super_admin"]},
            "resolution": {"label": "处置方案", "type": "textarea",
                           "roles": ["admin", "pmo", "pm", "super_admin"]},
        },
        "as_tickets": {
            "remark": {"label": "备注", "type": "text",
                       "roles": ["admin", "pmo", "tech", "super_admin"]},
            "status": {"label": "状态", "type": "select",
                       "roles": ["admin", "pmo", "tech", "super_admin"]},
        },
    }

    def __init__(self, db_path=None):
        self.db_path = db_path

    # ========================================================
    # 权限检查
    # ========================================================

    def set_current_roles(self, roles: List[str]) -> None:
        """显式设置当前角色（测试/CLI 用，优先于查表）。"""
        self._explicit_roles = roles

    def check_permission(self, user_id: str, table: str, field: str,
                         record_id: Optional[int] = None) -> bool:
        """权限检查：角色控制字段范围。"""
        table_conf = self.EDITABLE_FIELDS.get(table)
        if not table_conf:
            return False
        field_conf = table_conf.get(field)
        if not field_conf:
            return False

        roles = getattr(self, "_explicit_roles", None) or self._user_roles(user_id)
        return any(r in field_conf["roles"] for r in roles)

    # ========================================================
    # 编辑操作
    # ========================================================

    def edit_field(self, record_id: int, field: str, value: Any,
                   table: str, user_id: str) -> Dict:
        """单字段编辑（权限 + 历史 + 即时保存）。"""
        if not self.check_permission(user_id, table, field, record_id):
            raise PermissionError(
                f"用户 {user_id} 无权编辑 {table}.{field}")

        old_value = self._read_field(table, record_id, field)
        if old_value == value:
            return {"record_id": record_id, "field": field,
                    "changed": False, "message": "值未变化"}

        self._write_field(table, record_id, field, value)
        edit_id = self._write_history(table, record_id, field,
                                      old_value, value, user_id)
        return {"record_id": record_id, "field": field, "edit_id": edit_id,
                "old_value": old_value, "new_value": value, "changed": True}

    def batch_edit(self, record_ids: List[int], field: str, value: Any,
                   table: str, user_id: str) -> Dict:
        """批量编辑。"""
        results = {"succeeded": 0, "failed": 0, "errors": []}
        for rid in record_ids:
            try:
                r = self.edit_field(rid, field, value, table, user_id)
                results["succeeded"] += 1
            except (PermissionError, ValueError) as e:
                results["failed"] += 1
                results["errors"].append(
                    {"record_id": rid, "error": str(e)[:100]})
        return results

    def get_edit_history(self, record_id: int, table: str) -> List[Dict]:
        """获取编辑历史。"""
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                """SELECT * FROM db_edit_history
                   WHERE table_name = ? AND record_id = ?
                   ORDER BY id DESC""",
                (table, record_id),
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return []  # 表不存在（未初始化）
        finally:
            conn.close()

    def undo_edit(self, edit_id: int, user_id: str) -> Dict:
        """撤销单次编辑（恢复旧值）。"""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM db_edit_history WHERE id = ?", (edit_id,)
            ).fetchone()
            if not row:
                raise ValueError(f"编辑记录 {edit_id} 不存在")
            if row["operator"] != user_id:
                raise PermissionError("只能撤销自己的编辑")

            # 恢复旧值
            conn.execute(
                f"UPDATE {row['table_name']} SET {row['field']} = ? "
                f"WHERE id = ?",
                (row["old_value"], row["record_id"]),
            )
            conn.execute(
                "DELETE FROM db_edit_history WHERE id = ?", (edit_id,))
            conn.commit()
            return {"edit_id": edit_id, "undone": True,
                    "restored_value": row["old_value"]}
        finally:
            conn.close()

    # ========================================================
    # 内部工具
    # ========================================================

    def _user_roles(self, user_id: str) -> List[str]:
        """查用户角色（sys_user 表，JSON roles 列）。"""
        conn = get_connection(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sys_user (
                    user_id TEXT PRIMARY KEY,
                    roles TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT DEFAULT (datetime('now','localtime'))
                )
            """)
            row = conn.execute(
                "SELECT roles FROM sys_user WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if row and row[0]:
                return json.loads(row[0])
        except (sqlite3.Error, json.JSONDecodeError):
            pass
        finally:
            conn.close()
        return []

    def _read_field(self, table: str, record_id: int, field: str) -> Any:
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                f"SELECT {field} FROM {table} WHERE id = ?", (record_id,)
            ).fetchone()
            if not row:
                raise ValueError(f"记录 {table}/{record_id} 不存在")
            return row[0]
        finally:
            conn.close()

    def _write_field(self, table: str, record_id: int,
                     field: str, value: Any) -> None:
        conn = get_connection(self.db_path)
        try:
            conn.execute(
                f"UPDATE {table} SET {field} = ? WHERE id = ?",
                (value, record_id))
            conn.commit()
        finally:
            conn.close()

    def _write_history(self, table: str, record_id: int, field: str,
                       old_value: Any, new_value: Any, user_id: str) -> int:
        conn = get_connection(self.db_path)
        try:
            cur = conn.execute(
                """INSERT INTO db_edit_history
                   (table_name, record_id, field, old_value, new_value,
                    operator, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (table, record_id, field,
                 str(old_value)[:500], str(new_value)[:500],
                 user_id, datetime.now().isoformat()),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    @staticmethod
    def _ensure_history_table(conn) -> None:
        """确保编辑历史表存在（幂等）。"""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS db_edit_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_name TEXT NOT NULL,
                record_id INTEGER NOT NULL,
                column_name TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                operator TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)
