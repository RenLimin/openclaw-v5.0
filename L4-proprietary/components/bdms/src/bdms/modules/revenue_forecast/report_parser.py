"""report_parser — 财报 Excel → 规范化 ObligationRow。

输入：2026年计划确收&实际确收对比表（表头第 3 行，数据第 4 行起）。
  - Sheet「预算执行表」：锁定口径（col15..26 / col27 / col32..40），10,472 有效行
  - Sheet「计划确收底稿」：动态口径（col2 / col42），38,052 行

职责：
  - 读 Excel → ObligationRow（frozen dataclass）；
  - 关联：底稿 col7 → 预算执行表 col6（现行键），兜底 col8 → col4（预算键）；
  - 恒等式校验：col27=Σcol15..26、col40=col41+col42；不符进 ParseReport.issues，不静默。

不做聚合（engine 的事）。金额单位：元。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

from .classifier import MISSING_DATE, classify_due

# ─── Sheet/列配置（DESIGN-DETAIL §1）───

SHEET_BUDGET = "预算执行表"
SHEET_DRAFT = "计划确收底稿"
HEADER_ROW = 3        # 表头第 3 行
DATA_START_ROW = 4    # 数据第 4 行起

# 预算执行表列号（0-based）
B_GROUP = 0            # 分类：新签/递延
B_CONTRACT_NO = 1
B_BUDGET_ID = 4        # 履约ID（预算），带 YS
B_OBLIGATION_ID = 6    # 履约ID（现行键）
B_METHOD = 7           # 收入确认方法
B_AMOUNT = 8           # 单项履约义务金额
B_DONE_BEFORE = 9      # 截止20251231已确收
B_FUTURE_TOTAL = 10    # 2026年及以后计划确收
B_LOCKED_START = 15    # col15..26 逐月锁定
B_LOCKED_END = 26
B_LOCKED_YEAR = 27     # 2026年预计 = Σ15..26
B_ACTUAL_START = 32    # col32..40 1-9月实际
B_ACTUAL_END = 40

# 计划确收底稿列号（0-based）
D_RAW_DUE = 2          # 交付预计完成时间（动态主依据）
D_CONTRACT_NO = 3
D_OBLIGATION_ID = 7    # 履约ID → 预算执行表 col6
D_BUDGET_ID = 8        # 对应预算履约ID → col4；无预算="2026年无预算ID"
D_CONTRACT_NAME = 10
D_CUSTOMER = 11
D_END_USER = 12
D_METHOD = 33
D_PLAN_TOTAL = 40      # 单项履约义务金额/计划履约金额
D_DONE_BEFORE = 41     # 截止20251231已确收
D_AMOUNT_FUTURE = 42   # 2026年及以后计划确收（动态金额）

NO_BUDGET_TOKEN = "2026年无预算ID"

# 恒等式容差（元）——财报为人民币分级精度
IDENTITY_TOL = 0.01


# ─── 数据结构（DESIGN-DETAIL §3 内核部分）───


@dataclass(frozen=True)
class ObligationRow:
    """单行履约义务（预算执行表 + 底稿关联后的规范化结果）。

    未关联上预算执行表的底稿行（YP 老合同）category_group=""、
    locked_* 为 0；这些行 dyn 分类必为 ALREADY_DONE，金额对口径零影响。
    """

    obligation_id: str                       # 现行键 col7/col6
    budget_id: str                           # 预算键 col8/col4
    contract_no: str
    contract_name: str
    customer: str
    end_user: str
    revenue_method: str
    category_group: str                      # 新签 | 递延 | ""（未关联）
    # 锁定口径（来自预算执行表）
    locked_year: float                       # col27
    locked_monthly: tuple[float, ...]        # col15..26，长度 12
    actual_ytd: float                        # Σ col32..40
    # 动态口径（来自底稿）
    raw_due: str                             # col2 原文
    due_date: Optional[str]                  # ISO 日期或 None
    dyn_category: str                        # classifier 十类
    amount_future: float                     # col42
    dyn_month: Optional[int]                 # DUE_2026 的月份 1..12
    dyn_in_plan: bool                        # 是否计入动态 2026
    dyn_counted: float                       # 计入金额（=col42 或 0）

    @property
    def matched_budget(self) -> bool:
        """是否关联上预算执行表。"""
        return bool(self.category_group)


@dataclass(frozen=True)
class ValidationIssue:
    """恒等式/格式校验问题（不静默，随 ParseReport 返回）。"""

    sheet: str
    row_excel: int          # Excel 实际行号（便于人工定位）
    rule: str               # E1_LOCKED_SUM / E3_DRAFT_SUM
    expected: float
    actual: float
    detail: str


@dataclass(frozen=True)
class ParseReport:
    """解析结果：规范化行 + 校验报告 + 关联统计。"""

    rows: tuple[ObligationRow, ...]
    issues: tuple[ValidationIssue, ...] = ()
    budget_rows: int = 0
    draft_rows: int = 0
    join_by_current_key: int = 0   # 底稿 col7 → col6 命中
    join_by_budget_key: int = 0    # 兜底 col8 → col4 命中
    join_miss: int = 0

    @property
    def ok(self) -> bool:
        """恒等式全部零不符。"""
        return not self.issues


# ─── 基础解析工具 ───


def to_float(value: object) -> float:
    """数值列解析：数字直取，文本/None/布尔按 0。"""
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip().replace(",", "")
        if not s:
            return 0.0
        try:
            return float(s)
        except ValueError:
            return 0.0
    return 0.0


def to_text(value: object) -> str:
    """文本列规范化：None → ""，其余 strip 转字符串。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _iso_due(value: object) -> Optional[str]:
    """col2 原文 → ISO 日期串（不可解析为 None）。"""
    from .classifier import parse_due_date

    d = parse_due_date(value)
    return d.isoformat() if d else None


def _raw_due_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime.datetime):
        return value.date().isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    return str(value).strip()


# ─── 主入口 ───


def parse_report(
    source: Union[str, Path, object],
    *,
    forecast_year: int = 2026,
) -> ParseReport:
    """解析财报 Excel → ParseReport。

    Args:
        source: xlsx 路径，或已加载的 openpyxl Workbook（便于测试注入）。
        forecast_year: 动态预估年份（透传给分类判定的计入判断）。

    仅在本函数内读文件；解析逻辑本身无其他副作用。
    """
    wb = _load_workbook(source)
    try:
        missing = [s for s in (SHEET_BUDGET, SHEET_DRAFT) if s not in wb.sheetnames]
        if missing:
            raise ValueError(f"财报缺少 Sheet: {missing}；实际: {wb.sheetnames}")

        issues: list[ValidationIssue] = []

        # 1) 预算执行表 → 索引 + E1 校验
        budget_ws = wb[SHEET_BUDGET]
        budget_by_current: dict[str, tuple] = {}
        budget_by_budget_id: dict[str, tuple] = {}
        budget_rows = 0
        for excel_row, raw in enumerate(
            budget_ws.iter_rows(min_row=DATA_START_ROW, values_only=True),
            start=DATA_START_ROW,
        ):
            if raw[B_OBLIGATION_ID] in (None, ""):
                continue  # 合计行/空行（合计行 col6 为空）
            budget_rows += 1
            key = to_text(raw[B_OBLIGATION_ID])
            budget_by_current.setdefault(key, raw)
            budget_by_budget_id.setdefault(to_text(raw[B_BUDGET_ID]), raw)

            locked_sum = sum(
                to_float(raw[i]) for i in range(B_LOCKED_START, B_LOCKED_END + 1)
            )
            locked_year = to_float(raw[B_LOCKED_YEAR])
            if abs(locked_sum - locked_year) > IDENTITY_TOL:
                issues.append(
                    ValidationIssue(
                        sheet=SHEET_BUDGET, row_excel=excel_row,
                        rule="E1_LOCKED_SUM",
                        expected=locked_year, actual=locked_sum,
                        detail="col27 应 = Σcol15..26",
                    )
                )

        # 2) 底稿 → 关联 + E3 校验 + ObligationRow
        draft_ws = wb[SHEET_DRAFT]
        rows: list[ObligationRow] = []
        draft_rows = 0
        hit_current = hit_budget = miss = 0

        from .classifier import COUNTED_CATEGORIES

        for excel_row, raw in enumerate(
            draft_ws.iter_rows(min_row=DATA_START_ROW, values_only=True),
            start=DATA_START_ROW,
        ):
            if raw[D_OBLIGATION_ID] in (None, ""):
                continue  # 空行
            draft_rows += 1

            plan_total = to_float(raw[D_PLAN_TOTAL])
            done_before = to_float(raw[D_DONE_BEFORE])
            amount_future = to_float(raw[D_AMOUNT_FUTURE])
            if abs(plan_total - done_before - amount_future) > IDENTITY_TOL:
                issues.append(
                    ValidationIssue(
                        sheet=SHEET_DRAFT, row_excel=excel_row,
                        rule="E3_DRAFT_SUM",
                        expected=plan_total,
                        actual=done_before + amount_future,
                        detail="col40 应 = col41 + col42",
                    )
                )

            # 关联：现行键优先，预算键兜底
            current_key = to_text(raw[D_OBLIGATION_ID])
            budget_key = to_text(raw[D_BUDGET_ID])
            braw = budget_by_current.get(current_key)
            if braw is not None:
                hit_current += 1
            elif budget_key and budget_key != NO_BUDGET_TOKEN:
                braw = budget_by_budget_id.get(budget_key)
                if braw is not None:
                    hit_budget += 1
            if braw is None:
                miss += 1

            raw_due = raw[D_RAW_DUE]
            dyn_category, dyn_month = classify_due(raw_due)
            in_plan = dyn_category in COUNTED_CATEGORIES and braw is not None

            if braw is not None:
                locked_monthly = tuple(
                    to_float(braw[i])
                    for i in range(B_LOCKED_START, B_LOCKED_END + 1)
                )
                actual_ytd = sum(
                    to_float(braw[i])
                    for i in range(B_ACTUAL_START, B_ACTUAL_END + 1)
                )
                category_group = to_text(braw[B_GROUP])
                locked_year = to_float(braw[B_LOCKED_YEAR])
                budget_id = to_text(braw[B_BUDGET_ID])
                revenue_method = to_text(braw[B_METHOD])
                contract_no = to_text(braw[B_CONTRACT_NO])
            else:
                locked_monthly = tuple(0.0 for _ in range(12))
                actual_ytd = 0.0
                category_group = ""
                locked_year = 0.0
                budget_id = budget_key or NO_BUDGET_TOKEN
                revenue_method = to_text(raw[D_METHOD])
                contract_no = to_text(raw[D_CONTRACT_NO])

            rows.append(
                ObligationRow(
                    obligation_id=current_key,
                    budget_id=budget_id,
                    contract_no=contract_no or to_text(raw[D_CONTRACT_NO]),
                    contract_name=to_text(raw[D_CONTRACT_NAME]),
                    customer=to_text(raw[D_CUSTOMER]),
                    end_user=to_text(raw[D_END_USER]),
                    revenue_method=revenue_method,
                    category_group=category_group,
                    locked_year=locked_year,
                    locked_monthly=locked_monthly,
                    actual_ytd=actual_ytd,
                    raw_due=_raw_due_text(raw_due),
                    due_date=_iso_due(raw_due),
                    dyn_category=dyn_category,
                    amount_future=amount_future,
                    dyn_month=dyn_month,
                    dyn_in_plan=in_plan,
                    dyn_counted=amount_future if in_plan else 0.0,
                )
            )

        return ParseReport(
            rows=tuple(rows),
            issues=tuple(issues),
            budget_rows=budget_rows,
            draft_rows=draft_rows,
            join_by_current_key=hit_current,
            join_by_budget_key=hit_budget,
            join_miss=miss,
        )
    finally:
        # 只关闭我们自己打开的 workbook；路径字符串/Path 才调 load_workbook
        if _owns_workbook(source):
            wb.close()


def _owns_workbook(source: object) -> bool:
    return isinstance(source, (str, Path))


def _load_workbook(source: Union[str, Path, object]) -> object:
    if isinstance(source, (str, Path)):
        import openpyxl

        p = Path(source)
        if not p.is_file():
            raise FileNotFoundError(f"财报文件不存在: {p}")
        return openpyxl.load_workbook(p, read_only=True, data_only=True)
    # 视为已加载的 Workbook
    if not hasattr(source, "sheetnames"):
        raise TypeError(f"source 必须是 xlsx 路径或 openpyxl Workbook，实际: {type(source)}")
    return source
