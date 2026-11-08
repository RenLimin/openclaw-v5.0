"""repository — revenue_forecast 持久化层（Phase 3）。

严格按 DESIGN-DETAIL-REVENUE-FORECAST-v1.0 §4 DDL，四张表：
  forecast_period / forecast_line / forecast_monthly / forecast_totals。

职责边界：
  - 只做持久化与查询；不读 Excel、不调 engine、不造新数据结构；
  - 输入为 report_parser.ObligationRow 列表与 engine.ForecastResult；
  - 可注入 sqlite3 连接或 db path（含 :memory:）以便测试，不引连接池/第三方依赖。

事务语义：
  - save_result 全程单事务（SQLite autocommit DML 包在 BEGIN..COMMIT 内）；
  - 版本切换：同事务旧 is_current=0 → 新 period is_current=1，历史版本数据保留；
  - 同期重算：同事务 DELETE 该 period 的 line/monthly/totals 后重插，幂等无重复。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional, Sequence, Union

from .engine import ForecastResult
from .report_parser import ObligationRow

# ─── 常量 ───

BASIS_LOCKED = "locked"
BASIS_DYNAMIC_DUE = "dynamic_due"
BASIS_PIPELINE = "pipeline"
BASIS_VALUES = (BASIS_LOCKED, BASIS_DYNAMIC_DUE, BASIS_PIPELINE)

PIPELINE_MONTH_KEY = "pipeline"   # pipeline 桶在 forecast_monthly 中的 month 值
DEFAULT_SOURCE = "report"         # forecast_line.source，Part B 预留 report|ones

MONTH_KEYS = tuple(f"{m:02d}" for m in range(1, 13))


# ─── DDL（与 DETAIL §4 逐表对齐）───

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS forecast_period (
    period TEXT PRIMARY KEY, forecast_year INTEGER NOT NULL,
    source_file TEXT NOT NULL, is_current INTEGER NOT NULL DEFAULT 0,
    locked_total REAL NOT NULL, dynamic_total REAL NOT NULL,
    actual_ytd REAL NOT NULL, line_count INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS forecast_line (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL, obligation_id TEXT NOT NULL,
    budget_id TEXT, contract_no TEXT, contract_name TEXT, customer TEXT, end_user TEXT,
    category_group TEXT NOT NULL, revenue_method TEXT,
    locked_year REAL NOT NULL, actual_ytd REAL NOT NULL,
    raw_due TEXT, due_date TEXT, dyn_category TEXT NOT NULL,
    amount_future REAL NOT NULL, dyn_in_plan INTEGER NOT NULL, dyn_counted REAL NOT NULL,
    source TEXT NOT NULL DEFAULT 'report',
    UNIQUE(period, obligation_id)
);
CREATE INDEX IF NOT EXISTS idx_fl_cat ON forecast_line(period, dyn_category);
CREATE TABLE IF NOT EXISTS forecast_monthly (
    period TEXT NOT NULL, basis TEXT NOT NULL,
    month TEXT NOT NULL, category_group TEXT NOT NULL DEFAULT 'all',
    amount REAL NOT NULL,
    PRIMARY KEY(period, basis, month, category_group)
);
CREATE TABLE IF NOT EXISTS forecast_totals (
    period TEXT PRIMARY KEY, forecast_year INTEGER,
    locked_total REAL, locked_by_group_json TEXT,
    dynamic_total REAL, dynamic_by_group_json TEXT,
    dynamic_pipeline REAL, actual_ytd REAL, gap REAL
);
"""


class ForecastRepository:
    """双口径预估结果的 SQLite 仓储（仅持久化/查询）。

    构造：
        ForecastRepository(sqlite3_conn)   —— 调用方管理连接生命周期
        ForecastRepository("/path/x.db")   —— 仓储自建连接，close() 时关闭
        ForecastRepository(":memory:")
    """

    def __init__(self, conn_or_path: Union[sqlite3.Connection, str, Path]):
        if isinstance(conn_or_path, sqlite3.Connection):
            self._conn = conn_or_path
            self._owns_conn = False
        else:
            self._conn = sqlite3.connect(str(conn_or_path))
            self._owns_conn = True
        self._conn.row_factory = sqlite3.Row

    # ─── 生命周期 ───

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def close(self) -> None:
        if self._owns_conn:
            self._conn.close()

    def __enter__(self) -> "ForecastRepository":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ─── Schema ───

    def ensure_schema(self) -> None:
        """建四张表 + 索引。CREATE IF NOT EXISTS，连调幂等不报错。"""
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.commit()

    # ─── 写入 ───

    def save_result(
        self,
        period: str,
        rows: Sequence[ObligationRow],
        result: ForecastResult,
        source_file: str,
    ) -> None:
        """单事务写四表：版本切换 + 同期重建幂等。

        - 同事务先把全部 period 的 is_current 置 0，再 UPSERT 当前 period 为 1；
        - 当前 period 的 line/monthly/totals 先 DELETE 再重插，无重复行；
        - 其他 period 的明细数据原样保留。
        """
        if not period:
            raise ValueError("period 不能为空")
        conn = self._conn
        with conn:  # 单事务：成功 commit / 异常 rollback
            # 1) 版本切换：旧版本全部取消 current
            conn.execute("UPDATE forecast_period SET is_current = 0")

            # 2) period 行：存在则更新（保留 created_at），不存在则插入
            conn.execute(
                """
                INSERT INTO forecast_period
                    (period, forecast_year, source_file, is_current,
                     locked_total, dynamic_total, actual_ytd, line_count, created_at)
                VALUES (?, ?, ?, 1, ?, ?, ?, ?, datetime('now','localtime'))
                ON CONFLICT(period) DO UPDATE SET
                    forecast_year = excluded.forecast_year,
                    source_file   = excluded.source_file,
                    is_current    = 1,
                    locked_total  = excluded.locked_total,
                    dynamic_total = excluded.dynamic_total,
                    actual_ytd    = excluded.actual_ytd,
                    line_count    = excluded.line_count
                """,
                (
                    period, result.forecast_year, source_file,
                    result.locked_total, result.dynamic_total,
                    result.actual_ytd_total, result.line_count,
                ),
            )

            # 3) 同期重算：清理旧明细三表后重插
            conn.execute("DELETE FROM forecast_line WHERE period = ?", (period,))
            conn.execute("DELETE FROM forecast_monthly WHERE period = ?", (period,))
            conn.execute("DELETE FROM forecast_totals WHERE period = ?", (period,))

            conn.executemany(
                """
                INSERT INTO forecast_line
                    (period, obligation_id, budget_id, contract_no, contract_name,
                     customer, end_user, category_group, revenue_method,
                     locked_year, actual_ytd, raw_due, due_date, dyn_category,
                     amount_future, dyn_in_plan, dyn_counted, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        period, r.obligation_id, r.budget_id, r.contract_no,
                        r.contract_name, r.customer, r.end_user,
                        r.category_group, r.revenue_method,
                        r.locked_year, r.actual_ytd, r.raw_due, r.due_date,
                        r.dyn_category, r.amount_future,
                        1 if r.dyn_in_plan else 0, r.dyn_counted,
                        DEFAULT_SOURCE,
                    )
                    for r in rows
                ],
            )

            # 4) 逐月：locked / dynamic_due 各 12 行 + pipeline 桶 1 行（category_group='all'）
            monthly_rows = []
            for mk in MONTH_KEYS:
                monthly_rows.append(
                    (period, BASIS_LOCKED, mk, "all", result.locked_monthly[mk])
                )
                monthly_rows.append(
                    (period, BASIS_DYNAMIC_DUE, mk, "all",
                     result.dynamic_due_monthly[mk])
                )
            monthly_rows.append(
                (period, BASIS_PIPELINE, PIPELINE_MONTH_KEY, "all",
                 result.dynamic_pipeline)
            )
            conn.executemany(
                """
                INSERT INTO forecast_monthly (period, basis, month, category_group, amount)
                VALUES (?, ?, ?, ?, ?)
                """,
                monthly_rows,
            )

            # 5) 汇总（by_group 以 JSON 落库）
            conn.execute(
                """
                INSERT INTO forecast_totals
                    (period, forecast_year, locked_total, locked_by_group_json,
                     dynamic_total, dynamic_by_group_json,
                     dynamic_pipeline, actual_ytd, gap)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    period, result.forecast_year, result.locked_total,
                    json.dumps(result.locked_by_group, ensure_ascii=False),
                    result.dynamic_total,
                    json.dumps(result.dynamic_by_group, ensure_ascii=False),
                    result.dynamic_pipeline, result.actual_ytd_total,
                    result.gap_dynamic_minus_locked,
                ),
            )

    # ─── 查询：period ───

    def get_current_period(self) -> Optional[dict]:
        """返回当前 period 行；无 current 返回 None。"""
        row = self._conn.execute(
            "SELECT * FROM forecast_period WHERE is_current = 1 "
            "ORDER BY period DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def list_periods(self) -> list[dict]:
        """全部账期，按 period 降序（含历史版本）。"""
        rows = self._conn.execute(
            "SELECT * FROM forecast_period ORDER BY period DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    # ─── 查询：汇总/逐月 ───

    def get_totals(self, period: str) -> Optional[dict]:
        """读 totals；by_group JSON 解析回 dict。不存在返回 None。"""
        row = self._conn.execute(
            "SELECT * FROM forecast_totals WHERE period = ?", (period,)
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["locked_by_group"] = json.loads(d.pop("locked_by_group_json") or "{}")
        d["dynamic_by_group"] = json.loads(d.pop("dynamic_by_group_json") or "{}")
        return d

    def get_monthly(self, period: str, basis: str) -> dict:
        """读逐月。

        - locked / dynamic_due：返回 {"01".. "12": amount}（缺月补 0）；
        - pipeline：返回 {"pipeline": amount}。
        """
        if basis not in BASIS_VALUES:
            raise ValueError(f"basis 必须 ∈ {BASIS_VALUES}，实际: {basis!r}")
        rows = self._conn.execute(
            "SELECT month, amount FROM forecast_monthly "
            "WHERE period = ? AND basis = ? AND category_group = 'all'",
            (period, basis),
        ).fetchall()
        data = {r["month"]: r["amount"] for r in rows}
        if basis == BASIS_PIPELINE:
            return {PIPELINE_MONTH_KEY: data.get(PIPELINE_MONTH_KEY, 0.0)}
        return {mk: data.get(mk, 0.0) for mk in MONTH_KEYS}

    # ─── 查询：明细分页 ───

    def query_lines(
        self,
        period: str,
        category: Optional[str] = None,
        in_plan: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """明细分页查询，返回 {"total": int, "items": [dict, ...]}。

        - category：按 dyn_category 精确过滤（十类标签）；
        - in_plan：True/False 按 dyn_in_plan 过滤；
        - page 从 1 起；按 obligation_id 稳定排序。
        """
        page = max(int(page), 1)
        page_size = max(int(page_size), 1)
        where = ["period = ?"]
        params: list = [period]
        if category is not None:
            where.append("dyn_category = ?")
            params.append(category)
        if in_plan is not None:
            where.append("dyn_in_plan = ?")
            params.append(1 if in_plan else 0)
        where_sql = " AND ".join(where)

        total = self._conn.execute(
            f"SELECT COUNT(*) AS c FROM forecast_line WHERE {where_sql}", params
        ).fetchone()["c"]

        offset = (page - 1) * page_size
        rows = self._conn.execute(
            f"SELECT * FROM forecast_line WHERE {where_sql} "
            f"ORDER BY obligation_id LIMIT ? OFFSET ?",
            params + [page_size, offset],
        ).fetchall()
        items = [self._line_to_dict(r) for r in rows]
        return {"total": total, "items": items}

    @staticmethod
    def _line_to_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        d["dyn_in_plan"] = bool(d["dyn_in_plan"])
        return d
