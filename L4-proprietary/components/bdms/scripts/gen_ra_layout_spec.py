"""从人工 golden 提取紧凑版式规范 → src/.../assets/golden_layout_202606.json。

Rex 2026-11-24 拍板 D2：导出 Excel 尽量按格式对齐（字体 / 单元格颜色 / 行高 /
列宽 / 合并 / 冻结 / 打印）；入库仍按 DB 格式。

只存「可复用规则」，不存逐格快照：
  - col_style         数据区每列众数字体/填充/对齐（大表靠列默认压缩）
  - header_col_style  前 N 行表头段的同类统计
  - filled            实心填充单元格（含其字体，覆盖列默认）
  - row_heights / col_widths / merges / freeze / print / tab

性能：全程**单次行序遍历**（O(单元格数)），不做按列重扫（百万格表上会退化）。
用法：python3 scripts/gen_ra_layout_spec.py [golden]
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

DEFAULT_GOLDEN = (
    "/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/202606/"
    "2026年计划确收&实际确收对比表202601-06-0724 - 差异分析.xlsx"
)
OUT = Path(__file__).resolve().parents[1] / (
    "src/bdms/modules/revenue_analysis/assets/golden_layout_202606.json")
HEADER_ROWS = 3


def _rgb(c):
    if c is None:
        return None
    raw = getattr(c, "rgb", None)
    if isinstance(raw, str):
        return raw[2:] if len(raw) == 8 else raw.upper()
    theme = getattr(c, "theme", None)
    if theme is not None:
        return f"theme{theme}:{round(getattr(c, 'tint', 0) or 0, 4)}"
    idx = getattr(c, "indexed", None)
    return f"idx{idx}" if idx is not None else None


def _font(f):
    return (f.name, f.size, bool(f.bold), _rgb(f.color))


def _fill(fl):
    if fl is None or fl.fill_type != "solid":
        return None
    return _rgb(fl.start_color)


def _align(a):
    return (a.horizontal, a.vertical, bool(a.wrap_text))


def extract(path: Path) -> dict:
    wb = load_workbook(path)
    spec = {"source": str(path), "header_rows": HEADER_ROWS, "sheets": {}}
    for name in wb.sheetnames:
        t0 = time.time()
        ws = wb[name]
        # 累积器：按 (区段, 列) 计数；区段 0=表头段，1=数据段
        cf = {0: {}, 1: {}}
        ci = {0: {}, 1: {}}
        ca = {0: {}, 1: {}}
        filled = {}
        for row in ws.iter_rows():
            r = row[0].row
            seg = 0 if r <= HEADER_ROWS else 1
            for c in row:
                val, fl = c.value, c.fill
                if val is None and fl.fill_type is None:
                    continue
                key = c.column
                d = cf[seg].setdefault(key, Counter())
                d[_font(c.font)] += 1
                d2 = ci[seg].setdefault(key, Counter())
                d2[_fill(fl)] += 1
                d3 = ca[seg].setdefault(key, Counter())
                d3[_align(c.alignment)] += 1
                fv = _fill(fl)
                if fv:
                    ent = {"fill": fv}
                    fnt = _font(c.font)
                    base = None
                    b = cf[seg].get(key)
                    if b:
                        modal = b.most_common(1)[0][0]
                        base = (modal[0], modal[1], modal[2])
                    cur = (fnt[0], fnt[1], fnt[2])
                    if not base or cur != base:
                        ent["font"] = dict(zip(("n", "s", "b", "c"), fnt))
                    filled[f"{r}{get_column_letter(c.column)}"] = ent

        def pack(seg):
            out = {}
            for col in sorted(cf[seg]):
                rec = {"font": dict(zip(("n", "s", "b", "c"),
                                        cf[seg][col].most_common(1)[0][0]))}
                f = ci[seg].get(col)
                if f:
                    mf = f.most_common(1)[0][0]
                    if mf:
                        rec["fill"] = mf
                al = ca[seg].get(col)
                if al:
                    ma = al.most_common(1)[0][0]
                    if ma != (None, "center", False):
                        rec["align"] = dict(zip(("h", "v", "w"), ma))
                out[get_column_letter(col)] = rec
            return out

        heights = {str(r): ws.row_dimensions[r].height
                   for r in range(1, ws.max_row + 1)
                   if ws.row_dimensions[r].height}
        widths = {k: v.width for k, v in ws.column_dimensions.items() if v.width}
        ps, mar = ws.page_setup, ws.page_margins
        spec["sheets"][name] = {
            "col_style": pack(1),
            "header_col_style": pack(0),
            "filled": filled,
            "row_heights": heights,
            "col_widths": widths,
            "merges": sorted(str(m) for m in ws.merged_cells.ranges),
            "tab": _rgb(ws.sheet_properties.tabColor),
            "freeze": ws.freeze_panes,
            "print": {
                "orient": ps.orientation, "paper": ps.paperSize,
                "fitW": ps.fitToWidth, "fitH": ps.fitToHeight,
                "m_l": mar.left, "m_r": mar.right,
                "m_t": mar.top, "m_b": mar.bottom,
                "titles": ws.print_title_rows,
            },
        }
        print(f"{name}: col_style={len(spec['sheets'][name]['col_style'])} "
              f"hdr={len(spec['sheets'][name]['header_col_style'])} "
              f"filled={len(filled)} h={len(heights)} w={len(widths)} "
              f"({time.time()-t0:.1f}s)", file=sys.stderr)
    wb.close()
    return spec


if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(DEFAULT_GOLDEN)
    sp = extract(src)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(sp, ensure_ascii=False), encoding="utf-8")
    print(f"✅ wrote {OUT} ({OUT.stat().st_size} bytes)")
