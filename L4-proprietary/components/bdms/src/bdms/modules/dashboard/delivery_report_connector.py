# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""交付月报 DASHBOARD 聚合查询适配器 v2。

对齐 DESIGN-DETAIL-DELIVERY-REPORT-v2.1.md Step 4：
统计 Sheet（6-14）不单独落盘，导出时通过本连接器实时聚合 dr_sheet_row。

对齐黄金基准（202606）透视表格式。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from bdms.core import db as _db


# ─── 9 种标准状态（签约统计右表） ───
STATUS_ORDER = [
    '1：正常交付', '2：应交未交', '3：交付异常', '4：正常验收',
    '5：应验未验', '6：验收异常', '7：正常服务', '8：应结未结', '9：已结项',
]

# 标准异常类别
STD_ABNORMAL_CATEGORIES = [
    '1：甲方不具备交付条件', '2：甲方未按照合同约定验收',
    '3：甲方确认终止但无终止协议下单', '4：甲方需求/期限变更但无补充协议下单',
    '5：缺少穿透验收单（渠道-最终用户）', '6：项目启动延期',
    '7：交付资源不足', '8：其他',
]

# 标准事业部排序
STD_DEPT_ORDER = [
    '北区金融部', '北区营销部', '东区营销部', '华中营销部', '南区营销部',
    '西区营销部', '西区金融部', '东区金融部', '南区金融部', '华中金融部',
]


def _status_from_flags(row) -> str:
    """从 9 个状态标志列推断履约项统计状态。"""
    flag_cols = [
        ('1：正常交付', 'c57'), ('2：应交未交', 'c58'), ('3：交付异常', 'c59'),
        ('4：正常验收', 'c60'), ('5：应验未验', 'c61'), ('6：验收异常', 'c62'),
        ('7：正常服务', 'c63'), ('8：应结未结', 'c64'), ('9：已结项', 'c65'),
    ]
    for label, col in flag_cols:
        val = row.get(col, 0)
        if val and str(val) in ('1', '1.0', 'True', 'true'):
            return label
    return ''


class DeliveryReportConnector:
    """交付月报统计聚合连接器 v2（透视表格式）。"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    # ============================================================
    # 公共入口
    # ============================================================

    def build_stats_sheets(self, month: str) -> Dict[str, pd.DataFrame]:
        """构建全部统计 Sheet（透视表格式对齐黄金基准）。"""
        return {
            "异常台账": self.build_abnormal_ledger(month),
            "交付效率统计": self.build_efficiency_stats(month),
            "签约统计": self.build_sign_stats(month),
            "交接统计": self.build_handover_stats(month),
        }

    # ============================================================
    # Sheet 6: 异常台账（合计/验收异常/交付异常 × 2 个基准年）
    # ============================================================

    def build_abnormal_ledger(self, month: str) -> pd.DataFrame:
        """异常台账：17 列 × ~10 行。

        黄金基准布局：3 组横向拼接（合计 | 验收异常 | 交付异常）
        每组 5 列：合同归档年份 | 前存量 | 新增 | 已处理完毕 | 处理中
        """
        df = self._load_sheet_df(month, "异常项目")
        if df is None or df.empty:
            return pd.DataFrame()

        year = int(month[:4])

        # 提取年份
        df['合同归档年份'] = pd.to_datetime(df['合同归档日期'], errors='coerce').dt.year
        df['报备年份'] = pd.to_datetime(df['异常报备日期'], errors='coerce').dt.year
        df['归档年份'] = pd.to_datetime(df['异常归档日期'], errors='coerce').dt.year
        df['异常影响情况'] = df.get('异常影响情况', pd.Series([''] * len(df)))

        # 过滤"4：不统计"
        df = df[~df['异常影响情况'].astype(str).str.contains('4：不统计', na=False)]

        years = sorted([int(y) for y in df['合同归档年份'].dropna().unique()])

        pieces = []
        for base_year in (year - 1, year):
            for category, label in [(None, '合计'), ('验收', '验收异常'), ('交付', '交付异常')]:
                sub = df.copy()
                if category:
                    sub = sub[sub['异常影响情况'].astype(str).str.contains(category, na=False)]

                rows = []
                for y in years:
                    yd = sub[sub['合同归档年份'] == y]
                    before = len(yd[(yd['报备年份'] < base_year) & ((yd['归档年份'] >= base_year) | yd['归档年份'].isna())])
                    new = len(yd[yd['报备年份'] == base_year])
                    done = len(yd[(yd.get('状态', pd.Series([''] * len(yd))).astype(str) == '已完成') & (yd['归档年份'] == base_year)])
                    proc = len(yd[yd.get('状态', pd.Series([''] * len(yd))).astype(str) != '已完成'])
                    rows.append({
                        f'{label}_合同归档年份': str(y),
                        f'{label}_前存量': before,
                        f'{label}_新增': new,
                        f'{label}_已处理完毕': done,
                        f'{label}_处理中': proc,
                    })
                # 总计
                total = {f'{label}_合同归档年份': '总计'}
                for k in ['前存量', '新增', '已处理完毕', '处理中']:
                    total[f'{label}_{k}'] = sum(r[f'{label}_{k}'] for r in rows)
                rows.append(total)
                pieces.append(pd.DataFrame(rows))

        if not pieces:
            return pd.DataFrame()

        # 横向拼接
        max_rows = max(len(p) for p in pieces)
        out = pd.DataFrame(index=range(max_rows))
        for p in pieces:
            p.index = range(len(p))
            out = pd.concat([out, p], axis=1)
        return out

    # ============================================================
    # Sheet 7: 交付效率统计（18 列 × ~25 行）
    # ============================================================

    def build_efficiency_stats(self, month: str) -> pd.DataFrame:
        """交付效率统计：三列布局（项目经理明细/部门汇总/中心汇总）。

        黄金基准结构（18 列 × ~25 行）：
        - 列 1-6:  项目经理所属部门/项目经理/偏差率/平均偏差率/偏差率/平均偏差率
        - 列 8-12:  部门/偏差率/平均偏差率/偏差率/平均偏差率
        - 列 14-18: 中心/偏差率/平均偏差率/偏差率/平均偏差率
        """
        df = self._load_sheet_df(month, "签约")
        if df is None or df.empty:
            return pd.DataFrame()

        max_rows = 25
        # 输出为 openpyxl 写入准备：row = list of values per row
        rows = []

        # 行1: 标题行
        row1 = [None] * 18
        row1[2] = '交付计划准确性（<50%）'
        row1[4] = '交付及时性（<20%）'
        row1[7] = '部门'
        row1[8] = '交付计划准确性（<50%）'
        row1[10] = '交付及时性（<20%）'
        row1[13] = '中心'
        row1[14] = '交付计划准确性（<50%）'
        row1[16] = '交付及时性（<20%）'
        rows.append(row1)

        # 行2: 列头
        headers = ['项目经理团队', '项目经理', '偏差率', '平均偏差率', '偏差率', '平均偏差率', None,
                   '', '偏差率', '平均偏差率', '偏差率', '平均偏差率', None,
                   '', '偏差率', '平均偏差率', '偏差率', '平均偏差率']
        rows.append(headers)

        # 列索引 (0-based)
        COL_L_TEAM, COL_L_PM, COL_L_ACC_RATE, COL_L_ACC_MEAN, COL_L_ONT_RATE, COL_L_ONT_MEAN = 0, 1, 2, 3, 4, 5
        COL_M_DEPT, COL_M_ACC_RATE, COL_M_ACC_MEAN, COL_M_ONT_RATE, COL_M_ONT_MEAN = 7, 8, 9, 10, 11
        COL_R_CENTER, COL_R_ACC_RATE, COL_R_ACC_MEAN, COL_R_ONT_RATE, COL_R_ONT_MEAN = 13, 14, 15, 16, 17

        # 准备项目经理级数据
        pm_col = self._find_col(df, ['负责人', '项目经理'])
        team_col = self._find_col(df, ['责任销售所属团队', '项目经理所属部门', '项目经理团队'])
        acc_rate_col = self._find_col(df, ['c68', 'c69', 'c70', 'c71', '交付计划准确率'])
        ont_rate_col = self._find_col(df, ['c72', 'c73', 'c74', 'c75', '按时交付率'])

        if not pm_col:
            df['项目经理'] = 'UNKNOWN'
            pm_col = '项目经理'
        if not team_col:
            df['项目经理所属部门'] = '#N/A'
            team_col = '项目经理所属部门'

        # 计算偏差率（简化：基于 c68-c75 列的数值）
        for col_suffix in ['c68', 'c69', 'c70', 'c71', 'c72', 'c73', 'c74', 'c75']:
            if col_suffix in df.columns:
                df[col_suffix] = pd.to_numeric(df[col_suffix], errors='coerce').fillna(0)

        # 左侧：按项目经理明细
        dept_col_for_group = team_col
        df[dept_col_for_group] = df[dept_col_for_group].fillna('#N/A').astype(str)

        pm_groups = df.groupby([dept_col_for_group, pm_col]).agg(
            count=('ID', 'nunique')
        ).reset_index().sort_values([dept_col_for_group, pm_col])

        # 限制为 23 行
        pm_groups = pm_groups.head(23)

        prev_team = None
        row_idx = 2  # 0-based row index (row3 in Excel)
        dept_rows = {}  # dept -> row index for middle section

        for _, rd in pm_groups.iterrows():
            team = str(rd[dept_col_for_group]) if pd.notna(rd[dept_col_for_group]) else '#N/A'
            pm = str(rd[pm_col]) if pd.notna(rd[pm_col]) else '#N/A'

            row_data = [None] * 18
            # 团队名只在第一次出现时显示
            if team != prev_team:
                row_data[COL_L_TEAM] = team
                prev_team = team
            row_data[COL_L_PM] = pm

            # 偏差率：计算该项目经理的有差异项目占比
            dept_mask = df[dept_col_for_group] == team
            pm_mask = df[pm_col] == pm
            pm_df = dept_mask & pm_mask
            plan_acc_vals = pd.to_numeric(df.loc[pm_df, acc_rate_col], errors='coerce') if acc_rate_col else pd.Series([0])
            plan_ont_vals = pd.to_numeric(df.loc[pm_df, ont_rate_col], errors='coerce') if ont_rate_col else pd.Series([0])

            row_data[COL_L_ACC_RATE] = round(float((plan_acc_vals.abs() > 0).mean() * 100), 2) if not plan_acc_vals.empty else 0
            row_data[COL_L_ACC_MEAN] = round(float(plan_acc_vals.mean()), 2) if not plan_acc_vals.empty and plan_acc_vals.notna().any() else 0
            row_data[COL_L_ONT_RATE] = round(float((plan_ont_vals.abs() > 0).mean() * 100), 2) if not plan_ont_vals.empty else 0
            row_data[COL_L_ONT_MEAN] = round(float(plan_ont_vals.mean()), 2) if not plan_ont_vals.empty and plan_ont_vals.notna().any() else 0

            rows.append(row_data)
            row_idx += 1

            # 记录部门位置（用于中间列）
            if team not in dept_rows:
                dept_rows[team] = row_idx - 2  # middle section starts at row 3 (Excel)

        # 中间：按部门汇总
        for dept_name, excel_row in sorted(dept_rows.items()):
            dept_mask = df[dept_col_for_group] == dept_name
            dept_df = df[dept_mask]
            plan_acc = pd.to_numeric(dept_df[acc_rate_col], errors='coerce') if acc_rate_col else pd.Series([0])
            plan_ont = pd.to_numeric(dept_df[ont_rate_col], errors='coerce') if ont_rate_col else pd.Series([0])

            row_data = [None] * 18
            row_data[COL_M_DEPT] = dept_name
            row_data[COL_M_ACC_RATE] = round(float((plan_acc.abs() > 0).mean() * 100), 2) if not plan_acc.empty else 0
            row_data[COL_M_ACC_MEAN] = round(float(plan_acc.mean()), 2) if not plan_acc.empty and plan_acc.notna().any() else 0
            row_data[COL_M_ONT_RATE] = round(float((plan_ont.abs() > 0).mean() * 100), 2) if not plan_ont.empty else 0
            row_data[COL_M_ONT_MEAN] = round(float(plan_ont.mean()), 2) if not plan_ont.empty and plan_ont.notna().any() else 0

            # 确保行存在
            while len(rows) <= excel_row + 2:
                rows.append([None] * 18)
            # 合并到对应行
            for ci in [COL_M_DEPT, COL_M_ACC_RATE, COL_M_ACC_MEAN, COL_M_ONT_RATE, COL_M_ONT_MEAN]:
                if row_data[ci] is not None:
                    rows[excel_row + 2][ci] = row_data[ci]

        # 右侧：中心汇总（所有项目的汇总）
        if acc_rate_col or ont_rate_col:
            all_plan_acc = pd.to_numeric(df[acc_rate_col], errors='coerce') if acc_rate_col else pd.Series([0])
            all_plan_ont = pd.to_numeric(df[ont_rate_col], errors='coerce') if ont_rate_col else pd.Series([0])

            center_row = [None] * 18
            center_row[COL_R_CENTER] = '交付中心'
            center_row[COL_R_ACC_RATE] = round(float((all_plan_acc.abs() > 0).mean() * 100), 2) if not all_plan_acc.empty else 0
            center_row[COL_R_ACC_MEAN] = round(float(all_plan_acc.mean()), 2) if not all_plan_acc.empty and all_plan_acc.notna().any() else 0
            center_row[COL_R_ONT_RATE] = round(float((all_plan_ont.abs() > 0).mean() * 100), 2) if not all_plan_ont.empty else 0
            center_row[COL_R_ONT_MEAN] = round(float(all_plan_ont.mean()), 2) if not all_plan_ont.empty and all_plan_ont.notna().any() else 0

            # 填充剩余行
            for extra_row in range(3, 25):
                while len(rows) <= extra_row:
                    rows.append([None] * 18)
                for ci in [COL_R_CENTER, COL_R_ACC_RATE, COL_R_ACC_MEAN, COL_R_ONT_RATE, COL_R_ONT_MEAN]:
                    if extra_row == 3:
                        rows[extra_row][ci] = center_row[ci]
                    else:
                        rows[extra_row][ci] = 0

        # 补齐到 25 行
        while len(rows) < 25:
            rows.append([None] * 18)

        return pd.DataFrame(rows[:25])

    # ============================================================
    # Sheet 8: 签约统计（15 行 × 15 列透视表）
    # ============================================================

    def build_sign_stats(self, month: str) -> pd.DataFrame:
        """签约统计：左表按年份计数，右表按状态×年份交叉。

        黄金基准结构（15 行 × 15 列）：
        - 行1-3: 筛选器（项目经理所属部门/统计项目编号/项目状态）
        - 行4: 空行
        - 行5: 列名（行标签/计数项:ID/空×3/计数项:ID/列标签/年份.../总计）
        - 行6-14: 数据行（左：年份计数，右：状态×年份交叉）
        """
        df = self._load_sheet_df(month, "签约")
        if df is None or df.empty:
            return pd.DataFrame()

        year = int(month[:4])
        max_rows = 15

        # 计算立项年份
        df['立项年份'] = pd.to_datetime(df['立项日期'], errors='coerce').dt.year
        df['ID'] = df.get('ID', df.get('id', range(len(df))))

        # 计算 9 状态
        df['履约项统计状态'] = df.apply(_status_from_flags, axis=1)

        # 左表：按立项年份统计项目数
        year_counts = df.groupby('立项年份')['ID'].nunique()
        years = sorted([int(y) for y in year_counts.index if pd.notna(y) and int(y) >= 2019 and int(y) <= year])
        if years:
            full_years = list(range(2019, max(years) + 1))
        else:
            full_years = list(range(2019, year + 1))

        # 右表：履约项统计状态 × 立项年份 交叉表
        valid_df = df[df['履约项统计状态'] != '']
        pivot = valid_df.pivot_table(
            index='履约项统计状态', columns='立项年份',
            values='ID', aggfunc='nunique', fill_value=0
        )

        # 构建输出
        rows = []

        # 行1-3: 筛选器
        for field in ['项目经理所属部门', '统计项目编号', '项目状态']:
            row = [None] * 15
            row[0] = field
            row[1] = '(全部)'
            row[5] = field
            row[6] = '(全部)'
            rows.append(row)

        # 行4: 空行
        rows.append([None] * 15)

        # 行5: 列名
        header_row = [None] * 15
        header_row[0] = '行标签'
        header_row[1] = '计数项:ID'
        # 列3-5留空
        header_row[5] = '计数项:ID'
        header_row[6] = '列标签'
        rows.append(header_row)

        # 行6: 右表表头
        row6 = [None] * 15
        row6[5] = '行标签'
        ordered_years_r = [year] + [y for y in full_years if y != year]
        for ci, yl in enumerate(ordered_years_r[:8], 7):
            row6[ci] = f'{yl}年'
        row6[14] = '总计'
        rows.append(row6)

        # 数据行（左+右）
        for i, y in enumerate(full_years):
            row = [None] * 15
            # 左表
            row[0] = f'{y}年'
            row[1] = int(year_counts.get(y, 0))
            # 右表（状态 × 年份 交叉）
            for ri, status in enumerate(STATUS_ORDER):
                target_row = len(rows) + ri
                if target_row < max_rows:
                    while len(rows) <= target_row:
                        rows.append([None] * 15)
                    rows[target_row][5] = status
                    for ci, col_year in enumerate(ordered_years_r[:8]):
                        val = int(pivot.loc[status, col_year]) if status in pivot.index and col_year in pivot.columns else 0
                        rows[target_row][7 + ci] = val
                    # 行总计
                    row_total = sum(
                        int(pivot.loc[status, cy]) if status in pivot.index and cy in pivot.columns else 0
                        for cy in ordered_years_r
                    )
                    rows[target_row][14] = row_total

        # 左表总计
        total_row = [None] * 15
        total_row[0] = '总计'
        total_row[1] = int(df['ID'].nunique())
        rows.append(total_row)

        # 右表总计
        right_total = [None] * 15
        right_total[5] = '总计'
        for ci, col_year in enumerate(ordered_years_r[:8]):
            val = int(pivot[col_year].sum()) if col_year in pivot.columns else 0
            right_total[7 + ci] = val
        right_total[14] = int(pivot.values.sum())
        rows.append(right_total)

        # 空行补齐
        while len(rows) < max_rows:
            rows.append([None] * 15)

        return pd.DataFrame(rows[:max_rows])

    # ============================================================
    # 交接统计
    # ============================================================

    def build_handover_stats(self, month: str) -> pd.DataFrame:
        """交接统计：确收/验收交接的汇总。"""
        rows = []
        for sheet in ('确收交接', '验收交接'):
            df = self._load_sheet_df(month, sheet)
            if df is None or df.empty:
                rows.append({'Sheet': sheet, '行数': 0, '金额合计': 0})
                continue
            amount_col = self._find_col(df, ['金额', '确收金额', '验收金额', '合同金额', '单项履约义务金额'])
            total = 0
            if amount_col:
                vals = pd.to_numeric(df[amount_col], errors='coerce')
                total = round(float(vals.sum()), 2) if vals.notna().any() else 0
            rows.append({'Sheet': sheet, '行数': len(df), '金额合计': total})
        return pd.DataFrame(rows)

    # ============================================================
    # 图例 Sheet（15）
    # ============================================================

    def get_legend_config(self) -> pd.DataFrame:
        """读 md_reference legend_config → 图例 DataFrame。"""
        conn = _db.get_connection(self.db_path)
        try:
            header_row = conn.execute(
                "SELECT extra FROM md_reference "
                "WHERE data_type = 'legend_config' AND code = '__header__'"
            ).fetchone()

            if header_row:
                columns = list(json.loads(header_row['extra']).values())
            else:
                sample = conn.execute(
                    "SELECT extra FROM md_reference "
                    "WHERE data_type = 'legend_config' AND enabled = 1 LIMIT 1"
                ).fetchone()
                if not sample or not sample['extra']:
                    return pd.DataFrame()
                columns = list(json.loads(sample['extra']).keys())

            rows = conn.execute(
                "SELECT code, label, extra FROM md_reference "
                "WHERE data_type = 'legend_config' AND enabled = 1 "
                "ORDER BY sort_order, code"
            ).fetchall()

            data = []
            for r in rows:
                extra = json.loads(r['extra']) if r['extra'] else {}
                row_data = {col: extra.get(col, '') for col in columns}
                data.append(row_data)

            return pd.DataFrame(data, columns=columns)
        finally:
            conn.close()

    # ============================================================
    # 内部工具
    # ============================================================

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
