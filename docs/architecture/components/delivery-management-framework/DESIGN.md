# L3 通用交付管理框架（DMS-Framework）设计文档

> 本文档是 [系统架构](../../00-system-architecture.md) 的 L3 交付管理框架设计。
> 是 [ADR-202609-025](../adr/ADR-202609-025-delivery-management-framework.md) 的实现级设计。

## 0. 元信息

| 字段 | 值 |
|---|---|
| 文档版本 | 1.3 (2026-09-04 - 14 modules complete + KB sync) |
| 文档状态 | design |
| 决策状态 | ADR-025 proposed |
| 配套 ADR | ADR-202609-025 |
| 配套文档 | `../../02-generic-business-layer.md` |

---

## 1. 定位

### 1.1 框架 vs 系统

**本框架不是"一个交付管理系统"，而是一套可复用的交付管理框架引擎。**

```
┌─────────────────────────────────────────────────────────────┐
│  L3 通用交付管理框架（本文件）                               │
│  = 框架引擎 + 扩展点 + 通用模块 + 知识库                     │
│                                                              │
│  它提供：                                                    │
│  · ModuleRegistry（模块注册引擎）                            │
│  · StateMachineEngine（状态机引擎）                          │
│  · RACIEngine（职责矩阵引擎）                                │
│  · CLIFramework（统一 CLI 框架）                             │
│  · BaseModel（统一数据模型基类）                             │
│  · EventBus（模块间通信）                                    │
│  · 知识库结构规范                                            │
│                                                              │
│  它不绑定任何具体业务流程。                                  │
└───────────────────────┬─────────────────────────────────────┘
                        │ 继承 + 配置覆盖
          ┌─────────────┼─────────────────────┐
          ▼             ▼                     ▼
   ┌────────────┐ ┌────────────┐      ┌────────────┐
   │ L4 Bangcle │ │ L4 其他    │      │ L4 未来    │
   │ 交付管理    │ │ 交付管理    │      │ 交付管理    │
   └────────────┘ └────────────┘      └────────────┘
          │
          │  部署形态
          ▼
   ┌─────────────────────────────┐
   │  SaaS 服务（互联网多租户）    │
   │  HTTP API + 多租户 + 认证    │
   └─────────────────────────────┘
```

### 1.2 在分层架构中的位置

```
横切关注点
┌─────────────────────────────────────────────────────────────┐
│  L4  专有业务层 — 继承框架 + 专有配置                       │
├─────────────────────────────────────────────────────────────┤
│  L3  通用业务层 — ★ 本框架                                  │
│      框架引擎 + 通用模块 + 知识库                            │
│      运行时无关                                              │
├─────────────────────────────────────────────────────────────┤
│  L2  基础设施层 — 持久化/配置/知识库工具链                   │
├─────────────────────────────────────────────────────────────┤
│  L1  运行时抽象层                                            │
├─────────────────────────────────────────────────────────────┤
│  L0  系统安装层                                              │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 设计原则

| 原则 | 说明 |
|------|------|
| **框架与业务分离** | 引擎管机制，业务管逻辑 |
| **OCP 开闭** | 对扩展开放（配置/注册），对修改关闭（不改框架代码） |
| **DIP 依赖倒置** | L4 依赖框架抽象（BaseModel/ModuleRegistry），不依赖具体实现 |
| **SoC 关注点分离** | 状态机/RACI/模块注册各司其职 |
| **最小框架** | 只抽象当前实际需要的，不预判未来 |
| **统一入口** | 单一 CLI + 单一数据库 |
| **热插拔** | 模块注册即用，移除不影响框架 |
| **SaaS-ready** | 数据结构预埋多租户，存储层可切换，认证接口抽象 |
| **Metadata-driven** | 自定义字段元数据表，租户级字段扩展（借鉴 Salesforce） |
| **Hybrid Tenancy** | 共享/Schema-per/数据库-per 三级路由（借鉴 Jira + 2026 trend） |
| **Workflow Scheme** | Workflow ↔ 业务类型映射，支持多流程并存（借鉴 Jira） |

---

## 2. 业界调研

### 2.1 开源项目参考

| 项目 | GitHub Stars | 核心借鉴 |
|------|-------------|---------|
| **Plane.so** | 38.7k | Workspace→Project→Module→Issue 四层分解；Schema 与 Work 数据分离；Cycles（Sprint） |
| **OpenProject** | 15.4k | Work Package 统一模型（task/bug/milestone/phase 都是 WP 的 type）；status+priority+assignee 通用属性 |
| **GitHub Projects** | — | Project→Issue→Sub-issue 三层；Milestone 6 字段表；可自定义字段 |
| **NocoBase** | 22k | 数据建模驱动的 no-code，自定义工作流和角色 |
| **Leantime** | — | 战略→执行对齐：Goal→Milestone→Task + 文档 |
| **Focalboard** | — | Kanban/Table/Gallery/Calendar 多视图共享同一数据集 |

### 2.2 方法论参考

| 来源 | 核心内容 | 对框架的启发 |
|------|---------|-------------|
| **PMBOK 8th (2026)** | 6 原则 + 7 绩效域 + 40 过程 | 知识体系骨架 |
| **RACI 矩阵 (PMI)** | Responsible/Accountable/Consulted/Informed | 角色-职责松耦合引擎 |
| **ITIL 4 SVS** | 服务价值系统 + 实践 | 售后/服务交付子模块知识 |
| **Scrum Guide** | Sprint/Backlog/角色 | 敏捷子模块知识 |

### 2.3 关键设计模式

| 模式 | 业界案例 | 本框架应用 |
|------|---------|-----------|
| **框架 + 实例化** | Spring Framework → Java 应用 | DMS-Framework → L4 交付系统 |
| **插件注册** | WordPress Plugins / VS Code Extensions | ModuleRegistry + ModuleManifest |
| **状态机引擎** | Spring StateMachine / XState | 可配置状态流转 |
| **模板方法** | Django CMS / Strapi | 框架定义骨架，L4 填内容 |
| **策略模式** | 支付网关多策略 | 业务规则可替换 |

---

## 3. 框架架构

### 3.1 总体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLI 入口 (dms)                           │
│                  dms <module> <command> [options]                │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│                      CLIFramework                               │
│  · 命令注册/路由                                                │
│  · 参数解析/校验                                                │
│  · 输出格式化 (table/json/markdown)                             │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│                      ModuleRegistry                             │
│  · 模块发现/注册/注销                                           │
│  · 依赖解析（模块间）                                           │
│  · 生命周期管理（init/start/stop）                              │
│  · Hook 注册/触发                                               │
└─────────┬───────────────────────────────────────────┬───────────┘
          │                                           │
┌─────────▼──────────┐                    ┌──────────▼──────────┐
│  StateMachineEngine │                    │    RACIEngine        │
│  · 状态定义          │                    │  · 能力原子管理       │
│  · 转换规则          │                    │  · 角色模板管理       │
│  · Guard 条件        │                    │  · 项目级分配         │
│  · 转换 Hook         │                    │  · 冲突检测           │
└────────────────────┘                    └─────────────────────┘
          │                                           │
          └───────────────────┬───────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│                        EventBus                                  │
│  · 发布/订阅                                                    │
│  · 模块间解耦通信                                                │
│  · 事件持久化（审计日志）                                        │
└─────────────────────────────┬─────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│                    BaseModel + Repository                        │
│  · 统一数据访问                                                  │
│  · 表命名空间隔离（模块前缀）                                    │
│  · CRUD + 迁移 + 审计                                           │
│  · SQLite 实现                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 模块模型

#### 3.2.1 ModuleManifest（模块声明）

每个模块通过 `ModuleManifest` 声明自身：

```python
@dataclass
class ModuleManifest:
    name: str                    # 模块名（CLI 子命令名）
    version: str                 # 语义版本
    description: str             # 模块描述
    tables: list[str]            # 模块拥有的表（命名空间隔离）
    commands: list[CommandDef]   # 注册的 CLI 命令
    dependencies: list[str]      # 依赖的模块名
    hooks: dict[str, str]        # Hook 映射：event → handler
    config_schema: dict          # 模块配置 JSON Schema
```

#### 3.2.2 内置模块（框架首次验证）

| 模块 | 表 | 命令 | 依赖 |
|------|-----|------|------|
| `project` | projects, project_members, stakeholders | create/list/show/update/delete | 无 |
| `milestone` | work_items (type=milestone) | create/list/show/achieve/miss | project |
| `deliverable` | work_items (type=deliverable) | create/list/submit/approve/reject | project |
| `risk` | work_items (type=risk) | create/list/show/mitigate/resolve | project |
| `raci` | responsibility_assignments | assign/list/show/validate | project |

#### 3.2.3 模块注册示例

```python
# project 模块
PROJECT_MODULE = ModuleManifest(
    name="project",
    version="1.0.0",
    description="项目全生命周期管理",
    tables=["projects", "project_members", "stakeholders"],
    commands=[
        CommandDef("create", create_project, "创建项目"),
        CommandDef("list", list_projects, "列出项目"),
        CommandDef("show", show_project, "查看项目详情"),
        CommandDef("update", update_project, "更新项目"),
        CommandDef("delete", delete_project, "删除项目"),
    ],
    dependencies=[],
    hooks={}
)

# milestone 模块
MILESTONE_MODULE = ModuleManifest(
    name="milestone",
    version="1.0.0",
    description="里程碑跟踪管理",
    tables=["work_items"],
    commands=[
        CommandDef("create", create_milestone, "创建里程碑"),
        CommandDef("list", list_milestones, "列出里程碑"),
        CommandDef("achieve", achieve_milestone, "标记达成"),
        CommandDef("miss", miss_milestone, "标记错过"),
    ],
    dependencies=["project"],
    hooks={
        "work_item.status_changed": "milestone.on_status_changed"
    }
)
```

### 3.3 状态机引擎

#### 3.3.1 设计

参考 Spring StateMachine / XState，提供可配置的状态流转：

```python
@dataclass
class StateMachine:
    name: str
    states: list[str]
    initial: str
    transitions: list[Transition]
    guards: dict[str, Callable]      # 转换前置条件
    hooks: dict[str, list[Callable]] # 转换前后钩子

@dataclass
class Transition:
    event: str                       # 触发事件
    source: str | list[str]          # 源状态
    target: str                      # 目标状态
    guard: str | None = None         # 守卫条件名
```

#### 3.3.2 项目状态机（默认配置）

```
initiated ──start──► planning ──plan_complete──► executing
     │                   │                          │
     │                   ├──pause──► on_hold ──resume─┤
     │                   │                          │
     │                   └──cancel──► archived ◄─────┘
     │
     └──cancel──► archived

executing ──complete──► monitoring ──accept──► closing ──close──► closed
     │                      │                     │
     └──block──► on_hold    └──reject──► executing  └──cancel──► archived
```

#### 3.3.3 工作项状态机（按 type 区分）

```
task:       todo ──start──► in_progress ──complete──► done
                  │               │
                  └──block──► blocked ──unblock──┘

milestone:  pending ──start──► in_progress ──achieve──► achieved
                                  │
                                  └──miss──► missed

deliverable: draft ──submit──► review ──accept──► accepted
                                   │
                                   └──reject──► draft

risk:       identified ──mitigate──► mitigating ──resolve──► resolved
                                  │
                                  └──occur──► occurred
```

**L4 扩展方式**：通过配置文件覆盖状态定义，不改引擎代码。

### 3.4 RACI 引擎

#### 3.4.1 三层模型

```
┌─────────────────────────────────────────────────┐
│  Layer 1: Capability（能力原子）                 │
│  粒度最小的职责单元                              │
│  12 个预定义能力，L4 可扩展                      │
└─────────────────────┬───────────────────────────┘
                      │ 组合
┌─────────────────────▼───────────────────────────┐
│  Layer 2: RoleTemplate（角色模板）               │
│  预定义的能力组合                                │
│  6 个预定义模板，L4 可扩展                       │
└─────────────────────┬───────────────────────────┘
                      │ 实例化 + 裁剪
┌─────────────────────▼───────────────────────────┐
│  Layer 3: Assignment（项目级分配）               │
│  具体项目中的实际 RACI 分配                      │
│  每个项目独立配置                                │
└─────────────────────────────────────────────────┘
```

#### 3.4.2 能力原子清单

| # | 能力 ID | 说明 | 关联角色 |
|---|---------|------|---------|
| 1 | `scope_management` | 范围定义、WBS、变更控制 | 项目经理、产品经理 |
| 2 | `schedule_management` | 进度计划、关键路径、里程碑 | 项目经理、交付经理 |
| 3 | `risk_management` | 风险识别、评估、应对 | 项目经理 |
| 4 | `stakeholder_management` | 干系人识别、沟通计划 | 项目经理、客户成功 |
| 5 | `quality_management` | 质量标准、验收、回顾 | QA、项目经理 |
| 6 | `deliverable_management` | 交付物定义、跟踪、验收 | 交付经理 |
| 7 | `milestone_tracking` | 里程碑设定、监控、报告 | 交付经理 |
| 8 | `resource_management` | 资源分配、工作量、冲突 | 项目经理、交付总监 |
| 9 | `budget_management` | 预算编制、成本跟踪、变更 | 项目经理、交付总监 |
| 10 | `communication_management` | 会议、报告、升级 | 项目经理、Scrum Master |
| 11 | `contract_interface` | 合同条款、付款节点、索赔 | 项目经理、合同管理员 |
| 12 | `sla_tracking` | SLA 定义、监控、违约预警 | 交付经理、客户成功 |

#### 3.4.3 角色模板

| 角色模板 | 能力组合 | 典型场景 |
|---------|---------|---------|
| **项目经理** | 1+2+3+4+8+9+10+11 | 端到端项目交付 |
| **交付经理** | 2+6+7+12 | 里程碑/交付物跟踪 |
| **产品经理** | 1+4+5 | 需求定义、验收 |
| **Scrum Master** | 2+5+10 | 敏捷过程管理 |
| **QA 工程师** | 5 | 质量保障 |
| **交付总监** | 2+8+9+10 | 项目组合监控 |

#### 3.4.4 RACI 引擎 API

```python
class RACIEngine:
    def register_capability(self, cap: Capability) -> None
    def register_role_template(self, template: RoleTemplate) -> None
    def assign(self, project_id, member_id, capability, raci_role) -> Assignment
    def get_assignments(self, project_id, work_item_id=None) -> list[Assignment]
    def validate(self, project_id) -> ValidationResult
    def get_member_roles(self, project_id, member_id) -> list[Role]
    def check_conflicts(self, project_id) -> list[Conflict]
```

#### 3.4.5 冲突检测规则

| 规则 | 说明 |
|------|------|
| 每任务每能力有且仅 1 个 A | Accountable 唯一 |
| 每任务每能力至少 1 个 R | 不能无人负责 |
| 同一人不能同时是 R 和 A | 执行与问责分离（建议） |
| 能力必须被角色模板覆盖 | 分配的能力在角色模板中存在 |


### 3.5 WorkflowScheme（流程方案）

> 借鉴 Jira Workflow Scheme：Workflow ↔ 业务类型映射，支持同一项目中不同业务对象使用不同流程。

```python
@dataclass
class WorkflowScheme:
    """流程方案：定义业务类型到工作流/状态机的映射"""
    name: str
    description: str
    mappings: dict[str, str]   # {issue_type: workflow_name}
    # 例: {"task": "default_task_flow", "deliverable": "approval_flow"}
```

**框架内置 Scheme**：

| Scheme 名称 | task | milestone | deliverable | risk |
|-------------|------|-----------|-------------|------|
| `default` | task_flow | milestone_flow | deliverable_flow | risk_flow |
| `simple` | simple_task | simple_milestone | simple_deliverable | simple_risk |
| `approval` | task_flow | milestone_flow | strict_approval_flow | risk_flow |

**L4 扩展方式**：
```python
# L4 定义专有 Scheme
BANGCLE_SCHEME = WorkflowScheme(
    name="bangcle_standard",
    description="Bangcle 标准交付流程",
    mappings={
        "task": "bangcle_task_flow",
        "deliverable": "bangcle_qa_approval_flow",  # 交付物走 QA 审批
        "milestone": "bangcle_milestone_flow",
        "risk": "bangcle_risk_flow"
    }
)
```

### 3.6 EventBus（模块间通信）

```python
class EventBus:
    def subscribe(self, event: str, handler: Callable) -> None
    def publish(self, event: str, payload: dict) -> None
    def get_history(self, entity_type, entity_id) -> list[Event]
```

**预定义事件**：

| 事件 | 触发时机 | 订阅者示例 |
|------|---------|-----------|
| `project.created` | 项目创建后 | milestone: 创建默认里程碑 |
| `project.status_changed` | 项目状态变更 | raci: 重新校验分配 |
| `work_item.created` | 工作项创建 | project: 更新进度 |
| `work_item.status_changed` | 工作项状态变更 | milestone: 检查达成条件 |
| `deliverable.accepted` | 交付物验收 | project: 更新完成度 |
| `risk.occurred` | 风险发生 | project: 触发升级流程 |

**L4 扩展方式**：L4 模块订阅事件，不修改发布方代码。

### 3.7 CLI 框架

#### 3.7.1 命令结构

```bash
dms <module> <command> [options]
```

#### 3.7.2 内置命令

```bash
# 系统级
dms init                           # 初始化框架（建库 + 注册模块）
dms status                         # 框架状态（模块/表/版本）
dms module list                    # 列出已注册模块
dms module info <name>             # 模块详情

# 项目级
dms project create "XXX" --type software_delivery
dms project list
dms project show <id>
dms project update <id> --status executing
dms project delete <id>

# 里程碑级
dms milestone create <project_id> "需求确认" --due 2026-09-30
dms milestone list <project_id>
dms milestone achieve <id>
dms milestone miss <id>

# 交付物级
dms deliverable create <project_id> "PRD" --milestone <id>
dms deliverable submit <id> --file ./prd.docx
dms deliverable approve <id>
dms deliverable reject <id> --reason "不完整"

# 风险级
dms risk create <project_id> "技术风险" --probability high --impact high
dms risk mitigate <id> --plan "增加技术预研"
dms risk resolve <id>

# RACI
dms raci assign <project_id> <member> <capability> --role R
dms raci show <project_id>
dms raci validate <project_id>
```

#### 3.7.3 输出格式

```bash
dms project list                    # 默认表格
dms project list --json             # JSON（程序消费）
dms project list --markdown         # Markdown（文档嵌入）
```

---

## 4. 数据模型

### 4.1 设计原则

1. **统一工作项模型**：task/milestone/deliverable/risk/decision 都是 `work_items` 的 type
2. **表命名空间隔离**：模块表通过前缀隔离（`project_*` / `raci_*`）
3. **L4 扩展字段**：`proprietary_metadata` JSON 列，L4 添加专有字段不改表结构
4. **审计日志**：所有写操作记录 `change_logs`

### 4.2 ER 图

```
┌──────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│  projects    │     │  work_items       │     │ responsibility_     │
│              │     │                    │     │ assignments         │
│ id (PK)      │◄────┤ project_id (FK)   │     │                     │
│ name         │ 1:N │ id (PK)           │     │ id (PK)             │
│ description  │     │ type              │     │ project_id (FK) ────┤──► projects
│ status       │     │ title             │     │ work_item_id (FK)   │──► work_items
│ priority     │     │ description       │     │ member_id           │
│ planned_start│     │ status            │     │ capability          │
│ planned_end  │     │ priority          │     │ raci_role           │
│ actual_start │     │ assignee_id (FK)  │     │ notes               │
│ actual_end   │     │ reviewer_id       │     └─────────────────────┘
│ budget       │     │ planned_date      │
│ currency     │     │ actual_date       │     ┌─────────────────────┐
│ owner_id(FK) │     │ due_date          │     │ project_members     │
│ proprietary_ │     │ estimated_hours   │     │                     │
│  metadata    │     │ actual_hours      │     │ project_id (FK)     │──► projects
└──────┬───────┘     │ parent_id (FK)    │     │ member_id           │
       │             │ metadata          │     │ member_name         │
       │             └───────────────────┘     │ role_template       │
       │                                      └─────────────────────┘
       │
       │         ┌──────────────────┐
       │         │ stakeholders     │
       │         │                  │
       └────────►│ project_id (FK)  │
            1:N │ id (PK)          │
                 │ name             │
                 │ role             │
                 │ org              │
                 │ influence        │
                 │ interest         │
                 └──────────────────┘

┌──────────────────┐     ┌──────────────────────┐
│ change_logs      │     │ module_registry      │
│                  │     │                      │
│ id (PK)          │     │ name (PK)            │
│ entity_type      │     │ version              │
│ entity_id        │     │ description          │
│ action           │     │ tables               │
│ field_name       │     │ commands             │
│ old_value        │     │ dependencies         │
│ new_value        │     │ hooks                │
│ actor_id         │     │ installed_at         │
│ created_at       │     └──────────────────────┘
└──────────────────┘
```

### 4.3 DDL

```sql
-- 框架版本表
CREATE TABLE IF NOT EXISTS schema_version (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

-- 模块注册表
CREATE TABLE IF NOT EXISTS module_registry (
    name TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    description TEXT,
    tables TEXT NOT NULL,           -- JSON array
    commands TEXT NOT NULL,         -- JSON array
    dependencies TEXT NOT NULL,     -- JSON array
    hooks TEXT NOT NULL,            -- JSON object
    installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 项目表
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    type TEXT DEFAULT 'generic',            -- generic|software_delivery|construction|...
    status TEXT DEFAULT 'initiated',
    priority TEXT DEFAULT 'medium',
    planned_start DATE,
    planned_end DATE,
    actual_start DATE,
    actual_end DATE,
    budget REAL,
    currency TEXT DEFAULT 'CNY',
    owner_id TEXT,
    tenant_id TEXT NOT NULL DEFAULT 'system',
    proprietary_metadata TEXT,              -- L4 扩展点（JSON）
    proprietary_metadata TEXT,              -- L4 扩展点（JSON）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 工作项表（统一模型）
CREATE TABLE IF NOT EXISTS work_items (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    type TEXT NOT NULL,                     -- task|milestone|deliverable|risk|decision
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'draft',
    priority TEXT DEFAULT 'medium',
    assignee_id TEXT,
    reviewer_id TEXT,
    planned_date DATE,
    actual_date DATE,
    due_date DATE,
    estimated_hours REAL,
    actual_hours REAL,
    parent_id TEXT REFERENCES work_items(id),
    metadata TEXT,                          -- 类型特有属性（JSON）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 项目成员表
CREATE TABLE IF NOT EXISTS project_members (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    member_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT 'system',  -- SaaS 多租户隔离
    member_name TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT 'system',  -- SaaS 多租户隔离
    role_template TEXT,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (project_id, member_id)
);

-- 干系人表
CREATE TABLE IF NOT EXISTS stakeholders (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    role TEXT,
    org TEXT,
    tenant_id TEXT NOT NULL DEFAULT 'system',  -- SaaS 多租户隔离
    influence TEXT DEFAULT 'medium',
    interest TEXT DEFAULT 'medium',
    notes TEXT
);

-- ★ Metadata-driven 自定义字段（借鉴 Salesforce）
CREATE TABLE IF NOT EXISTS custom_fields (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'system',
    entity_type TEXT NOT NULL,         -- project | work_item | member
    field_name TEXT NOT NULL,
    field_type TEXT NOT NULL,          -- text | number | date | boolean | select | multiselect
    field_options TEXT,                -- select 选项（JSON）
    required BOOLEAN DEFAULT FALSE,
    default_value TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, entity_type, field_name)
);

-- RACI 职责分配表
CREATE TABLE IF NOT EXISTS responsibility_assignments (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    work_item_id TEXT REFERENCES work_items(id) ON DELETE CASCADE,
    member_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT 'system',  -- SaaS 多租户隔离
    capability TEXT NOT NULL,
    raci_role TEXT NOT NULL,                -- R|A|C|I
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, work_item_id, member_id, capability)
);

-- 变更日志表
CREATE TABLE IF NOT EXISTS change_logs (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    field_name TEXT,
    old_value TEXT,
    new_value TEXT,
    actor_id TEXT,
    tenant_id TEXT NOT NULL DEFAULT 'system',  -- SaaS 多租户隔离
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_work_items_project ON work_items(project_id);
CREATE INDEX IF NOT EXISTS idx_work_items_type ON work_items(type);
CREATE INDEX IF NOT EXISTS idx_work_items_status ON work_items(status);
CREATE INDEX IF NOT EXISTS idx_work_items_assignee ON work_items(assignee_id);
CREATE INDEX IF NOT EXISTS idx_work_items_parent ON work_items(parent_id);
CREATE INDEX IF NOT EXISTS idx_raci_project ON responsibility_assignments(project_id);
CREATE INDEX IF NOT EXISTS idx_raci_member ON responsibility_assignments(member_id);
CREATE INDEX IF NOT EXISTS idx_raci_capability ON responsibility_assignments(capability);
CREATE INDEX IF NOT EXISTS idx_change_logs_entity ON change_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_stakeholders_project ON stakeholders(project_id);
CREATE INDEX IF NOT EXISTS idx_projects_tenant ON projects(tenant_id);
CREATE INDEX IF NOT EXISTS idx_work_items_tenant ON work_items(tenant_id);
CREATE INDEX IF NOT EXISTS idx_raci_tenant ON responsibility_assignments(tenant_id);
CREATE INDEX IF NOT EXISTS idx_change_logs_tenant ON change_logs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_custom_fields_tenant ON custom_fields(tenant_id, entity_type);
```

### 4.4 L4 扩展机制

L4 通过 `proprietary_metadata` JSON 列扩展，不改表结构：

```json
// projects.proprietary_metadata 示例（L4 Bangcle）
{
  "bangcle_client_id": "BCL-2026-0042",
  "contract_id": "SCA-001-0001",
  "sla_binding": {
    "response_time_hours": 4,
    "resolution_time_hours": 24,
    "penalty_rate": 0.001
  },
  "client_acceptance_criteria": ["功能验收", "性能验收", "安全验收"]
}
```

---

## 5. 知识库设计

### 5.1 目录结构

```
knowledge-base/by-category/business/delivery-management/
├── README.md                              # 维度总索引
├── INDEX.md                               # 快速索引

├── capabilities/                          # 能力知识（独立于角色）
│   ├── scope-management.md
│   ├── schedule-management.md
│   ├── risk-management.md
│   ├── stakeholder-management.md
│   ├── quality-management.md
│   ├── deliverable-management.md
│   ├── milestone-tracking.md
│   ├── resource-management.md
│   ├── budget-management.md
│   ├── communication-management.md
│   ├── contract-interface.md
│   └── sla-tracking.md

├── methodologies/                         # 方法论
│   ├── pmbok-8th/
│   │   ├── principles.md
│   │   ├── performance-domains.md
│   │   ├── processes.md
│   │   └── tailoring.md
│   ├── agile/
│   │   ├── scrum-guide.md
│   │   ├── kanban.md
│   │   ├── hybrid.md
│   │   └── user-stories.md
│   ├── raci/
│   │   ├── framework.md
│   │   ├── agile-adaptation.md
│   │   └── anti-patterns.md
│   └── itil-4/
│       ├── svs.md
│       └── practices.md

├── roles/                                 # 角色模板
│   ├── project-manager/
│   │   ├── SOUL.md
│   │   ├── AGENTS.md
│   │   ├── IDENTITY.md
│   │   └── capability-map.md             # 引用 capabilities/
│   ├── delivery-manager/
│   ├── product-manager/
│   ├── scrum-master/
│   ├── qa-engineer/
│   └── delivery-director/

├── templates/                             # 交付物模板
│   ├── project-charter.md
│   ├── raci-matrix.md
│   ├── milestone-plan.md
│   ├── risk-register.md
│   ├── status-report.md
│   ├── deliverable-checklist.md
│   └── change-request.md

├── data-model/                            # 数据模型参考
│   ├── entity-relationship.md
│   ├── state-machines.md
│   └── schema.sql

└── references/                            # 外部参考
    ├── openproject-lessons.md
    ├── plane-lessons.md
    └── github-projects-lessons.md
```

### 5.2 知识文档标准

遵循现有知识库 frontmatter 规范，新增 `capability` 标签：

```yaml
---
title: "范围管理知识"
description: "项目范围定义、WBS 编制、变更控制的方法与工具"
source: "PMBOK 8th §5"
version: "8th"
category: "business"
dimension: "delivery-management"
sub_area: "capabilities"
type: "industry"
tags: ["scope_management", "wbs", "change_control", "planning"]
capability: "scope_management"            # 关联能力原子
xref:
  - path: "roles/project-manager/capability-map.md"
    relation: "referenced_by"
last_reviewed: "2026-09-03"
---
```

---

## 6. SaaS 预埋设计

### 6.1 设计原则

**L3 框架不实现 SaaS 业务逻辑（计费/认证/前端），但预埋 SaaS 基础设施结构。**

```
L3 框架（预埋）                L4 Bangcle SaaS（实现）
─────────────────────────      ─────────────────────────
tenant_id 字段（所有表）    →   多租户中间件（自动注入）
连接池抽象（Repository）   →   PostgreSQL + 连接池
API 路由注册机制           →   FastAPI HTTP API
AuthProvider 接口          →   OAuth2 / JWT 认证
模块配置 Schema            →   租户级模块开关
proprietary_metadata       →   租户级计费/配额
```

### 6.2 多租户数据模型

#### 6.2.1 租户隔离策略

采用 **Shared Database, Shared Schema, tenant_id 隔离**（阶段 1），向上兼容独立 schema/独立库：

| 策略 | 阶段 | 说明 |
|------|------|------|
| Shared Schema + tenant_id | L3 + L4 初期 | 所有租户共享表，tenant_id 隔离行 |
| Shared Database, Schema-per-tenant | L4 增长期 | 大租户独立 schema |
| Database-per-tenant | L4 成熟期 | 超大租户独立数据库 |

**★ Hybrid 租户路由（2026 最佳实践）**：

```
                    ┌─────────────────────┐
                    │   TenantRouter       │
                    │   (根据租户等级路由)  │
                    └──────┬───────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
   ┌────────────┐  ┌────────────┐  ┌────────────┐
   │  Shared DB  │  │ Schema-per │  │ Database   │
   │  (free/   │  │ -tenant    │  │ -per-tenant│
   │   standard) │  │ (business) │  │ (enterprise│
   └────────────┘  └────────────┘  └────────────┘
```

```python
class TenantRouter:
    """Hybrid 多租户路由：根据租户等级分配存储资源"""
    def get_connection(self, tenant_id: str) -> Database:
        tier = self.get_tenant_tier(tenant_id)
        if tier == "enterprise":
            return self.get_dedicated_db(tenant_id)
        elif tier == "business":
            return self.get_schema_db(tenant_id)
        else:
            return self.get_shared_db()
```

**租户迁移**：
```bash
# 免费 → 付费：共享库迁移到独立 schema
dms tenant migrate <tenant_id> --target schema-per-tenant

# 付费 → 企业：独立 schema 迁移到独立数据库
dms tenant migrate <tenant_id> --target database-per-tenant
```

**★ PostgreSQL Row-Level Security（RLS）安全网**：

即使应用层忘记过滤 tenant_id，数据库级 RLS 强制隔离：

```sql
-- 启用 RLS
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE work_items ENABLE ROW LEVEL SECURITY;

-- 创建隔离策略
CREATE POLICY tenant_isolation_projects ON projects
    USING (tenant_id = current_setting('app.current_tenant')::TEXT);

-- 应用层只需 SET LOCAL app.current_tenant = 'xxx'
-- 数据库强制过滤，即使代码有 bug 也安全
```

L3 阶段 Repository 预留 set_tenant_context() 方法，L4 启用 RLS。

#### 6.2.2 tenant_id 注入规则

```python
class BaseModel:
    tenant_id: str = Field(default="system")  # 默认 "system" = 单租户模式

    def save(self):
        if not self.tenant_id:
            self.tenant_id = TenantContext.current()
        self.db.save(self)
```

**所有业务表都带 `tenant_id`**：projects / work_items / project_members / responsibility_assignments / stakeholders / change_logs。

#### 6.2.3 租户上下文

```python
from contextvars import ContextVar

class TenantContext:
    _current = ContextVar("tenant_id", default="system")

    
    def set(cls, tenant_id: str):
        cls._current.set(tenant_id)

    
    def current(cls) -> str:
        return cls._current.get()
```

### 6.3 存储层抽象

Repository 层支持 SQLite → PostgreSQL 无缝切换，自动注入 tenant_id 过滤。

### 6.4 API 路由注册机制

```python

class RouteDef:
    method: str                  # GET|POST|PUT|DELETE
    path: str                    # /api/v1/projects
    handler: str                 # 处理函数引用
    module: str                  # 所属模块
    auth_required: bool = True
    rate_limit: str | None = None
```

模块注册时声明 API 路由，L4 用 FastAPI 绑定。

### 6.5 认证接口抽象

```python
class AuthProvider(Protocol):
    async def authenticate(self, token: str) -> AuthResult: ...
    async def authorize(self, user: AuthUser, resource: str, action: str) -> bool: ...
    async def get_tenant(self, user: AuthUser) -> str: ...
```

L4 实现：OAuth2 + JWT / API Key / SAML-SSO。

### 6.6 SaaS 部署架构（L4 参考）

```
                    ┌─────────────┐
                    │  CDN/Edge   │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  API Gateway │  ← 认证/限流/路由
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ API Pod  │ │ API Pod  │ │ API Pod  │
        └────┬─────┘ └────┬─────┘ └────┬─────┘
             │            │            │
             └────────────┼────────────┘
                          │
                    ┌─────▼─────┐
                    │ PostgreSQL │
                    │ (Primary  │
                    │  + Read   │
                    │  Replica) │
                    └───────────┘
```

### 6.7 SaaS 化检查清单

| 项目 | L3 框架（预埋） | L4 SaaS（实现） |
|------|----------------|----------------|
| tenant_id 字段 | ✅ 所有表 | — |
| Repository 过滤 | ✅ 自动注入 | — |
| 连接池抽象 | ✅ 接口定义 | PostgreSQL 实现 |
| API 路由注册 | ✅ RouteDef | FastAPI 绑定 |
| 认证接口 | ✅ AuthProvider | OAuth2 + JWT |
| 限流 | ✅ rate_limit 声明 | Gateway 实现 |
| 计费/配额 | — | metered 模块 |
| 前端 | — | React/Vue |
| 监控/告警 | — | Prometheus + Grafana |
| Hybrid 租户路由 | ✅ TenantRouter 接口 | 三级存储路由实现 |
| PostgreSQL RLS | ✅ set_tenant_context() | RLS 策略 + FORCE ROW LEVEL |
| Metadata-driven 字段 | ✅ custom_fields 表 | 租户自定义字段 UI |
| Workflow Scheme | ✅ Scheme 注册 + 映射 | 业务级 Scheme 配置 |
| Schema diff/migrate | ✅ schema_version 表 | CLI diff + migrate |
| 多租户迁移工具 | — | 独立脚本 |

---

## 7. L4 继承机制

### 6.1 继承方式

```
L4 专有业务（如 Bangcle 交付管理）
  ├── extends L3 框架引擎（不修改）
  ├── extends L3 通用模块（配置覆盖）
  ├── extends L3 知识库（新增专有知识）
  ├── adds 专有模块（如 bangcle_contract）
  ├── adds 专有角色模板（如 bangcle_pm）
  └── adds 专有配置（状态机覆盖、RACI 默认模板）
```

### 6.2 L4 扩展点清单

| 扩展点 | 机制 | L4 操作 |
|--------|------|---------|
| **模块注册** | `ModuleManifest` | 注册专有模块 |
| **状态机覆盖** | YAML/JSON 配置 | 定义专有状态流转 |
| **能力原子扩展** | `register_capability()` | 新增专有能力 |
| **角色模板扩展** | `register_role_template()` | 定义专有角色 |
| **数据模型扩展** | `proprietary_metadata` JSON | 添加专有字段 |
| **Hook 注册** | `EventBus.subscribe()` | 响应系统事件 |
| **CLI 命令扩展** | `commands` 注册 | 模块自动获得 CLI |
| **知识库扩展** | 新增目录 | 引用 L3 + 叠加专有 |

### 6.3 L4 建设流程（未来）

```
Step 1: Rex 提供专有业务流程图、业务逻辑
Step 2: 分析哪些 L3 模块可复用、哪些需扩展
Step 3: 创建 L4 配置（状态机覆盖 + RACI 默认模板）
Step 4: 注册专有模块（如需要）
Step 5: 编写专有知识文档
Step 6: 端到端验证
```

---

## 8. 与现有组件的关系

### 7.1 L2 复用

| L2 组件 | 复用方式 |
|---------|---------|
| **持久化适配** | SQLite + Repository 模式（直接复用） |
| **配置管理** | 框架配置走 `config.sh` 治理流程 |
| **知识库工具链** | `kb_index.py` 扩展支持业务知识库 |
| **Office 文档生成** | 交付物模板渲染（未来） |
| **可观测性** | 框架运行日志 + 事件追踪 |

### 7.2 L4 集成

| L4 组件 | 关系 | 集成方式 |
|---------|------|---------|
| **SCA-001 合同审批** | 子模块 | 作为 `contract` 模块注册，通过 EventBus 与 project 模块通信 |
| **BDMS 交付中心** | 未来继承者 | 继承框架 + Bangcle 专有配置 |

---

## 9. 开发计划

### Phase 0: 设计（当前）

| 步骤 | 内容 | 产出 |
|------|------|------|
| 1 | ADR-025 | 决策记录 |
| 2 | DESIGN.md（本文件） | 框架设计文档 |

### Phase 1: 框架引擎

| 步骤 | 内容 | 产出 |
|------|------|------|
| 1 | ModuleRegistry + ModuleManifest | 模块注册引擎 |
| 2 | StateMachineEngine | 状态机引擎 |
| 3 | RACIEngine | 职责矩阵引擎 |
| 4 | EventBus | 事件总线 |
| 5 | CLIFramework | CLI 框架 |
| 6 | BaseModel + Repository + 迁移 | 数据访问层 |
| 7 | TenantContext + AuthProvider 接口 | SaaS 基础（租户上下文 + 认证抽象） |
| 8 | RouteDef + API 路由注册 | SaaS 基础（API 规范） |
| 9 | WorkflowScheme 引擎 | 流程方案注册 + 映射 |
| 10 | custom_fields 元数据表 | Metadata-driven 自定义字段 |
| 11 | TenantRouter 接口 | Hybrid 多租户路由（L3 接口 + L4 实现） |

### Phase 2: 通用模块

| 步骤 | 内容 | 产出 |
|------|------|------|
| 1 | project 模块 | 项目管理 |
| 2 | milestone 模块 | 里程碑跟踪 |
| 3 | deliverable 模块 | 交付物管理 |
| 4 | risk 模块 | 风险管理 |
| 5 | raci 模块 | 职责分配 CLI |
| 6 | quality 模块 | 质量管理 |
| 7 | resource 模块 | 资源管理 |
| 8 | budget 模块 | 预算管理 |
| 9 | communication 模块 | 沟通管理 |
| 10 | contract 模块 | 合同接口 |
| 11 | sla 模块 | SLA 跟踪 |
| 12 | task 模块 | 任务看板 |
| 13 | issue 模块 | 问题分诊 |
| 14 | decision 模块 | 决策日志 |

### Phase 3: 知识库

|------|------|------|
| 1 | capabilities/ | 15 篇能力知识（+ task/issue/decision） |
| 2 | methodologies/ | PMBOK + 敏捷 + RACI + ITIL |
| 3 | roles/ | 6 角色模板 |
| 4 | templates/ | 8 个模板 |
| 5 | data-model/ | ER 图 + 状态机 + DDL |
| 6 | references/ | 3 篇开源借鉴 |

### Phase 4: 验证

| 步骤 | 内容 | 产出 |
|------|------|------|
| 1 | 实例化示例项目 | 端到端测试 |
| 2 | 热插拔测试 | 新增/移除模块 |
| 3 | 扩展点测试 | 模拟 L4 场景 |

---

## 10. 验证标准

| 指标 | 标准 | 验证方式 |
|------|------|---------|
| 框架可实例化 | 创建新项目无需改框架代码 | 端到端测试 |
| 模块热插拔 | 注册即用，移除不影响框架 | 测试模块验证 |
| 统一入口 | `dms <module> <command>` 访问所有模块 | CLI 实测 |
| 统一数据 | 共享 `delivery.db`，表命名隔离 | 数据库审查 |
| RACI 松耦合 | 同角色不同项目不同职责 | RACI 测试 |
| 状态机可配置 | 不改引擎代码定义新状态流 | 配置覆盖测试 |
| 知识召回率 | 业务问题召回相关知识 ≥ 80% | memory_search |
| L4 可扩展 | 模拟 L4 不改框架完成扩展 | 扩展点测试 |
| 14 模块全覆盖 | 14 业务模块注册+CLI+测试全过 | `dms module list` + pytest |
| 事件联动 | project.cancelled → 12 模块自动响应 | E2E 联动测试 |
| 测试覆盖 | 228 测试全过 | pytest |

---

## 11. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 过度设计 | 中 | 高 | 基于当前需求设计扩展点，不预判未来 |
| 扩展点不足 | 中 | 高 | L4 建设时 review，必要时回炉 |
| SQLite 并发 | 低 | 中 | WAL 模式 + 连接池 |
| 知识库质量 | 中 | 中 | 基于权威来源 + 季度审查 |
| 框架 bug 影响面 | 低 | 高 | 单元测试 + 集成测试覆盖 |

---

## 12. 变更历史

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-09-03 | 1.0 | 初版：框架引擎 + 通用模块 + 知识库 + L4 继承机制 |
| 2026-09-04 | 1.3 | 14 模块补齐（+ task/issue/decision）+ KB capabilities 15 篇 + 228 测试全过 |
| 2026-09-03 | 1.2 | 6 项业界优化：Metadata-driven 字段 + Hybrid 多租户 + RLS + Workflow Scheme + Schema 版本控制 + 租户迁移 |
| 2026-09-03 | 1.1 | SaaS 预埋：tenant_id + 连接池抽象 + AuthProvider + RouteDef + 部署架构 |

---

## 相关文档

- 系统架构主文档: `../../00-system-architecture.md`
- L3 通用业务层: `../../02-generic-business-layer.md`
- L3 知识库体系架构: `../../03-knowledge-base-architecture.md`
- ADR-025: `../../../../knowledge-base/by-category/project-experience/adr/ADR-202609-025-delivery-management-framework.md`
- 知识库索引: `../../../../knowledge-base/README.md`
