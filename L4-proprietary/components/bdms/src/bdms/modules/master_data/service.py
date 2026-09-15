"""【模块3】交付管理基础数据 —— 服务层（编排 + 写操作）。

对外契约（见 docs/MODULE-CONTRACT.md §2）：
    list_xxx / get_xxx / create_xxx / update_xxx / delete_xxx

本模块命名为 list_items / get_item / create_item / update_item / delete_item，
并额外提供 list_types / list_legend / import_legend_from_excel。
"""

import json
from pathlib import Path
from typing import Any, Optional

from bdms.core import db as _db
from bdms.core.paths import find_revenue_source
from .engine import (
    MasterDataEngine, DATA_TYPES, DEFAULT_DATA_TYPE, DEFAULT_SORT_STEP,
    make_code,
)


class MasterDataService:
    """基础数据服务：CRUD + 从手工报表导入图例。"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else None
        self.engine = MasterDataEngine(self.db_path)

    # ─── 建表兜底（幂等）───

    def ensure_schema(self) -> None:
        _db.init_db(self.db_path)

    # ─── 查询 ───

    def list_types(self) -> list[dict]:
        return self.engine.list_types()

    def list_items(self, data_type: str = DEFAULT_DATA_TYPE,
                   include_disabled: bool = False,
                   keyword: Optional[str] = None) -> list[dict]:
        return self.engine.list_items(data_type, include_disabled, keyword)

    def list_legend(self, include_disabled: bool = False) -> list[dict]:
        """图例专用快捷方法。"""
        return self.engine.list_items("legend", include_disabled)

    def get_item(self, data_type: str, code: str) -> Optional[dict]:
        return self.engine.get_item(data_type, code)

    def get_labels(self, data_type: str) -> list[str]:
        return self.engine.get_labels(data_type)

    # ─── 变更 ───

    def create_item(self, data_type: str, label: str,
                    code: Optional[str] = None,
                    extra: Optional[dict] = None,
                    sort_order: Optional[int] = None) -> dict:
        """新增基础数据条目。

        返回 {"ok": bool, "action": "created"|"exists", "item": {...}}
        """
        if not data_type or not str(data_type).strip():
            raise ValueError("data_type 不能为空")
        label = (label or "").strip()
        if not label:
            raise ValueError("label 不能为空")

        code = (code or make_code(label)).strip()
        conn = _db.get_connection(self.db_path)
        try:
            existed = conn.execute(
                "SELECT * FROM md_reference WHERE data_type = ? AND code = ?",
                (data_type, code),
            ).fetchone()
            if existed:
                return {"ok": False, "action": "exists",
                        "item": self.engine._row_to_dict(existed)}

            if sort_order is None:
                row = conn.execute(
                    "SELECT MAX(sort_order) AS m FROM md_reference WHERE data_type = ?",
                    (data_type,),
                ).fetchone()
                sort_order = (row["m"] or 0) + DEFAULT_SORT_STEP

            conn.execute(
                """INSERT INTO md_reference
                   (data_type, code, label, extra, sort_order, enabled, updated_at)
                   VALUES (?, ?, ?, ?, ?, 1, datetime('now', 'localtime'))""",
                (data_type, code, label,
                 json.dumps(extra, ensure_ascii=False) if extra else None,
                 sort_order),
            )
            conn.commit()
            return {"ok": True, "action": "created",
                    "item": self.engine.get_item(data_type, code)}
        finally:
            conn.close()

    def update_item(self, data_type: str, code: str, **data) -> dict:
        """更新条目。支持 label / extra / sort_order / enabled / new_code。"""
        conn = _db.get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM md_reference WHERE data_type = ? AND code = ?",
                (data_type, code),
            ).fetchone()
            if not row:
                return {"ok": False, "action": "not_found",
                        "message": f"{data_type}/{code} 不存在"}

            sets: list[str] = []
            params: list = []
            if "label" in data:
                sets.append("label = ?"); params.append(str(data["label"]).strip())
            if "extra" in data:
                ev = data["extra"]
                sets.append("extra = ?")
                params.append(json.dumps(ev, ensure_ascii=False)
                              if isinstance(ev, (dict, list)) else ev)
            if "sort_order" in data:
                sets.append("sort_order = ?"); params.append(int(data["sort_order"]))
            if "enabled" in data:
                sets.append("enabled = ?"); params.append(1 if data["enabled"] else 0)
            if "new_code" in data and data["new_code"]:
                sets.append("code = ?"); params.append(str(data["new_code"]).strip())

            if not sets:
                return {"ok": False, "action": "noop", "message": "无更新字段"}

            sets.append("updated_at = datetime('now', 'localtime')")
            params += [data_type, code]
            conn.execute(
                f"UPDATE md_reference SET {', '.join(sets)} "
                f"WHERE data_type = ? AND code = ?", params,
            )
            conn.commit()
            new_code = str(data.get("new_code") or code)
            return {"ok": True, "action": "updated",
                    "item": self.engine.get_item(data_type, new_code)}
        finally:
            conn.close()

    def delete_item(self, data_type: str, code: str, hard: bool = False) -> dict:
        """删除条目。默认**软删除**（enabled=0）。"""
        conn = _db.get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM md_reference WHERE data_type = ? AND code = ?",
                (data_type, code),
            ).fetchone()
            if not row:
                return {"ok": False, "action": "not_found",
                        "message": f"{data_type}/{code} 不存在"}
            if hard:
                conn.execute(
                    "DELETE FROM md_reference WHERE data_type = ? AND code = ?",
                    (data_type, code),
                )
                action = "deleted_hard"
            else:
                conn.execute(
                    """UPDATE md_reference SET enabled = 0,
                       updated_at = datetime('now', 'localtime')
                       WHERE data_type = ? AND code = ?""",
                    (data_type, code),
                )
                action = "soft_deleted"
            conn.commit()
            return {"ok": True, "action": action, "data_type": data_type, "code": code}
        finally:
            conn.close()

    def restore_item(self, data_type: str, code: str) -> dict:
        """恢复软删除条目。"""
        return self.update_item(data_type, code, enabled=True)

    # ─── 从手工报表导入图例 ───

    def import_legend_from_excel(
        self,
        excel_path: Optional[Path] = None,
        month: str = "202606",
        sheet_name: str = "图例",
        overwrite: bool = True,
        data_types: Optional[list[str]] = None,
    ) -> dict:
        """从手工报表「图例」sheet 导入基础数据。

        参数：
          excel_path  源 xlsx；None 时用 paths.find_revenue_source(month) 自动定位
          month       用于自动定位源文件的月份
          data_types  只导入指定类型；None = 全部块

        返回：
          {"ok", "source", "month", "imported": {dt: n}, "skipped": {...},
           "warnings": [...], "total"}
        """
        if excel_path is None:
            excel_path = find_revenue_source(month)
            if excel_path is None:
                return {"ok": False, "message":
                        f"未找到 {month} 的确收对比表（图例源），请显式传 excel_path"}
        excel_path = Path(excel_path)

        parsed = self.engine.parse_legend_excel(excel_path, sheet_name)

        conn = _db.get_connection(self.db_path)
        imported: dict[str, int] = {}
        skipped: dict[str, int] = {}
        try:
            for dt, items in parsed["blocks"].items():
                if data_types and dt not in data_types:
                    continue
                n = 0
                sk = 0
                for it in items:
                    if overwrite:
                        # 覆盖语义：同 (data_type, code) 更新 label/extra/sort_order
                        conn.execute(
                            """INSERT INTO md_reference
                               (data_type, code, label, extra, sort_order, enabled, updated_at)
                               VALUES (?, ?, ?, ?, ?, 1, datetime('now','localtime'))
                               ON CONFLICT(data_type, code) DO UPDATE SET
                                 label = excluded.label,
                                 extra = excluded.extra,
                                 sort_order = excluded.sort_order,
                                 enabled = 1,
                                 updated_at = datetime('now','localtime')""",
                            (dt, it["code"], it["label"],
                             json.dumps(it["extra"], ensure_ascii=False)
                             if it["extra"] else None,
                             it["sort_order"]),
                        )
                        n += 1
                    else:
                        cur = conn.execute(
                            """INSERT OR IGNORE INTO md_reference
                               (data_type, code, label, extra, sort_order, enabled)
                               VALUES (?, ?, ?, ?, ?, 1)""",
                            (dt, it["code"], it["label"],
                             json.dumps(it["extra"], ensure_ascii=False)
                             if it["extra"] else None,
                             it["sort_order"]),
                        )
                        if cur.rowcount:
                            n += 1
                        else:
                            sk += 1
                imported[dt] = n
                skipped[dt] = sk

            # 记录导入日志
            conn.execute(
                """INSERT INTO import_log
                   (module, month, source_type, source_path, data_type,
                    row_count, status, message)
                   VALUES ('master_data', ?, 'xlsx', ?, ?, ?, 'done', ?)""",
                (month, str(excel_path),
                 ",".join(imported.keys()), sum(imported.values()),
                 f"图例 sheet，有效数据行 {parsed['valid_rows']}"),
            )
            # 登记月份数据
            conn.commit()
        finally:
            conn.close()

        return {
            "ok": True,
            "source": str(excel_path),
            "month": month,
            "sheet": parsed["sheet"],
            "valid_rows": parsed["valid_rows"],
            "max_row": parsed["max_row"],
            "imported": imported,
            "skipped": skipped,
            "total": sum(imported.values()),
            "warnings": parsed["warnings"],
        }

    # ─── 统计摘要 ───

    def summary(self) -> dict:
        """基础数据概览（Web 首页/看板用）。"""
        types = self.engine.list_types()
        return {
            "types": types,
            "total_items": self.engine.count(),
            "enabled_items": self.engine.count(include_disabled=False),
            "known_types": DATA_TYPES,
        }
