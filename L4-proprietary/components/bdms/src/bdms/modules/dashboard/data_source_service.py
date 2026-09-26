# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""DashboardDataSourceService — 数据源注册 + SQL 辅助操作。

对齐 DESIGN-DETAIL-DASHBOARD-v2.1.md §6.4。
新模块即插即用：register_source 注册聚合 SQL → compute_metric 实时计算。
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from bdms.core.db import get_connection


class SqlValidationError(Exception):
    """SQL 校验失败。"""


# 危险 SQL 模式（防注入/防破坏）
_FORBIDDEN_PATTERNS = [
    r"\bDROP\b", r"\bDELETE\b", r"\bINSERT\b", r"\bUPDATE\b",
    r"\bALTER\b", r"\bCREATE\b", r"\bATTACH\b", r"\bDETACH\b",
    r"\bPRAGMA\b",
]
_SELECT_ONLY_RE = re.compile(r"^\s*SELECT\s+.+\s+FROM\s+.+$", re.DOTALL | re.IGNORECASE)


class DashboardDataSourceService:
    """数据源注册服务。"""

    def __init__(self, db_path=None):
        self.db_path = db_path

    # ========================================================
    # 数据源 CRUD
    # ========================================================

    def register_source(self, source_key: str, module: str, title: str,
                        category: str, aggregate_sql: str,
                        refresh_mode: str = "realtime",
                        description: str = "") -> Dict:
        """注册新数据源（自动 SQL 校验 + 说明生成）。"""
        self.validate_sql(aggregate_sql)

        conn = get_connection(self.db_path)
        try:
            self._ensure_table(conn)
            conn.execute(
                """INSERT OR REPLACE INTO dashboard_data_source
                   (source_key, module, title, category, aggregate_sql,
                    refresh_mode, description, enabled, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                (source_key, module, title, category, aggregate_sql,
                 refresh_mode, description or f"{module}/{title}",
                 datetime.now().isoformat()),
            )
            conn.commit()

            auto_desc = self._describe_sql(aggregate_sql)
            return {
                "source_key": source_key,
                "description_auto": auto_desc,
                "warnings": [],
            }
        finally:
            conn.close()

    def list_sources(self, enabled_only: bool = True) -> List[Dict]:
        """列出所有已注册数据源。"""
        conn = get_connection(self.db_path)
        try:
            where = "WHERE enabled = 1" if enabled_only else ""
            rows = conn.execute(
                f"SELECT * FROM dashboard_data_source {where} "
                f"ORDER BY module, category, source_key"
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()

    def compute_metric(self, source_key: str,
                       month: Optional[str] = None) -> Dict:
        """计算指定数据源的指标值。"""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT aggregate_sql FROM dashboard_data_source "
                "WHERE source_key = ? AND enabled = 1",
                (source_key,),
            ).fetchone()
            if not row:
                raise ValueError(f"数据源 {source_key} 未注册或已禁用")

            sql = row[0]
            params: List[Any] = []
            if month:
                if "?" in sql:
                    params.append(month)
                if "?" in sql and len([c for c in sql if c == "?"]) > 1:
                    # 两个占位符（month 前缀两种格式）
                    params = [month, f"{month[:4]}-{month[4:6]}"]

            result = conn.execute(sql, params).fetchone()
            value = result[0] if result else None
            return {"source_key": source_key, "month": month, "value": value}
        finally:
            conn.close()

    # ========================================================
    # SQL 辅助操作
    # ========================================================

    def validate_sql(self, sql: str) -> None:
        """SQL 校验：只允许 SELECT，禁止写操作。"""
        if not sql or not sql.strip():
            raise SqlValidationError("SQL 为空")

        if not _SELECT_ONLY_RE.match(sql):
            raise SqlValidationError(
                "只允许 SELECT ... FROM ... 查询语句")

        for pattern in _FORBIDDEN_PATTERNS:
            if re.search(pattern, sql, re.IGNORECASE):
                raise SqlValidationError(
                    f"SQL 包含禁止的关键字: {pattern.strip(chr(92)).strip('b')}")

    def dry_run_sql(self, sql: str, limit: int = 10) -> Dict:
        """SQL 试运行（加 LIMIT 保护）。"""
        self.validate_sql(sql)
        safe_sql = sql.rstrip().rstrip(";")
        if "LIMIT" not in safe_sql.upper():
            safe_sql = f"SELECT * FROM ({safe_sql}) LIMIT {int(limit)}"

        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(safe_sql).fetchall()
            columns = [d[0] for d in conn.execute(safe_sql).description] \
                if conn.execute(safe_sql).description else []
            return {
                "columns": columns,
                "rows": [dict(r) for r in rows],
                "row_count": len(rows),
            }
        except sqlite3.Error as e:
            raise SqlValidationError(f"SQL 执行失败: {e}")
        finally:
            conn.close()

    def describe_sql(self, sql: str) -> Dict:
        """SQL 描述：返回涉及的表/列/聚合方式。"""
        self.validate_sql(sql)
        return {
            "tables": self._extract_tables(sql),
            "aggregations": self._extract_aggregations(sql),
            "has_group_by": "GROUP BY" in sql.upper(),
            "has_month_param": "?" in sql,
        }

    def suggest_field_mapping(self, source_key: str) -> List[Dict]:
        """建议字段映射（基于已注册数据源的表结构）。"""
        sources = self.list_sources()
        return [
            {"source_key": s["source_key"], "module": s["module"],
             "title": s["title"]}
            for s in sources
        ]

    @staticmethod
    def _describe_sql(sql: str) -> str:
        """生成 SQL 自动说明。"""
        tables = DashboardDataSourceService._extract_tables(sql)
        aggs = DashboardDataSourceService._extract_aggregations(sql)
        parts = []
        if aggs:
            parts.append(" + ".join(aggs))
        if tables:
            parts.append("按 " + "/".join(tables))
        return "统计：" + (" ".join(parts) if parts else "自定义查询")

    @staticmethod
    def _extract_tables(sql: str) -> List[str]:
        return re.findall(
            r"\bFROM\s+([a-z_][a-z0-9_]*)", sql, re.IGNORECASE)

    @staticmethod
    def _extract_aggregations(sql: str) -> List[str]:
        return sorted(set(
            m.upper() for m in re.findall(
                r"\b(COUNT|SUM|AVG|MIN|MAX)\s*\(", sql, re.IGNORECASE)))

    @staticmethod
    def _ensure_table(conn) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dashboard_data_source (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_key TEXT UNIQUE NOT NULL,
                module TEXT NOT NULL,
                title TEXT NOT NULL,
                category TEXT,
                aggregate_sql TEXT NOT NULL,
                refresh_mode TEXT DEFAULT 'realtime',
                description TEXT,
                enabled INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                updated_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)
