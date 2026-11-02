"""【模块3】交付管理基础数据 —— 引擎层（纯查询，无副作用）。

职责：
  1. 管理 md_reference 表（图例/参考字典）的读取与结构校验
  2. 从真实手工报表「图例」sheet 解析图例数据（纯解析，不落库）

设计要点（基于 202606 交付月报实测结构）：
  源文件：2026交付月报-20260630.xlsx（48 列交付月报，权威图例源）
  「图例」sheet 实际结构：
    - 名义 506 行 × 48 列，但**有效数据只有第 1-35 行**（36 行及以后全空，
      Excel 残留空行），第 1 行是各图例块的标题行
    - 48 列被「组间空列」切成 5 大类 11 个数据块：

        类 | 块                       | 列(1-based) | 数据行数
        ---+--------------------------+------------+--------
         1 | 项目经理/部门/中心/备注    | 1-4        | 34（逐行）
         2 | 考核规则矩阵（20 行组合）  | 6-11       | 20（positional）
         3 | 状态/状态类别             | 13-14      | 8（状态带类别）
         3 | 履约项统计状态            | 21         | 9
         3 | 项目统计状态              | 22         | 5
         3 | 财报-交付/确收状态        | 23         | 4
         3 | 财报-验收状态             | 24         | 3
         4 | 责任销售所属团队/统计     | 27-28      | 18（团队带统计）
         5 | 确收交接跨月/不合格/验收   | 30-32      | 各 3

  重要：不使用 header_mapper.detect_header_row 直接取表头行 —— 本 sheet
  表头行右侧全为空、真数据仅 35 行，因此**显式按列区间解析**，再用
  HeaderMapper 做标题名校验（标题缺失时告警而非静默跳过）。
  考核规则块（kind=positional）逐行保留（不去重），考核项为合并单元格
  向下填充；其余块去重为枚举。
"""

import re
from pathlib import Path
from typing import Any, Optional

from openpyxl import load_workbook

from bdms.core import db as _db
from bdms.core.header_mapper import HeaderMapper, normalize_header


# ─── 支持的数据类型 ───

# ─── 数据类型：权威源 = 202606 交付月报「图例」sheet（48 列）───
# 共 11 个 data_type，全部是「从 R2 起顶部对齐」的逐行块：
#   - 简单枚举：每行一个 label
#   - 带子字段：label + extra（如状态带类别、销售带统计组）
#   - 考核规则矩阵：20 行规则组合（kind=positional，不去重）
DATA_TYPES: dict[str, str] = {
    # 1. 项目经理信息
    "project_manager": "项目经理",
    # 2. 交付考核信息（20 行规则矩阵）
    "assessment_rule": "考核项",
    # 3. 履约义务状态
    "obligation_status": "状态",
    "item_stat_status": "履约项统计状态",
    "project_stat_status": "项目统计状态",
    "fin_delivery_status": "财报-交付/确收状态",
    "fin_accept_status": "财报-验收状态",
    # 4. 营销团队信息
    "sales_team": "责任销售所属团队",
    # 5. 财务交接差异
    "delivery_cross_month_reason": "确收交接跨月原因",
    "delivery_fail_reason": "确收交接不合格原因",
    "accept_fail_reason": "验收交接不合格原因",
}

DEFAULT_DATA_TYPE = "project_manager"
DEFAULT_SORT_STEP = 10


# ─── 图例块定义：源 sheet 列区间 → (data_type, 是否有说明列) ───
# col 为 1-based 列号，与 HeaderMapper 一致

# 映射对象：权威源 = 202606 交付月报「图例」sheet（48 列）。
# col 为 1-based 列号，与 HeaderMapper 一致。
#
#   1-based 列 → 表头（R1）
#     1 项目经理 / 2 部门 / 3 中心 / 4 备注
#     6 考核项 / 7 偏差类别 / 8 是否跨月 / 9 偏差是否大于15个自然日
#     10 加权系数 / 11 备注
#     13 状态 / 14 状态类别
#     21 履约项统计状态 / 22 项目统计状态
#     23 财报-交付/确收状态 / 24 财报-验收状态
#     27 责任销售所属团队 / 28 销售团队-统计
#     30 确收交接跨月原因 / 31 确收交接不合格原因 / 32 验收交接不合格原因
#   列 5/12/25/29/33+ 为组间空列；组3的 15-20、25 列为日期/工作安排，图例无枚举值。
LEGEND_BLOCKS: list[dict] = [
    # 1. 项目经理信息（34 行，逐行带 dept/center/note）
    {"data_type": "project_manager", "title_col": 1, "label_col": 1,
     "extra_cols": {2: "dept", 3: "center", 4: "person_status"},
     "skip_labels": ["*"], "skip_note": "透视表「全部」汇总行，不入基础数据",
     "strip": False,
     # 逆向装配：extra 字段 → 0-based 列（0 项目经理/1 部门/2 中心/3 人员状态）
     "grid_label_col": 0,
     "grid_extra": {1: "dept", 2: "center", 3: "person_status"}},
    # 2. 交付考核信息：20 行规则矩阵（R2-R21；考核项为合并单元格）。
    #    kind=positional → 每行一条规则、不去重；label 由考核项+偏差类别
    #    组合，extra 存跨月/>15/系数/备注。
    {"data_type": "assessment_rule", "kind": "positional",
     "title_col": 6, "label_col": 6,
     "label_extra_col": 7,
     "extra_cols": {8: "cross_month", 9: "gt15_days", 10: "weight_factor",
                    11: "note"},
     # 逆向装配：extra 字段 → 0-based 列（item 仅在合并锚点输出）
     "grid_map": {4: "item", 5: "category", 6: "cross_month",
                  7: "gt15_days", 8: "weight_factor", 9: "note"}},
    # 3. 履约义务状态
    {"data_type": "obligation_status", "title_col": 13, "label_col": 13,
     "extra_cols": {14: "category"},
     "grid_label_col": 10,
     "grid_extra": {11: "category"}},
    {"data_type": "item_stat_status", "title_col": 21, "label_col": 21,
     "grid_label_col": 12},
    {"data_type": "project_stat_status", "title_col": 22, "label_col": 22,
     "grid_label_col": 13},
    {"data_type": "fin_delivery_status", "title_col": 23, "label_col": 23,
     "grid_label_col": 14},
    {"data_type": "fin_accept_status", "title_col": 24, "label_col": 24,
     "grid_label_col": 15},
    # 4. 营销团队信息（18 团队，逐行带统计组）
    {"data_type": "sales_team", "title_col": 27, "label_col": 27,
     "extra_cols": {28: "stat"},
     "grid_label_col": 16,
     "grid_extra": {17: "stat"}},
    # 5. 财务交接差异
    {"data_type": "delivery_cross_month_reason", "title_col": 30, "label_col": 30,
     "grid_label_col": 18},
    {"data_type": "delivery_fail_reason", "title_col": 31, "label_col": 31,
     "grid_label_col": 19},
    {"data_type": "accept_fail_reason", "title_col": 32, "label_col": 32,
     "grid_label_col": 20},
]

# 清理后导出布局：21 列紧凑图例（2026-11-02 Rex 审核通过）。
# 删除空表头列（原 5/12/15-20/25/26/29/33-48），只保留 5 组真实数据列；
# 供 get_legend_config() 逆向装配时锁定列位置。
LEGEND_21_HEADERS: tuple[str, ...] = (
    "项目经理", "部门", "中心", "人员状态",
    "考核项", "偏差类别", "是否跨月", "偏差是否大于15自然日", "加权系数", "备注",
    "状态", "状态类别",
    "履约项统计状态", "项目统计状态", "财报-交付/确收状态", "财报-验收状态",
    "责任销售所属团队", "销售团队-统计",
    "确收交接跨月原因", "确收交接不合格原因", "验收交接不合格原因",
)

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
    """由 label 生成稳定可读的 code（同一 label 永远得到同一 code）。

    规则：
      - 纯 ASCII 字母/数字/._-  → 小写原样
      - 含中文等非 ASCII     → 保留中文/字母数字，其余转下划线

    例：'正常确收' → '正常确收'；'差异确收（当年可消除）' → '差异确收_当年可消除'

    这样 code 与 label 一一对应、幂等可复现，且在 Web/CLI 上直接可读。
    """
    s = str(label).strip()
    if not s:
        return ""
    if re.fullmatch(r"[A-Za-z0-9_.\-]+", s):
        return s.lower()
    # 中文/混合：保留中文与字母数字，其余（括号/空格/标点）归一为下划线
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "_", s, flags=re.UNICODE)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "u"


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

            if blk.get("kind") == "positional":
                blocks[dt] = self._parse_positional_block(
                    blk, data_rows, warnings)
                continue

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
            skip_labels = set(blk.get("skip_labels") or [])
            for r in data_rows:
                label = _clean(r[label_col - 1]) if label_col - 1 < len(r) else None
                if not label:
                    continue
                if label in skip_labels:
                    warnings.append(
                        f"{dt}: 跳过汇总行 {label!r}"
                        + (f"（{blk['skip_note']}）" if blk.get("skip_note") else "")
                    )
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

    def _parse_positional_block(
        self, blk: dict, data_rows: list, warnings: list[str]
    ) -> list[dict]:
        """解析「逐行规则矩阵」块（如交付考核 20 行规则）。

        与普通枚举块的区别：
          - 不去重：每行是一条规则组合（label 列可为合并单元格，向下填充）
          - label = 主键列（label_col）+ 副标签列（label_extra_col）
          - 其余列进 extra；空 label 行（纯空）跳过
        """
        dt = blk["data_type"]
        label_col = blk["label_col"]
        label_extra_col = blk.get("label_extra_col")

        def cell(r, col1: int):
            idx = col1 - 1
            return _clean(r[idx]) if 0 <= idx < len(r) else None

        items: list[dict] = []
        anchor = ""          # 合并单元格向下填充值
        order = 1
        for r in data_rows:
            primary = cell(r, label_col)
            if primary:
                anchor = primary
            secondary = cell(r, label_extra_col) if label_extra_col else None
            # 规则行判定：有副标签列时，每行必须带副标签（避免合并错向下
            # 填充到块外产生幽灵行）；无副标签列时，要求本行主键存在。
            row_has = secondary if label_extra_col else primary
            if not row_has:
                continue
            label = f"{anchor}-{secondary}" if (anchor and secondary) else (anchor or secondary)

            extra: dict[str, str] = {}
            # 合并单元格语义：item 只在锚点行（本行主键非空）写入，
            # 保证逆向装配时与原文件合并单元格行为逐字节一致。
            if primary:
                extra["item"] = anchor
            if secondary:
                extra["category"] = secondary
            for col, attr in (blk.get("extra_cols") or {}).items():
                v = cell(r, col)
                if v:
                    extra[attr] = v
            extra["_source_row"] = order

            items.append({
                "code": f"r{order:02d}",
                "label": label,
                "extra": extra or None,
                "sort_order": order * DEFAULT_SORT_STEP,
            })
            order += 1

        if not items:
            warnings.append(f"{dt}: 未解析到任何规则行（列{label_col} 为空？）")
        return items
