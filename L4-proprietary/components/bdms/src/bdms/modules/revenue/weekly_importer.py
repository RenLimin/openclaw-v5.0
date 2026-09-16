"""周报签约项目统计 —— 导入器。

数据源：ONES 导出的 `YYYYMM周报-签约项目统计.csv`（约 22MB / 55 列 / 1.4 万行）。

用途：补齐「预算执行表」中依赖周报的列，尤其是：
  - c93 所属产线（周报）  ← CSV c26「所属产线」

键：`BI履约ID`（CSV c0）↔ 手工报表「履约ID」（预算执行表 c10）。

设计要点：
  - 按**列名**定位列，不按列号（源文件列序可能变动）
  - 同一 BI履约ID 可能多行（多履约项），仅保留首次出现（与手工 VLOOKUP 语义一致）
  - 幂等：重复导入同一月份先删后插
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Optional

WEEKLY_SCHEMA = """
CREATE TABLE IF NOT EXISTS weekly_signing (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    month         TEXT NOT NULL,
    perf_id       TEXT NOT NULL,
    sales_contract_no TEXT,
    contract_name TEXT,
    prod_line     TEXT,
    project_status TEXT,
    pmo_note      TEXT,
    note          TEXT,
    owner         TEXT,
    dept          TEXT,
    raw           TEXT,
    UNIQUE(month, perf_id)
);
CREATE INDEX IF NOT EXISTS idx_ws_perf ON weekly_signing(perf_id);
CREATE INDEX IF NOT EXISTS idx_ws_month ON weekly_signing(month);
"""

# 目标字段 → CSV 列名
FIELD_TO_COL: dict[str, str] = {
    "perf_id": "BI履约ID",
    "sales_contract_no": "销售合同编号",
    "contract_name": "合同名称",
    "prod_line": "所属产线",
    "project_status": "状态",
    "pmo_note": "PMO备注",
    "note": "备注",
    "owner": "负责人",
    "dept": "事业部（区域）",
}


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(WEEKLY_SCHEMA)


def _split_perf_ids(key: str) -> list[str]:
    """拆分可能用「、」串联的履约ID单元格。

    例：'A、B、C' → ['A', 'B', 'C']；单值原样返回。
    手工报表的 VLOOKUP 能命中串联串中的任一子项，故需为每项建索引。
    """
    if not key:
        return []
    if "、" not in key:
        return [key]
    return [p.strip() for p in key.split("、") if p.strip()]


def _read_header_and_index(path: Path) -> tuple[list[str], dict[str, int]]:
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        rdr = csv.reader(f)
        header = next(rdr)
    idx = {name: i for i, name in enumerate(header)}
    missing = [c for f_, c in FIELD_TO_COL.items() if c not in idx]
    if "BI履约ID" in missing:
        raise ValueError(f"源文件缺少关键列「BI履约ID」: {path}")
    return header, idx


def import_weekly_csv(
    csv_path: str | Path,
    db_path: str | Path,
    month: str,
    *,
    verbose: bool = False,
) -> dict:
    """导入一个月份的周报 CSV。

    返回 {"month", "rows_read", "rows_written", "skipped_no_key"}。
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(csv_path)

    header, idx = _read_header_and_index(csv_path)
    cols = {f_: idx.get(c) for f_, c in FIELD_TO_COL.items()}

    conn = sqlite3.connect(db_path)
    try:
        ensure_schema(conn)
        # 幂等：先删同月数据
        conn.execute("DELETE FROM weekly_signing WHERE month=?", (month,))

        rows_read = 0
        written = 0
        skipped = 0
        seen: set[str] = set()

        with open(csv_path, encoding="utf-8-sig", errors="replace", newline="") as f:
            rdr = csv.reader(f)
            next(rdr)
            batch = []
            for row in rdr:
                rows_read += 1
                ci = cols["perf_id"]
                key = row[ci].strip() if ci is not None and ci < len(row) else ""
                if not key:
                    skipped += 1
                    continue
                if key in seen:      # 同履约ID 只保留首次（VLOOKUP 语义）
                    continue
                seen.add(key)

                def _v(field: str) -> Optional[str]:
                    j = cols.get(field)
                    if j is None or j >= len(row):
                        return None
                    v = (row[j] or "").strip()
                    return v or None

                batch.append((
                    month, key,
                    _v("sales_contract_no"), _v("contract_name"),
                    _v("prod_line"), _v("project_status"),
                    _v("pmo_note"), _v("note"), _v("owner"), _v("dept"),
                    None,
                ))
                # 同一单元格可能用「、」串联多个履约ID（如 A、B、C），
                # 手工 VLOOKUP 能命中其中任一 —— 故为每个子键各建一行
                for _sub in _split_perf_ids(key):
                    if _sub == key:
                        continue
                    batch.append((
                        month, _sub,
                        _v("sales_contract_no"), _v("contract_name"),
                        _v("prod_line"), _v("project_status"),
                        _v("pmo_note"), _v("note"), _v("owner"), _v("dept"),
                        key,   # raw 记录来源主键，便于追溯
                    ))
                if len(batch) >= 2000:
                    conn.executemany(
                        "INSERT OR REPLACE INTO weekly_signing "
                        "(month,perf_id,sales_contract_no,contract_name,prod_line,"
                        "project_status,pmo_note,note,owner,dept,raw) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?)", batch)
                    written += len(batch)
                    batch = []
            if batch:
                conn.executemany(
                    "INSERT OR REPLACE INTO weekly_signing "
                    "(month,perf_id,sales_contract_no,contract_name,prod_line,"
                    "project_status,pmo_note,note,owner,dept,raw) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)", batch)
                written += len(batch)

        conn.commit()
    finally:
        conn.close()

    result = {"month": month, "rows_read": rows_read,
              "rows_written": written, "skipped_no_key": skipped}
    if verbose:
        print(f"✅ 周报导入 {month}: 读取 {rows_read}, 写入 {written}, 跳过 {skipped}")
    return result


def load_prod_line_index(db_path: str | Path, month: str) -> dict[str, str]:
    """返回 {perf_id: prod_line}，供 exporter 的 c93 使用。"""
    conn = sqlite3.connect(db_path)
    try:
        try:
            rows = conn.execute(
                "SELECT perf_id, prod_line FROM weekly_signing "
                "WHERE month=? AND prod_line IS NOT NULL", (month,)
            ).fetchall()
        except sqlite3.OperationalError:
            return {}
    finally:
        conn.close()
    return {r[0]: r[1] for r in rows}
