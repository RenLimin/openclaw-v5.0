"""统一 DB 层 — SQLite 连接、schema 管理、通用 CRUD。

设计：单库多表，按模块前缀分区（dr_ = 交付月报, rr_ = 确认收入）。
所有业务表带 month 字段（YYYYMM）用于按月幂等。
"""

import sqlite3
import json
import threading
from contextlib import contextmanager
from typing import Any, Iterator, Optional

from .paths import DB_PATH, ensure_dirs


# 线程本地连接缓存（业务代码大量使用 conn.close()，缓存必须自愈）
_thread_local = threading.local()


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """获取数据库连接。

    注意：每次返回新连接，由调用方负责 close。
    业务模块大量使用 `finally: conn.close()` 模式，缓存连接会互相踩踏。
    """
    ensure_dirs()
    path = str(db_path or DB_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction(db_path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    """事务上下文：成功 commit，异常 rollback。"""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def close_connection(db_path: Optional[Path] = None) -> None:
    """关闭当前线程的缓存连接（测试用）。"""
    ensure_dirs()
    path = str(db_path or DB_PATH)
    conn = getattr(_thread_local, path, None)
    if conn is not None:
        try:
            conn.close()
        except sqlite3.ProgrammingError:
            pass
        delattr(_thread_local, path)


# ─── Schema 定义 ───

SCHEMA = """
-- ===== 元数据 =====

-- 生成任务记录
CREATE TABLE IF NOT EXISTS job (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    module TEXT NOT NULL,              -- delivery_report | revenue
    month TEXT NOT NULL,               -- YYYYMM
    mode TEXT NOT NULL DEFAULT 'auto', -- auto | read | regenerate
    status TEXT NOT NULL DEFAULT 'pending',  -- pending|running|done|failed
    progress INTEGER DEFAULT 0,
    message TEXT,
    output_path TEXT,
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_job_module_month ON job(module, month);

-- 月度数据登记：记录哪个月已落盘
CREATE TABLE IF NOT EXISTS report_month (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    module TEXT NOT NULL,
    month TEXT NOT NULL,
    source_path TEXT,
    generated_at TEXT DEFAULT (datetime('now', 'localtime')),
    row_counts TEXT,                   -- JSON: {table: count}
    UNIQUE(module, month)
);

-- ===== 基础数据（模块3）=====

-- 图例/参考数据：报表计算时引用的字典
CREATE TABLE IF NOT EXISTS md_reference (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_type TEXT NOT NULL,           -- legend | dept | product | abnormal_type ...
    code TEXT NOT NULL,
    label TEXT NOT NULL,
    extra TEXT,                        -- JSON 附加属性
    sort_order INTEGER DEFAULT 0,
    enabled INTEGER DEFAULT 1,
    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(data_type, code)
);
CREATE INDEX IF NOT EXISTS idx_md_ref_type ON md_reference(data_type);

-- ===== 系统设定（模块5）=====

CREATE TABLE IF NOT EXISTS sys_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);

-- ===== 日志 =====

CREATE TABLE IF NOT EXISTS import_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    module TEXT NOT NULL,
    month TEXT NOT NULL,
    source_type TEXT,                  -- ones_csv | xlsx | manual
    source_path TEXT,
    data_type TEXT,
    row_count INTEGER,
    status TEXT,
    message TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
"""


def init_db(db_path: Optional[Path] = None) -> None:
    """初始化 schema（幂等）。加载 v1 基础 + v2.1 全部模块 schema。"""
    from .schemas import DR_SCHEMA, RR_SCHEMA, DASHBOARD_SCHEMA
    from .schemas_v21 import (
        CR_SCHEMA, PM_SCHEMA, CT_SCHEMA, RK_SCHEMA,
        AS_SCHEMA, CH_SCHEMA, INT_SCHEMA, KB_SCHEMA,
        DASH_V2_SCHEMA, OUTBOX_SCHEMA, IMPORT_ERRORS_SCHEMA,
        DR_EXT_SCHEMA, RR_EXT_SCHEMA, PF_SCHEMA,
    )
    conn = get_connection(db_path)
    try:
        # 轻量列迁移：旧库已存在的表，ALTER TABLE 补齐新增列（幂等）
        _migrate_columns(conn)
        conn.executescript(SCHEMA)
        conn.executescript(DR_SCHEMA)
        conn.executescript(RR_SCHEMA)
        conn.executescript(DASHBOARD_SCHEMA)
        # v2.1 模块 schema
        conn.executescript(CR_SCHEMA)
        conn.executescript(PM_SCHEMA)
        conn.executescript(CT_SCHEMA)
        conn.executescript(RK_SCHEMA)
        conn.executescript(AS_SCHEMA)
        conn.executescript(CH_SCHEMA)
        conn.executescript(INT_SCHEMA)
        conn.executescript(KB_SCHEMA)
        conn.executescript(DASH_V2_SCHEMA)
        conn.executescript(OUTBOX_SCHEMA)
        conn.executescript(IMPORT_ERRORS_SCHEMA)
        conn.executescript(DR_EXT_SCHEMA)
        conn.executescript(RR_EXT_SCHEMA)
        conn.executescript(PF_SCHEMA)
        seed_defaults(conn)
        conn.commit()
    finally:
        pass  # 线程本地连接不 close，避免后续操作拿到已关闭连接


def _migrate_columns(conn: sqlite3.Connection) -> None:
    """轻量列迁移：对已存在的表补齐新增列（幂等）。

    SQLite 的 CREATE TABLE IF NOT EXISTS 不会给已存在的表加列，
    新版本 schema 新增的列需要 ALTER TABLE 补上。
    """
    migrations: list[tuple[str, str, str]] = [
        # (表名, 列名, 列定义)
        ("cr_contracts", "impl_owner", "TEXT"),
        ("cr_contracts", "impl_status", "TEXT DEFAULT 'not_started'"),
        ("pm_projects", "impl_owner", "TEXT"),
        ("pm_projects", "impl_status", "TEXT DEFAULT 'not_started'"),
        ("pm_projects", "impl_start_date", "TEXT"),
        ("pm_projects", "impl_end_date", "TEXT"),
        ("as_tickets", "description", "TEXT"),
        ("as_tickets", "state", "TEXT DEFAULT 'open'"),
        ("as_tickets", "service_level", "TEXT DEFAULT 'silver'"),
        ("as_tickets", "source", "TEXT DEFAULT 'warranty'"),
        ("as_tickets", "response_deadline", "TEXT"),
        ("as_tickets", "resolution_deadline", "TEXT"),
        ("as_tickets", "response_at", "TEXT"),
        ("as_tickets", "resolution", "TEXT"),
        ("as_tickets", "resolution_type", "TEXT"),
        ("as_tickets", "close_note", "TEXT"),
        ("as_tickets", "customer_contact", "TEXT"),
        ("as_tickets", "customer_phone", "TEXT"),
        ("as_warranty_contracts", "contract_no", "TEXT"),
        ("as_warranty_contracts", "customer_contact", "TEXT"),
        ("as_warranty_contracts", "customer_phone", "TEXT"),
        ("ct_timesheets", "created_by", "TEXT"),
        ("ct_timesheets", "updated_by", "TEXT"),
        ("ct_timesheets", "updated_at", "TEXT"),
        ("pf_timesheet", "approval_comment", "TEXT"),
        ("pf_timesheet", "created_by", "TEXT"),
    ]
    for table, column, coldef in migrations:
        try:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            if cols and column not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coldef}")
        except sqlite3.Error:
            pass  # 表不存在则跳过（executescript 会建）


# ─── 宽表行读写（月报/确收共用）───

def save_sheet_rows(conn: sqlite3.Connection, month: str, sheet: str,
                    columns: list[str], rows: list[dict],
                    prefix: str = "dr", overwrite: bool = True,
                    index_fields: dict = None) -> int:
    """保存一个 Sheet 的数据。

    prefix: "dr"(交付月报) | "rr"(确收)
    index_fields: 额外索引列 {列名: 值取值方式}，仅 rr 用
    """
    table = f"{prefix}_sheet_row"
    meta_table = f"{prefix}_sheet_meta"
    month_col = "month" if prefix == "dr" else "period"

    if overwrite:
        conn.execute(f"DELETE FROM {table} WHERE {month_col} = ? AND sheet = ?",
                     (month, sheet))

    for idx, row in enumerate(rows):
        data = json.dumps(row, ensure_ascii=False, default=str)
        if prefix == "rr":
            conn.execute(
                f"""INSERT OR REPLACE INTO {table}
                    ({month_col}, sheet, row_index, contract_no, category,
                     archive_month, perf_id, data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (month, sheet, idx,
                 str(row.get("合同编号", "") or row.get("合同编号（校准）", "") or ""),
                 str(row.get("分类", "") or ""),
                 str(row.get("合同归档月份", "") or ""),
                 str(row.get("履约ID", "") or ""),
                 data),
            )
        else:
            conn.execute(
                f"INSERT OR REPLACE INTO {table} ({month_col}, sheet, row_index, data)\n                    VALUES (?, ?, ?, ?)",
                (month, sheet, idx, data),
            )

    conn.execute(
        f"""INSERT INTO {meta_table} ({month_col}, sheet, columns, row_count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT({month_col}, sheet) DO UPDATE SET
              columns = excluded.columns, row_count = excluded.row_count""",
        (month, sheet, json.dumps(columns, ensure_ascii=False), len(rows)),
    )
    return len(rows)


def load_sheet_rows(conn: sqlite3.Connection, month: str, sheet: str,
                    prefix: str = "dr") -> tuple[list[str], list[dict]]:
    """读取 Sheet 数据。返回 (columns, rows)。"""
    meta_table = f"{prefix}_sheet_meta"
    month_col = "month" if prefix == "dr" else "period"
    meta = conn.execute(
        f"SELECT columns, row_count FROM {meta_table} WHERE {month_col}=? AND sheet=?",
        (month, sheet),
    ).fetchone()
    if not meta:
        return [], []
    columns = json.loads(meta["columns"])
    rows = []
    for r in conn.execute(
        f"SELECT data FROM {prefix}_sheet_row WHERE {month_col}=? AND sheet=? ORDER BY row_index",
        (month, sheet),
    ):
        rows.append(json.loads(r["data"]))
    return columns, rows


def list_sheets(conn: sqlite3.Connection, month: str, prefix: str = "dr") -> list[str]:
    """列出某月已落盘的所有 Sheet。"""
    meta_table = f"{prefix}_sheet_meta"
    month_col = "month" if prefix == "dr" else "period"
    rows = conn.execute(
        f"SELECT sheet FROM {meta_table} WHERE {month_col}=? ORDER BY id", (month,)
    ).fetchall()
    return [r["sheet"] for r in rows]


# ─── 通用工具 ───

def upsert_settings(conn: sqlite3.Connection, key: str, value: Any,
                    description: str = None) -> None:
    """写入系统设置。"""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False)
    conn.execute(
        """INSERT INTO sys_settings (key, value, description)
           VALUES (?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET
             value = excluded.value,
             updated_at = datetime('now', 'localtime')""",
        (key, value, description),
    )


def get_settings(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    """读取系统设置。"""
    row = conn.execute("SELECT value FROM sys_settings WHERE key = ?", (key,)).fetchone()
    if not row:
        return default
    val = row["value"]
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return val


def get_all_settings(conn: sqlite3.Connection) -> dict:
    """读取所有设置。"""
    rows = conn.execute("SELECT key, value, description FROM sys_settings").fetchall()
    out = {}
    for r in rows:
        try:
            out[r["key"]] = json.loads(r["value"])
        except (json.JSONDecodeError, TypeError):
            out[r["key"]] = r["value"]
    return out


# ─── 默认设置 ───

DEFAULT_SETTINGS = {
    "view.default_months_back": 12,
    "view.default_month": None,
    "view.available_months": [],
    "report.auto_overwrite": False,
    "report.excel_output_dir": "output",
}


def seed_defaults(conn: sqlite3.Connection) -> None:
    """写入默认设置（仅当不存在）。"""
    for key, value in DEFAULT_SETTINGS.items():
        if get_settings(conn, key, None) is None:
            upsert_settings(conn, key, value)


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def get_month_status(conn: sqlite3.Connection, module: str, month: str) -> Optional[dict]:
    """查询某模块某月是否已生成。"""
    row = conn.execute(
        "SELECT * FROM report_month WHERE module = ? AND month = ?",
        (module, month),
    ).fetchone()
    return dict(row) if row else None


def register_month(conn: sqlite3.Connection, module: str, month: str,
                   source_path: str = None, row_counts: dict = None) -> None:
    """登记某模块某月数据已落盘。"""
    conn.execute(
        """INSERT INTO report_month (module, month, source_path, row_counts, generated_at)
           VALUES (?, ?, ?, ?, datetime('now', 'localtime'))
           ON CONFLICT(module, month) DO UPDATE SET
             source_path = excluded.source_path,
             row_counts = excluded.row_counts,
             generated_at = datetime('now', 'localtime')""",
        (module, month, source_path,
         json.dumps(row_counts or {}, ensure_ascii=False)),
    )


def list_months(conn: sqlite3.Connection, module: str = None) -> list[dict]:
    """列出已登记的月份。"""
    if module:
        rows = conn.execute(
            "SELECT * FROM report_month WHERE module = ? ORDER BY month DESC", (module,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM report_month ORDER BY month DESC"
        ).fetchall()
    return [dict(r) for r in rows]


# ─── 任务（job）生命周期 ───

def create_job(conn: sqlite3.Connection, module: str, month: str,
               mode: str = "auto") -> int:
    """创建任务记录，返回 job_id。"""
    cur = conn.execute(
        """INSERT INTO job (module, month, mode, status, progress, started_at)
           VALUES (?, ?, ?, 'running', 0, datetime('now', 'localtime'))""",
        (module, month, mode),
    )
    return cur.lastrowid


def update_job_status(conn: sqlite3.Connection, job_id: int, status: str,
                      progress: int = None, message: str = None,
                      output_path: str = None) -> None:
    """更新任务状态。"""
    sets = ["status = ?"]
    params: list = [status]
    if progress is not None:
        sets.append("progress = ?")
        params.append(progress)
    if message is not None:
        sets.append("message = ?")
        params.append(message)
    if output_path is not None:
        sets.append("output_path = ?")
        params.append(output_path)
    if status in ("done", "failed"):
        sets.append("finished_at = datetime('now', 'localtime')")
    params.append(job_id)
    conn.execute(f"UPDATE job SET {', '.join(sets)} WHERE id = ?", params)


def get_job(conn: sqlite3.Connection, job_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM job WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def list_jobs(conn: sqlite3.Connection, module: str = None,
              limit: int = 20) -> list[dict]:
    if module:
        rows = conn.execute(
            "SELECT * FROM job WHERE module = ? ORDER BY id DESC LIMIT ?",
            (module, limit),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM job ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]
