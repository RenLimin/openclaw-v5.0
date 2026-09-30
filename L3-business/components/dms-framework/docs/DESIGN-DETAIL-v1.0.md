# DMS-Framework — 详细设计文档（DESIGN-DETAIL）

> 版本：v1.0（2026-09-29）
> 层级：L3 通用业务层
> 状态：⏳ 待 Rex 审核

---

## 1. 接口契约

### 1.1 模块注册引擎（core/module.py）

```python
@dataclass
class CommandDef:
    name: str                          # "project create"
    help: str = ""
    handler: Callable[..., None]        # 命令处理函数
    arguments: list[dict[str, Any]]    # argparse 参数定义

@dataclass
class ModuleManifest:
    name: str                          # 模块名（semver x.y.z）
    version: str = "0.1.0"
    description: str = ""
    dependencies: list[str] = []       # 依赖模块名
    commands: list[CommandDef] = []    # 模块提供的 CLI 命令
    tables: list[str] = []             # 模块拥有的数据库表
    events_subscribed: list[str] = []  # 订阅的事件模式
    config_schema: dict[str, Any] = {}
    migrations: list[tuple[str, str]] = []  # (version, description)

class BaseModule(ABC):
    def initialize(self, db, config, container) -> None: ...
    def on_ready(self, container) -> None: ...

class ModuleRegistry:
    def register(manifest, factory) -> None: ...
    def get(name) -> BaseModule: ...
    def list_modules() -> list[ModuleManifest]: ...
    def resolve_dependencies() -> list[str]: ...  # 拓扑排序
    def initialize_all(db, config) -> None: ...
```

### 1.2 事件总线（core/event_bus.py）

```python
@dataclass
class Event:
    name: str                    # 点分路径 "project.created"
    payload: dict[str, Any]      # 事件数据
    timestamp: datetime
    source: str                  # 发出模块
    entity_type: str = ""
    entity_id: str = ""

class EventBus:
    def subscribe(pattern: str, handler: Callable[[Event], None]) -> None: ...
    def unsubscribe(pattern: str, handler: Callable[[Event], None]) -> None: ...
    def publish(name: str, payload: dict, source: str, ...) -> None: ...
    def get_history(entity_type, entity_id, event_pattern, limit) -> list[Event]: ...
    def stats() -> dict[str, int]: ...
```

### 1.3 状态机引擎（core/state_machine.py）

```python
@dataclass
class State:
    name: str                    # 状态名
    category: str                # todo|in_progress|done|cancelled|blocked
    is_start: bool = False
    is_terminal: bool = False
    description: str = ""

@dataclass
class Transition:
    name: str                    # 迁移名
    from_state: str
    to_state: str
    guards: list[Callable[[dict], bool]] = []
    on_enter: list[Callable[[dict], None]] = []
    on_exit: list[Callable[[dict], None]] = []

class StateMachine:
    def add_state(state: State) -> None: ...
    def add_transition(transition: Transition) -> None: ...
    def get_start_state() -> str: ...
    def can_transition(current_state: str, transition_name: str) -> bool: ...
    def get_available_transitions(current_state: str, context: dict) -> list[str]: ...
    def fire(current_state: str, transition_name: str, context: dict) -> tuple[str, str]: ...

class StateMachineEngine:
    def register(name: str, machine: StateMachine) -> None: ...
    def create_entity(entity_type: str, entity_id: str, tenant_id: str) -> EntityState: ...
    def transition(entity_type: str, entity_id: str, action: str, context: dict) -> str: ...
    def get_available_transitions(entity_type: str, entity_id: str, context: dict) -> list[str]: ...
```

### 1.4 RACI 引擎（core/raci.py）

```python
CAPABILITY_ATOMS: list[str]        # 12 个能力原子
ROLE_TEMPLATES: dict[str, list[str]]  # 6 个角色模板
RACI_ROLES = {"R", "A", "C", "I"}

@dataclass
class Assignment:
    project_id: str
    member_id: str
    capability: str
    raci_role: str                 # R|A|C|I
    work_item_id: str | None = None
    role_template: str | None = None
    tenant_id: str = "system"

@dataclass
class Conflict:
    type: str                      # multiple_accountable|no_accountable|raci_mismatch
    project_id: str
    capability: str
    description: str

@dataclass
class Gap:
    project_id: str
    capability: str
    missing_roles: list[str]

class RACIEngine:
    def assign(assignment: Assignment) -> None: ...
    def unassign(assignment: Assignment) -> bool: ...
    def get_assignments(project_id, ...) -> list[Assignment]: ...
    def check_conflicts(project_id: str) -> list[Conflict]: ...
    def validate_coverage(project_id: str, ...) -> list[Gap]: ...
    def get_responsibility_matrix(project_id: str) -> dict: ...
    def assign_by_role(project_id, member_id, role_name, raci_role) -> list[Assignment]: ...
```

### 1.5 数据持久化（core/database.py）

```python
class Database:
    def connect() -> sqlite3.Connection: ...
    def close() -> None: ...
    def set_tenant_context(tenant_id: str) -> None: ...
    def get_current_tenant() -> str: ...
    def execute(sql: str, params: tuple | dict) -> sqlite3.Cursor: ...
    def commit() -> None: ...
    def rollback() -> None: ...

@dataclass
class BaseModel:
    id: str = ""
    tenant_id: str = "system"
    created_at: str = ""
    updated_at: str = ""
    __tablename__: ClassVar[str] = ""
    search_fields: ClassVar[list[str]] = ["title", "name", "description"]
    def save(db: Database) -> None: ...
    def delete(db: Database) -> None: ...
    @classmethod
    def get(cls, db: Database, id: str) -> Optional["BaseModel"]: ...
    @classmethod
    def list(cls, db: Database, *, search, sort_by, sort_order, offset, limit, **filters) -> list: ...
    @classmethod
    def count(cls, db: Database, *, search, **filters) -> int: ...

class Repository(Generic[T]):
    def add(entity: T) -> T: ...
    def get(id: str) -> T | None: ...
    def update(entity: T) -> T: ...
    def delete(id: str) -> bool: ...
    def list(**filters) -> list[T]: ...
    def count(**filters) -> int: ...

class MigrationManager:
    def register(version: str, description: str, up: Callable) -> None: ...
    def get_current_version(db: Database) -> str: ...
    def migrate(db: Database, target: str = "latest") -> None: ...
    def diff(db: Database) -> list[str]: ...
```

### 1.6 SaaS 多租户（core/saas.py）

```python
class TenantContext:
    _var: ContextVar[str]  # 默认 "system"
    @classmethod
    def set(tenant_id: str) -> None: ...
    @classmethod
    def current() -> str: ...
    @classmethod
    def scope(tenant_id: str) -> _TenantScope: ...  # 上下文管理器

@dataclass
class AuthResult:
    success: bool
    user_id: str = ""
    tenant_id: str = ""
    roles: list[str] = []
    permissions: list[str] = []

class AuthProvider(ABC):
    def authenticate(credentials: dict) -> AuthResult: ...
    def authorize(user_id: str, resource: str, action: str) -> bool: ...
    def get_tenant(user_id: str) -> str: ...

class TenantRouter:
    def get_connection(tenant_id: str) -> Any: ...
    def get_tenant_tier(tenant_id: str) -> str: ...
    def set_tenant_tier(tenant_id: str, tier: str) -> None: ...
    def register_dedicated_db(tenant_id: str, db: Any) -> None: ...

@dataclass
class RouteDef:
    path: str
    method: str
    handler: str           # "module.command"
    auth_required: bool = True
    rate_limit: str | None = None
    description: str = ""

class RouteRegistry:
    def register(route: RouteDef) -> None: ...
    def list_routes() -> list[RouteDef]: ...
    def find(method: str, path: str) -> Optional[RouteDef]: ...
```

### 1.7 API 工厂（core/api.py）

```python
class AppState:
    registry: ModuleRegistry
    db: Any
    config: dict[str, Any]

def create_app(
    registry: ModuleRegistry,
    db: Any,
    config: dict[str, Any] | None = None,
    title: str = "DMS Framework API",
    version: str = "1.0.0",
) -> FastAPI: ...
```

---

## 2. 数据模型

### 2.1 基础模型（所有模块继承）

```
BaseModel
├── id: str (UUID, 主键)
├── tenant_id: str (默认 "system")
├── created_at: str (ISO 8601)
└── updated_at: str (ISO 8601)
```

### 2.2 各模块数据模型

| 模块 | 表名 | 核心字段 |
|------|------|---------|
| tenant | `tenants` | id, name, tier, status, config |
| project | `projects` | id, name, description, status, owner_id, start_date, end_date |
| milestone | `milestones` | id, project_id, name, due_date, status |
| deliverable | `deliverables` | id, project_id, name, type, status, accepted_at |
| risk | `risks` | id, project_id, title, probability, impact, status |
| raci | `raci_assignments` | id, project_id, member_id, capability, raci_role |
| quality | `quality_checks` | id, project_id, name, status, score |
| resource | `resources` | id, project_id, name, type, allocation |
| budget | `budgets` | id, project_id, category, planned, actual |
| communication | `communications` | id, project_id, type, content, sent_at |
| contract | `contracts` | id, project_id, title, status, signed_at |
| sla | `sla_items` | id, project_id, metric, target, actual |
| task | `tasks` | id, project_id, title, status, assignee_id |
| issue | `issues` | id, project_id, title, severity, status |
| decision | `decisions` | id, project_id, title, rationale, decided_at |

### 2.3 事件对象

```
Event
├── name: str          # "project.created"
├── payload: dict      # 事件数据
├── timestamp: datetime
├── source: str        # 发出模块
├── entity_type: str   # 关联实体类型
└── entity_id: str     # 关联实体 ID
```

### 2.4 状态机模型

```
StateMachine
├── name: str
├── states: dict[str, State]
│   └── State: name, category, is_start, is_terminal
├── transitions: dict[str, Transition]
│   └── Transition: name, from_state, to_state, guards, on_enter, on_exit
└── _from_index: dict[str, list[str]]

EntityState
├── entity_type: str
├── entity_id: str
├── current_state: str
├── history: list[dict]
└── tenant_id: str
```

### 2.5 RACI 模型

```
Assignment
├── project_id: str
├── member_id: str
├── capability: str     # 12 个能力原子之一
├── raci_role: str      # R|A|C|I
├── work_item_id: str | None
├── role_template: str | None
└── tenant_id: str
```

---

## 3. 技术方案

### 3.1 模块注册与依赖解析

**注册流程**：
1. 模块定义 `ModuleManifest`（name, version, dependencies, commands, tables）
2. 模块定义 factory 函数（接收 manifest，返回 BaseModule 实例）
3. `ModuleRegistry.register(manifest, factory)` 存入内部 dict

**初始化流程**：
1. `resolve_dependencies()` 使用 Kahn 算法拓扑排序
2. 校验所有依赖已注册，检测循环依赖
3. 按拓扑顺序实例化模块，调用 `initialize(db, config, container)`
4. 全部初始化完成后，依次调用 `on_ready(container)`

**生命周期**：
```
register → initialize → on_ready → (运行中) → shutdown
```

### 3.2 事件驱动架构

**发布/订阅**：
- 订阅：`subscribe(pattern, handler)`，pattern 支持 fnmatch 通配符
- 发布：`publish(name, payload, source, entity_type, entity_id)`
- 分发：遍历所有匹配的 handler，单个异常不影响其他

**防递归**：
- 发布中再次发布 → 事件入队
- 当前发布完成后 → 处理队列

**历史记录**：
- 默认保留 10000 条
- 支持按 entity_type / entity_id / event_pattern 过滤

### 3.3 状态机引擎

**定义阶段**：
1. 创建 `StateMachine(name, description)`
2. 添加状态 `add_state(State(name, category, is_start, is_terminal))`
3. 添加迁移 `add_transition(Transition(name, from, to, guards, on_enter, on_exit))`

**执行阶段**：
1. `StateMachineEngine.register(name, machine)` 注册状态机定义
2. `create_entity(type, id, tenant_id)` 创建实体状态（初始化为 start state）
3. `transition(type, id, action, context)` 触发迁移
4. `get_available_transitions(type, id, context)` 查询可用迁移

**迁移执行顺序**：
1. 校验迁移存在且 from_state 匹配
2. 执行所有 guards（全部返回 True 才继续）
3. 执行 on_exit hooks
4. 执行 on_enter hooks
5. 更新 EntityState.current_state
6. 记录历史

### 3.4 RACI 职责引擎

**三层模型**：
1. **能力原子**：12 个最小交付能力单元（scope_management, schedule_management 等）
2. **角色模板**：6 个标准角色（project_manager, delivery_manager 等），每个包含若干能力
3. **项目分配**：Assignment 记录（project + member + capability + raci_role）

**冲突检测规则**：
1. 同一 (work_item, capability) 有多个 A → multiple_accountable
2. 同一 (work_item, capability) 没有 A → no_accountable
3. 同一人在同一 (work_item, capability) 既是 R 又是 A → raci_mismatch

**覆盖验证**：
- 每个 (work_item, capability) 至少有 R 和 A
- 返回 Gap 列表（缺 R 和/或 A 的能力）

### 3.5 数据持久化

**Database 层**：
- 线程安全：thread-local 连接
- 租户上下文：set_tenant_context 注入
- 事务：commit / rollback

**BaseModel 层**：
- 自动时间戳：created_at / updated_at
- 自动 ID：UUID 生成
- 自动 tenant_id：从 Database 获取
- CRUD：save / delete / get / list / count
- 搜索：search_fields 模糊匹配
- 排序：sort_by + sort_order
- 分页：offset + limit

**Repository 层**：
- 泛型封装：对 BaseModel 子类做租户隔离的 CRUD
- 忽略租户查询：get_by_id_ignore_tenant（管理视图）

**MigrationManager 层**：
- 版本化迁移：register(version, description, up)
- 版本追踪：__schema_version 表
- 拓扑排序：按版本号顺序执行
- 租户级迁移：在 TenantContext.scope 内执行

### 3.6 SaaS 多租户

**TenantContext**：
- contextvars.ContextVar 实现线程 + 协程安全
- scope(tenant_id) 上下文管理器
- 默认值 "system"

**TenantRouter**：
- 共享数据库（默认）：所有租户共享一个 DB
- 独立数据库（可扩展）：register_dedicated_db(tenant_id, db)
- 租户等级：free / business / enterprise

**AuthProvider**：
- 接口定义：authenticate / authorize / get_tenant
- L4 实现具体认证方式（JWT / Session / API Key / OAuth）

### 3.7 API 工厂

**create_app 流程**：
1. 创建 AppState（registry, db, config）
2. 创建 FastAPI 实例
3. 添加 CORS 中间件
4. 注册全局路由：
   - `/api/v1` → 重定向到 /docs
   - `/health` → 健康检查
   - `/api/v1/auth/login` → 用户登录
   - `/api/v1/auth/api-keys` → API Key 管理
   - `/api/v1/auth/me` → 当前用户
   - `/api/v1/modules` → 模块列表
   - `/api/v1/tenants` → 租户管理
5. 初始化模块 + 执行迁移
6. 遍历模块，注册 CRUD 路由：
   - GET/POST `/api/v1/{module}` → 列表/创建
   - GET/PUT/DELETE `/api/v1/{module}/{id}` → 详情/更新/删除
   - POST `/api/v1/{module}/{id}/actions/{action}` → 状态迁移
   - POST/DELETE `/api/v1/{module}/batch` → 批量操作
7. 注册 Web UI（可选）

**自动方法发现**：
- 命名约定：`create_{singular}`, `get_{singular}`, `list_{plural}`, `delete_{singular}`, `transition_{singular}`, `update_{singular}`
- 回退：前缀匹配

---

## 4. 目录结构

```
dms-framework/
├── dms.py                      # CLI 统一入口
├── dms_api.py                  # API 入口
├── core/                       # 框架引擎
│   ├── __init__.py
│   ├── module.py               # ModuleRegistry + ModuleManifest
│   ├── state_machine.py        # 状态机引擎
│   ├── raci.py                 # RACI 职责引擎
│   ├── workflow_scheme.py      # 流程方案引擎
│   ├── event_bus.py            # 事件总线
│   ├── cli.py                  # CLI 框架
│   ├── database.py             # BaseModel + Repository + 迁移
│   ├── saas.py                 # TenantContext + AuthProvider + TenantRouter
│   ├── api.py                  # API 框架
│   ├── webui.py                # Web UI 引擎
│   ├── config.py               # 配置管理
│   ├── auth.py                 # JWT 认证
│   └── migrations.py           # DDL 迁移脚本
├── modules/                    # 业务模块
│   ├── tenant/                 # 租户管理
│   ├── project/                # 项目管理
│   ├── milestone/              # 里程碑
│   ├── deliverable/            # 交付物
│   ├── risk/                   # 风险
│   ├── raci/                   # RACI 管理
│   ├── quality/                # 质量
│   ├── resource/               # 资源
│   ├── budget/                 # 预算
│   ├── communication/          # 沟通
│   ├── contract/               # 合同
│   ├── sla/                    # SLA
│   ├── task/                   # 任务
│   ├── issue/                  # 问题
│   └── decision/               # 决策
├── templates/                  # Web 模板（Jinja2）
├── static/                     # 静态资源
├── tests/                      # 单元 + 集成测试
│   ├── test_core.py            # 核心引擎测试
│   ├── test_core_boundary.py   # 边界测试
│   ├── test_modules.py         # 模块测试
│   ├── test_integration.py     # 集成测试
│   ├── test_api.py             # API 测试
│   ├── test_config.py          # 配置测试
│   ├── test_webui.py           # Web UI 测试
│   └── test_*.py               # 各模块测试
└── docs/                       # 文档
    ├── PRD-v1.0.md
    ├── DESIGN-OUTLINE-v1.0.md
    ├── DESIGN-DETAIL-v1.0.md
    ├── VERIFICATION-v1.0.md
    └── OPERATIONS-v1.0.md
```

---

## 5. 依赖清单

| 依赖 | 版本 | 用途 | 必需 |
|------|------|------|------|
| Python | 3.10+ | 运行时 | ✅ |
| SQLite | 内置 | 默认数据库 | ✅ |
| FastAPI | 0.100+ | REST API | ✅ |
| Pydantic | 2.0+ | 数据校验 | ✅ |
| Jinja2 | 3.0+ | Web 模板 | ✅ |
| uvicorn | 0.20+ | ASGI 服务器 | ✅ |
| python-jose | 3.3+ | JWT 认证 | ✅ |
| passlib | 1.7+ | 密码哈希 | ✅ |
| pytest | 7.0+ | 测试框架 | ✅ |
| httpx | 0.25+ | HTTP 客户端（测试） | ✅ |
