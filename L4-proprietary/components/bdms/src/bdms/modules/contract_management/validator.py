"""合同导入校验器 — ContractValidator。

🔒 NO_TOKEN — 纯代码，零 AI 依赖。

继承 BaseValidator，实现合同批量导入的校验规则：
  - 合同号必填且唯一
  - 客户名必填（party_b）
  - 金额 > 0
  - 签约日期 ≤ 生效日期
  - 合同类型枚举校验

校验结果持久化到 cr_import_validation 表，
支持错误列表查询、人工校正、批量校验。
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Optional
from datetime import datetime

from bdms.modules.base import BaseValidator
from bdms.core import db as _db

from .models import CONTRACT_STATUSES


# ─── 校验规则编码 ───

class ContractValidationRule:
    """校验规则编码常量。"""
    CONTRACT_NO_REQUIRED = "CR-V001"
    CONTRACT_NO_UNIQUE = "CR-V002"
    PARTY_B_REQUIRED = "CR-V003"
    AMOUNT_POSITIVE = "CR-V004"
    DATE_ORDER = "CR-V005"
    CONTRACT_TYPE_ENUM = "CR-V006"
    TITLE_REQUIRED = "CR-V007"
    EFFECTIVE_DATE_FORMAT = "CR-V008"
    SIGN_DATE_FORMAT = "CR-V009"


VALID_CONTRACT_TYPES = {
    "software_license", "service", "framework", "nda",
    "maintenance", "consulting", "outsourcing", "custom_dev",
}


class ContractValidator(BaseValidator):
    """合同导入校验器。

    校验结果写入 cr_import_validation 表。
    """

    module_name = "contract_management"
    validation_table = "cr_import_validation"

    # ========================================================
    # BaseValidator 接口实现
    # ========================================================

    def validate_row(
        self,
        sheet: str,
        row: dict[str, Any],
        row_index: int,
    ) -> list[dict[str, Any]]:
        """校验单行合同数据。

        Args:
            sheet: Sheet 名称
            row: 行数据字典
            row_index: 行序号

        Returns:
            错误列表（空列表表示通过）
        """
        errors: list[dict[str, Any]] = []

        # V001: 合同号必填
        contract_no = (row.get("contract_no") or "").strip()
        if not contract_no:
            errors.append(self._make_error(
                ContractValidationRule.CONTRACT_NO_REQUIRED,
                "ERROR",
                "合同号不能为空",
                "contract_no",
                "",
            ))

        # V007: 合同名称必填
        title = (row.get("title") or "").strip()
        if not title:
            errors.append(self._make_error(
                ContractValidationRule.TITLE_REQUIRED,
                "ERROR",
                "合同名称不能为空",
                "title",
                "",
            ))

        # V003: 客户名（乙方）必填
        party_b = (row.get("party_b") or "").strip()
        if not party_b:
            errors.append(self._make_error(
                ContractValidationRule.PARTY_B_REQUIRED,
                "ERROR",
                "客户名称（乙方）不能为空",
                "party_b",
                "",
            ))

        # V004: 金额 > 0
        try:
            amount = float(row.get("amount", 0) or 0)
            if amount <= 0:
                errors.append(self._make_error(
                    ContractValidationRule.AMOUNT_POSITIVE,
                    "ERROR",
                    f"合同金额必须大于 0，当前值: {amount}",
                    "amount",
                    str(row.get("amount", "")),
                ))
        except (ValueError, TypeError):
            errors.append(self._make_error(
                ContractValidationRule.AMOUNT_POSITIVE,
                "ERROR",
                f"合同金额格式无效: {row.get('amount', '')}",
                "amount",
                str(row.get("amount", "")),
            ))
            amount = 0

        # V006: 合同类型枚举校验
        contract_type = (row.get("contract_type") or "").strip()
        if contract_type and contract_type not in VALID_CONTRACT_TYPES:
            errors.append(self._make_error(
                ContractValidationRule.CONTRACT_TYPE_ENUM,
                "WARNING",
                f"合同类型 '{contract_type}' 不在枚举范围内，有效值: {sorted(VALID_CONTRACT_TYPES)}",
                "contract_type",
                contract_type,
            ))

        # V005: 签约日期 ≤ 生效日期
        sign_date = (row.get("signed_date") or row.get("sign_date") or "").strip()
        effective_date = (row.get("effective_date") or "").strip()

        if sign_date and effective_date:
            try:
                sign_dt = datetime.strptime(sign_date[:10], "%Y-%m-%d")
                eff_dt = datetime.strptime(effective_date[:10], "%Y-%m-%d")
                if sign_dt > eff_dt:
                    errors.append(self._make_error(
                        ContractValidationRule.DATE_ORDER,
                        "ERROR",
                        f"签约日期 ({sign_date}) 不能晚于生效日期 ({effective_date})",
                        "signed_date",
                        sign_date,
                    ))
            except ValueError:
                # 日期格式有问题
                errors.append(self._make_error(
                    ContractValidationRule.SIGN_DATE_FORMAT,
                    "WARNING",
                    f"签约日期格式无效: {sign_date}，应为 YYYY-MM-DD",
                    "signed_date",
                    sign_date,
                ))

        elif effective_date and not sign_date:
            pass  # 只有生效日期没问题
        elif sign_date and not effective_date:
            pass  # 只有签约日期也没问题

        return errors

    def validate_batch(
        self,
        sheet: str,
        rows: list[dict[str, Any]],
        month: str,
    ) -> dict[str, Any]:
        """批量校验合同数据。

        除了逐行校验，还会检查合同号的批量唯一性。

        Args:
            sheet: Sheet 名称
            rows: 数据行列表
            month: 月份（批次标识）

        Returns:
            {
                "batch_no": str,
                "sheet": str,
                "month": str,
                "total_rows": int,
                "error_count": int,
                "warning_count": int,
                "results": list[dict],
            }
        """
        batch_no = f"CR-IMP-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        all_results: list[dict[str, Any]] = []
        error_count = 0
        warning_count = 0

        # 逐行校验
        seen_contract_nos: dict[str, list[int]] = {}
        for i, row in enumerate(rows):
            row_idx = i + 1
            row_errors = self.validate_row(sheet, row, row_idx)

            # 记录合同号用于批量去重检查
            contract_no = (row.get("contract_no") or "").strip()
            if contract_no:
                seen_contract_nos.setdefault(contract_no, []).append(row_idx)

            for err in row_errors:
                err["row_index"] = row_idx
                err["sheet_name"] = sheet
                err["batch_no"] = batch_no
                all_results.append(err)
                if err["severity"] == "ERROR":
                    error_count += 1
                else:
                    warning_count += 1

        # V002: 批量内合同号唯一性检查
        for contract_no, row_indices in seen_contract_nos.items():
            if len(row_indices) > 1:
                for ridx in row_indices:
                    err = self._make_error(
                        ContractValidationRule.CONTRACT_NO_UNIQUE,
                        "ERROR",
                        f"合同号 '{contract_no}' 在导入文件中重复出现（行: {row_indices}）",
                        "contract_no",
                        contract_no,
                    )
                    err["row_index"] = ridx
                    err["sheet_name"] = sheet
                    err["batch_no"] = batch_no
                    all_results.append(err)
                    error_count += 1

        # 按行号排序
        all_results.sort(key=lambda e: e.get("row_index", 0))

        return {
            "batch_no": batch_no,
            "sheet": sheet,
            "month": month,
            "total_rows": len(rows),
            "error_count": error_count,
            "warning_count": warning_count,
            "results": all_results,
        }

    def persist_validation_results(
        self,
        month: str,
        results: dict[str, Any],
    ) -> int:
        """将校验结果写入 cr_import_validation 表。

        Args:
            month: 月份
            results: validate_batch 返回的结果字典

        Returns:
            写入的记录数
        """
        conn = self._get_conn()
        try:
            count = 0
            batch_no = results.get("batch_no", "")
            for err in results.get("results", []):
                conn.execute(
                    """INSERT INTO cr_import_validation
                       (batch_no, row_index, sheet_name, rule_code, severity,
                        column_name, original_value, message, status, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', datetime('now', 'localtime'))""",
                    (
                        batch_no,
                        err.get("row_index", 0),
                        err.get("sheet_name", "contracts"),
                        err.get("rule_code", ""),
                        err.get("severity", "ERROR"),
                        err.get("column_name", ""),
                        str(err.get("original_value", "")),
                        err.get("message", ""),
                    ),
                )
                count += 1
            conn.commit()
            return count
        finally:
            conn.close()

    # ========================================================
    # 查询接口
    # ========================================================

    def list_pending(
        self,
        month: str = None,
        severity: Optional[str] = None,
        batch_no: str = None,
    ) -> list[dict[str, Any]]:
        """列出待处理的校验问题。

        Args:
            month: 月份（可选）
            severity: 按严重程度过滤（ERROR/WARNING），None 表示全部
            batch_no: 批次号（可选）

        Returns:
            待处理问题列表
        """
        conn = self._get_conn()
        try:
            conditions = ["status = 'pending'"]
            params: list = []
            if severity:
                conditions.append("severity = ?")
                params.append(severity)
            if batch_no:
                conditions.append("batch_no = ?")
                params.append(batch_no)
            where = " AND ".join(conditions)

            rows = conn.execute(
                f"""SELECT * FROM cr_import_validation
                    WHERE {where}
                    ORDER BY batch_no, row_index, id""",
                params,
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def apply_manual_correction(
        self,
        validation_id: int,
        corrected_value: str,
        operator: str = "",
    ) -> dict[str, Any]:
        """应用人工校正单条记录。

        Args:
            validation_id: 校验记录 ID
            corrected_value: 校正后的值
            operator: 操作人

        Returns:
            {"updated": bool, "id": int}
        """
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM cr_import_validation WHERE id = ?",
                (validation_id,),
            ).fetchone()
            if not row:
                return {"updated": False, "id": validation_id, "reason": "not_found"}

            conn.execute(
                """UPDATE cr_import_validation
                   SET corrected_value = ?, corrected_by = ?,
                       corrected_at = datetime('now', 'localtime'),
                       status = 'corrected'
                   WHERE id = ?""",
                (corrected_value, operator, validation_id),
            )
            conn.commit()
            return {"updated": True, "id": validation_id}
        finally:
            conn.close()

    def get_batch_summary(self, batch_no: str) -> dict[str, Any]:
        """获取批次校验汇总。

        Args:
            batch_no: 批次号

        Returns:
            {batch_no, total_errors, total_warnings, by_rule, pending_count, corrected_count}
        """
        conn = self._get_conn()
        try:
            # 按严重程度统计
            sev_rows = conn.execute(
                """SELECT severity, COUNT(*) as cnt FROM cr_import_validation
                   WHERE batch_no = ? GROUP BY severity""",
                (batch_no,),
            ).fetchall()
            by_severity = {r["severity"]: r["cnt"] for r in sev_rows}

            # 按状态统计
            status_rows = conn.execute(
                """SELECT status, COUNT(*) as cnt FROM cr_import_validation
                   WHERE batch_no = ? GROUP BY status""",
                (batch_no,),
            ).fetchall()
            by_status = {r["status"]: r["cnt"] for r in status_rows}

            # 按规则统计
            rule_rows = conn.execute(
                """SELECT rule_code, COUNT(*) as cnt FROM cr_import_validation
                   WHERE batch_no = ? GROUP BY rule_code ORDER BY cnt DESC""",
                (batch_no,),
            ).fetchall()
            by_rule = {r["rule_code"]: r["cnt"] for r in rule_rows}

            return {
                "batch_no": batch_no,
                "total_errors": by_severity.get("ERROR", 0),
                "total_warnings": by_severity.get("WARNING", 0),
                "by_severity": by_severity,
                "by_status": by_status,
                "by_rule": by_rule,
                "pending_count": by_status.get("pending", 0),
                "corrected_count": by_status.get("corrected", 0),
                "ignored_count": by_status.get("ignored", 0),
            }
        finally:
            conn.close()
