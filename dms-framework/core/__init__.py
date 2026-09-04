"""
core — DMS Framework 核心引擎
交付管理框架的核心层：模块注册、状态机、RACI、工作流方案、事件总线、CLI、数据库、SaaS。

所有 L4 业务系统只需要从 core 导入以下公开 API 即可。
"""
from __future__ import annotations

# 模块系统
from .module import (
    BaseModule,
    CommandDef,
    ModuleManifest,
    ModuleRegistry,
)

# 状态机
from .state_machine import (
    EntityState,
    State,
    StateMachine,
    StateMachineEngine,
    Transition,
)

# RACI
from .raci import (
    Assignment,
    CAPABILITY_ATOMS,
    CAPABILITY_LABELS,
    Conflict,
    Gap,
    RACI_LABELS,
    ROLE_LABELS,
    ROLE_TEMPLATES,
    RACIEngine,
)

# 工作流方案
from .workflow_scheme import (
    AGILE_SCHEME,
    DEFAULT_SCHEME,
    WATERFALL_SCHEME,
    WorkflowScheme,
    WorkflowSchemeEngine,
)

# 事件总线
from .event_bus import (
    Event,
    EventBus,
)

# CLI
from .cli import (
    CLICommand,
    CLIFramework,
)

# 数据库
from .database import (
    BaseModel,
    Database,
    Migration,
    MigrationManager,
    Repository,
)

# SaaS
from .saas import (
    AuthProvider,
    AuthResult,
    RouteDef,
    RouteRegistry,
    TenantContext,
    TenantRouter,
)


__all__ = [
    # module
    "BaseModule",
    "CommandDef",
    "ModuleManifest",
    "ModuleRegistry",
    # state_machine
    "EntityState",
    "State",
    "StateMachine",
    "StateMachineEngine",
    "Transition",
    # raci
    "Assignment",
    "CAPABILITY_ATOMS",
    "CAPABILITY_LABELS",
    "Conflict",
    "Gap",
    "RACI_LABELS",
    "ROLE_LABELS",
    "ROLE_TEMPLATES",
    "RACIEngine",
    # workflow_scheme
    "AGILE_SCHEME",
    "DEFAULT_SCHEME",
    "WATERFALL_SCHEME",
    "WorkflowScheme",
    "WorkflowSchemeEngine",
    # event_bus
    "Event",
    "EventBus",
    # cli
    "CLICommand",
    "CLIFramework",
    # database
    "BaseModel",
    "Database",
    "Migration",
    "MigrationManager",
    "Repository",
    # saas
    "AuthProvider",
    "AuthResult",
    "RouteDef",
    "RouteRegistry",
    "TenantContext",
    "TenantRouter",
]
