# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""图例基础数据结构化落盘：202606 交付月报「图例」sheet（48 列）→ md_reference。

权威源（48 列交付月报）：
  /Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/
  202606/2026交付月报-20260630.xlsx

按 5 大类拆为 11 个 data_type（除考核矩阵外均去重枚举）：
  1 项目经理信息    project_manager（extra: dept/center/person_status，
                    31 真人 + 未立项/已结项 = 33 条，去掉 * 汇总行）
  2 交付考核信息    assessment_rule（20 行规则矩阵，positional）
  3 履约义务状态    obligation_status（extra: category）/ item_stat_status /
                    project_stat_status / fin_delivery_status / fin_accept_status
  4 营销团队信息    sales_team（extra: stat）
  5 财务交接差异    delivery_cross_month_reason / delivery_fail_reason /
                    accept_fail_reason

2026-11-02 清理决策（Rex 审核 7 点通过）：
  - 删除空表头列 → 导出 21 列紧凑布局（LEGEND_21_HEADERS）
  - project_manager 跳过 `*` 透视表汇总行，备注列拆为 person_status 人员状态

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

# 权威 48 列交付月报（202606）
DEFAULT_SOURCE = Path(
    "/Users/bangcle/Bangcle Workspace/01. Management/2026/"
    "2026团队报告/202606/2026交付月报-20260630.xlsx"
)

# 受管类型（= LEGEND_BLOCKS 全部 data_type）
MANAGED_TYPES = [b["data_type"] for b in LEGEND_BLOCKS]
# 历史/上一轮遗留类型，落盘时一并清理：
#   16 列轮：legend, deviation_status, deviation_reason, delay_accept_*,
#            abnormal_*, team, product, dept
#   48 列首轮（独立枚举拆法）：assessment_item, deviation_category,
#            cross_month, gt15_days, weight_factor, assessment_note,
#            obligation_status_category, sales_team_stat
LEGACY_TYPES = [
    "legend",
    "deviation_status", "deviation_reason",
    "delay_accept_reason", "delay_accept_action",
    "abnormal_type", "abnormal_category", "team", "product", "dept",
    "assessment_item", "deviation_category", "cross_month", "gt15_days",
    "weight_factor", "assessment_note", "obligation_status_category",
    "sales_team_stat",
]


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
