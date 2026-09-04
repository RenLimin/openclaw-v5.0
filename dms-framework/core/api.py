"""
core/api.py — FastAPI 应用工厂
自动从 ModuleRegistry 生成 CRUD REST 路由 + 认证 + 租户中间件。
"""
from __future__ import annotations

import json
from typing import Any, Callable, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, create_model

from core.auth import TokenData, create_access_token, get_current_user
from core.module import ModuleRegistry
from core.saas import TenantContext

# ---------------------------------------------------------------------------
# 应用状态（依赖注入）
# ---------------------------------------------------------------------------


class AppState:
    """FastAPI 应用的全局状态。"""

    def __init__(self, registry: ModuleRegistry, db: Any, config: dict[str, Any]) -> None:
        self.registry = registry
        self.db = db
        self.config = config


# ---------------------------------------------------------------------------
# Pydantic 模型生成
# ---------------------------------------------------------------------------


def _snake_to_camel(name: str) -> str:
    """snake_case → camelCase"""
    parts = name.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


def _to_pydantic_model(dataclass_type: type, name: str = "") -> type[BaseModel]:
    """将 dataclass 类型转换为 Pydantic BaseModel。

    用于自动生成请求/响应 schema。
    """
    import dataclasses

    fields = {}
    for f in dataclasses.fields(dataclass_type):
        f_type = f.type
        # 处理 Optional / str | None 等
        if hasattr(f_type, "__origin__"):
            f_type = str | None
        default = f.default if f.default is not dataclasses.MISSING else None
        if default is None and str(f.type).startswith("Optional"):
            fields[f.name] = (f_type | None, None)
        elif default is not dataclasses.MISSING:
            fields[f.name] = (f_type, default)
        else:
            fields[f.name] = (f_type, ...)

    model_name = name or f"{dataclass_type.__name__}Schema"
    return create_model(model_name, **fields)


# ---------------------------------------------------------------------------
# 通用 CRUD 路由生成器
# ---------------------------------------------------------------------------


def _register_crud_routes(
    app: FastAPI,
    module_name: str,
    module_instance: Any,
    app_state: AppState,
) -> None:
    """为单个模块注册通用 CRUD 路由。

    自动生成的端点：
    - GET    /api/v1/{module}         列表
    - POST   /api/v1/{module}         创建
    - GET    /api/v1/{module}/{id}    详情
    - PUT    /api/v1/{module}/{id}    更新
    - DELETE /api/v1/{module}/{id}    删除
    - POST   /api/v1/{module}/{id}/actions/{action}  状态迁移
    """
    prefix = f"/api/v1/{module_name}"

    # ── 列表 ──────────────────────────────────────────────────────────

    @app.get(prefix, tags=[module_name], summary=f"列出 {module_name}")
    async def list_items(
        status_filter: str | None = Query(None, alias="status"),
        current_user: TokenData = Depends(get_current_user),
    ):
        TenantContext.set(current_user.tenant_id)
        # 查找 list 方法
        list_fn = _find_method(module_instance, "list", module_name)
        if not list_fn:
            raise HTTPException(status_code=501, detail=f"Module {module_name} does not support list")
        try:
            items = list_fn(status=status_filter) if status_filter else list_fn()
            return [_serialize(item) for item in items]
        except TypeError:
            items = list_fn()
            return [_serialize(item) for item in items]

    # ── 创建 ──────────────────────────────────────────────────────────

    @app.post(prefix, tags=[module_name], summary=f"创建 {module_name}", status_code=201)
    async def create_item(
        body: dict[str, Any],
        current_user: TokenData = Depends(get_current_user),
    ):
        TenantContext.set(current_user.tenant_id)
        create_fn = _find_method(module_instance, "create", module_name)
        if not create_fn:
            raise HTTPException(status_code=501, detail=f"Module {module_name} does not support create")
        try:
            result = create_fn(**body)
            return _serialize(result)
        except TypeError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # ── 详情 ──────────────────────────────────────────────────────────

    @app.get(f"{prefix}/{{item_id}}", tags=[module_name], summary=f"获取 {module_name} 详情")
    async def get_item(
        item_id: str,
        current_user: TokenData = Depends(get_current_user),
    ):
        TenantContext.set(current_user.tenant_id)
        get_fn = _find_method(module_instance, "get", module_name)
        if not get_fn:
            raise HTTPException(status_code=501, detail=f"Module {module_name} does not support get")
        result = get_fn(item_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"{module_name} not found: {item_id}")
        return _serialize(result)

    # ── 更新 ──────────────────────────────────────────────────────────

    @app.put(f"{prefix}/{{item_id}}", tags=[module_name], summary=f"更新 {module_name}")
    async def update_item(
        item_id: str,
        body: dict[str, Any],
        current_user: TokenData = Depends(get_current_user),
    ):
        TenantContext.set(current_user.tenant_id)
        update_fn = _find_method(module_instance, "update", module_name)
        if not update_fn:
            raise HTTPException(status_code=501, detail=f"Module {module_name} does not support update")
        result = update_fn(item_id, **body)
        if result is None:
            raise HTTPException(status_code=404, detail=f"{module_name} not found: {item_id}")
        return _serialize(result)

    # ── 删除 ──────────────────────────────────────────────────────────

    @app.delete(f"{prefix}/{{item_id}}", tags=[module_name], summary=f"删除 {module_name}")
    async def delete_item(
        item_id: str,
        current_user: TokenData = Depends(get_current_user),
    ):
        TenantContext.set(current_user.tenant_id)
        delete_fn = _find_method(module_instance, "delete", module_name)
        if not delete_fn:
            raise HTTPException(status_code=501, detail=f"Module {module_name} does not support delete")
        result = delete_fn(item_id)
        if not result:
            raise HTTPException(status_code=404, detail=f"{module_name} not found: {item_id}")
        return {"deleted": True, "id": item_id}

    # ── 状态迁移 ──────────────────────────────────────────────────────

    @app.post(f"{prefix}/{{item_id}}/actions/{{action_name}}", tags=[module_name], summary=f"执行 {module_name} 状态迁移")
    async def transition_item(
        item_id: str,
        action_name: str,
        body: dict[str, Any] | None = None,
        current_user: TokenData = Depends(get_current_user),
    ):
        TenantContext.set(current_user.tenant_id)
        transition_fn = _find_method(module_instance, "transition", module_name)
        if not transition_fn:
            raise HTTPException(status_code=501, detail=f"Module {module_name} does not support transitions")
        try:
            kwargs = body or {}
            result = transition_fn(item_id, action_name, **kwargs)
            return _serialize(result)
        except (ValueError, KeyError) as e:
            raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _find_method(instance: Any, action: str, module_name: str) -> Optional[Callable]:
    """在模块实例中查找方法。

    命名约定（自动探测）:
      create → create_{singular}  (e.g. create_project)
      get    → get_{singular}    (e.g. get_project)
      list   → list_{plural}     (e.g. list_projects)
      delete → delete_{singular}  (e.g. delete_project)
      transition → transition_{singular} (e.g. transition_project)
      update → update_{singular}  (e.g. update_project)

    其中 singular = module_name 去掉末尾 's'，plural = module_name。
    优先精确匹配，回退到前缀匹配。
    """
    singular = module_name.rstrip("s")
    plural = module_name

    # 精确候选名（按优先级）
    candidates: list[str] = []
    if action == "list":
        candidates = [f"list_{plural}", f"list_{singular}", "list"]
    elif action == "create":
        candidates = [f"create_{singular}", f"create_{plural}", "create"]
    elif action == "get":
        candidates = [f"get_{singular}", f"get_{plural}", "get"]
    elif action == "delete":
        candidates = [f"delete_{singular}", f"delete_{plural}", "delete"]
    elif action == "transition":
        candidates = [f"transition_{singular}", f"transition_{plural}", "transition"]
    elif action == "update":
        candidates = [f"update_{singular}", f"update_{plural}", "update"]
    else:
        candidates = [f"{action}_{singular}", f"{action}_{plural}", action]

    for name in candidates:
        fn = getattr(instance, name, None)
        if fn and callable(fn):
            return fn

    # 回退：前缀匹配
    prefix = f"{action}_"
    for attr in dir(instance):
        if attr.startswith(prefix) and callable(getattr(instance, attr)):
            return getattr(instance, attr)

    return None


def _serialize(obj: Any) -> dict[str, Any]:
    """将 dataclass / model 实例序列化为 dict。"""
    import dataclasses

    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        d = {}
        for k, v in dataclasses.asdict(obj).items():
            if isinstance(v, str):
                try:
                    d[k] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    d[k] = v
            else:
                d[k] = v
        return d
    if hasattr(obj, "__dict__"):
        return dict(obj.__dict__)
    if isinstance(obj, dict):
        return obj
    return {"value": str(obj)}


# ---------------------------------------------------------------------------
# 应用工厂
# ---------------------------------------------------------------------------


def create_app(
    registry: ModuleRegistry,
    db: Any,
    config: dict[str, Any] | None = None,
    title: str = "DMS Framework API",
    version: str = "1.0.0",
) -> FastAPI:
    """创建 FastAPI 应用。

    1. 初始化所有模块
    2. 注册全局路由（health / auth / modules）
    3. 为每个模块注册 CRUD 路由
    """
    app_state = AppState(registry, db, config or {})

    app = FastAPI(
        title=title,
        version=version,
        description="DMS Framework L3 — 通用交付管理框架 REST API",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS（开发期宽松，L4 收紧）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── 健康检查 ──────────────────────────────────────────────────────

    @app.get("/health", tags=["system"])
    async def health():
        return {
            "status": "ok",
            "modules": len(registry.list_modules()),
            "version": version,
        }

    # ── 认证端点 ──────────────────────────────────────────────────────

    @app.post("/api/v1/auth/login", tags=["auth"], summary="用户登录（用户名密码）")
    async def login(credentials: dict[str, Any]):
        from core.auth import _user_store, create_access_token
        user = _user_store.verify_password(
            credentials.get("username", ""),
            credentials.get("password", ""),
        )
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
        token = create_access_token(
            user_id=user["user_id"],
            tenant_id=user["tenant_id"],
            roles=user["roles"],
        )
        return {
            "access_token": token,
            "token_type": "bearer",
            "user_id": user["user_id"],
            "tenant_id": user["tenant_id"],
            "roles": user["roles"],
        }

    @app.post("/api/v1/auth/api-keys", tags=["auth"], summary="创建 API Key")
    async def create_api_key(
        body: dict[str, Any],
        current_user: TokenData = Depends(get_current_user),
    ):
        from core.auth import _user_store
        raw_key = _user_store.create_api_key(
            user_id=current_user.sub,
            tenant_id=current_user.tenant_id,
            roles=current_user.roles,
            description=body.get("description", ""),
        )
        return {"api_key": raw_key, "description": body.get("description", "")}

    @app.get("/api/v1/auth/me", tags=["auth"], summary="当前用户信息")
    async def me(current_user: TokenData = Depends(get_current_user)):
        return {
            "user_id": current_user.sub,
            "tenant_id": current_user.tenant_id,
            "roles": current_user.roles,
            "permissions": current_user.permissions,
        }

    # ── 模块管理 ──────────────────────────────────────────────────────

    @app.get("/api/v1/modules", tags=["system"], summary="列出所有模块")
    async def list_modules():
        return [
            {
                "name": m.name,
                "version": m.version,
                "description": m.description,
                "dependencies": m.dependencies,
                "tables": m.tables,
            }
            for m in registry.list_modules()
        ]

    # ── 租户管理端点 ────────────────────────────────────────────────

    @app.get("/api/v1/tenants", tags=["tenant"], summary="列出租户")
    async def list_tenants(current_user: TokenData = Depends(get_current_user)):
        if not registry.has_module("tenant"):
            raise HTTPException(status_code=503, detail="Tenant module not available")
        mod = registry.get("tenant")
        tenants = mod.list_tenants()
        return [_serialize(t) for t in tenants]

    @app.post("/api/v1/tenants", tags=["tenant"], summary="创建租户", status_code=201)
    async def create_tenant(
        body: dict[str, Any],
        current_user: TokenData = Depends(get_current_user),
    ):
        if not registry.has_module("tenant"):
            raise HTTPException(status_code=503, detail="Tenant module not available")
        mod = registry.get("tenant")
        t = mod.create_tenant(**body)
        return _serialize(t)

    @app.get("/api/v1/tenants/{tenant_id}", tags=["tenant"], summary="获取租户详情")
    async def get_tenant(
        tenant_id: str,
        current_user: TokenData = Depends(get_current_user),
    ):
        if not registry.has_module("tenant"):
            raise HTTPException(status_code=503, detail="Tenant module not available")
        mod = registry.get("tenant")
        t = mod.get_tenant(tenant_id)
        if not t:
            raise HTTPException(status_code=404, detail="Tenant not found")
        return _serialize(t)

    @app.delete("/api/v1/tenants/{tenant_id}", tags=["tenant"], summary="删除租户")
    async def delete_tenant(
        tenant_id: str,
        current_user: TokenData = Depends(get_current_user),
    ):
        if not registry.has_module("tenant"):
            raise HTTPException(status_code=503, detail="Tenant module not available")
        mod = registry.get("tenant")
        result = mod.delete_tenant(tenant_id)
        if not result:
            raise HTTPException(status_code=404, detail="Tenant not found")
        return {"deleted": True, "id": tenant_id}

    # ── 为每个模块注册 CRUD 路由 ─────────────────────────────────────

    # 确保 migration 已执行 + 模块已初始化
    if not registry.is_initialized:
        from core.migrations import migrate
        migrate(db.connect())
        registry.initialize_all(db, config or {})

    for manifest in registry.list_modules():
        module_instance = registry.get(manifest.name)
        _register_crud_routes(app, manifest.name, module_instance, app_state)

    # ── Web UI ────────────────────────────────────────────────────────
    from core.config import get_config
    _cfg = get_config()
    if _cfg.webui_enabled:
        try:
            from core.webui import register_webui_routes
            register_webui_routes(app, registry, db)
        except Exception as e:
            import logging
            logging.getLogger("dms.api").warning(f"Web UI not loaded: {e}")

    return app
