# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""AfterSalesExporter — 售后数据导出器。

支持导出：
- 工单列表（CSV）
- SLA 统计报表（CSV）
"""
from __future__ import annotations

import csv
import io
from typing import Any, Dict, List

from bdms.modules.base import BaseExporter

from .engine import AfterSalesEngine


class AfterSalesExporter(BaseExporter):
    """售后导出器。"""

    def __init__(self):
        self.engine = AfterSalesEngine()

    def export_tickets_csv(self, **filters) -> str:
        """导出工单列表为 CSV 字符串。"""
        tickets, _ = self.engine.list_tickets(page_size=10000, **filters)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "工单号", "标题", "状态", "优先级", "服务等级", "来源",
            "关联项目", "客户名称", "客户联系人", "联系电话",
            "指派工程师", "创建时间", "响应时间", "解决时间", "关闭时间",
            "响应截止", "解决截止", "解决方案", "解决类型"
        ])

        for t in tickets:
            writer.writerow([
                t.get("ticket_no", ""),
                t.get("title", ""),
                t.get("state", ""),
                t.get("priority", ""),
                t.get("service_level", ""),
                t.get("source", ""),
                t.get("project_id", ""),
                t.get("customer_name", ""),
                t.get("customer_contact", ""),
                t.get("customer_phone", ""),
                t.get("assignee", ""),
                t.get("created_at", ""),
                t.get("response_at", ""),
                t.get("resolved_at", ""),
                t.get("closed_at", ""),
                t.get("response_deadline", ""),
                t.get("resolution_deadline", ""),
                t.get("resolution", ""),
                t.get("resolution_type", ""),
            ])

        return output.getvalue()

    def export_sla_summary_csv(self, **kwargs) -> str:
        """导出 SLA 统计报表为 CSV 字符串。"""
        summary = self.engine.get_sla_summary(**kwargs)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["指标", "值"])
        writer.writerow(["总工单数", summary["total_tickets"]])
        writer.writerow(["响应 SLA 达标率 (%)", summary["response_sla_rate"]])
        writer.writerow(["解决 SLA 达标率 (%)", summary["resolution_sla_rate"]])
        writer.writerow(["平均响应时间 (小时)", summary["avg_response_time_hours"]])
        writer.writerow(["平均解决时间 (小时)", summary["avg_resolution_time_hours"]])
        writer.writerow(["响应超期工单数", summary["overdue_response"]])
        writer.writerow(["解决超期工单数", summary["overdue_resolution"]])

        return output.getvalue()
