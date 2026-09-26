# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""项目管理模块 RBAC 权限系统。

定义：
- 角色（Role）：pm / pmo / tech / gm
- 权限（Permission）：pm_view / pm_create / pm_edit / pm_delete / pm_approve / pm_export / pm_after_sales
- require_permission 装饰器
"""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Set

from bdms.modules.base import PermissionError


# ============================================================
# 权限定义
# ============================================================

class PMPermission:
    """项目管理权限常量。"""
    PM_VIEW = "pm_view"              # 查看项目
    PM_CREATE = "pm_create"          # 创建项目
    PM_EDIT = "pm_edit"              # 编辑项目
    PM_DELETE = "pm_delete"          # 删除项目
    PM_APPROVE = "pm_approve"        # 审批项目
    PM_EXPORT = "pm_export"          # 导出项目
    PM_AFTER_SALES = "pm_after_sales"  # 售后管理


ALL_PM_PERMISSIONS: List[str] = [
    PMPermission.PM_VIEW,
    PMPermission.PM_CREATE,
    PMPermission.PM_EDIT,
    PMPermission.PM_DELETE,
    PMPermission.PM_APPROVE,
    PMPermission.PM_EXPORT,
    PMPermission.PM_AFTER_SALES,
]


# ============================================================
# 角色定义
# ============================================================

class PMRole:
    """项目管理角色常量。"""
    PM = "pm"              # 项目经理
    PMO = "pmo"            # PMO
    TECH = "tech"          # 技术
    GM = "gm"              # 总经理


# 角色 -> 权限集 映射
ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    PMRole.PM: {
        PMPermission.PM_VIEW,
        PMPermission.PM_CREATE,
        PMPermission.PM_EDIT,
        PMPermission.PM_EXPORT,
        PMPermission.PM_AFTER_SALES,
    },
    PMRole.PMO: {
        PMPermission.PM_VIEW,
        PMPermission.PM_CREATE,
        PMPermission.PM_EDIT,
        PMPermission.PM_DELETE,
        PMPermission.PM_APPROVE,
        PMPermission.PM_EXPORT,
        PMPermission.PM_AFTER_SALES,
    },
    PMRole.TECH: {
        PMPermission.PM_VIEW,
        PMPermission.PM_AFTER_SALES,
    },
    PMRole.GM: {
        PMPermission.PM_VIEW,
        PMPermission.PM_CREATE,
        PMPermission.PM_EDIT,
        PMPermission.PM_DELETE,
        PMPermission.PM_APPROVE,
        PMPermission.PM_EXPORT,
        PMPermission.PM_AFTER_SALES,
    },
}


# ============================================================
# 权限上下文（线程本地）
# ============================================================

import threading
_thread_local = threading.local()


def set_current_user(user_id: str, roles: List[str]) -> None:
    """设置当前用户（用于权限校验）。"""
    _thread_local.user_id = user_id
    _thread_local.roles = set(roles)
    # 计算权限集
    perms: Set[str] = set()
    for role in roles:
        perms.update(ROLE_PERMISSIONS.get(role, set()))
    _thread_local.permissions = perms


def get_current_user() -> Optional[str]:
    """获取当前用户 ID。"""
    return getattr(_thread_local, "user_id", None)


def get_current_roles() -> Set[str]:
    """获取当前用户角色。"""
    return getattr(_thread_local, "roles", set())


def get_current_permissions() -> Set[str]:
    """获取当前用户权限集。"""
    return getattr(_thread_local, "permissions", set())


def has_permission(permission: str) -> bool:
    """检查当前用户是否有指定权限。"""
    return permission in get_current_permissions()


def require_permission(permission: str) -> Callable:
    """权限检查装饰器。

    用法::

        @require_permission(PMPermission.PM_VIEW)
        def get_project(self, project_id):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not has_permission(permission):
                raise PermissionError(
                    f"Permission denied: '{permission}'. "
                    f"User roles: {get_current_roles()}"
                )
            return func(*args, **kwargs)
        return wrapper
    return decorator


def clear_current_user() -> None:
    """清除当前用户上下文（测试用）。"""
    if hasattr(_thread_local, "user_id"):
        del _thread_local.user_id
    if hasattr(_thread_local, "roles"):
        del _thread_local.roles
    if hasattr(_thread_local, "permissions"):
        del _thread_local.permissions
