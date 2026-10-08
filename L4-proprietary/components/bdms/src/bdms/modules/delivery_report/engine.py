"""交付月报计算引擎 v3.3 — 累积快照 + 月份回退修正。"""

import sys
from pathlib import Path
from typing import Optional

import pandas as pd
from openpyxl import Workbook

from bdms.core import db as _db

_LEGACY_DIR = Path(__file__).resolve().parents[5] / "delivery-center" / "src"
if str(_LEGACY_DIR) not in sys.path:
    sys.path.insert(0, str(_LEGACY_DIR))

try:
    from delivery_center.v2 import delivery_report_generator as _legacy
    _HAS_LEGACY = True
    _LEGACY_IMPORT_ERROR = None
except ImportError as e:
    _legacy = None
    _HAS_LEGACY = False
    _LEGACY_IMPORT_ERROR = str(e)

from bdms.modules.dashboard.delivery_report_connector import DeliveryReportConnector
from bdms.modules.integration.adapters.pipeline import DeliveryReportPipeline, DataSourceError
from bdms.modules.integration.adapters.ones_adapter import MissingSourceError

SHEET_ORDER = [
    "签约", "POC&提前实施", "异常项目", "确收交接", "验收交接",
    "异常台账", "交付效率统计", "签约统计", "产品-授权&维保统计",
    "POC&提前实施统计", "提前实施分事业部统计", "异常统计",
    "交付异常分事业部统计", "交接统计", "图例",
]


class MissingSourceError(Exception):
    """当月数据源缺失且无法回退时抛出。"""
    pass


def _resolve_csv(month: str, kind: str) -> Path:
    """解析 CSV 文件路径。
    
    优先级：
    1. {ONES_DIR}/{month}周报-{kind}.csv
    2. {ONES_DIR}/{fallback_name}（通用名）
    
    kind: sign | poc | exception | revenue | acceptance
    
    Raises:
        MissingSourceError: 当月 CSV 不存在且无通用名回退
    """
    from bdms.core.paths import ones_dir, month_dir
    
    patterns = {
        "sign": (ones_dir(), f"{{m}}周报-签约项目统计.csv", "签约项目统计.csv"),
        "poc": (ones_dir(), f"{{m}}周报-POC&提前实施统计.csv", "poc_提前实施.csv"),
        "exception": (ones_dir(), f"{{m}}-签约项目异常处置.csv", "异常处置.csv"),
    }
    
    if kind in patterns:
        search_dir, tmpl, fallback = patterns[kind]
        # 精确匹配当月
        p = search_dir / tmpl.format(m=month)
        if p.exists():
            return p
        # 回退到前一个月
        prev_month = str(int(month) - 1).zfill(6)
        p = search_dir / tmpl.format(m=prev_month)
        if p.exists():
            return p
        # 回退到通用名
        p = search_dir / fallback
        if p.exists():
            return p
        return None
    
    # revenue / acceptance（在 month_dir 查找）
    if kind in ('revenue', 'acceptance'):
        # 先当月
        d = month_dir(month)
        if d.exists():
            if kind == 'revenue':
                for f in d.glob(f"{month}确收凭证交接-确收.csv"):
                    return f
            else:
                for f in d.glob(f"{month}确收凭证交接-验收.csv"):
                    return f
        # 回退前一个月
        prev_month = str(int(month) - 1).zfill(6)
        d = month_dir(prev_month)
        if d.exists():
            if kind == 'revenue':
                for f in d.glob(f"{prev_month}确收凭证交接-确收.csv"):
                    return f
            else:
                for f in d.glob(f"{prev_month}确收凭证交接-验收.csv"):
                    return f
    
    return None


def _load_csv_resolved(month: str, kind: str) -> pd.DataFrame:
    """加载 CSV，带月份回退。"""
    path = _resolve_csv(month, kind)
    if path is None:
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, dtype=str, encoding='utf-8')
        # 列名对齐
        col_rename = {
            "履约项异常/变更备注": "履约项异常/变更类型",
            "合同开始日期": "合同起始日期",
        }
        df = df.rename(columns={k: v for k, v in col_rename.items() if k in df.columns})
        return df
    except Exception:
        return pd.DataFrame()


def _wb_to_df(wb, sheet_name):
    ws = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return pd.DataFrame()
    header = [str(c) if c is not None else "" for c in rows[0]]
    data = [list(r) for r in rows[1:] if any(c is not None for c in r)]
    return pd.DataFrame(data, columns=header) if data else pd.DataFrame(columns=header)


class DeliveryReportEngine:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path
        self.connector = DeliveryReportConnector(db_path)
        self.pipeline = DeliveryReportPipeline(db_path)

    def compute(self, month: str) -> dict[str, pd.DataFrame]:
        if not _HAS_LEGACY:
            raise RuntimeError(f"delivery-center 不可用: {_LEGACY_IMPORT_ERROR}")

        result = {}
        
        # ── 1. 从数据源提取原始数据（缺失立即报错，不静默回退） ──
        try:
            raw_data = self.pipeline.extract_raw_data(month)
        except DataSourceError as e:
            raise RuntimeError(f"数据源缺失: {e}")

        df_sign = pd.DataFrame(raw_data["sign"])
        df_poc = pd.DataFrame(raw_data["poc"])
        df_exc = pd.DataFrame(raw_data["exception"])
        df_rev = pd.DataFrame(raw_data["revenue"])
        df_acc = pd.DataFrame(raw_data["acceptance"])

        # ── 2. 核心数据 (Sheet 1-5) ──
        result["签约"] = _legacy.build_sign_sheet_df(df_sign, df_exc)
        result["POC&提前实施"] = _legacy.build_poc_sheet_df(df_poc, df_exc)
        result["异常项目"] = _legacy.build_exception_df(df_exc, result["签约"]) 

        # 确收交接 (4)
        if not df_rev.empty and hasattr(_legacy, "build_revenue_handover_df"):
            try:
                result["确收交接"] = _legacy.build_revenue_handover_df(df_rev, month)
            except Exception:
                result["确收交接"] = df_rev
        else:
            result["确收交接"] = pd.DataFrame()

        # 验收交接 (5)
        if not df_acc.empty and hasattr(_legacy, "build_acceptance_handover_df"):
            try:
                result["验收交接"] = _legacy.build_acceptance_handover_df(df_acc, month)
            except Exception:
                result["验收交接"] = df_acc
        else:
            result["验收交接"] = pd.DataFrame()

        # ── 3. 统计 (Sheet 6-14) 通过 connector ──
        stats = self.connector.build_stats_sheets(month)
        for name, df in stats.items():
            if df is not None and not df.empty:
                result[name] = df

        # 交付效率统计单独构建（不在 connector 中）
        if "交付效率统计" not in result or result.get("交付效率统计", pd.DataFrame()).empty:
            result["交付效率统计"] = self._build_efficiency_stats_from_db(month)

        # ── 4. 图例 (Sheet 15) ──
        legend_df = self.connector.get_legend_config()
        if legend_df is not None and not legend_df.empty:
            result["图例"] = legend_df

        return result

    def persist(self, month: str, data: dict[str, pd.DataFrame],
                overwrite: bool = True) -> dict:
        """持久化数据到 DB。
        
        事务保护：所有 Sheet 写入 + report_month 注册在同一事务中，
        任一失败则全部回滚，避免幽灵记录（注册了月份但数据不全）。
        """
        conn = _db.get_connection(self.db_path)
        try:
            counts = {}
            for sheet, df in data.items():
                if df is None or df.empty:
                    continue
                df = self._dedupe_columns(df)
                columns = list(df.columns)
                rows = df.fillna("").to_dict(orient="records")
                n = _db.save_sheet_rows(conn, month, sheet, columns, rows,
                                        prefix="dr", overwrite=overwrite)
                counts[sheet] = n
            _db.register_month(conn, "delivery_report", month, row_counts=counts)
            conn.commit()
            return counts
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def load(self, month: str) -> dict[str, pd.DataFrame]:
        conn = _db.get_connection(self.db_path)
        try:
            sheets = _db.list_sheets(conn, month, prefix="dr")
            out = {}
            for sheet in sheets:
                columns, rows = _db.load_sheet_rows(conn, month, sheet, prefix="dr")
                if rows:
                    out[sheet] = pd.DataFrame(rows, columns=columns)
            return out
        finally:
            conn.close()

    def has_data(self, month: str) -> bool:
        conn = _db.get_connection(self.db_path)
        try:
            return _db.get_month_status(conn, "delivery_report", month) is not None
        finally:
            conn.close()

    @staticmethod
    def _dedupe_columns(df: pd.DataFrame) -> pd.DataFrame:
        if len(df.columns) == len(set(df.columns)):
            return df
        seen: dict[str, int] = {}
        new_cols = []
        for c in df.columns:
            if c in seen:
                seen[c] += 1
                new_cols.append(f"{c}.{seen[c]}")
            else:
                seen[c] = 0
                new_cols.append(c)
        out = df.copy()
        out.columns = new_cols
        return out

    def _build_efficiency_stats_from_db(self, month: str) -> pd.DataFrame:
        """交付效率统计委托 connector。"""
        return self.connector.build_efficiency_stats(month)
