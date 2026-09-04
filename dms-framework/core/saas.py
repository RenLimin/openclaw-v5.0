"""
core/saas.py — SaaS 基础设施
租户上下文 + 认证接口 + 租户路由 + API 路由定义。
"""
from __future__ import annotations

import contextvars
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# TenantContext — 线程本地租户上下文
# ---------------------------------------------------------------------------

class TenantContext:
    """租户上下文（线程 + 协程安全）。

    用 contextvars.ContextVar 保证每个执行上下文有独立的 tenant_id，
    兼容 threading.local（同步）和 asyncio（异步）两种场景。
    默认值 "system" 用于系统级操作（如迁移、初始化）。

    典型用法:
        with TenantContext.scope("tenant_123"):
            # 这里所有操作都在 tenant_123 上下文中
            repo.list()
    """

    _var: contextvars.ContextVar[str] = contextvars.ContextVar(
        "tenant_id", default="system"
    )

    @classmethod
    def set(cls, tenant_id: str) -> None:
        if not tenant_id or not isinstance(tenant_id, str):
            raise ValueError("tenant_id must be a non-empty string")
        cls._var.set(tenant_id)

    @classmethod
    def current(cls) -> str:
        return cls._var.get()

    @classmethod
    def reset(cls) -> None:
        cls._var.set("system")

    @classmethod
    def scope(cls, tenant_id: str) -> "_TenantScope":
        """上下文管理器：进入时设置 tenant_id，退出时恢复原值。"""
        return _TenantScope(tenant_id)


class _TenantScope:
    def __init__(self, tenant_id: str) -> None:
        self._new = tenant_id
        self._token: contextvars.Token[str] | None = None

    def __enter__(self) -> None:
        self._token = TenantContext._var.set(self._new)

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._token is not None:
            TenantContext._var.reset(self._token)


# ---------------------------------------------------------------------------
# AuthResult — 认证结果
# ---------------------------------------------------------------------------

@dataclass
class AuthResult:
    """认证结果。"""

    success: bool
    user_id: str = ""
    tenant_id: str = ""
    roles: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    error: str = ""

    def __bool__(self) -> bool:
        return self.success


# ---------------------------------------------------------------------------
# AuthProvider — 认证提供者接口
# ---------------------------------------------------------------------------

class AuthProvider(ABC):
    """认证提供者接口。L4 业务系统实现此接口。

    框架本身不实现具体认证方式，只定义契约。
    L4 可以用 JWT / Session / API Key / OAuth 等任意方式。
    """

    @abstractmethod
    def authenticate(self, credentials: dict[str, Any]) -> AuthResult:
        """验证凭据，返回认证结果。

        credentials 示例:
        - {"username": "...", "password": "..."}
        - {"token": "..."}
        - {"api_key": "..."}
        """
        ...

    @abstractmethod
    def authorize(self, user_id: str, resource: str, action: str) -> bool:
        """检查用户是否有权对资源执行操作。

        resource: 资源标识，如 "project:123" / "deliverable:*"
        action: 操作类型，如 "read" / "write" / "delete" / "approve"
        """
        ...

    @abstractmethod
    def get_tenant(self, user_id: str) -> str:
        """获取用户所属的 tenant_id。"""
        ...


# ---------------------------------------------------------------------------
# 租户等级
# ---------------------------------------------------------------------------

TENANT_TIERS = {"free", "business", "enterprise"}


# ---------------------------------------------------------------------------
# TenantRouter — 租户路由（混合多租户）
# ---------------------------------------------------------------------------

class TenantRouter:
    """租户路由：混合多租户策略。

    默认共享数据库（所有租户在同一个 DB，用 tenant_id 隔离）。
    L4 可以覆盖为独立数据库模式（每个租户一个 DB），或混合模式。

    设计为接口形式，L4 实现具体路由逻辑。
    """

    def __init__(self, shared_db: Any = None) -> None:
        self._shared_db = shared_db
        self._dedicated: dict[str, Any] = {}  # tenant_id -> db connection
        self._tiers: dict[str, str] = {}  # tenant_id -> tier

    def get_connection(self, tenant_id: str) -> Any:
        """获取租户对应的数据库连接。

        默认实现：所有租户共享一个数据库。
        L4 可覆盖此方法实现独立数据库模式。
        """
        if tenant_id in self._dedicated:
            return self._dedicated[tenant_id]
        return self._shared_db

    def get_tenant_tier(self, tenant_id: str) -> str:
        """获取租户等级：free | business | enterprise。"""
        return self._tiers.get(tenant_id, "free")

    def set_tenant_tier(self, tenant_id: str, tier: str) -> None:
        if tier not in TENANT_TIERS:
            raise ValueError(f"Invalid tier: {tier}, must be one of {TENANT_TIERS}")
        self._tiers[tenant_id] = tier

    def register_dedicated_db(self, tenant_id: str, db: Any) -> None:
        """为指定租户注册独立数据库。"""
        self._dedicated[tenant_id] = db

    def is_dedicated(self, tenant_id: str) -> bool:
        return tenant_id in self._dedicated


# ---------------------------------------------------------------------------
# RouteDef — API 路由定义
# ---------------------------------------------------------------------------

@dataclass
class RouteDef:
    """API 路由定义。

    模块通过 RouteDef 声明自己的 API 端点。
    L4 可以将其绑定到 FastAPI / Flask / aiohttp 等具体框架。

    handler 格式: "module_name.command_name" 或直接是可调用对象
    """

    path: str
    method: str  # GET / POST / PUT / DELETE / PATCH
    handler: str  # "module.command" 格式的引用
    auth_required: bool = True
    rate_limit: str | None = None  # 如 "100/minute" / "1000/hour"
    description: str = ""
    request_schema: dict[str, Any] = field(default_factory=dict)
    response_schema: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.method.upper() not in {"GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"}:
            raise ValueError(f"Invalid HTTP method: {self.method}")
        if not self.path.startswith("/"):
            raise ValueError(f"Route path must start with '/': {self.path}")
        # handler 必须是 module.command 格式
        parts = self.handler.split(".")
        if len(parts) != 2:
            raise ValueError(f"Handler must be 'module.command' format: {self.handler}")


# ---------------------------------------------------------------------------
# RouteRegistry — 路由注册表
# ---------------------------------------------------------------------------

class RouteRegistry:
    """API 路由注册表。模块注册自己的路由，L4 统一绑定。"""

    def __init__(self) -> None:
        self._routes: list[RouteDef] = []
        self._by_path: dict[tuple[str, str], RouteDef] = {}  # (method, path) -> route

    def register(self, route: RouteDef) -> None:
        key = (route.method.upper(), route.path)
        if key in self._by_path:
            raise ValueError(f"Route already registered: {route.method} {route.path}")
        self._routes.append(route)
        self._by_path[key] = route

    def list_routes(self) -> list[RouteDef]:
        return list(self._routes)

    def find(self, method: str, path: str) -> Optional[RouteDef]:
        return self._by_path.get((method.upper(), path))

    def by_tag(self, tag: str) -> list[RouteDef]:
        return [r for r in self._routes if tag in r.tags]

    def by_module(self, module_name: str) -> list[RouteDef]:
        return [r for r in self._routes if r.handler.startswith(f"{module_name}.")]
