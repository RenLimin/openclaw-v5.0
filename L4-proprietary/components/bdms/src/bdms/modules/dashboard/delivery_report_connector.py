# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""交付月报 DASHBOARD 聚合查询适配器。

对齐 DESIGN-DETAIL-DELIVERY-REPORT-v2.1.md Step 4：
统计 Sheet（6-14）不单独落盘，导出时通过本连接器实时聚合 dr_sheet_row。

聚合逻辑参考黄金基准手工报表的统计口径。
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from bdms.core import db as _db


class DeliveryReportConnector:
    """交付月报统计聚合连接器（读 dr_sheet_row，实时聚合）。"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    # ========================================================
    # 公共入口
    # ========================================================

    def build_stats_sheets(self, month: str) -> Dict[str, pd.DataFrame]:
        """构建全部统计 Sheet（异常台账 / 交付效率统计 / 交接统计）。"""
        return {
            "异常台账": self.build_abnormal_ledger(month),
            "交付效率统计": self.build_efficiency_stats(month),
            "签约统计": self.build_sign_stats(month),
            "交接统计": self.build_handover_stats(month),
        }

    # ========================================================
    # Sheet 6: 异常台账（3 组 × 2 年份基准）
    # ========================================================

    def build_abnormal_ledger(self, month: str) -> pd.DataFrame:
        """异常台账：合计/验收异常/交付异常 × 基准年。

        口径（黄金基准）：
        - 前存量：报备 < 基准年 且 (归档 >= 基准年 或 未归档)
        - 新增：报备年 = 基准年
        - 已处理完毕：状态=已完成 且 归档年 = 基准年
        - 处理中：状态 != 已完成
        """
        df = self._load_sheet_df(month, "异常项目")
        if df is None or df.empty:
            return pd.DataFrame()

        year = int(month[:4])
        frames = []
        for base_year in (year - 1, year):
            for category, label in ((None, "合计"),
                                    ("验收", "验收异常"),
                                    ("交付", "交付异常")):
                sub = self._abnormal_one(df, base_year, category)
                if sub is not None and not sub.empty:
                    frames.append((label, base_year, sub))

        # 横向拼接（label, base_year 相同的一组）
        if not frames:
            return pd.DataFrame()

        # 按组拼接：同 label+base_year 的左侧是合计组，右侧是分类组
        # 黄金基准布局：合计 | 验收异常 | 交付异常（横向三组）
        return self._hstack_groups(df, year)

    def _abnormal_one(self, df: pd.DataFrame, base_year: int,
                      category: Optional[str]) -> Optional[pd.DataFrame]:
        """生成一组异常台账。"""
        d = df
        if category:
            cat_col = "异常项目-类别"
            if cat_col in d.columns:
                d = d[d[cat_col].astype(str).str.contains(category, na=False)]

        impact = "异常影响情况"
        if impact in d.columns:
            d = d[~d[impact].astype(str).str.contains("4：不统计", na=False)]

        def _year(v: Any) -> Optional[int]:
            try:
                s = str(v)[:10]
                if len(s) >= 4 and s[:4].isdigit():
                    return int(s[:4])
            except Exception:
                pass
            return None

        archive_y = d.get("合同归档日期")
        report_y = d.get("异常报备日期")
        resolve_y = d.get("异常归档日期")
        status = d.get("状态")

        def _col(col):
            """列不存在时返回全 None 序列。"""
            if col is None:
                return pd.Series([None] * len(d), index=d.index)
            return col

        archive_y = _col(archive_y)
        report_y = _col(report_y)
        resolve_y = _col(resolve_y)
        status = _col(status)

        rows = []
        years = sorted({
            _year(v) for v in archive_y if _year(v) is not None
        })
        for y in years:
            mask = archive_y.apply(lambda v: _year(v) == y)
            yd = d[mask.fillna(False)]
            if yd.empty:
                continue

            ry = report_y[mask.fillna(False)]
            vy = resolve_y[mask.fillna(False)]
            st = status[mask.fillna(False)]

            before = 0
            new = 0
            done = 0
            processing = 0
            for i in yd.index:
                r = _year(ry[i])
                v = _year(vy[i])
                s = str(st[i])
                if r is not None and r < base_year and (v is None or v >= base_year):
                    before += 1
                if r == base_year:
                    new += 1
                if s == "已完成" and v == base_year:
                    done += 1
                if s != "已完成":
                    processing += 1

            rows.append({
                "合同归档年份": str(y),
                f"{base_year}年之前存量": before,
                f"{base_year}年新增": new,
                f"{base_year}年已处理完毕": done,
                "处理中": processing,
            })

        if not rows:
            return None
        total = {
            k: (sum(r[k] for r in rows) if k != "合同归档年份" else "总计")
            for k in rows[0]
        }
        rows.append(total)
        return pd.DataFrame(rows)

    def _hstack_groups(self, df: pd.DataFrame, year: int) -> pd.DataFrame:
        """横向拼接 3 组（合计/验收异常/交付异常）× 2 基准年。"""
        pieces = []
        for base_year in (year - 1, year):
            for category in (None, "验收", "交付"):
                one = self._abnormal_one(df, base_year, category)
                pieces.append(one)

        # 统一列名后横向拼
        max_rows = max((len(p) for p in pieces if p is not None), default=0)
        out = pd.DataFrame(index=range(max_rows))
        col_offset = 0
        for i, p in enumerate(pieces):
            if p is None or p.empty:
                col_offset += 5 + 1
                continue
            renamed = p.copy()
            renamed.columns = [f"col_{col_offset + j}" for j in range(p.shape[1])]
            renamed.index = range(len(renamed))
            for c in renamed.columns:
                out[c] = renamed[c]
            col_offset += p.shape[1] + 1  # +1 空列分隔
        return out

    # ========================================================
    # Sheet 7: 交付效率统计
    # ========================================================

    def build_efficiency_stats(self, month: str) -> pd.DataFrame:
        """交付效率统计：按事业部的交付计划准确率 / 按时交付率。"""
        df = self._load_sheet_df(month, "签约")
        if df is None or df.empty:
            return pd.DataFrame()

        dept_col = self._find_col(df, ["所属产线", "事业部", "部门"])
        if not dept_col:
            return pd.DataFrame()

        acc_col = self._find_col(df, ["交付计划准确率"])
        ontime_col = self._find_col(df, ["按时交付率"])

        groups = df[dept_col].astype(str).value_counts()
        rows = []
        for dept, total in groups.items():
            row = {"事业部": dept, "项目数": int(total)}
            if acc_col:
                vals = pd.to_numeric(df[df[dept_col] == dept][acc_col], errors="coerce")
                row["平均交付计划准确率"] = round(float(vals.mean() * 100), 1) if not vals.empty and vals.notna().any() else None
            if ontime_col:
                vals = pd.to_numeric(df[df[dept_col] == dept][ontime_col], errors="coerce")
                row["平均按时交付率"] = round(float(vals.mean() * 100), 1) if not vals.empty and vals.notna().any() else None
            rows.append(row)
        return pd.DataFrame(rows)

    # ========================================================
    # Sheet 8: 签约统计
    # ========================================================

    def build_sign_stats(self, month: str) -> pd.DataFrame:
        """签约统计：按事业部/产线的签约金额与数量。"""
        df = self._load_sheet_df(month, "签约")
        if df is None or df.empty:
            return pd.DataFrame()

        dept_col = self._find_col(df, ["所属产线", "事业部"])
        amount_col = self._find_col(df, ["签约金额", "合同金额", "金额"])

        groups = df[dept_col].astype(str).value_counts()
        rows = []
        for dept, total in groups.items():
            row = {"事业部": dept, "签约数": int(total)}
            if amount_col:
                vals = pd.to_numeric(df[df[dept_col] == dept][amount_col], errors="coerce")
                row["签约金额"] = round(float(vals.sum()), 2) if vals.notna().any() else 0.0
            rows.append(row)
        return pd.DataFrame(rows)

    # ========================================================
    # 交接统计
    # ========================================================

    def build_handover_stats(self, month: str) -> pd.DataFrame:
        """交接统计：确收/验收交接的汇总。"""
        rows = []
        for sheet in ("确收交接", "验收交接"):
            df = self._load_sheet_df(month, sheet)
            if df is None or df.empty:
                rows.append({"Sheet": sheet, "行数": 0})
                continue
            amount_col = self._find_col(df, ["金额", "确收金额", "验收金额"])
            row = {"Sheet": sheet, "行数": len(df)}
            if amount_col:
                vals = pd.to_numeric(df[amount_col], errors="coerce")
                row["金额合计"] = round(float(vals.sum()), 2) if vals.notna().any() else 0.0
            rows.append(row)
        return pd.DataFrame(rows)

    # ========================================================
    # 图例 Sheet（15）
    # ========================================================

    def get_legend_config(self) -> pd.DataFrame:
        """读 md_reference legend_config → 图例 DataFrame。"""
        conn = _db.get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT code, label, extra FROM md_reference "
                "WHERE data_type = 'legend_config' AND enabled = 1 "
                "ORDER BY sort_order, code"
            ).fetchall()
            if not rows:
                return pd.DataFrame()
            return pd.DataFrame(
                [{"code": r[0], "label": r[1],
                  **(json.loads(r[2]) if r[2] else {})} for r in rows]
            )
        finally:
            conn.close()

    # ========================================================
    # 内部工具
    # ========================================================

    def _load_sheet_df(self, month: str, sheet: str) -> Optional[pd.DataFrame]:
        """从 dr_sheet_row 读某 Sheet 数据。"""
        conn = _db.get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT columns FROM dr_sheet_meta WHERE month = ? AND sheet = ?",
                (month, sheet),
            ).fetchone()
            if not row:
                return None
            columns = json.loads(row[0])
            data_rows = conn.execute(
                "SELECT data FROM dr_sheet_row WHERE month = ? AND sheet = ? ORDER BY row_index",
                (month, sheet),
            ).fetchall()
            if not data_rows:
                return None
            records = [json.loads(r[0]) for r in data_rows]
            return pd.DataFrame(records, columns=columns)
        finally:
            conn.close()

    @staticmethod
    def _find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
        """模糊找列名。"""
        for c in candidates:
            if c in df.columns:
                return c
            for col in df.columns:
                if c in str(col):
                    return col
        return None
