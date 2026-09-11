# delivery-management-framework

## 设计目标

为交付管理提供领域驱动设计（DDD）骨架，包含项目管理、RACI 矩阵、状态机、事件总线等核心能力。解决交付流程中职责不清、状态混乱、模块耦合的问题。

## 架构决策

- **领域驱动设计（DDD）**：按业务领域划分模块（project/work_item/stakeholder 等），每个模型独立演进
- **统一 BaseModel**：所有领域模型继承 `BaseModel`，统一 `tenant_id`、`created_at`、`updated_at` 和 CRUD 接口
- **模块注册引擎**：`ModuleRegistry` 自动发现模块、解析依赖、管理生命周期
- **事件驱动**：`EventBus` 实现发布/订阅模式，模块间解耦通信
- **状态机引擎**：`StateMachineEngine` 提供显式状态定义和转移规则
- **RACI 责任矩阵**：独立引擎管理 Responsible/Accountable/Consulted/Informed 角色分配
- **统一 CLI 框架**：命令自动注册，通过 `dms_cli.py` 统一入口

## 模块划分

```
delivery-management-framework/
├── dms_cli.py                  # CLI 统一入口
├── cli/                        # CLI 框架（命令注册/分发）
├── models/                     # 基础模型
│   └── base.py                 # BaseModel（tenant_id + CRUD）
├── project/                    # 项目管理
├── project_member/             # 项目成员
├── work_item/                  # 工作项管理
├── stakeholder/                # 利益相关者
├── responsibility/             # 责任分配
├── change_log/                 # 变更日志
├── raci/                       # RACI 引擎
├── state_machine/              # 状态机引擎
├── event_bus/                  # 事件总线
├── registry/                   # 模块注册引擎
├── repo/                       # 通用仓储基类
├── migrations/                 # 数据库迁移
└── tests/                      # 单元测试
```

## 关键接口/数据结构

- `BaseModel`：所有模型基类，提供 `tenant_id`、`is_deleted`、CRUD 方法
- `ModuleRegistry`：模块注册，支持自动发现、依赖解析、生命周期管理
- `EventBus`：事件总线，`publish(event, data)` / `subscribe(event, handler)`
- `StateMachineEngine`：状态机，定义状态集合、转移规则、事件触发
- `RACIEngine`：RACI 矩阵，管理角色分配和查询
- `Project`：项目模型，含名称、状态、成员列表
- `WorkItem`：工作项模型，关联项目和负责人

## 依赖关系

- **依赖**：Python 3.10+、SQLite/MySQL
- **被依赖**：`dms-framework`（DMS-Framework 组件，继承并扩展本框架能力）

## 演进方向

1. **与 dms-framework 整合**：DMS-Framework 已包含更完整的模块（tenant/milestone/deliverable 等），未来可能合并
2. **工作流引擎**：从状态机升级为完整工作流，支持并行审批
3. **权限系统**：基于 RACI 模型实现细粒度权限控制
4. **API 层**：暴露 RESTful API 供外部系统集成
