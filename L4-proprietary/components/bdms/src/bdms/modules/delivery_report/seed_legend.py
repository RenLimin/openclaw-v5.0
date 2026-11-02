# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""图例基础数据结构化落盘：权威 16 列源「图例」sheet → md_reference。

源文件（权威，16 列）：
  data/source_snapshots/202606/
    2026年计划确收&实际确收对比表202601-06-0724 - 差异分析.xlsx

按 5 大类拆为 9 个 data_type（去重列表）：
  1 项目经理信息      project_manager（extra: dept/note）
  2 确收差异分析      deviation_status / deviation_reason（extra: note）
  3 验收差异分析      delay_accept_reason / delay_accept_action
  4 预算执行进度      abnormal_type / abnormal_category
  5 团队/产线         team / product
  另：dept 从项目经理的部门列去重提取。

用法: python3 -m bdms.modules.delivery_report.seed_legend [源文件.xlsx]
幂等：重复执行覆盖更新（先清空受管类型再写入）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from bdms.core import db as _db
from bdms.modules.master_data.engine import (
    DATA_TYPES,
    LEGEND_BLOCKS,
    MasterDataEngine,
)

# 权威 16 列源（202606 快照）
DEFAULT_SOURCE = Path(
    "/Users/bangcle/.openclaw/workspace/L4-proprietary/components/bdms/"
    "data/source_snapshots/202606/"
    "2026年计划确收&实际确收对比表202601-06-0724 - 差异分析.xlsx"
)

# 受管类型（= LEGEND_BLOCKS 全部 data_type）
MANAGED_TYPES = [b["data_type"] for b in LEGEND_BLOCKS]
# 历史遗留类型（仅清理 16 列侧的废弃 type）。
# 注意：不清理 legend_config —— 它是 48 列月报管线（validator 枚举 /
# calibration / exporter 往返）的内部数据，与本基础数据共存。
LEGACY_TYPES = ["legend"]


def seed_legend(source_path: Path = None, db_path: Path = None) -> dict:
    """从权威 16 列源解析图例 → 按 9 个 data_type 结构化落盘。

    返回 {"seeded": 总条目数, "types": {data_type: count}, "warnings": [...]}。
    """
    source_path = Path(source_path) if source_path else DEFAULT_SOURCE
    if not source_path.exists():
        return {"error": f"源文件不存在: {source_path}", "seeded": 0,
                "types": {}, "warnings": []}

    engine = MasterDataEngine(db_path)
    parsed = engine.parse_legend_excel(source_path)
    blocks = parsed.get("blocks", {})
    warnings = list(parsed.get("warnings", []))

    conn = _db.get_connection(db_path)
    try:
        # 清空受管类型 + 历史遗留（幂等覆盖）
        for dt in MANAGED_TYPES + LEGACY_TYPES:
            conn.execute("DELETE FROM md_reference WHERE data_type = ?", (dt,))

        type_counts: dict[str, int] = {}
        total = 0
        for dt in MANAGED_TYPES:
            items = blocks.get(dt, [])
            for it in items:
                extra = it.get("extra")
                extra_json = (json.dumps(extra, ensure_ascii=False)
                              if extra else None)
                conn.execute(
                    """INSERT INTO md_reference
                       (data_type, code, label, extra, sort_order, enabled)
                       VALUES (?, ?, ?, ?, ?, 1)
                       ON CONFLICT(data_type, code) DO UPDATE SET
                         label = excluded.label,
                         extra = excluded.extra,
                         sort_order = excluded.sort_order,
                         enabled = excluded.enabled,
                         updated_at = datetime('now', 'localtime')""",
                    (dt, it["code"], it["label"], extra_json,
                     it.get("sort_order", 0)),
                )
            type_counts[dt] = len(items)
            total += len(items)
        conn.commit()
    finally:
        conn.close()

    return {
        "seeded": total,
        "source": str(source_path),
        "valid_rows": parsed.get("valid_rows", 0),
        "types": type_counts,
        "type_labels": {dt: DATA_TYPES.get(dt, dt) for dt in MANAGED_TYPES},
        "warnings": warnings,
    }


if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    result = seed_legend(src)
    print(json.dumps(result, ensure_ascii=False, indent=2))
