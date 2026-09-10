#!/usr/bin/env python3
"""
BDMS 交付月报 V2 — 报表生成器 v2 初稿

整合 7 大引擎输出，生成结构化报表数据（Excel 格式）。

7 大引擎：
  1. status_engine     — 履约项状态判定（9 种）
  2. mapping_engine    — 项目经理/部门/中心映射
  3. scoring_engine    — 考核计算（交付计划准确率 / 按时交付率）
  4. exception_engine  — 异常项目处理
  5. handover_engine   — 确收/验收交接明细
  6. contract_engine   — 合同信息关联（本文件新增调用）
  7. hours_engine      — POC 工时统计（本文件新增调用）

输出：15 个 Sheet 的 Excel 文件，结构见 spec-report-structure.md

设计原则（v2 演进）：
  - 引擎解耦：每个引擎独立输入输出，生成器只做组装
  - 数据优先：先生成所有 DataFrame，再统一写 Excel
  - 可测试：核心计算逻辑全在引擎里，生成器只做编排
"""

import sys
from pathlib import Path
from datetime import datetime
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.utils import get_column_letter

# 引擎路径
ENGINES_DIR = Path(__file__).parent.parent / "engines"
UTILS_DIR = Path(__file__).parent.parent / "utils"
CONFIG_DIR = Path(__file__).parent.parent / "config"
sys.path.insert(0, str(ENGINES_DIR))
sys.path.insert(0, str(UTILS_DIR))
sys.path.insert(0, str(CONFIG_DIR))

# 7 大引擎
from status_engine import add_status_columns
from scoring_engine import add_scoring_columns
from mapping_engine import (
    add_mapping_columns,
    add_simple_computed_columns,
    add_exception_lookup_columns,
)
from exception_engine import build_exception_df
from handover_engine import build_revenue_handover_df, build_acceptance_handover_df
from contract_engine import add_contract_columns, load_oa_contracts
from hours_engine import add_poc_hours_column, aggregate_by_contract

# 精确格式配置
try:
    from sheet_formats import SHEET_FORMAT_MAP
except ImportError:
    SHEET_FORMAT_MAP = {}


# ============================================================
# 样式常量（精确匹配手工报表）
# ============================================================

HEADER_FONT = Font(name="微软雅黑", bold=True, size=10, color="FFFFFF")
HEADER_FILL = PatternFill(start_color="FF2D73BA", end_color="FF2D73BA", fill_type="solid")
DATA_FONT = Font(name="微软雅黑", size=10, color="FF000000")
THIN_BORDER = Border(
    left=Side(style='thin', color="FF000000"),
    right=Side(style='thin', color="FF000000"),
    top=Side(style='thin', color="FF000000"),
    bottom=Side(style='thin', color="FF000000"),
)
HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)
DATA_ALIGN = Alignment(horizontal="left", vertical="center")


# ============================================================
# Sheet 顺序（15 个，与 spec-report-structure.md 完全一致）
# ============================================================

SHEET_ORDER = [
    "交付效率统计",
    "签约统计",
    "产品-授权&维保统计",
    "签约",
    "POC&提前实施统计",
    "提前实施分事业部统计",
    "POC&提前实施",
    "异常统计",
    "异常台账",
    "交付异常分事业部统计",
    "异常项目",
    "交接统计",
    "确收交接",
    "验收交接",
    "图例",
]


# ============================================================
# 输入配置
# ============================================================

class ReportConfig:
    """报表生成配置"""

    def __init__(
        self,
        report_month: str = "202606",
        ones_dir: Path = None,
        handover_base_dir: Path = None,
        oa_contract_path: Path = None,
        workhour_path: Path = None,
        output_dir: Path = None,
        legend_path: Path = None,
    ):
        self.report_month = report_month
        # 报告截止日期：当月最后一天
        year = int(report_month[:4])
        month = int(report_month[4:])
        if month == 12:
            self.report_date = f"{year}-12-31"
        else:
            next_month = datetime(year, month + 1, 1)
            last_day = (pd.Timestamp(next_month) - pd.Timedelta(days=1)).day
            self.report_date = f"{year}-{month:02d}-{last_day:02d}"

        self.ones_dir = ones_dir or Path.home() / ".openclaw" / "data" / "ones_exports"
        self.handover_base_dir = handover_base_dir or Path(
            "/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告"
        )
        self.oa_contract_path = oa_contract_path
        self.workhour_path = workhour_path
        self.output_dir = output_dir or Path.home() / ".openclaw" / "data" / "reports"
        self.legend_path = legend_path or (
            Path(__file__).parent.parent / "v1" / "config" / "legend_pm_dept.json"
        )


# ============================================================
# 数据加载层
# ============================================================

class DataLoader:
    """统一数据加载入口"""

    def __init__(self, config: ReportConfig):
        self.config = config

    def load_sign_contracts(self) -> pd.DataFrame:
        """加载 ONES 签约项目统计 CSV"""
        csv_path = self.config.ones_dir / f"{self.config.report_month}周报-签约项目统计.csv"
        if not csv_path.exists():
            csv_path = self.config.ones_dir / "签约项目统计.csv"
        df = pd.read_csv(csv_path, dtype=str, encoding="utf-8")
        df = self._normalize_ones_columns(df)
        print(f"📊 签约项目统计: {len(df)} 行 × {len(df.columns)} 列")
        return df

    def load_poc(self) -> pd.DataFrame:
        """加载 ONES POC&提前实施统计 CSV"""
        csv_path = self.config.ones_dir / f"{self.config.report_month}周报-POC&提前实施统计.csv"
        if not csv_path.exists():
            csv_path = self.config.ones_dir / "poc_提前实施.csv"
        df = pd.read_csv(csv_path, dtype=str, encoding="utf-8")
        df = self._normalize_ones_columns(df)
        print(f"📊 POC&提前实施: {len(df)} 行 × {len(df.columns)} 列")
        return df

    def load_exceptions(self) -> pd.DataFrame:
        """加载 ONES 异常项目处置 CSV"""
        csv_path = self.config.ones_dir / f"{self.config.report_month}-签约项目异常处置.csv"
        if not csv_path.exists():
            csv_path = self.config.ones_dir / "异常处置.csv"
        df = pd.read_csv(csv_path, dtype=str, encoding="utf-8")
        df = self._normalize_ones_columns(df)
        print(f"📊 异常项目处置: {len(df)} 行 × {len(df.columns)} 列")
        return df

    def load_revenue_handover(self) -> pd.DataFrame:
        """加载企微确收交接 CSV"""
        csv_path = (
            self.config.handover_base_dir
            / self.config.report_month
            / f"{self.config.report_month}确收凭证交接-确收.csv"
        )
        df = pd.read_csv(csv_path, dtype=str, encoding="utf-8")
        df = df.dropna(axis=1, how="all")  # 去全空列
        print(f"📊 确收交接: {len(df)} 行 × {len(df.columns)} 列")
        return df

    def load_acceptance_handover(self) -> pd.DataFrame:
        """加载企微验收交接 CSV"""
        csv_path = (
            self.config.handover_base_dir
            / self.config.report_month
            / f"{self.config.report_month}确收凭证交接-验收.csv"
        )
        df = pd.read_csv(csv_path, dtype=str, encoding="utf-8")
        # 列名修正
        if "深圳分公司-营销" in df.columns:
            df.rename(columns={"深圳分公司-营销": "销售部门"}, inplace=True)
        print(f"📊 验收交接: {len(df)} 行 × {len(df.columns)} 列")
        return df

    def load_oa_contracts(self) -> pd.DataFrame:
        """加载 OA 合同台账（contract_engine）"""
        df = load_oa_contracts(self.config.oa_contract_path)
        print(f"📊 OA 合同台账: {len(df)} 行")
        return df

    def load_workhours(self) -> pd.DataFrame:
        """加载工时填报明细（hours_engine）"""
        from hours_engine import load_workhour_detail
        df = load_workhour_detail(self.config.workhour_path)
        print(f"📊 工时填报明细: {len(df)} 行")
        return df

    def _normalize_ones_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """ONES 导出列名统一修正"""
        col_rename = {
            "履约项异常/变更备注": "履约项异常/变更类型",
            "合同开始日期": "合同起始日期",
        }
        return df.rename(columns={k: v for k, v in col_rename.items() if k in df.columns})


# ============================================================
# 引擎编排层
# ============================================================

class ReportEngineOrchestrator:
    """7 大引擎编排器

    输入原始数据，输出各明细 Sheet 的完整 DataFrame。
    """

    def __init__(self, config: ReportConfig):
        self.config = config
        self.report_date = config.report_date

    # ---- 签约明细（83 列 + 合同信息列） ----
    def build_sign_detail(self, df_sign_raw: pd.DataFrame, df_exc: pd.DataFrame,
                          df_oa_contracts: pd.DataFrame = None) -> pd.DataFrame:
        """构建签约明细 Sheet"""
        df = df_sign_raw.copy()

        # 1. 简单计算列（列 41-44）
        df = add_simple_computed_columns(df)

        # 2. 状态引擎（列 45-67）
        df = add_status_columns(df, self.report_date)

        # 3. 考核引擎（列 68-76）
        df = add_scoring_columns(df)

        # 4. 映射引擎（列 77-79）
        df = add_mapping_columns(df)

        # 5. 异常关联（列 80-83）
        df = add_exception_lookup_columns(df, df_exc)

        # 6. 合同引擎：补充 OA 合同信息
        if df_oa_contracts is not None and not df_oa_contracts.empty:
            df = add_contract_columns(df, df_contracts=df_oa_contracts)

        return df

    # ---- POC&提前实施明细（84 列 + 工时 + 合同） ----
    def build_poc_detail(self, df_poc_raw: pd.DataFrame, df_exc: pd.DataFrame,
                         df_hours_by_contract: pd.DataFrame = None,
                         df_oa_contracts: pd.DataFrame = None) -> pd.DataFrame:
        """构建 POC&提前实施明细 Sheet"""
        df = df_poc_raw.copy()

        # 1. 简单计算列
        df = add_simple_computed_columns(df)

        # 2. POC 专用计算列（持续周期等）
        df = self._add_poc_specific_columns(df)

        # 3. 状态引擎
        df = add_status_columns(df, self.report_date)

        # 4. 考核引擎
        df = add_scoring_columns(df)

        # 5. 映射引擎
        df = add_mapping_columns(df)

        # 6. 工时引擎：POC 项目工时合计
        if df_hours_by_contract is not None and not df_hours_by_contract.empty:
            df = add_poc_hours_column(df, df_hours_by_contract)
        else:
            df["POC项目工时合计（小时）"] = 0.0

        # 7. 合同引擎：补充 OA 合同信息
        if df_oa_contracts is not None and not df_oa_contracts.empty:
            df = add_contract_columns(df, df_contracts=df_oa_contracts)

        return df

    # ---- 异常项目明细 ----
    def build_exception_detail(self, df_exc_raw: pd.DataFrame,
                               df_sign: pd.DataFrame) -> pd.DataFrame:
        """构建异常项目明细 Sheet（复用 exception_engine）"""
        return build_exception_df(df_exc_raw, df_sign)

    # ---- 确收交接明细 ----
    def build_revenue_handover(self, df_raw: pd.DataFrame) -> pd.DataFrame:
        """构建确收交接明细 Sheet（复用 handover_engine）"""
        return build_revenue_handover_df(df_raw, self.config.report_month)

    # ---- 验收交接明细 ----
    def build_acceptance_handover(self, df_raw: pd.DataFrame) -> pd.DataFrame:
        """构建验收交接明细 Sheet（复用 handover_engine）"""
        return build_acceptance_handover_df(df_raw, self.config.report_month)

    # ---- 内部辅助 ----
    def _add_poc_specific_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """POC 专用计算列（持续周期、关联合同标记等）"""
        def _calc_duration(l_date, r_date):
            l_dt = pd.to_datetime(l_date.astype(str).str[:10], errors="coerce")
            r_dt = pd.to_datetime(r_date.astype(str).str[:10], errors="coerce")
            return (r_dt - l_dt).dt.days

        df["提前实施项目持续周期（天）"] = _calc_duration(df["立项日期"], df["实际结项日期"])

        def _duration_bucket(days):
            if pd.isna(days):
                return ""
            if days <= 30:
                return "1个月内"
            elif days <= 90:
                return "3个月内"
            elif days <= 180:
                return "6个月内"
            else:
                return "超过1年"

        df["提前实施项目持续周期-统计"] = df["提前实施项目持续周期（天）"].apply(_duration_bucket)
        df["提前实施项目是否已关联合同"] = df["销售合同编号"].notna().map({True: "是", False: "否"})
        df["关联合同归档日期"] = ""  # 预留：从 OA 合同关联
        df["统计所属项目"] = df["项目编号"] if "项目编号" in df.columns else df["所属项目"]

        return df


# ============================================================
# 统计 Sheet 生成（Pivot 层）
# ============================================================

class StatsSheetBuilder:
    """统计类 Sheet 生成器（从明细 DataFrame 做 pivot）

    对应 spec-report-structure.md §三 的 9 个统计 Sheet。
    """

    def __init__(self):
        pass

    # ---- 签约统计 ----
    def build_sign_stats(self, df_sign: pd.DataFrame) -> dict:
        """签约统计（左侧 Pivot + 右侧 Pivot）"""
        results = {}

        # 左侧：合同归档年度 × 计数
        if "合同归档年度" in df_sign.columns:
            pivot_left = df_sign.pivot_table(
                index="合同归档年度", values="ID", aggfunc="count"
            ).reset_index()
            pivot_left.columns = ["合同归档年度", "计数项:ID"]
            results["left"] = pivot_left

        # 右侧：履约项统计状态 × 合同归档年度
        status_col = "履约项统计状态（即，财报-交付/确收状态）"
        if status_col in df_sign.columns and "合同归档年度" in df_sign.columns:
            pivot_right = df_sign.pivot_table(
                index=status_col, columns="合同归档年度",
                values="ID", aggfunc="count", fill_value=0
            )
            pivot_right["总计"] = pivot_right.sum(axis=1)
            results["right"] = pivot_right

        return results

    # ---- POC 统计 ----
    def build_poc_stats(self, df_poc: pd.DataFrame) -> dict:
        """POC&提前实施统计（左/中/右三个 Pivot）"""
        results = {}

        # 左侧：立项年度 × 项目类型
        if "履约项立项年度" not in df_poc.columns:
            df_poc = df_poc.copy()
            df_poc["履约项立项年度"] = df_poc["立项日期"].apply(
                lambda x: str(x)[:4] if x and pd.notna(x) else ""
            )

        pivot_left = df_poc.pivot_table(
            index="履约项立项年度",
            columns="项目类型(概览)",
            values="ID", aggfunc="count", fill_value=0
        )
        pivot_left["总计"] = pivot_left.sum(axis=1)
        results["left"] = pivot_left

        # 中间：项目经理所属部门 × 持续周期（筛选提前实施）
        df_early = df_poc[df_poc["项目类型(概览)"] == "提前实施"]
        if not df_early.empty and "项目经理所属部门" in df_early.columns:
            pivot_mid = df_early.pivot_table(
                index="项目经理所属部门",
                columns="提前实施项目持续周期-统计",
                values="ID", aggfunc="count", fill_value=0
            )
            results["middle"] = pivot_mid

        # 右侧：所属产线 × 部门（工时求和，筛选 POC）
        df_poc_only = df_poc[df_poc["项目类型(概览)"] == "POC"]
        hours_col = "POC项目工时合计（小时）"
        if not df_poc_only.empty and hours_col in df_poc_only.columns:
            pivot_right = df_poc_only.pivot_table(
                index="所属产线",
                columns="项目经理所属部门",
                values=hours_col, aggfunc="sum", fill_value=0
            )
            results["right"] = pivot_right

        return results

    # ---- 异常统计 ----
    def build_abnormal_stats(self, df_exc: pd.DataFrame) -> dict:
        """异常统计（报备 Pivot + 归档 Pivot）"""
        results = {}
        df = df_exc.copy()

        # 解析异常报备年月
        if "异常报备日期" in df.columns:
            df["异常报备年份"] = df["异常报备日期"].apply(
                lambda x: str(x)[:4] if x and pd.notna(x) else ""
            )
            df["异常报备月份"] = df["异常报备日期"].apply(
                lambda x: str(x)[5:7] if x and pd.notna(x) and len(str(x)) >= 7 else ""
            )

        if "异常归档日期" in df.columns:
            df["异常归档年份"] = df["异常归档日期"].apply(
                lambda x: str(x)[:4] if x and pd.notna(x) else ""
            )
            df["异常归档月份"] = df["异常归档日期"].apply(
                lambda x: str(x)[5:7] if x and pd.notna(x) and len(str(x)) >= 7 else ""
            )

        # 筛选：异常影响情况 = 多项（有值的）
        if "异常影响情况" in df.columns:
            df_filtered = df[df["异常影响情况"].notna() & (df["异常影响情况"] != "")]
        else:
            df_filtered = df

        # 左侧：报备年份+月份 × 合同归档年度
        if all(c in df_filtered.columns for c in ["异常报备年份", "异常报备月份", "合同归档年度"]):
            pivot_left = df_filtered.pivot_table(
                index=["异常报备年份", "异常报备月份"],
                columns="合同归档年度",
                values="ID", aggfunc="count", fill_value=0
            )
            results["left"] = pivot_left

        # 右侧：归档年份+月份 × 合同归档年度
        if all(c in df_filtered.columns for c in ["异常归档年份", "异常归档月份", "合同归档年度"]):
            pivot_right = df_filtered.pivot_table(
                index=["异常归档年份", "异常归档月份"],
                columns="合同归档年度",
                values="ID", aggfunc="count", fill_value=0
            )
            results["right"] = pivot_right

        return results

    # ---- 异常台账 ----
    def build_abnormal_ledger(self, df_exc: pd.DataFrame) -> pd.DataFrame:
        """异常台账（合计 / 验收异常 / 交付异常 三组并排）"""
        # 骨架版本：返回空结构
        return pd.DataFrame()

    # ---- 交接统计 ----
    def build_handover_stats(self, df_rev: pd.DataFrame, df_acc: pd.DataFrame) -> dict:
        """交接统计（确收合格率 + 确收跨月率 + 验收合格率）"""
        results = {}

        for name, df in [("revenue", df_rev), ("acceptance", df_acc)]:
            if df.empty or "交接年月" not in df.columns:
                continue
            # 跨月交接 pivot
            pivot = df.pivot_table(
                index="交接年月", columns="跨月交接",
                values="ID", aggfunc="count", fill_value=0
            )
            # 计算比率
            pivot["总计"] = pivot.sum(axis=1)
            if "是" in pivot.columns:
                pivot["跨月比率"] = (pivot["是"] / pivot["总计"]).round(4)
            results[name] = pivot

        return results

    # ---- 交付效率统计 ----
    def build_efficiency_stats(self, df_sign: pd.DataFrame) -> pd.DataFrame:
        """交付效率统计（项目经理/部门/中心 三级汇总）"""
        # 骨架版本
        return pd.DataFrame()


# ============================================================
# Excel 写入层
# ============================================================

class ExcelWriter:
    """统一 Excel 写入器"""

    def __init__(self, output_path: Path):
        self.output_path = Path(output_path)
        self.wb = Workbook()
        # 删掉默认 sheet
        if "Sheet" in self.wb.sheetnames:
            del self.wb["Sheet"]

    def write_dataframe(
        self,
        df: pd.DataFrame,
        sheet_name: str,
        start_row: int = 1,
        start_col: int = 1,
        title_row: str = None,
    ):
        """写入 DataFrame 到指定 Sheet"""
        if sheet_name in self.wb.sheetnames:
            ws = self.wb[sheet_name]
        else:
            ws = self.wb.create_sheet(title=sheet_name)

        current_row = start_row

        # 标题行（第 1 行：报告日期）
        if title_row:
            cell = ws.cell(row=current_row, column=start_col, value=title_row)
            cell.font = DATA_FONT
            current_row += 1

        # 表头
        for col_idx, col_name in enumerate(df.columns, start_col):
            cell = ws.cell(row=current_row, column=col_idx, value=col_name)
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = HEADER_ALIGN
            cell.border = THIN_BORDER
        header_row = current_row
        current_row += 1

        # 数据（用 iloc 按位置取值，避免重名列导致 row[col_name] 返回 Series 的问题）
        for row_i in range(len(df)):
            row_vals = df.iloc[row_i].values
            for col_j, col_name in enumerate(df.columns):
                val = row_vals[col_j]
                # 标量 NaN 判断（兼容各种类型）
                try:
                    if pd.isna(val):
                        val = ""
                except (ValueError, TypeError):
                    pass  # 非标量（如数组）跳过 NaN 判断
                col_idx = start_col + col_j
                cell = ws.cell(row=current_row, column=col_idx, value=val)
                cell.font = DATA_FONT
                cell.alignment = DATA_ALIGN
                cell.border = THIN_BORDER
            current_row += 1

        # 列宽（自动）
        fmt = SHEET_FORMAT_MAP.get(sheet_name, {})
        for i, col_name in enumerate(df.columns, start_col):
            col_letter = get_column_letter(i)
            if fmt and "widths" in fmt and i - start_col < len(fmt["widths"]):
                ws.column_dimensions[col_letter].width = fmt["widths"][i - start_col]
            else:
                max_len = max(
                    len(str(col_name)),
                    df[col_name].astype(str).map(len).max() if len(df) > 0 else 10
                )
                ws.column_dimensions[col_letter].width = min(max_len + 2, 50)

        # 冻结
        if fmt and fmt.get("freeze"):
            ws.freeze_panes = fmt["freeze"]
        else:
            ws.freeze_panes = f"A{header_row + 1}"

        return ws

    def save(self):
        """保存文件"""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.wb.save(str(self.output_path))
        print(f"✅ 报表已保存: {self.output_path}")


# ============================================================
# 主入口
# ============================================================

def build_report(config: ReportConfig) -> Path:
    """
    主入口：根据配置生成完整交付月报 V2。

    流程：
      1. 加载所有原始数据
      2. 7 大引擎计算 → 各明细 DataFrame
      3. 统计 Sheet pivot
      4. 统一写入 Excel

    Args:
        config: ReportConfig 配置对象

    Returns:
        输出文件路径
    """
    print(f"\n{'='*60}")
    print(f"🚀 BDMS 交付月报 V2 生成器")
    print(f"   报告月份: {config.report_month}")
    print(f"   截止日期: {config.report_date}")
    print(f"{'='*60}\n")

    # 1. 加载数据
    print("[1/4] 加载原始数据...")
    loader = DataLoader(config)
    df_sign_raw = loader.load_sign_contracts()
    df_poc_raw = loader.load_poc()
    df_exc_raw = loader.load_exceptions()
    df_rev_raw = loader.load_revenue_handover()
    df_acc_raw = loader.load_acceptance_handover()

    # 可选数据
    try:
        df_oa_contracts = loader.load_oa_contracts()
    except Exception as e:
        print(f"  ⚠️ OA 合同加载失败（跳过）: {e}")
        df_oa_contracts = pd.DataFrame()

    try:
        df_workhours = loader.load_workhours()
        df_hours_by_contract = aggregate_by_contract(df_workhours)
    except Exception as e:
        print(f"  ⚠️ 工时数据加载失败（跳过）: {e}")
        df_hours_by_contract = pd.DataFrame()

    # 2. 引擎计算 → 明细 DataFrame
    print("\n[2/4] 引擎计算明细 Sheet...")
    orchestrator = ReportEngineOrchestrator(config)

    df_sign = orchestrator.build_sign_detail(df_sign_raw, df_exc_raw, df_oa_contracts)
    print(f"   ✅ 签约明细: {df_sign.shape[0]} 行 × {df_sign.shape[1]} 列")

    df_poc = orchestrator.build_poc_detail(df_poc_raw, df_exc_raw, df_hours_by_contract, df_oa_contracts)
    print(f"   ✅ POC&提前实施: {df_poc.shape[0]} 行 × {df_poc.shape[1]} 列")

    df_exception = orchestrator.build_exception_detail(df_exc_raw, df_sign)
    print(f"   ✅ 异常项目: {df_exception.shape[0]} 行 × {df_exception.shape[1]} 列")

    df_rev = orchestrator.build_revenue_handover(df_rev_raw)
    print(f"   ✅ 确收交接: {df_rev.shape[0]} 行 × {df_rev.shape[1]} 列")

    df_acc = orchestrator.build_acceptance_handover(df_acc_raw)
    print(f"   ✅ 验收交接: {df_acc.shape[0]} 行 × {df_acc.shape[1]} 列")

    # 3. 统计 Sheet
    print("\n[3/4] 生成统计 Sheet...")
    stats = StatsSheetBuilder()
    sign_stats = stats.build_sign_stats(df_sign)
    poc_stats = stats.build_poc_stats(df_poc)
    abnormal_stats = stats.build_abnormal_stats(df_exception)
    handover_stats = stats.build_handover_stats(df_rev, df_acc)
    print("   ✅ 统计 Sheet 计算完成（骨架版）")

    # 4. 写 Excel
    print("\n[4/4] 写入 Excel...")
    output_file = config.output_dir / f"交付月报-{config.report_month}-v2.xlsx"
    writer = ExcelWriter(output_file)

    # 明细 Sheet
    writer.write_dataframe(df_sign, "签约", title_row=config.report_date)
    writer.write_dataframe(df_poc, "POC&提前实施", title_row=config.report_date)
    writer.write_dataframe(df_exception, "异常项目")
    writer.write_dataframe(df_rev, "确收交接")
    writer.write_dataframe(df_acc, "验收交接")

    # 统计 Sheet（骨架版，写入空结构 + 左侧 Pivot 数据）
    # 签约统计（左右并排，先写左侧）
    if "left" in sign_stats:
        writer.write_dataframe(sign_stats["left"], "签约统计")

    writer.save()

    print(f"\n🎉 报表生成完成: {output_file}")
    return output_file


# ============================================================
# CLI 入口
# ============================================================

def main():
    """命令行入口"""
    if len(sys.argv) > 1:
        report_month = sys.argv[1]
    else:
        report_month = "202606"

    config = ReportConfig(report_month=report_month)
    build_report(config)


if __name__ == "__main__":
    main()


# ============================================================
# JSON 导出 + 明细导出（v2 双格式输出）
# ============================================================

def export_report_json(
    sheet_data: dict,
    output_path: Path,
    include_empty: bool = False,
) -> Path:
    """
    将报表数据以 JSON 格式导出。

    每个 Sheet 对应一个 key，值为 list[dict]（按行记录）。
    日期/数值类型自动序列化（datetime → ISO string, NaN → null）。

    Args:
        sheet_data: {sheet_name: DataFrame} 字典
        output_path: 输出 JSON 文件路径
        include_empty: 是否包含空 Sheet

    Returns:
        输出文件路径
    """
    import json

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = {}
    for sheet_name, df in sheet_data.items():
        if df is None or (df.empty and not include_empty):
            continue
        # 处理重名列：to_json(orient='records') 要求列名唯一
        # 给重复列名加 .1 / .2 后缀（保留原始列顺序）
        if len(df.columns) != len(set(df.columns)):
            from collections import Counter
            col_counts = Counter()
            new_cols = []
            for col in df.columns:
                col_counts[col] += 1
                if col_counts[col] == 1:
                    new_cols.append(col)
                else:
                    new_cols.append(f"{col}.{col_counts[col] - 1}")
            df = df.copy()
            df.columns = new_cols

        # orient='records' 输出 list[dict]，date_format='iso' 处理日期
        records = json.loads(
            df.to_json(orient="records", date_format="iso", force_ascii=False)
        )
        result[sheet_name] = {
            "row_count": len(records),
            "col_count": len(df.columns),
            "columns": list(df.columns),
            "data": records,
        }

    # 元信息
    result["_meta"] = {
        "generated_at": datetime.now().isoformat(),
        "sheet_count": len([k for k in result if not k.startswith("_")]),
        "version": "v2",
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"📄 JSON 导出完成: {output_path}")
    return output_path


def export_detail_by_dimension(
    df: pd.DataFrame,
    dimension_col: str,
    output_dir: Path,
    format: str = "csv",  # csv | xlsx | json
    prefix: str = "detail",
) -> list:
    """
    按维度列拆分明细并分别导出（多维度明细导出）。

    例如：按部门导出各部门签约明细、按项目经理导出异常明细。

    Args:
        df: 明细 DataFrame
        dimension_col: 维度列名（如"项目经理所属部门"、"产品分类"）
        output_dir: 输出目录
        format: 输出格式（csv / xlsx / json）
        prefix: 文件名前缀

    Returns:
        生成的文件路径列表
    """
    if df.empty or dimension_col not in df.columns:
        return []

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = []
    for value, group in df.groupby(dimension_col, dropna=False):
        # 文件名安全化
        safe_value = str(value).replace("/", "_").replace(" ", "")
        if safe_value == "nan" or safe_value == "":
            safe_value = "未分类"

        base_name = f"{prefix}_{safe_value}"

        if format == "csv":
            path = output_dir / f"{base_name}.csv"
            group.to_csv(path, index=False, encoding="utf-8-sig")
        elif format == "xlsx":
            path = output_dir / f"{base_name}.xlsx"
            group.to_excel(path, index=False)
        elif format == "json":
            path = output_dir / f"{base_name}.json"
            import json
            records = json.loads(
                group.to_json(orient="records", date_format="iso", force_ascii=False)
            )
            with open(path, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
        else:
            raise ValueError(f"不支持的格式: {format}（可选: csv / xlsx / json）")

        files.append(path)

    print(f"📂 按「{dimension_col}」拆分为 {len(files)} 个 {format.upper()} 文件 → {output_dir}")
    return files


def build_report_with_exports(config: ReportConfig) -> dict:
    """
    一体化入口：生成 Excel 报表 + JSON 导出 + 多维明细导出。

    整合所有引擎输出，返回 {excel: Path, json: Path, detail_files: list}。

    Args:
        config: ReportConfig 配置

    Returns:
        dict，包含各格式输出路径
    """
    # 1. 先构建所有数据（复用 build_report 的数据管线，但不写 Excel）
    loader = DataLoader(config)
    df_sign_raw = loader.load_sign_contracts()
    df_poc_raw = loader.load_poc()
    df_exc_raw = loader.load_exceptions()
    df_rev_raw = loader.load_revenue_handover()
    df_acc_raw = loader.load_acceptance_handover()

    try:
        df_oa_contracts = loader.load_oa_contracts()
    except Exception:
        df_oa_contracts = pd.DataFrame()

    try:
        df_workhours = loader.load_workhours()
        df_hours_by_contract = aggregate_by_contract(df_workhours)
    except Exception:
        df_hours_by_contract = pd.DataFrame()

    orchestrator = ReportEngineOrchestrator(config)
    df_sign = orchestrator.build_sign_detail(df_sign_raw, df_exc_raw, df_oa_contracts)
    df_poc = orchestrator.build_poc_detail(df_poc_raw, df_exc_raw, df_hours_by_contract, df_oa_contracts)
    df_exception = orchestrator.build_exception_detail(df_exc_raw, df_sign)
    df_rev = orchestrator.build_revenue_handover(df_rev_raw)
    df_acc = orchestrator.build_acceptance_handover(df_acc_raw)

    # 2. 写 Excel
    output_excel = config.output_dir / f"交付月报-{config.report_month}-v2.xlsx"
    writer = ExcelWriter(output_excel)
    writer.write_dataframe(df_sign, "签约", title_row=config.report_date)
    writer.write_dataframe(df_poc, "POC&提前实施", title_row=config.report_date)
    writer.write_dataframe(df_exception, "异常项目")
    writer.write_dataframe(df_rev, "确收交接")
    writer.write_dataframe(df_acc, "验收交接")
    writer.save()

    # 3. 导出 JSON
    sheet_data = {
        "签约": df_sign,
        "POC&提前实施": df_poc,
        "异常项目": df_exception,
        "确收交接": df_rev,
        "验收交接": df_acc,
    }
    output_json = config.output_dir / f"交付月报-{config.report_month}-v2.json"
    export_report_json(sheet_data, output_json)

    # 4. 按部门多维导出签约明细（CSV）
    detail_dir = config.output_dir / f"交付月报-{config.report_month}-v2-details"
    detail_files = []
    if not df_sign.empty and "项目经理所属部门" in df_sign.columns:
        detail_files = export_detail_by_dimension(
            df_sign, "项目经理所属部门", detail_dir, format="csv", prefix="签约明细"
        )

    return {
        "excel": output_excel,
        "json": output_json,
        "detail_dir": detail_dir,
        "detail_files": detail_files,
    }
