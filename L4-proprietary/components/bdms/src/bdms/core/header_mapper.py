"""表头自适应列映射。

背景（2026-09-15）：
确收对比表的列结构随月份演进：
  202606: 预算执行表表头在行2-3，10 个 sheet
  202608: 预算执行表表头在行3，4 个 sheet，计划确收底稿 +7 列
硬编码列号（如 config.BudgetCol.CONTRACT_NO=2）会随数据源演进失效。

设计：
  1. 自动探测表头行（首个"非空单元格数 > 阈值"的行）
  2. 按**列名**匹配目标字段，不按列号
  3. 同名列表头（如两个"合同编号"）按出现顺序消歧（第 1 个/第 2 个）
  4. 匹配失败时记录，不静默

用法：
  mapper = HeaderMapper(header_row)
  idx = mapper.index("合同编号")        # 第 1 个匹配
  idx2 = mapper.index("合同编号", nth=2)  # 第 2 个匹配
"""

import re
from typing import Optional

# 表头探测阈值：一行里非空且非公式的单元格数
HEADER_MIN_CELLS = 10
# 表头有效性：唯一列名占比下限（分组标题行会大量重复/空）
HEADER_MIN_UNIQUE_RATIO = 0.5


def normalize_header(text) -> str:
    """归一化表头文本：去空白、全角转半角、去括号差异。"""
    if text is None:
        return ""
    s = str(text).strip()
    # 全角括号 → 半角
    s = s.replace("（", "(").replace("）", ")")
    # 去除所有空白
    s = re.sub(r"\s+", "", s)
    # 去除公式残留
    s = s.replace("=", "")
    return s


def is_formula(value) -> bool:
    return isinstance(value, str) and value.startswith("=")


def detect_header_row(ws, max_scan: int = 8) -> Optional[int]:
    """探测表头行：返回最可能的表头行号（1-based）。

    判定策略（应对分组标题行干扰）：
      1. 候选 = 非空非公式单元格数 >= HEADER_MIN_CELLS 且唯一列名占比合格的行
      2. 在候选中选**单元格数最多**的那行（真表头总是最宽的）

    示例：
      202606 预算执行表：行2=分组标题(11列), 行3=真表头(93列) → 选行3
      202608 预算执行表：行3=真表头(44列) → 选行3
    """
    candidates: list[tuple[int, int]] = []  # (行号, 单元格数)
    for ri, row in enumerate(ws.iter_rows(min_row=1, max_row=max_scan, values_only=True), 1):
        cells = [str(v).strip() for v in row
                 if v is not None and not is_formula(v) and str(v).strip()]
        if len(cells) < HEADER_MIN_CELLS:
            continue
        unique_ratio = len(set(cells)) / len(cells)
        if unique_ratio < HEADER_MIN_UNIQUE_RATIO:
            continue
        candidates.append((ri, len(cells)))

    if not candidates:
        return None
    # 选单元格数最多的（真表头最宽）；同宽时取最靠上的
    candidates.sort(key=lambda x: (-x[1], x[0]))
    return candidates[0][0]


def read_header(ws, row_idx: int) -> list[str]:
    """读取指定行的表头（归一化后的字符串列表，保持列位置）。"""
    headers = []
    for row in ws.iter_rows(min_row=row_idx, max_row=row_idx, values_only=True):
        headers = [normalize_header(v) for v in row]
        break
    return headers


class HeaderMapper:
    """列名 → 列索引(1-based) 的映射器。"""

    def __init__(self, headers: list[str]):
        self.headers = headers
        # 建立 name → [索引列表]（1-based）
        self._index: dict[str, list[int]] = {}
        for i, name in enumerate(headers, start=1):
            if not name:
                continue
            self._index.setdefault(name, []).append(i)
        self.unmatched: set[str] = set()

    def index(self, name: str, nth: int = 1, required: bool = False) -> Optional[int]:
        """查找列索引。

        nth: 同名列的第几个（1-based）
        required: True 时匹配失败抛异常
        """
        key = normalize_header(name)
        positions = self._index.get(key, [])
        if len(positions) >= nth:
            return positions[nth - 1]
        if required:
            raise KeyError(f"表头缺少列: {name} (第{nth}个)")
        self.unmatched.add(name)
        return None

    def index_any(self, *names: str, nth: int = 1) -> Optional[int]:
        """按优先级依次尝试多个候选列名。"""
        for name in names:
            idx = self.index(name, nth=nth)
            if idx is not None:
                return idx
        return None

    def index_prefix(self, prefix: str, nth: int = 1) -> Optional[int]:
        """按前缀匹配（用于列名带后缀变化的场景）。"""
        pat = normalize_header(prefix)
        matches = [i for i, name in enumerate(self.headers, start=1)
                   if name and name.startswith(pat)]
        if len(matches) >= nth:
            return matches[nth - 1]
        return None

    def find_month_columns(self, year: str = "2026") -> dict[str, int]:
        """查找月份列：{"202601": 16, ...}。

        处理"同名月份列出现两次"的情况（预算月 vs 实际月）：
        第一次出现归为 plan，第二次归为 actual。
        """
        pat = re.compile(rf"^{year}(0[1-9]|1[0-2])$")
        seen: dict[str, list[int]] = {}
        for i, name in enumerate(self.headers, start=1):
            if name and pat.match(name):
                seen.setdefault(name, []).append(i)

        out: dict[str, int] = {}
        for month, positions in seen.items():
            out[f"{month}@1"] = positions[0]
            if len(positions) > 1:
                out[f"{month}@2"] = positions[1]
        return out

    def all_matches(self, name: str) -> list[int]:
        return list(self._index.get(normalize_header(name), []))
