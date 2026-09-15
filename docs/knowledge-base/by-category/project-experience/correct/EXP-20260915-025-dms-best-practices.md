---
title: "DMS 框架最佳实践与扩展指南"
id: EXP-20260915-025
date: 2026-09-15
type: correct
project: delivery-management-framework
category: project-experience
layers: [L3]
phase: manage
tags: [dms, best-practice, architecture, extension, lessons-learned]
---

# DMS 框架最佳实践与扩展指南

## 概述
本文汇总 DMS 交付管理框架的架构模式、最佳实践和踩坑经验，帮助开发者快速上手并正确扩展框架。适用对象：L3 框架维护者、L4 业务模块开发者。

---

## 一、架构模式

### 1.1 统一模块架构
每个模块都遵循相同的四层结构，保持一致性：

```
my_module/
├── __init__.py              # 导出 manifest 和工厂函数
├── my_module_model.py       # 数据模型（继承 BaseModel）
├── my_module_service.py     # 业务逻辑（可选，复杂模块需要）
└── module.py                # ModuleManifest + _factory()
```

**必须有**：
- ModuleManifest（声明模块元信息）
- `_factory(container)` 函数（创建模块实例）
- 数据模型（继承 BaseModel，获取 tenant_id 等公共能力）

### 1.2 模块间通信三原则

| 原则 | 说明 | 反例 |
|------|------|------|
| **事件优先** | 模块间通过 EventBus 通信，不直接调用 | `from other_module import xxx` |
| **数据隔离** | 模块只读写自己的表，不跨模块查表 | 直接 JOIN 其他模块的表 |
| **契约声明** | 依赖在 manifest.dependencies 中声明 | 隐式依赖（不声明但实际用了） |

**正确示例**：
```python
# ✅ 通过事件解耦
def handle_project_cancelled(event):
    project_id = event.entity_id
    # 处理本模块的响应逻辑
    self.defer_all_milestones(project_id)

# 在 manifest.hooks 中声明
manifest = ModuleManifest(
    name="milestone",
    hooks={"project.cancelled": "handle_project_cancelled"},
    dependencies=["project"]
)
```

**错误示例**：
```python
# ❌ 直接 import 和调用
from project.project_model import Project
projects = Project.query(...)  # 跨模块直接读数据
```

### 1.3 Repository 模式
所有数据访问通过 Repository 层，不直接写 SQL：

```python
# ✅ 正确
repo = BaseRepository(db_path, ProjectModel, "projects")
project = repo.get_by_id("proj-001")

# ❌ 错误
conn = sqlite3.connect(db_path)
conn.execute("SELECT * FROM projects WHERE id = ?", ("proj-001",))
```

好处：
- 租户隔离自动处理（不用每次写 `WHERE tenant_id = ?`）
- 切换数据库只改 Repository 类
- 统一的错误处理和日志

### 1.4 无状态状态机的正确用法
状态机引擎是无状态的，调用方需要自己维护状态：

```python
# 正确模式
current_state = project.status  # 从 DB 读
new_state = state_machine.trigger("project", current_state, "start")
if new_state:
    project.status = new_state   # 写回 DB
    project.save()
    event_bus.publish(Event("project.started", {...}))
```

**不要**在状态机里存状态——那会引入并发问题，且和存储耦合。

---

## 二、扩展新模块的标准流程

### 步骤 1：定义数据模型
```python
# my_module/my_module_model.py
from dataclasses import dataclass
from models.base import BaseModel

@dataclass
class MyModuleItem(BaseModel):
    project_id: str = ""
    title: str = ""
    status: str = "draft"
    
    @classmethod
    def table_name(cls):
        return "my_module_items"
```

### 步骤 2：定义状态机（如果需要状态流转）
```python
def _build_state_machine():
    return StateMachine(
        name="my_module",
        states=["draft", "active", "completed", "cancelled"],
        initial="draft",
        transitions=[
            Transition(event="activate", source="draft", target="active"),
            Transition(event="complete", source="active", target="completed"),
            Transition(event="cancel", source=["draft", "active"], target="cancelled"),
        ]
    )
```

### 步骤 3：定义模块服务类（可选）
```python
class MyModuleService:
    def __init__(self, container):
        self._container = container
        self._repo = BaseRepository(container.db_path, MyModuleItem)
```

### 步骤 4：定义 CLI 命令处理函数
```python
def create_handler(subparser):
    subparser.add_argument("--project-id", required=True)
    subparser.add_argument("--title", required=True)
    
    def execute(args):
        # 创建逻辑
        return 0
    return execute
```

### 步骤 5：声明 ModuleManifest
```python
# my_module/module.py
manifest = ModuleManifest(
    name="my_module",
    version="1.0.0",
    description="我的模块",
    tables=["my_module_items"],
    dependencies=["project"],
    commands=[
        CommandDef(name="my_module:create", handler=create_handler, description="创建"),
        CommandDef(name="my_module:list", handler=list_handler, description="列表"),
    ],
    hooks={
        "project.cancelled": "on_project_cancelled",
    }
)

def _factory(container):
    return MyModuleService(container)
```

### 步骤 6：注册到框架
```python
# 在框架启动时
registry.register(my_module.manifest, my_module._factory)
```

完成！新模块自动出现在 CLI、EventBus、依赖图中。

---

## 三、常见踩坑与避坑指南

### 坑 1：Database save 后没 commit
**症状**：create 成功但 get 查不到
**原因**：`BaseModel.save()` 只执行 SQL，不调用 `commit()`
**避坑**：Repository 层的 insert/update/delete 末尾必须加 `conn.commit()`
**当前状态**：BaseRepository 已修复，使用正确模式

### 坑 2：TenantContext 与 Database._tenant 脱节
**症状**：测试里 `TenantContext.set("test")` 但查询仍用 "system"
**原因**：Database 自己维护了 `_tenant` 变量，不读 TenantContext
**避坑**：所有租户查询统一走 `TenantContext.current()`，不要自己存一份
**当前状态**：BaseRepository 已修复，使用 `_current_tenant()` 方法

### 坑 3：空字符串 vs NULL 的外键约束
**症状**：work_item_id 默认 ""，触发外键约束失败
**原因**：SQLite 中外键约束对空字符串也检查，空串 != NULL
**避坑**：可选外键的默认值用 `None`，数据库存 NULL
**当前状态**：RACI 模块已修复

### 坑 4：并行开发的 API 不一致
**症状**：多个 subagent 并行开发，transition 返回值格式不统一
**原因**：没有先定 API 契约就开工
**避坑**：并行开发前必须给出精确的 API 契约，包括：
- 函数签名
- 参数类型
- 返回值类型和格式
- 异常类型

### 坑 5：subagent 产出幻觉
**症状**：subagent 报告"完成了"，但文件目录是空的
**原因**：subagent 可能把"计划做的"当成"已经做完的"
**避坑**：
- 每批 subagent 任务必须包含**明确的验证命令**
- 主 agent 必须**逐条验证文件存在**，不能信汇报
- 写文件任务要给具体的 `cat > file << EOF` 式指令

### 坑 6：不要信"看起来像"
**症状**：看到 key 长度像 17 位就判"是明文凭据"
**原因**：用启发式代替实证
**避坑**：
- 所有判断必须有实际证据（运行命令、读文件、查文档）
- "看起来像"只能作为线索，不能作为结论
- 确认的代价远低于误判的代价

---

## 四、性能最佳实践

### 4.1 RACI 查询走内存
RACI 引擎是内存版的，查询极快。不要为了"持久化"而每次查 DB——
- 写操作：DB + 内存双写
- 读操作：直接走内存
- 启动时：从 DB 加载到内存

### 4.2 Repository 批量操作
大量数据操作时，避免循环调用 `insert()`，用批量插入：

```python
# 低效：循环 insert
for item in items:
    repo.insert(item)

# 高效：批量 insert（需自行实现 execute many）
repo.bulk_insert(items)
```

> 当前 BaseRepository 未提供 bulk_insert，可根据需要扩展。

### 4.3 事件不要发太细
事件粒度要适中：
- **太粗**：`project.updated` — 改了什么不知道，订阅者全量刷新
- **太细**：`project.name_changed` / `project.owner_changed` — 事件爆炸，订阅者要订阅一堆
- **适中**：`project.status_changed` / `project.created` / `project.deleted` — 有明确业务语义

判断标准：订阅者拿到这个事件后，能不能知道该做什么。

---

## 五、测试最佳实践

### 5.1 核心引擎测试要充分
状态机、RACI、EventBus 这些引擎是框架的基础，测试覆盖率必须 100%：
- 正常路径
- 边界条件
- 异常输入
- 并发场景（如果有状态）

### 5.2 跨模块联动必须测 E2E
单元测试只能测单个模块，事件联动、级联效应必须有 E2E 测试：
- project.cancelled → 各子模块是否正确响应？
- 模块卸载 → 其他模块是否受影响？
- 循环依赖检测 → 会不会死循环？

### 5.3 测试金字塔
```
    /   E2E 测试    \    少量（关键路径）
   /  集成测试       \   中量（模块间交互）
  /  单元测试         \  大量（每个函数）
```

---

## 六、演进路线参考

当前是骨架版，未来可以按以下方向演进（优先级从高到低）：

### Phase 3：业务模块扩展
- milestone / deliverable / risk 模块
- WorkflowScheme 引擎（工作流方案切换）
- custom_fields 元数据表（元数据驱动自定义字段）

### Phase 4：SaaS 能力
- TenantRouter（Hybrid 多租户路由）
- AuthProvider（认证接口抽象）
- PostgreSQL 适配 + RLS

### Phase 5：平台化
- 模块市场（第三方模块安装/管理）
- API 层（FastAPI / GraphQL）
- Web UI
- 权限系统（基于 RACI）

---

## 七、代码质量约定

### 7.1 文件行数
- 单个模块主文件：≤ 300 行
- 引擎文件：≤ 300 行
- 测试文件：不限，但一个测试类不超过 20 个用例

超过说明可能职责过多，考虑拆分。

### 7.2 命名约定
| 类型 | 格式 | 示例 |
|------|------|------|
| 模块名 | snake_case | `project`, `work_item` |
| 类名 | PascalCase | `ProjectService`, `StateMachineEngine` |
| 函数名 | snake_case | `create_project`, `get_by_id` |
| 事件名 | `entity.action` | `project.created`, `raci.assignment_changed` |
| 命令名 | `module:action` | `project:create`, `raci:matrix` |

### 7.3 日志约定
- `logger.debug`：详细调试信息（每次调用）
- `logger.info`：重要状态变更（注册、注销、初始化完成）
- `logger.warning`：非致命异常（重复注册、注销不存在的）
- `logger.error`：错误（handler 抛异常、DB 操作失败）

---

## 八、相关资源

### 核心文档
- [ADR-025 框架设计决策](../adr/ADR-202609-025-delivery-management-framework.md)
- [DESIGN.md 框架设计文档](../../../../architecture/components/delivery-management-framework/DESIGN.md)
- [README.md 使用说明](L3-business/components/delivery-management-framework/README.md)

### 能力卡片
- [模块注册引擎](EXP-20260915-020-dms-module-registry-capability.md)
- [状态机引擎](EXP-20260915-021-dms-state-machine-capability.md)
- [RACI 引擎](EXP-20260915-022-dms-raci-capability.md)
- [事件总线](EXP-20260915-023-dms-event-bus-capability.md)

### 使用指南
- [CLI 使用指南](EXP-20260915-024-dms-cli-usage-guide.md)

### 参考
- PMBOK 8th — 项目管理知识体系
- RACI Matrix — 责任分配矩阵标准
- Enterprise Integration Patterns — 企业集成模式
- Domain-Driven Design — 领域驱动设计

---

_本文持续更新，有新的踩坑和最佳实践请补充到这里。_
