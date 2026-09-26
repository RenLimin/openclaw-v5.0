# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""ProjectExporter — 项目数据导出器。

支持导出：
- 项目列表 Excel/CSV（含实施字段）
- 导出字段：项目号、名称、客户、合同号、PM、金额、状态、实施负责人、实施状态、开始/结束日期
"""
from __future__ import annotations

import csv
import io
from typing import Any, Dict, List, Optional, Tuple

from bdms.core.db import get_connection
from bdms.modules.base import BaseExporter

from .engine import ProjectEngine


class ProjectExporter(BaseExporter):
    """项目导出器。"""

    EXPORT_COLUMNS = [
        ("project_no", "项目号"),
        ("project_name", "项目名称"),
        ("customer", "客户"),  # 从项目名/部门推断，或使用 customer 字段
        ("contract_no", "合同号"),
        ("pm", "项目经理"),
        ("budget", "项目金额"),
        ("status", "项目状态"),
        ("impl_owner", "实施负责人"),
        ("impl_status", "实施状态"),
        ("start_date", "开始日期"),
        ("end_date", "结束日期"),
        ("impl_start_date", "实施开始日期"),
        ("impl_end_date", "实施结束日期"),
    ]

    def __init__(self):
        self.engine = ProjectEngine()

    def export_projects_csv(self, **filters) -> str:
        """导出项目列表为 CSV 字符串。

        导出字段：项目号、名称、客户、合同号、PM、金额、状态、
                   实施负责人、实施状态、开始/结束日期
        """
        # 获取项目列表
        projects, _ = self.engine.list_projects(page_size=10000, **filters)

        # 获取合同号映射
        project_ids = [p["id"] for p in projects if p.get("contract_id")]
        contract_map = {}
        if project_ids:
            conn = get_connection()
            placeholders = ",".join(["?"] * len(project_ids))
            rows = conn.execute(
                f"""SELECT p.id as project_id, c.contract_no
                    FROM pm_projects p
                    LEFT JOIN cr_contracts c ON p.contract_id = c.id
                    WHERE p.id IN ({placeholders})""",
                project_ids
            ).fetchall()
            contract_map = {r["project_id"]: r["contract_no"] for r in rows if r["contract_no"]}

        output = io.StringIO()
        writer = csv.writer(output)

        # 表头
        writer.writerow([
            "项目号", "项目名称", "客户", "合同号", "项目经理",
            "项目金额", "项目状态", "实施负责人", "实施状态",
            "开始日期", "结束日期", "实施开始日期", "实施结束日期"
        ])

        # 状态中文映射
        status_map = {
            "initiating": "立项中",
            "planning": "规划中",
            "executing": "执行中",
            "delivering": "交付中",
            "accepting": "验收中",
            "closing": "结项中",
            "closed": "已结项",
            "after_sales": "售后维保中",
            "cancelled": "已取消",
        }

        impl_status_map = {
            "not_started": "未开始",
            "in_progress": "进行中",
            "delayed": "延期",
            "completed": "已完成",
        }

        for p in projects:
            contract_no = contract_map.get(p["id"], "")
            status = status_map.get(p.get("status", ""), p.get("status", ""))
            impl_status = impl_status_map.get(
                p.get("impl_status", ""), p.get("impl_status", "")
            )
            # 客户字段：优先 dept 或 project_type（模拟客户信息）
            customer = p.get("dept", "")

            writer.writerow([
                p.get("project_no", ""),
                p.get("project_name", ""),
                customer,
                contract_no,
                p.get("pm", ""),
                p.get("budget", 0),
                status,
                p.get("impl_owner", ""),
                impl_status,
                p.get("start_date", ""),
                p.get("end_date", ""),
                p.get("impl_start_date", ""),
                p.get("impl_end_date", ""),
            ])

        return output.getvalue()

    def export_projects_dict(self, **filters) -> List[Dict[str, Any]]:
        """导出项目列表为字典列表（用于后续处理）。"""
        projects, _ = self.engine.list_projects(page_size=10000, **filters)
        return projects
