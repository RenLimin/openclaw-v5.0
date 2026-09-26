# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""ProjectValidator — 项目数据导入校验器。

继承 BaseImporter，提供：
- 单行数据校验
- 批量校验 + 错误持久化
- 唯一性、外键、日期、金额等校验规则
"""
from __future__ import annotations

import csv
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bdms.core.db import get_connection, transaction
from bdms.modules.base import BaseImporter, ValidationError

from .engine import ProjectEngine


class ProjectValidator(BaseImporter):
    """项目数据导入校验器。"""

    def __init__(self):
        self.engine = ProjectEngine()

    # ========================================================
    # 单行校验
    # ========================================================

    def validate_row(self, row: Dict[str, Any]) -> List[Dict[str, Any]]:
        """校验单行项目数据。

        校验规则：
        1. 项目号唯一
        2. 合同号存在（如果提供了 contract_no）
        3. 开始日期 ≤ 结束日期
        4. PM 必填
        5. 金额 > 0
        6. 日期格式正确

        Args:
            row: 项目数据行

        Returns:
            错误列表，每项: {field, error_message}
        """
        errors: List[Dict[str, Any]] = []

        # 1. 项目号（必填 + 格式 + 唯一性）
        project_no = str(row.get("project_no", "")).strip()
        if not project_no:
            errors.append({"field": "project_no", "error_message": "项目号不能为空"})
        else:
            # 唯一性校验
            conn = get_connection()
            existing = conn.execute(
                "SELECT id FROM pm_projects WHERE project_no = ? AND deleted_at IS NULL",
                (project_no,)
            ).fetchone()
            if existing:
                errors.append({"field": "project_no", "error_message": f"项目号已存在: {project_no}"})

        # 2. 项目名称必填
        project_name = str(row.get("project_name", "")).strip()
        if not project_name:
            errors.append({"field": "project_name", "error_message": "项目名称不能为空"})

        # 3. PM 必填
        pm = str(row.get("pm", "")).strip()
        if not pm:
            errors.append({"field": "pm", "error_message": "项目经理(PM)不能为空"})

        # 4. 金额 > 0
        budget = row.get("budget", row.get("amount", 0))
        try:
            budget_val = float(budget) if budget else 0.0
            if budget_val <= 0:
                errors.append({"field": "budget", "error_message": "项目金额必须大于 0"})
        except (ValueError, TypeError):
            errors.append({"field": "budget", "error_message": f"金额格式无效: {budget}"})

        # 5. 日期校验
        start_date = str(row.get("start_date", "")).strip()
        end_date = str(row.get("end_date", "")).strip()

        if start_date:
            if not self._is_valid_date(start_date):
                errors.append({"field": "start_date", "error_message": f"开始日期格式无效: {start_date}（应为 YYYY-MM-DD）"})

        if end_date:
            if not self._is_valid_date(end_date):
                errors.append({"field": "end_date", "error_message": f"结束日期格式无效: {end_date}（应为 YYYY-MM-DD）"})

        if start_date and end_date and self._is_valid_date(start_date) and self._is_valid_date(end_date):
            if start_date > end_date:
                errors.append({"field": "end_date", "error_message": "结束日期不能早于开始日期"})

        # 6. 合同号存在性（如果提供）
        contract_no = str(row.get("contract_no", "")).strip()
        if contract_no:
            conn = get_connection()
            contract = conn.execute(
                "SELECT id FROM cr_contracts WHERE contract_no = ? AND deleted_at IS NULL",
                (contract_no,)
            ).fetchone()
            if not contract:
                errors.append({"field": "contract_no", "error_message": f"合同号不存在: {contract_no}"})

        return errors

    def _is_valid_date(self, date_str: str) -> bool:
        """检查日期格式是否为 YYYY-MM-DD。"""
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    # ========================================================
    # 批量校验 + 错误持久化
    # ========================================================

    def validate_batch(
        self,
        rows: List[Dict[str, Any]],
        module: str = "project_management",
        persist_errors: bool = True,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """批量校验项目数据。

        Args:
            rows: 数据行列表
            module: 模块名
            persist_errors: 是否持久化错误到 sys_import_errors 表

        Returns:
            (all_errors_list, batch_no)
        """
        batch_no = f"IMP-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        all_errors: List[Dict[str, Any]] = []

        for row_idx, row in enumerate(rows, start=1):
            row_errors = self.validate_row(row)
            for err in row_errors:
                error_entry = {
                    "row_index": row_idx,
                    "field_name": err["field"],
                    "error_message": err["error_message"],
                    "row_data": json.dumps(row, ensure_ascii=False, default=str),
                }
                all_errors.append(error_entry)

        if persist_errors and all_errors:
            self._persist_errors(batch_no, module, all_errors)

        return all_errors, batch_no

    def _persist_errors(
        self,
        batch_no: str,
        module: str,
        errors: List[Dict[str, Any]],
    ) -> None:
        """将错误持久化到 sys_import_errors 表。"""
        conn = get_connection()
        with transaction():
            for err in errors:
                conn.execute(
                    """INSERT INTO sys_import_errors
                       (batch_no, module, row_index, field_name, error_message, row_data)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        batch_no,
                        module,
                        err.get("row_index", 0),
                        err.get("field_name", ""),
                        err.get("error_message", ""),
                        err.get("row_data", ""),
                    )
                )

    def get_errors_by_batch(self, batch_no: str) -> List[Dict[str, Any]]:
        """按批次号查询导入错误。"""
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM sys_import_errors WHERE batch_no = ? ORDER BY row_index, id",
            (batch_no,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ========================================================
    # 从文件导入（BaseImporter 接口）
    # ========================================================

    def import_from_file(self, file_path: str, **kwargs) -> List[Dict[str, Any]]:
        """从 CSV 文件导入项目数据（先校验后导入）。

        CSV 表头：
        project_no,project_name,project_type,dept,pm,contract_no,start_date,end_date,budget

        Returns:
            导入结果列表: [{row, success, project_id?, errors?}]
        """
        path = Path(file_path)
        if not path.exists():
            raise ValidationError(f"File not found: {file_path}")

        rows = []
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(dict(row))

        # 先批量校验
        errors, batch_no = self.validate_batch(rows)
        if errors:
            return [
                {"row": e["row_index"], "success": False,
                 "field": e["field_name"], "error": e["error_message"]}
                for e in errors
            ]

        # 校验通过，批量导入
        results = []
        with transaction():
            for row_idx, row in enumerate(rows, start=1):
                try:
                    # 解析 contract_id
                    contract_id = None
                    contract_no = str(row.get("contract_no", "")).strip()
                    if contract_no:
                        conn = get_connection()
                        c = conn.execute(
                            "SELECT id FROM cr_contracts WHERE contract_no = ? AND deleted_at IS NULL",
                            (contract_no,)
                        ).fetchone()
                        if c:
                            contract_id = c["id"]

                    project_id = self.engine.create_project(
                        project_name=str(row.get("project_name", "")).strip(),
                        project_no=str(row.get("project_no", "")).strip() or None,
                        project_type=str(row.get("project_type", "")).strip(),
                        dept=str(row.get("dept", "")).strip(),
                        pm=str(row.get("pm", "")).strip(),
                        contract_id=contract_id,
                        start_date=str(row.get("start_date", "")).strip() or None,
                        end_date=str(row.get("end_date", "")).strip() or None,
                        budget=float(row.get("budget", 0) or 0),
                        created_by=kwargs.get("created_by", "import"),
                    )
                    results.append({"row": row_idx, "success": True, "project_id": project_id})
                except Exception as e:
                    results.append({"row": row_idx, "success": False, "error": str(e)})

        return results
