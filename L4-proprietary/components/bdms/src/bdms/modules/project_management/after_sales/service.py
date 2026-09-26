# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""AfterSalesService — 售后服务层。

职责：
- 售后移交（项目 → 售后）
- 工单全生命周期编排
- SLA 管理
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from bdms.core.db import transaction
from bdms.modules.base import BaseService

from .engine import AfterSalesEngine


class AfterSalesService(BaseService):
    """售后服务层：售后移交 + 工单全生命周期 + SLA 管理。"""

    def __init__(self):
        self.engine = AfterSalesEngine()

    # ========================================================
    # 售后移交
    # ========================================================

    def transfer_to_after_sales(
        self,
        project_id: int,
        warranty_period_months: int = 12,
        service_level: str = "silver",
        customer_contact: str = "",
        customer_phone: str = "",
        remaining_tickets: int = 0,
    ) -> int:
        """项目结项后转入售后维保。

        创建维保合同，设置服务等级与质保期。

        Returns:
            warranty_contract_id
        """
        # 检查是否已有 active 维保合同
        existing = self.engine.get_warranty_by_project(project_id)
        if existing:
            # 已有维保合同，返回现有 ID（幂等）
            return existing["id"]

        with transaction():
            contract_id = self.engine.create_warranty_contract(
                project_id=project_id,
                warranty_period_months=warranty_period_months,
                service_level=service_level,
                customer_contact=customer_contact,
                customer_phone=customer_phone,
                remaining_tickets=remaining_tickets,
            )

        return contract_id

    # ========================================================
    # 工单生命周期
    # ========================================================

    def create_ticket(self, **kwargs) -> int:
        """创建售后工单。"""
        return self.engine.create_ticket(**kwargs)

    def assign_ticket(self, **kwargs) -> None:
        """分派工单。"""
        self.engine.assign_ticket(**kwargs)

    def start_ticket(self, ticket_id: int, operator: str) -> None:
        """开始处理工单。"""
        self.engine.start_ticket(ticket_id, operator)

    def resolve_ticket(self, **kwargs) -> None:
        """解决工单。"""
        self.engine.resolve_ticket(**kwargs)

    def close_ticket(self, **kwargs) -> None:
        """关闭工单。"""
        self.engine.close_ticket(**kwargs)

    def reopen_ticket(self, **kwargs) -> None:
        """重新打开工单。"""
        self.engine.reopen_ticket(**kwargs)

    def get_ticket(self, ticket_id: int) -> Dict[str, Any]:
        """获取工单详情（含 SLA 状态）。"""
        return self.engine.get_ticket(ticket_id)

    def list_tickets(self, **kwargs) -> Tuple[List[Dict[str, Any]], int]:
        """查询工单列表。"""
        return self.engine.list_tickets(**kwargs)

    def update_ticket(self, ticket_id: int, **kwargs) -> None:
        """更新工单信息。"""
        self.engine.update_ticket(ticket_id, **kwargs)

    def delete_ticket(self, ticket_id: int, operator: str = "system") -> None:
        """删除工单（软删除）。"""
        self.engine.delete_ticket(ticket_id, operator)

    # ========================================================
    # SLA 统计
    # ========================================================

    def get_sla_summary(self, **kwargs) -> Dict[str, Any]:
        """获取 SLA 统计概览。"""
        return self.engine.get_sla_summary(**kwargs)

    def get_overdue_tickets(self, **kwargs) -> List[Dict[str, Any]]:
        """获取超期工单列表。"""
        # 先列出所有未关闭工单，再过滤 SLA 超时的
        tickets, _ = self.engine.list_tickets(
            state="in_progress", page_size=1000, **kwargs
        )
        overdue = []
        for t in tickets:
            sla = self.engine._calculate_sla_status(t)
            if sla["is_overdue_response"] or sla["is_overdue_resolution"]:
                t["sla"] = sla
                overdue.append(t)
        return overdue

    # ========================================================
    # 维保合同
    # ========================================================

    def get_warranty(self, project_id: int) -> Optional[Dict[str, Any]]:
        """获取项目维保合同。"""
        return self.engine.get_warranty_by_project(project_id)
