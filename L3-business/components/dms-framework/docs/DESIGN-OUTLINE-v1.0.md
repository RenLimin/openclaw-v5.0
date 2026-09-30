# DMS-Framework — 产品概要设计（DESIGN-OUTLINE）

> 版本：v1.0（2026-09-29）
> 层级：L3 通用业务层
> 状态：⏳ 待 Rex 审核

---

## 1. 整体架构

### 1.1 系统定位

DMS-Framework 是 L3 通用业务层的**交付管理框架引擎**，
为 L4 业务系统（如 BDMS、delivery-center）提供统一的基础设施能力：
模块管理、状态机、RACI 职责矩阵、事件总线、多租户、CLI 框架、REST API。

```
┌─────────────────────────────────────────────────────────┐
│                    L4 业务系统                          │
│         (BDMS / delivery-center / 未来系统)              │
├─────────────────────────────────────────────────────────┤
│                    DMS-Framework (L3)                    │
│  ┌─────────┐ ┌──────────┐ ┌───────┐ ┌───────────────┐  │
│  │Module   │ │State     │ │RACI   │ │Event          │  │
│  │Registry │ │Machine   │ │Engine │ │Bus            │  │
│  └─────────┘ └──────────┘ └───────┘ └───────────────┘  │
│  ┌─────────┐ ┌──────────┐ ┌───────┐ ┌───────────────┐  │
│  │CLI      │ │API       │ │SaaS   │ │Config         │  │
│  │Framework│ │Factory   │ │Multi- │ │Management     │  │
│  │         │ │(FastAPI) │ │tenant │ │               │  │
│  └─────────┘ └──────────┘ └───────┘ └───────────────┘  │
├─────────────────────────────────────────────────────────┤
│                    SQLite / PostgreSQL                   │
└─────────────────────────────────────────────────────────┘
```

### 1.2 模块划分

| 模块 | 职责 | 文件 |
|------|------|------|
| **core/module.py** | 模块注册中心 + 依赖拓扑排序 + 生命周期 | `core/module.py` |
| **core/state_machine.py** | 通用 FSM 引擎（状态/迁移/guard/hook） | `core/state_machine.py` |
| **core/raci.py** | RACI 职责引擎（能力原子/角色模板/冲突检测） | `core/raci.py` |
| **core/event_bus.py** | 事件总线（发布订阅 + 历史回溯） | `core/event_bus.py` |
| **core/database.py** | 存储抽象层（Database/BaseModel/Repository/Migration） | `core/database.py` |
| **core/cli.py** | CLI 框架（命令注册/分发） | `core/cli.py` |
| **core/api.py** | FastAPI 应用工厂 + 自动 CRUD 路由生成 | `core/api.py` |
| **core/saas.py** | SaaS 多租户（上下文/认证/路由） | `core/saas.py` |
| **core/config.py** | 配置管理（三级优先级） | `core/config.py` |
| **core/workflow_scheme.py** | 多套工作流方案引擎 | `core/workflow_scheme.py` |
| **core/auth.py** | JWT 认证 + API Key | `core/auth.py` |
| **core/webui.py** | Web UI 引擎（Jinja2） | `core/webui.py` |
| **core/migrations.py** | DDL 迁移脚本 | `core/migrations.py` |
| **dms.py** | CLI 统一入口 + FrameworkRegistry | `dms.py` |
| **15 个业务模块** | 项目管理/里程碑/交付物/风险/RACI/质量/资源/预算/沟通/合同/SLA/任务/问题/决策/租户 | `modules/` |

### 1.3 数据流

```
用户请求
  │
  ├── CLI 路径 ──▶ dms.py ──▶ FrameworkRegistry ──▶ 模块 command handler
  │
  ├── API 路径 ──▶ FastAPI ──▶ 模块 CRUD handler ──▶ BaseModel ──▶ Repository ──▶ Database
  │
  └── Web UI 路径 ──▶ Jinja2 模板 ──▶ API 调用
```

---

## 2. 接口契约

### 2.1 CLI 命令

| 命令 | 说明 |
|------|------|
| `dms init` | 初始化框架 + 数据库 |
| `dms module list` | 列出已注册模块 |
| `dms schema diff` | 查看待执行迁移 |
| `dms schema migrate` | 执行数据库迁移 |
| `dms event stats` | 查看事件总线统计 |
| `dms workflow list/set/resolve` | 工作流方案管理 |
| `dms <module> <command>` | 模块业务命令 |

### 2.2 RESTful API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/api/v1/modules` | 列出模块 |
| GET/POST | `/api/v1/auth/login` | 用户登录 |
| GET | `/api/v1/auth/me` | 当前用户 |
| GET/POST | `/api/v1/{module}` | 模块 CRUD |
| GET/PUT/DELETE | `/api/v1/{module}/{id}` | 模块实例操作 |
| POST | `/api/v1/{module}/{id}/actions/{action}` | 状态迁移 |
| POST/DELETE | `/api/v1/{module}/batch` | 批量操作 |

### 2.3 内部契约（核心引擎）

| 引擎 | 接口 | 说明 |
|------|------|------|
| ModuleRegistry | `register(manifest, factory)` | 注册模块 |
| ModuleRegistry | `initialize_all(db, config)` | 初始化所有模块 |
| EventBus | `subscribe(pattern, handler)` / `publish(name, payload)` | 事件发布订阅 |
| StateMachine | `add_state(state)` / `add_transition(t)` | 定义状态机 |
| StateMachineEngine | `register(name, machine)` / `create_entity(type, id)` | 状态机管理 |
| RACIEngine | `assign(a)` / `check_conflicts(project_id)` | RACI 分配与检测 |
| Database | `execute(sql, params)` / `commit()` | 数据库操作 |
| BaseModel | `save(db)` / `delete(db)` / `get(db, id)` / `list(db, **filters)` | ORM 基类 |
| Repository | `add(entity)` / `get(id)` / `list(**filters)` | 泛型仓储 |

---

## 3. 技术方案

### 3.1 模块注册与依赖解析

```
模块注册 → manifest 声明（name/version/dependencies/commands/tables）
         → factory 函数（接收 manifest，返回 BaseModule 实例）
         → ModuleRegistry.register(manifest, factory)

初始化 → 拓扑排序（Kahn 算法）
       → 按顺序实例化 + initialize(db, config, container)
       → 全部完成后依次调用 on_ready(container)
```

### 3.2 事件驱动架构

```
模块 A ──publish("project.created")──▶ EventBus ──dispatch──▶ 订阅者 B/C/D
                                        │
                                        ├── 支持 glob 模式匹配
                                        ├── 历史记录（默认 10000 条）
                                        └── 防递归（发布中事件排队）
```

### 3.3 状态机引擎

```
StateMachine（定义）
  ├── State（name/category/is_start/is_terminal）
  ├── Transition（name/from/to/guards/on_enter/on_exit）
  └── fire(current_state, transition_name, context)

StateMachineEngine（运行时）
  ├── register(name, machine)
  ├── create_entity(type, id, tenant_id)
  ├── transition(type, id, action, context)
  └── get_available_transitions(type, id, context)
```

### 3.4 多租户策略

```
TenantContext（contextvars.ContextVar）
  ├── 线程 + 协程安全
  ├── scope(tenant_id) 上下文管理器
  └── 默认 "system"

TenantRouter
  ├── 共享数据库（默认）
  ├── 独立数据库（L4 可扩展）
  └── 租户等级（free/business/enterprise）
```

### 3.5 API 自动注册

```
create_app(registry, db, config)
  ├── 初始化模块
  ├── 注册全局路由（health/auth/modules）
  ├── 遍历模块 → _register_crud_routes()
  │     ├── GET/POST /api/v1/{module}（列表/创建）
  │     ├── GET/PUT/DELETE /api/v1/{module}/{id}（详情/更新/删除）
  │     ├── POST /api/v1/{module}/{id}/actions/{action}（状态迁移）
  │     └── POST/DELETE /api/v1/{module}/batch（批量操作）
  └── 注册 Web UI（可选）
```

---

## 4. 依赖关系

### 4.1 外部依赖

| 依赖 | 版本 | 用途 |
|------|------|------|
| Python | 3.10+ | 运行时 |
| SQLite | 内置 | 默认数据库 |
| FastAPI | 0.100+ | REST API |
| Pydantic | 2.0+ | 数据校验 |
| Jinja2 | 3.0+ | Web 模板 |

### 4.2 内部依赖

| 依赖 | 说明 |
|------|------|
| core/module.py | 所有模块的基础 |
| core/database.py | 数据持久化 |
| core/event_bus.py | 模块间通信 |
| core/state_machine.py | 状态管理 |
| core/saas.py | 多租户 |

---

## 5. 演进路线

| 阶段 | 内容 | 状态 |
|------|------|------|
| Phase 1 | 基础框架（module/state/raci/event/database） | ✅ 完成 |
| Phase 2 | CLI 统一入口 + 模块自动发现 | ✅ 完成 |
| Phase 3 | FastAPI 应用工厂 + 自动 CRUD | ✅ 完成 |
| Phase 4 | SaaS 多租户 + 认证 | ✅ 完成 |
| Phase 5 | Web UI + 工作流方案 | ✅ 完成 |
| Phase 6 | 分布式支持 + 消息队列 | 📋 规划中 |
| Phase 7 | 插件市场 + 第三方模块 | 📋 规划中 |
