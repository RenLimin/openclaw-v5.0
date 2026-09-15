"""交付月报计算引擎。

复用来源：delivery-center/src/delivery_center/v2/delivery_report_generator.py
重构点：原实现是「加载 → 计算 → 直接写 Excel」的线性脚本；
       现拆为 加载/计算 与 输出 两层，中间加 DB 持久化。

数据流：
  原始 CSV → 计算 DataFrame → 持久化到 DB → Excel 导出

幂等语义：
  compute(month) 永远重新计算（纯函数，无副作用）
  service 层决定是「读 DB」还是「重新计算并覆盖」
"""

import sys
from pathlib import Path
from typing import Optional

import pandas as pd

from bdms.core import db as _db
from bdms.core.paths import find_ones_file, find_revenue_source, month_dir


# ─── 复用 delivery-center 的计算函数 ───
# 通过 sys.path 引入既有实现，避免复制代码
_LEGACY_DIR = Path(__file__).resolve().parents[5] / "delivery-center" / "src"
if str(_LEGACY_DIR) not in sys.path:
    sys.path.insert(0, str(_LEGACY_DIR))

try:
    from delivery_center.v2 import delivery_report_generator as _legacy
    _HAS_LEGACY = True
except ImportError as e:  # pragma: no cover
    _legacy = None
    _HAS_LEGACY = False
    _LEGACY_IMPORT_ERROR = str(e)


# 本模块产出的 Sheet 清单
SHEETS = ["签约", "POC&提前实施", "异常项目", "确收交接", "验收交接"]


class DeliveryReportEngine:
    """交付月报计算引擎（无状态，方法可独立调用）。"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    # ─── 数据源检查 ───

    def check_sources(self, month: str) -> dict:
        """检查某月的数据源是否齐备。"""
        return {
            "sign": find_ones_file(month, "sign"),
            "poc": find_ones_file(month, "poc"),
            "exception": find_ones_file(month, "exception"),
            "revenue_handover": find_revenue_source(month),
        }

    def sources_available(self, month: str) -> bool:
        src = self.check_sources(month)
        return bool(src["sign"])

    # ─── 计算 ───

    def compute(self, month: str) -> dict[str, pd.DataFrame]:
        """计算某月全部 Sheet。纯计算，不落盘。

        Returns: {sheet_name: DataFrame}
        """
        if not _HAS_LEGACY:
            raise RuntimeError(
                f"无法加载 delivery-center 计算模块: {_LEGACY_IMPORT_ERROR}"
            )

        # 复用原实现的加载函数
        df_sign = _legacy.load_ones_sign_contracts(month)
        df_poc = _legacy.load_ones_poc(month)
        df_exc = _legacy.load_ones_exceptions(month)

        result: dict[str, pd.DataFrame] = {}

        # 签约（83 列）
        sign_full = _legacy.build_sign_sheet_df(df_sign, df_exc)
        result["签约"] = sign_full

        # POC&提前实施（84 列）
        poc_full = _legacy.build_poc_sheet_df(df_poc, df_exc)
        result["POC&提前实施"] = poc_full

        # 异常项目（38 列）
        result["异常项目"] = _legacy.build_exception_df(df_exc, sign_full)

        # 确收交接 / 验收交接
        try:
            df_rev = _legacy.load_handover_revenue(month)
            if hasattr(_legacy, "build_revenue_handover_df"):
                result["确收交接"] = _legacy.build_revenue_handover_df(df_rev, month)
        except Exception:
            pass

        try:
            df_acc = _legacy.load_handover_acceptance(month)
            if hasattr(_legacy, "build_acceptance_handover_df"):
                result["验收交接"] = _legacy.build_acceptance_handover_df(df_acc, month)
        except Exception:
            pass

        return result

    # ─── 持久化 ───

    @staticmethod
    def _dedupe_columns(df: pd.DataFrame) -> pd.DataFrame:
        """处理重名列（源数据可能有多义列名）。"""
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

    def persist(self, month: str, data: dict[str, pd.DataFrame],
                overwrite: bool = True) -> dict:
        """将计算结果落盘到 DB。"""
        conn = _db.get_connection(self.db_path)
        try:
            counts = {}
            for sheet, df in data.items():
                # 去重列名（源数据可能有重名列，pandas 会丢数据）
                df = self._dedupe_columns(df)
                columns = list(df.columns)
                rows = df.fillna("").to_dict(orient="records")
                n = _db.save_sheet_rows(conn, month, sheet, columns, rows,
                                        prefix="dr", overwrite=overwrite)
                counts[sheet] = n
            _db.register_month(conn, "delivery_report", month, row_counts=counts)
            conn.commit()
            return counts
        finally:
            conn.close()

    def load(self, month: str) -> dict[str, pd.DataFrame]:
        """从 DB 读取某月数据。"""
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
        """DB 中是否已有该月数据。"""
        conn = _db.get_connection(self.db_path)
        try:
            return _db.get_month_status(conn, "delivery_report", month) is not None
        finally:
            conn.close()
