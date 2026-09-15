"""【模块3】交付管理基础数据 —— 引擎层（纯查询，无副作用）。

职责：
  1. 管理 md_reference 表（图例/参考字典）的读取与结构校验
  2. 从真实手工报表「图例」sheet 解析图例数据（纯解析，不落库）

设计要点（基于 202606 源文件实测结构）：
  源文件：2026年计划确收&实际确收对比表202601-06-0724 - 差异分析.xlsx
  「图例」sheet 实际结构：
    - 名义 506 行 × 16 列，但**有效数据只有第 1-35 行**（36 行及以后全空，Excel 残留空行）
    - 第 1 行是各图例块的标题行
    - 16 列被「组间空列」切成 8 个块：

        块 | 列区间 | 标题             | 说明列
        ---+--------+------------------+------------------------
         1 | 1-3    | 项目经理/部门/备注 | 无（3 列联合定义）
         2 | 5      | 偏差-状态/趋势    | 无
         3 | 6-7    | 偏差-原因类别     | 第 7 列 = 类别说明
         4 | 9      | 滞后验收原因      | 无
         5 | 10     | 滞后验收处置措施  | 无
         6 | 12     | 预算执行进度      | 无
         7 | 13     | 预算执行进度类别  | 无
         8 | 15-16  | 团队/产线         | 无

  重要：不使用 header_mapper.detect_header_row 直接取表头行 —— 实测该 sheet
  第 1 行的非空单元格数为 12（< HEADER_MIN_CELLS=10 的阈值虽然勉强达标，
  但表头行右侧全为空、且真数据仅 35 行），且 merged_cells 为空、存在 4 个
  无标题分隔列。因此本模块**显式按列区间解析**，再用 HeaderMapper 做
  标题名校验（标题缺失时告警而非静默跳过）。
"""

import re
from pathlib import Path
from typing import Any, Optional

from openpyxl import load_workbook

from bdms.core import db as _db
from bdms.core.header_mapper import HeaderMapper, normalize_header


# ─── 支持的数据类型 ───

DATA_TYPES: dict[str, str] = {
    "legend": "图例（偏差状态/趋势）",
    "dept": "部门",
    "product": "产品线",
    "team": "团队",
    "abnormal_type": "异常类型（预算执行进度）",
    "abnormal_category": "异常类别（预算执行进度类别）",
    "deviation_reason": "偏差原因类别",
    "deviation_reason_note": "偏差原因类别说明",
    "delay_accept_reason": "滞后验收原因",
    "delay_accept_action": "滞后验收处置措施",
    "project_manager": "项目经理",
    "project_status": "项目经理状态（离职/转岗等）",
}

DEFAULT_DATA_TYPE = "legend"
DEFAULT_SORT_STEP = 10


# ─── 图例块定义：源 sheet 列区间 → (data_type, 是否有说明列) ───
# col 为 1-based 列号，与 HeaderMapper 一致

LEGEND_BLOCKS: list[dict] = [
    {"data_type": "project_manager", "title_col": 1, "label_col": 1,
     "extra_cols": {2: "dept", 3: "status"}, "strip": False},
    {"data_type": "legend", "title_col": 5, "label_col": 5},
    {"data_type": "deviation_reason", "title_col": 6, "label_col": 6,
     "extra_cols": {7: "note"}},
    {"data_type": "delay_accept_reason", "title_col": 9, "label_col": 9},
    {"data_type": "delay_accept_action", "title_col": 10, "label_col": 10},
    {"data_type": "abnormal_type", "title_col": 12, "label_col": 12},
    {"data_type": "abnormal_category", "title_col": 13, "label_col": 13},
    {"data_type": "team", "title_col": 15, "label_col": 15},
    {"data_type": "product", "title_col": 16, "label_col": 16},
    # 部门：源 sheet 无独立「部门」图例块，但第 2 列（项目经理的部门归属）
    # 提供了权威部门清单。用 dedup_from 从该列**去重提取**，让 dept 类型
    # 真正可用（报表按部门下钻时需要）。第 3 列备注中的「项目管理部」等
    # 组织标签一并纳入。
    {"data_type": "dept", "title_col": 2, "label_col": 2, "dedup_from": True},
]

# 该 sheet 的真实数据截止行（实测 35 行有效；用非空扫描兜底，不硬编码）
LEGEND_SHEET_NAME = "图例"


def _clean(val: Any) -> Optional[str]:
    """清洗单元格值：None/空白 → None，其余转字符串去首尾空白。"""
    if val is None:
        return None
    if isinstance(val, float) and val.is_integer():
        val = int(val)
    s = str(val).strip()
    return s if s else None


def make_code(label: str) -> str:
    """由 label 生成稳定的 code（同一 label 永远得到同一 code）。

    规则：ASCII 字母数字下划线保留；中文等非 ASCII 转 unicode 码点串。
    这样 code 与 label 一一对应、幂等可复现，且不依赖排序位置。
    """
    s = str(label).strip()
    if not s:
        return ""
    if re.fullmatch(r"[A-Za-z0-9_.\-]+", s):
        return s.lower()
    # 中文/混合：unicode 码点十六进制，稳定且唯一
    return "u" + "_".join(f"{ord(ch):x}" for ch in s)


class MasterDataEngine:
    """基础数据引擎 —— 只读查询 + 纯解析。"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else None

    # ─── 查询 ───

    def list_types(self) -> list[dict]:
        """列出所有数据类型及其条目数（含中文说明）。"""
        conn = _db.get_connection(self.db_path)
        try:
            rows = conn.execute(
                """SELECT data_type,
                          COUNT(*) AS total,
                          SUM(CASE WHEN enabled = 1 THEN 1 ELSE 0 END) AS enabled_count
                   FROM md_reference GROUP BY data_type ORDER BY data_type"""
            ).fetchall()
            out = []
            for r in rows:
                dt = r["data_type"]
                out.append({
                    "data_type": dt,
                    "label": DATA_TYPES.get(dt, dt),
                    "total": r["total"],
                    "enabled_count": r["enabled_count"] or 0,
                })
            return out
        finally:
            conn.close()

    def list_items(self, data_type: str, include_disabled: bool = False,
                   keyword: Optional[str] = None) -> list[dict]:
        """列出某类型下的条目（默认只返回 enabled=1）。"""
        conn = _db.get_connection(self.db_path)
        try:
            sql = "SELECT * FROM md_reference WHERE data_type = ?"
            params: list = [data_type]
            if not include_disabled:
                sql += " AND enabled = 1"
            if keyword:
                sql += " AND (label LIKE ? OR code LIKE ?)"
                params += [f"%{keyword}%", f"%{keyword}%"]
            sql += " ORDER BY sort_order, id"
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def get_item(self, data_type: str, code: str) -> Optional[dict]:
        """按 (data_type, code) 取单条。"""
        conn = _db.get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM md_reference WHERE data_type = ? AND code = ?",
                (data_type, code),
            ).fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            conn.close()

    def get_labels(self, data_type: str) -> list[str]:
        """取某类型的 label 列表（报表计算时的字典引用）。"""
        return [it["label"] for it in self.list_items(data_type)]

    def count(self, data_type: Optional[str] = None,
              include_disabled: bool = True) -> int:
        conn = _db.get_connection(self.db_path)
        try:
            if data_type:
                sql = "SELECT COUNT(*) AS c FROM md_reference WHERE data_type = ?"
                params: tuple = (data_type,)
                if not include_disabled:
                    sql += " AND enabled = 1"
            else:
                sql = "SELECT COUNT(*) AS c FROM md_reference"
                params = ()
            return conn.execute(sql, params).fetchone()["c"]
        finally:
            conn.close()

    @staticmethod
    def _row_to_dict(row) -> dict:
        import json
        d = dict(row)
        extra = d.get("extra")
        if extra:
            try:
                d["extra"] = json.loads(extra)
            except (ValueError, TypeError):
                pass
        d["enabled"] = bool(d.get("enabled"))
        return d

    # ─── 解析源文件（纯函数，不落库）───

    def parse_legend_excel(self, excel_path: Path,
                           sheet_name: str = LEGEND_SHEET_NAME) -> dict:
        """解析手工报表「图例」sheet → {data_type: [item, ...]}。

        返回：
          {
            "sheet": "图例",
            "header_row": 1,
            "valid_rows": 35,
            "max_row": 506,
            "blocks": {data_type: [{"code","label","extra","sort_order"}...]},
            "unmatched_headers": [...],
            "warnings": [...],
          }
        不抛异常（除了文件不存在/无 sheet），问题记录在 warnings。
        """
        excel_path = Path(excel_path)
        if not excel_path.exists():
            raise FileNotFoundError(f"图例源文件不存在: {excel_path}")

        wb = load_workbook(excel_path, read_only=True, data_only=True)
        try:
            if sheet_name not in wb.sheetnames:
                raise KeyError(
                    f"源文件缺少「{sheet_name}」sheet，实际有: {wb.sheetnames}"
                )
            ws = wb[sheet_name]
            max_row = ws.max_row
            max_col = ws.max_column
            rows = list(ws.iter_rows(min_row=1, max_row=max_row, values_only=True))
        finally:
            wb.close()

        warnings: list[str] = []

        # 1) 表头行：本 sheet 固定为第 1 行（分组标题行，非宽表头）
        header_row = 1
        headers = [normalize_header(v) for v in (rows[0] if rows else [])]
        mapper = HeaderMapper(headers)

        # 2) 有效数据行：从第 2 行起到最后一个非空行
        valid_rows = 0
        for i, r in enumerate(rows[1:], start=2):
            if any(_clean(v) is not None for v in r):
                valid_rows = i
        if valid_rows == 0:
            warnings.append("图例 sheet 无有效数据行")

        data_rows = rows[1:valid_rows] if valid_rows else []

        # 3) 按块解析
        blocks: dict[str, list[dict]] = {}
        for blk in LEGEND_BLOCKS:
            dt = blk["data_type"]
            title_col = blk["title_col"]
            label_col = blk["label_col"]

            # 标题校验（用 HeaderMapper 归一化匹配，标题缺失 → 告警）
            title_name = mapper.headers[title_col - 1] if title_col <= len(mapper.headers) else ""
            if not title_name:
                warnings.append(
                    f"列{title_col} 标题为空，块 {dt} 仍按位置解析（请核对源文件结构）"
                )

            items: list[dict] = []
            seen: set[str] = set()
            order = 1
            for r in data_rows:
                label = _clean(r[label_col - 1]) if label_col - 1 < len(r) else None
                if not label:
                    continue
                code = make_code(label)
                if code in seen:
                    warnings.append(f"{dt}: 重复 label 已跳过 -> {label}")
                    continue
                seen.add(code)

                extra: dict = {}
                for col, attr in (blk.get("extra_cols") or {}).items():
                    v = _clean(r[col - 1]) if col - 1 < len(r) else None
                    if v:
                        extra[attr] = v
                # 通用：记录来源行号，便于回溯
                extra["_source_row"] = order

                items.append({
                    "code": code,
                    "label": label,
                    "extra": extra or None,
                    "sort_order": order * DEFAULT_SORT_STEP,
                })
                order += 1

            if not items:
                warnings.append(f"{dt}: 未解析到任何条目（列{label_col} 为空？）")
            elif blk.get("dedup_from"):
                warnings.append(f"{dt}: 从列{label_col} 去重提取 {len(items)} 个部门")
            blocks[dt] = items

        return {
            "sheet": sheet_name,
            "source_path": str(excel_path),
            "header_row": header_row,
            "header_names": [h for h in mapper.headers if h],
            "valid_rows": max(valid_rows - 1, 0),
            "max_row": max_row,
            "max_col": max_col,
            "blocks": blocks,
            "unmatched_headers": sorted(mapper.unmatched),
            "warnings": warnings,
        }
