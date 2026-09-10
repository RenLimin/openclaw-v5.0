"""v2 元数据库

轻量 SQLite，存：
- report_jobs: 报告生成任务（异步任务状态）
- import_logs: 数据导入记录
- report_summaries: 报告概要缓存（预览用）
"""

import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path.home() / ".openclaw" / "data" / "bdms_v2.db"


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """获取数据库连接"""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Optional[Path] = None):
    """初始化数据库表结构"""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # 报告生成任务
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS report_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            file_path TEXT,
            progress INTEGER DEFAULT 0,
            error_msg TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            completed_at TIMESTAMP
        )
    """)

    # 数据导入记录
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS import_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,
            source_path TEXT NOT NULL,
            data_type TEXT NOT NULL,
            rows_imported INTEGER DEFAULT 0,
            status TEXT NOT NULL,
            month TEXT,
            backup_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 报告概要缓存
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS report_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_job_id INTEGER,
            month TEXT NOT NULL,
            sheet_name TEXT NOT NULL,
            row_count INTEGER DEFAULT 0,
            summary_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (report_job_id) REFERENCES report_jobs(id)
        )
    """)

    # 索引
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_month ON report_jobs(month)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON report_jobs(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_imports_month ON import_logs(month)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_summaries_job ON report_summaries(report_job_id)")

    conn.commit()
    conn.close()
    return db_path or DB_PATH


# ========== report_jobs 操作 ==========

def create_job(month: str, db_path: Optional[Path] = None) -> int:
    """创建报告生成任务，返回 job_id"""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO report_jobs (month, status) VALUES (?, 'pending')",
        (month,)
    )
    conn.commit()
    job_id = cursor.lastrowid
    conn.close()
    return job_id


def update_job_status(job_id: int, status: str, progress: int = None,
                      file_path: str = None, error_msg: str = None,
                      db_path: Optional[Path] = None):
    """更新任务状态"""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    sets = ["status = ?"]
    params = [status]
    if progress is not None:
        sets.append("progress = ?")
        params.append(progress)
    if file_path is not None:
        sets.append("file_path = ?")
        params.append(file_path)
    if error_msg is not None:
        sets.append("error_msg = ?")
        params.append(error_msg)
    if status == "running":
        sets.append("started_at = CURRENT_TIMESTAMP")
    if status in ("completed", "failed"):
        sets.append("completed_at = CURRENT_TIMESTAMP")
    params.append(job_id)
    sql = f"UPDATE report_jobs SET {', '.join(sets)} WHERE id = ?"
    cursor.execute(sql, params)
    conn.commit()
    conn.close()


def get_job(job_id: int, db_path: Optional[Path] = None) -> Optional[dict]:
    """获取任务详情"""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM report_jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def list_jobs(limit: int = 20, db_path: Optional[Path] = None) -> list:
    """列出报告任务，按创建时间倒序"""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM report_jobs ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ========== import_logs 操作 ==========

def create_import_log(source_type: str, source_path: str, data_type: str,
                      status: str, rows_imported: int = 0, month: str = None,
                      backup_path: str = None,
                      db_path: Optional[Path] = None) -> int:
    """创建导入记录，返回 log_id"""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO import_logs (source_type, source_path, data_type, rows_imported, status, month, backup_path)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (source_type, source_path, data_type, rows_imported, status, month, backup_path))
    conn.commit()
    log_id = cursor.lastrowid
    conn.close()
    return log_id


def get_import_log(log_id: int, db_path: Optional[Path] = None) -> Optional[dict]:
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM import_logs WHERE id = ?", (log_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# ========== report_summaries 操作 ==========

def save_summaries(report_job_id: int, month: str, summaries: list,
                   db_path: Optional[Path] = None):
    """批量保存报告概要"""
    import json
    conn = get_connection(db_path)
    cursor = conn.cursor()
    for s in summaries:
        cursor.execute("""
            INSERT INTO report_summaries (report_job_id, month, sheet_name, row_count, summary_json)
            VALUES (?, ?, ?, ?, ?)
        """, (
            report_job_id, month,
            s.get("sheet_name", ""),
            s.get("row_count", 0),
            json.dumps(s.get("summary", {}), ensure_ascii=False)
        ))
    conn.commit()
    conn.close()


def get_summaries_by_job(report_job_id: int, db_path: Optional[Path] = None) -> list:
    """获取指定报告的所有 Sheet 概要"""
    import json
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT sheet_name, row_count, summary_json
        FROM report_summaries
        WHERE report_job_id = ?
        ORDER BY id
    """, (report_job_id,))
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "sheet_name": r["sheet_name"],
            "row_count": r["row_count"],
            "summary": json.loads(r["summary_json"]) if r["summary_json"] else {}
        }
        for r in rows
    ]


if __name__ == "__main__":
    path = init_db()
    print(f"✅ v2 元数据库初始化完成: {path}")
