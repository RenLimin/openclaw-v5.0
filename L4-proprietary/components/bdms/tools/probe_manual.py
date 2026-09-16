"""手工报表探针：以流式方式读取指定 sheet 的指定列（避免逐 cell 访问 O(n^2)）。"""
import sys, openpyxl
from collections import Counter

MAN = "/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/202606/2026交付月报-20260630.xlsx"
sheet = sys.argv[1]
cols = [int(x) for x in sys.argv[2].split(",")]
limit = int(sys.argv[3]) if len(sys.argv) > 3 else 0

wb = openpyxl.load_workbook(MAN, read_only=True, data_only=True)
ws = wb[sheet]
cnts = {c: Counter() for c in cols}
n = 0
for i, row in enumerate(ws.iter_rows(values_only=True), 1):
    n += 1
    if limit and i > limit:
        break
    for c in cols:
        v = row[c - 1] if row and c - 1 < len(row) else None
        if isinstance(v, str) and len(v) > 60:
            v = v[:60] + "…"
        cnts[c][v] += 1
print("sheet=%s rows=%d" % (sheet, n))
for c in cols:
    print(f"  c{c}: {cnts[c].most_common(12)}")
wb.close()
