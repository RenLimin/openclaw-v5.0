# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""图例配置预落盘：从黄金基准 Sheet-15 提取 → md_reference。

对齐 DESIGN-DETAIL-DELIVERY-REPORT-v2.1.md §Step 1d：
「图例配置：从黄金基准 Sheet-15 提取后预落盘到 md_reference
（data_type='legend_config'），48 列 × ~502 行」

用法: python3 -m bdms.modules.delivery_report.seed_legend [黄金基准.xlsx]
幂等：重复执行覆盖更新。
导出保证：列名与黄金基准完全一致，48 列 × 506 行。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import openpyxl

from bdms.core import db as _db

# 默认黄金基准（202606）
DEFAULT_GOLDEN = Path(
    "/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/"
    "202606/2026交付月报-20260630.xlsx"
)


def seed_legend(golden_path: Path = None, db_path: Path = None) -> dict:
    """从黄金基准提取图例配置 → md_reference（data_type='legend_config'）。

    保留全部行（506 行）和全部列（48 列），第 1 行作为表头。
    列名存在 extra JSON 中，key 为实际列名（如 "项目经理"/"部门"），
    不再用 c1/c2/c3 这种通用名。

    第 1 行表头作为「表头行」也存入 md_reference（code='__header__'），
    方便导出时还原列顺序。
    """
    golden_path = golden_path or DEFAULT_GOLDEN
    if not golden_path.exists():
        return {"error": f"黄金基准不存在: {golden_path}", "seeded": 0}

    wb = openpyxl.load_workbook(golden_path, read_only=True, data_only=True)
    if "图例" not in wb.sheetnames:
        wb.close()
        return {"error": "黄金基准无图例 Sheet", "seeded": 0}

    ws = wb["图例"]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if not rows:
        return {"error": "图例 Sheet 为空", "seeded": 0}

    # 第 1 行是表头（处理重名列，加序号后缀）
    raw_headers = [str(v).strip() if v is not None else f"col_{i}"
                   for i, v in enumerate(rows[0])]
    headers = []
    seen = {}
    for h in raw_headers:
        if h in seen:
            seen[h] += 1
            headers.append(f"{h}_{seen[h]}")
        else:
            seen[h] = 0
            headers.append(h)

    conn = _db.get_connection(db_path)
    seeded = 0
    try:
        # 先清空旧数据（幂等）
        conn.execute("DELETE FROM md_reference WHERE data_type = 'legend_config'")

        # 存表头行（特殊 code，用于导出时还原列顺序）
        header_dict = {headers[i]: headers[i] for i in range(len(headers))}
        conn.execute(
            """INSERT INTO md_reference
               (data_type, code, label, extra, sort_order, enabled)
               VALUES ('legend_config', '__header__', '表头行', ?, 0, 0)""",
            (json.dumps(header_dict, ensure_ascii=False),),
        )

        # 存数据行（第 2 行起）
        for r_idx in range(1, len(rows)):
            row = rows[r_idx]
            values = [str(v).strip() if v is not None else "" for v in row]

            # 构造 extra：用实际列名作为 key
            extra = {}
            for i, val in enumerate(values):
                if i < len(headers):
                    col_name = headers[i]
                else:
                    col_name = f"col_{i}"
                # 空值也保留吗？设计要求 48 列，每行 48 列，所以全保留
                extra[col_name] = val

            # code 用第 1 列（项目经理名），如果空就用行号
            code = values[0] if values[0] else f"row_{r_idx}"
            label = values[0] if values[0] else f"第{r_idx}行"

            conn.execute(
                """INSERT INTO md_reference
                   (data_type, code, label, extra, sort_order, enabled)
                   VALUES ('legend_config', ?, ?, ?, ?, 1)
                   ON CONFLICT(data_type, code) DO UPDATE SET
                     label = excluded.label,
                     extra = excluded.extra,
                     sort_order = excluded.sort_order,
                     enabled = excluded.enabled,
                     updated_at = datetime('now', 'localtime')""",
                (code, label,
                 json.dumps(extra, ensure_ascii=False),
                 r_idx),
            )
            seeded += 1
        conn.commit()
    finally:
        conn.close()

    return {
        "seeded": seeded,
        "total_columns": len(headers),
        "source": str(golden_path),
        "headers": headers,
    }


if __name__ == "__main__":
    golden = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    result = seed_legend(golden)
    # 只打印摘要，不打印全部表头
    result["headers_count"] = len(result.get("headers", []))
    result.pop("headers", None)
    print(json.dumps(result, ensure_ascii=False, indent=2))
