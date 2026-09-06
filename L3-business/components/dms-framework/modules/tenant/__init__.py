"""modules/tenant — 租户管理模块。

提供租户 CRUD + 租户级配置 + 模块开关。
表：tenants, tenant_config
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from core.database import BaseModel, Database, Repository
from core.module import BaseModule, CommandDef, ModuleManifest
from core.saas import TenantContext, TENANT_TIERS


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class Tenant(BaseModel):
    """租户模型。"""
    name: str = ""
    slug: str = ""  # URL 友好标识
    tier: str = "free"  # free | business | enterprise
    status: str = "active"  # active | suspended | cancelled
    contact_email: str = ""
    max_projects: int = 10
    max_users: int = 5
    metadata: str = ""
    __tablename__ = "tenants"


# ---------------------------------------------------------------------------
# 模块实现
# ---------------------------------------------------------------------------


class TenantModule(BaseModule):
    """租户管理模块。"""

    def initialize(self, db: Database, config: dict[str, Any], container: Any) -> None:
        self._db = db
        self._config = config
        self._container = container
        self._repo: Repository[Tenant] = Repository(db, Tenant, "tenants")

    def on_ready(self, container: Any) -> None:
        pass

    # -- CRUD --

    def create_tenant(
        self,
        name: str,
        slug: str = "",
        tier: str = "free",
        contact_email: str = "",
        max_projects: int = 10,
        max_users: int = 5,
    ) -> Tenant:
        """创建租户。"""
        if not slug:
            slug = name.lower().replace(" ", "-")
        if tier not in TENANT_TIERS:
            raise ValueError(f"Invalid tier: {tier}")
        t = Tenant(
            id=str(uuid.uuid4()),
            tenant_id="system",  # tenant 表自身用 system
            name=name, slug=slug, tier=tier,
            contact_email=contact_email,
            max_projects=max_projects, max_users=max_users,
        )
        self._repo.add(t)
        return t

    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        return self._repo.get(tenant_id)

    def get_tenant_by_slug(self, slug: str) -> Optional[Tenant]:
        results = self._repo.list(slug=slug)
        return results[0] if results else None

    def list_tenants(self, **filters) -> list[Tenant]:
        return self._repo.list(**filters)

    def update_tenant(self, tenant_id: str, **kwargs) -> Optional[Tenant]:
        t = self._repo.get(tenant_id)
        if not t:
            return None
        for k, v in kwargs.items():
            if hasattr(t, k):
                setattr(t, k, v)
        t.updated_at = datetime.now(timezone.utc).isoformat()
        self._repo.add(t)
        return t

    def delete_tenant(self, tenant_id: str) -> bool:
        t = self._repo.get(tenant_id)
        if not t:
            return False
        self._repo.delete(tenant_id)
        return True

    # -- 配额检查 --

    def check_quota(self, tenant_id: str, resource: str, current_count: int) -> dict[str, Any]:
        """检查租户配额。"""
        t = self._repo.get(tenant_id)
        if not t:
            return {"allowed": False, "reason": "Tenant not found"}

        limits = {
            "projects": t.max_projects,
            "users": t.max_users,
        }
        limit = limits.get(resource, 999)
        return {
            "allowed": current_count < limit,
            "limit": limit,
            "current": current_count,
            "remaining": max(0, limit - current_count),
        }


# ---------------------------------------------------------------------------
# Manifest + Factory
# ---------------------------------------------------------------------------

manifest = ModuleManifest(
    name="tenant",
    version="1.0.0",
    description="租户管理 — CRUD + 配额 + 模块开关",
    dependencies=[],
    tables=["tenants", "tenant_config"],
    commands=[
        CommandDef(name="tenant create", help="创建租户",
                   handler=lambda args, ctx: print("dms tenant create")),
        CommandDef(name="tenant list", help="列出租户",
                   handler=lambda args, ctx: print("dms tenant list")),
        CommandDef(name="tenant get", help="查看租户",
                   handler=lambda args, ctx: print("dms tenant get")),
    ],
)


def _factory(m: ModuleManifest) -> TenantModule:
    return TenantModule(m)
