# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""ProjectManagementRBACService — 带 RBAC 权限检查的项目管理服务。

在 ProjectManagementService 的基础上，通过 require_permission 装饰器
为每个方法添加权限校验。

权限清单：
- pm_view: 查看项目列表、详情、仪表盘
- pm_create: 创建项目
- pm_edit: 更新项目、启动、交付、验收、取消、重新激活
- pm_delete: 删除项目
- pm_approve: 结项审批
- pm_export: 导出项目数据
- pm_after_sales: 售后管理（移交售后、工单操作）
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from bdms.modules.base import BaseService

from .engine import ProjectEngine
from .security import PMPermission, require_permission
from .service import ProjectManagementService


class ProjectManagementRBACService(BaseService):
    """带 RBAC 权限检查的项目管理服务。

    所有方法都通过 require_permission 装饰器保护。
    """

    def __init__(self):
        self._inner = ProjectManagementService()
        self.project_engine = ProjectEngine()

    @property
    def inner(self) -> ProjectManagementService:
        """获取内部服务实例（绕过权限检查时用，需谨慎）。"""
        return self._inner

    # ========================================================
    # 查看类（pm_view）
    # ========================================================

    @require_permission(PMPermission.PM_VIEW)
    def get_project_detail(self, project_id: int) -> Dict[str, Any]:
        return self._inner.get_project_detail(project_id)

    @require_permission(PMPermission.PM_VIEW)
    def list_projects(self, **kwargs) -> Tuple[List[Dict[str, Any]], int]:
        return self._inner.list_projects(**kwargs)

    @require_permission(PMPermission.PM_VIEW)
    def get_project_dashboard(self, project_id: int) -> Dict[str, Any]:
        return self._inner.get_project_dashboard(project_id)

    # ========================================================
    # 创建类（pm_create）
    # ========================================================

    @require_permission(PMPermission.PM_CREATE)
    def create_project(self, **kwargs) -> int:
        return self._inner.create_project(**kwargs)

    # ========================================================
    # 编辑类（pm_edit）
    # ========================================================

    @require_permission(PMPermission.PM_EDIT)
    def start_project(self, project_id: int, **kwargs) -> None:
        return self._inner.start_project(project_id, **kwargs)

    @require_permission(PMPermission.PM_EDIT)
    def submit_delivery(self, **kwargs) -> int:
        return self._inner.submit_delivery(**kwargs)

    @require_permission(PMPermission.PM_EDIT)
    def accept_project(self, **kwargs) -> None:
        return self._inner.accept_project(**kwargs)

    @require_permission(PMPermission.PM_EDIT)
    def cancel_project(self, **kwargs) -> None:
        return self._inner.cancel_project(**kwargs)

    @require_permission(PMPermission.PM_EDIT)
    def reactivate_project(self, **kwargs) -> None:
        return self._inner.reactivate_project(**kwargs)

    # ========================================================
    # 删除类（pm_delete）
    # ========================================================

    @require_permission(PMPermission.PM_DELETE)
    def delete_project(self, project_id: int, **kwargs) -> None:
        return self.project_engine.delete_project(project_id, **kwargs)

    # ========================================================
    # 审批类（pm_approve）
    # ========================================================

    @require_permission(PMPermission.PM_APPROVE)
    def close_project(self, **kwargs) -> None:
        return self._inner.close_project(**kwargs)

    # ========================================================
    # 导出类（pm_export）
    # ========================================================

    @require_permission(PMPermission.PM_EXPORT)
    def export_projects(self, **kwargs) -> str:
        from .exporter import ProjectExporter
        exporter = ProjectExporter()
        return exporter.export_projects_csv(**kwargs)

    # ========================================================
    # 售后类（pm_after_sales）
    # ========================================================

    @require_permission(PMPermission.PM_AFTER_SALES)
    def transfer_to_after_sales(self, **kwargs) -> None:
        return self._inner.transfer_to_after_sales(**kwargs)
