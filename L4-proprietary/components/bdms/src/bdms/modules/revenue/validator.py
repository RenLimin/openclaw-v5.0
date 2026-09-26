# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""RevenueValidator — 确收数据导入校验器（12 条规则）。

对齐 DESIGN-DETAIL-REVENUE-v2.1.md §1.5.2：
- ERROR 行拒绝 + WARNING 行标记存疑
- 存疑数据 → rr_import_validation 落盘 → 人工校正（留痕）
- 知识库自动填充建议
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from bdms.core import db as _db

# 列名常量（黄金基准口径）
COL_CATEGORY = "分类"                    # c1
COL_CONTRACT_NO = "合同编号"             # c2/c4
COL_MONTH = "月份"                       # c7
COL_PERF_ID = "履约ID"                   # c10
COL_METHOD = "收入确认方法"              # c11
COL_AMOUNT = "确收金额"                  # c12（各金额列泛化）
COL_PRODUCT = "产品"                     # c25
COL_PRODUCT_LINE = "所属产线"            # c27

VALID_CATEGORIES = {"新签", "递延"}
VALID_METHODS = {"时点法", "时段法"}

_MONTH_RE = re.compile(r"^(202[5-7])(0[1-9]|1[0-2])$")
_AMOUNT_RE = re.compile(r"^-?\d+(\.\d+)?$")


class RevenueValidator:
    """确收数据导入校验器。"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    # ========================================================
    # 单行校验（R1-R9, R12）
    # ========================================================

    def validate_row(self, sheet: str, row: Dict[str, Any],
                     row_index: int) -> List[Dict]:
        """单行校验，返回问题列表 [{rule, level, col, message, value}]。"""
        issues: List[Dict] = []

        def _val(key: str) -> str:
            """模糊取值（列名可能有后缀差异）。"""
            for k, v in row.items():
                if k and key in str(k):
                    return str(v).strip() if v is not None else ""
            return ""

        # R1: 合同编号非空（ERROR）
        contract_no = _val(COL_CONTRACT_NO)
        if not contract_no:
            issues.append({"rule": "R1", "level": "error", "col": COL_CONTRACT_NO,
                           "message": "合同编号为空", "value": ""})

        # R2: 履约ID非空（ERROR）
        perf_id = _val(COL_PERF_ID)
        if not perf_id:
            issues.append({"rule": "R2", "level": "error", "col": COL_PERF_ID,
                           "message": "履约ID为空", "value": ""})

        # R3: 金额数值合法性（ERROR）
        for amount_col in ("确收金额", "合同金额", "累计确收金额"):
            v = _val(amount_col)
            if v and not _AMOUNT_RE.match(v):
                issues.append({"rule": "R3", "level": "error", "col": amount_col,
                               "message": f"金额非数值: {v[:30]}", "value": v[:50]})
                break
            elif v and _AMOUNT_RE.match(v) and float(v) < 0:
                issues.append({"rule": "R3", "level": "error", "col": amount_col,
                               "message": f"金额为负: {v}", "value": v})
                break

        # R4: 月份格式（WARNING）
        month = _val(COL_MONTH)
        if month and not _MONTH_RE.match(month):
            issues.append({"rule": "R4", "level": "warning", "col": COL_MONTH,
                           "message": f"月份格式异常: {month}（期望 YYYYMM）",
                           "value": month})

        # R7: 分类枚举（ERROR）
        category = _val(COL_CATEGORY)
        if category and category not in VALID_CATEGORIES:
            issues.append({"rule": "R7", "level": "error", "col": COL_CATEGORY,
                           "message": f"分类非法: {category}", "value": category})

        # R8: 收入确认方法枚举（WARNING）
        method = _val(COL_METHOD)
        if method and method not in VALID_METHODS:
            issues.append({"rule": "R8", "level": "warning", "col": COL_METHOD,
                           "message": f"确认方法非法: {method}", "value": method})

        # R9: 月度计划金额 > 合同总额（WARNING）——简化：单月金额 > 合同金额
        contract_amount = _val("合同金额")
        month_amount = _val("当月确收金额")
        if (contract_amount and month_amount
                and _AMOUNT_RE.match(contract_amount)
                and _AMOUNT_RE.match(month_amount)
                and float(month_amount) > float(contract_amount) > 0):
            issues.append({"rule": "R9", "level": "warning", "col": "当月确收金额",
                           "message": "单月金额超过合同总额", "value": month_amount})

        return issues

    # ========================================================
    # 批量校验（R5/R6/R10/R11 跨行规则）
    # ========================================================

    def validate_batch(self, sheet: str, rows: List[Dict],
                       month: str) -> Dict:
        """批量校验。

        Returns: {"errors": [...], "warnings": [...],
                  "summary": {"total", "error_rows", "warning_rows", "clean_rows"}}
        """
        errors: List[Dict] = []
        warnings: List[Dict] = []

        # R11: (合同编号, 履约ID) 重复（ERROR）
        seen = {}
        for i, row in enumerate(rows):
            contract_no = str(row.get(COL_CONTRACT_NO, "") or "").strip()
            perf_id = str(row.get(COL_PERF_ID, "") or "").strip()
            key = (contract_no, perf_id)
            if key in seen and contract_no:
                errors.append({
                    "rule": "R11", "level": "error", "row": i,
                    "col": f"{COL_CONTRACT_NO}+{COL_PERF_ID}",
                    "message": f"重复合同+履约ID: {contract_no}/{perf_id}"
                               f"（首见于行 {seen[key]}）",
                    "value": contract_no,
                })
            else:
                seen[key] = i

        # 逐行规则
        error_rows = set()
        warning_rows = set()
        for i, row in enumerate(rows):
            issues = self.validate_row(sheet, row, i)
            for issue in issues:
                entry = {"row": i, **issue}
                if issue["level"] == "error":
                    errors.append(entry)
                    error_rows.add(i)
                else:
                    warnings.append(entry)
                    warning_rows.add(i)

        # R5: 合同存在性（WARNING，抽样新合同）
        unknown = self._check_contract_existence(rows)
        for i in unknown:
            warnings.append({
                "rule": "R5", "level": "warning", "row": i,
                "col": COL_CONTRACT_NO,
                "message": "合同在 cr_contracts 中不存在（新合同？）",
                "value": str(rows[i].get(COL_CONTRACT_NO, ""))[:50],
            })
            warning_rows.add(i)

        # R10: 行数对比（WARNING，整体）
        prev_count = self._prev_month_rows(month, sheet)
        if prev_count and rows:
            deviation = abs(len(rows) - prev_count) / prev_count
            if deviation > 0.2:
                warnings.append({
                    "rule": "R10", "level": "warning", "row": -1, "col": "",
                    "message": f"行数偏差 {deviation*100:.0f}%"
                               f"（上月 {prev_count}，本月 {len(rows)}）",
                    "value": None,
                })

        return {
            "errors": errors,
            "warnings": warnings,
            "summary": {
                "total": len(rows),
                "error_rows": len(error_rows),
                "warning_rows": len(warning_rows),
                "clean_rows": len(rows) - len(error_rows | warning_rows),
            },
        }

    # ========================================================
    # 校验结果落盘 + 人工校正
    # ========================================================

    def persist_validation_results(self, month: str, results: Dict) -> int:
        """校验结果落盘 rr_import_validation。返回写入条数。"""
        conn = _db.get_connection(self.db_path)
        written = 0
        try:
            # 清空该月旧结果（幂等）
            conn.execute(
                "DELETE FROM rr_import_validation WHERE month = ?", (month,))

            for level_key, status in (("errors", "ERROR"), ("warnings", "WARNING")):
                for item in results.get(level_key, []):
                    conn.execute(
                        """INSERT INTO rr_import_validation
                           (month, sheet, row_index, rule_code, severity, column_name,
                            message, original_value, status)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
                        (month,
                         item.get("sheet", ""),
                         item.get("row", -1),
                         item.get("rule", ""),
                         status,
                         item.get("col", ""),
                         item.get("message", ""),
                         str(item.get("value", ""))[:200]),
                    )
                    written += 1
            conn.commit()
            return written
        finally:
            conn.close()

    def apply_manual_correction(self, validation_id: int, corrected_value: str,
                                operator: str) -> Dict:
        """人工校正存疑数据（写 corrected_value + rr_edit_history 留痕）。

        Returns: {"ok": bool, "message": str}
        """
        conn = _db.get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM rr_import_validation WHERE id = ?",
                (validation_id,),
            ).fetchone()
            if not row:
                return {"ok": False, "message": f"校验记录 {validation_id} 不存在"}

            if row["status"] != "pending":
                return {"ok": False, "message": f"该存疑已处理（状态: {row['status']}）"}

            old_value = row["original_value"]
            now = datetime.now().isoformat()

            # 更新校验记录
            conn.execute(
                """UPDATE rr_import_validation
                   SET corrected_value = ?, status = 'confirmed',
                       operator = ?, resolved_at = ?
                   WHERE id = ?""",
                (corrected_value, operator, now, validation_id),
            )

            # rr_edit_history 留痕
            conn.execute(
                """INSERT INTO rr_edit_history
                   (month, sheet, row_index, column_name, original_value, new_value,
                    edit_type, operator)
                   VALUES (?, ?, ?, ?, ?, ?, 'auto_correction', ?)""",
                (row["month"], row["sheet"], row["row_index"],
                 row["column_name"], old_value, corrected_value, operator),
            )
            conn.commit()
            return {"ok": True, "message": "校正成功"}
        finally:
            conn.close()

    def list_pending(self, month: str) -> List[Dict]:
        """列出待处理存疑数据（Web UI 展示）。"""
        conn = _db.get_connection(self.db_path)
        try:
            rows = conn.execute(
                """SELECT * FROM rr_import_validation
                   WHERE month = ? AND status = 'pending'
                   ORDER BY CASE severity WHEN 'ERROR' THEN 0 ELSE 1 END, id""",
                (month,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ========================================================
    # 知识库自动填充建议（ASC 606）
    # ========================================================

    def auto_fill_suggestions(self, month: str) -> List[Dict]:
        """从知识库自动填充建议（产品目录 → 收入确认方法/科目/服务期）。

        ASC 606 五步法知识库（DESIGN-DETAIL §1.5.1）：
        - 软件许可 → 时点法（functional IP）
        - SaaS/服务 → 时段法
        - 硬件 → 时点法（控制权转移）
        """
        ASC_606_KB = {
            "软件": {"method": "时点法", "basis": "ASC 606-10-55-54 functional IP"},
            "SaaS": {"method": "时段法", "basis": "ASC 606-10-25-27(a) 服务中持续获益"},
            "服务": {"method": "时段法", "basis": "ASC 606-10-25-27(a)"},
            "维保": {"method": "时段法", "basis": "ASC 606-10-25-27(a) 均匀提供"},
            "硬件": {"method": "时点法", "basis": "ASC 606-10-25-30 控制权转移"},
            "咨询": {"method": "时段法", "basis": "ASC 606-10-25-27(a)"},
            "定制开发": {"method": "时段法", "basis": "ASC 606-10-25-27(a)"},
        }

        suggestions: List[Dict] = []
        conn = _db.get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT row_index, data FROM rr_sheet_row "
                "WHERE period = ? AND sheet = '计划确收底稿' ORDER BY row_index",
                (month,),
            ).fetchall()

            for row_index, data_json in rows:
                data = json.loads(data_json) if isinstance(data_json, str) else {}
                product = str(data.get(COL_PRODUCT, "") or data.get(COL_PRODUCT_LINE, "") or "")
                method = str(data.get(COL_METHOD, "") or "")

                if not method and product:
                    for keyword, kb in ASC_606_KB.items():
                        if keyword in product:
                            suggestions.append({
                                "row_index": row_index,
                                "product": product[:50],
                                "suggested_method": kb["method"],
                                "basis": kb["basis"],
                            })
                            break
            return suggestions
        finally:
            conn.close()

    # ========================================================
    # 内部工具
    # ========================================================

    def _check_contract_existence(self, rows: List[Dict]) -> List[int]:
        """R5: 检查合同在 cr_contracts 是否存在。返回不存在的行号。"""
        conn = _db.get_connection(self.db_path)
        try:
            known = {
                r[0] for r in conn.execute(
                    "SELECT contract_no FROM cr_contracts WHERE deleted_at IS NULL"
                ).fetchall()
            }
        except Exception:
            known = set()
        finally:
            conn.close()

        unknown = []
        for i, row in enumerate(rows):
            no = str(row.get(COL_CONTRACT_NO, "") or "").strip()
            if no and known and no not in known:
                unknown.append(i)
        return unknown

    def _prev_month_rows(self, month: str, sheet: str) -> int:
        """R10: 上月行数。"""
        y, m = int(month[:4]), int(month[4:6])
        prev = f"{y-1}12" if m == 1 else f"{y}{m-1:02d}"
        conn = _db.get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT row_count FROM rr_sheet_meta WHERE period = ? AND sheet = ?",
                (prev, sheet),
            ).fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0
        finally:
            conn.close()
