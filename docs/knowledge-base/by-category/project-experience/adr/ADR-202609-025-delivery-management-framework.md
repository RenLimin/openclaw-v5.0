---
type: adr
id: ADR-202609-025
date: 2026-09-03
title: L3 通用交付管理框架设计（DMS-Framework）
status: accepted
deciders: [Rex]
layers: [L3, L4]
tags: [delivery-management, framework, module-registry, raci, state-machine, multi-tenant]
supersedes: null
superseded_by: null
---

# [ADR-202609-025] L3 通用交付管理框架设计（DMS-Framework）

## 1. 状态
**accepted**（设计已接受，当前为骨架实现阶段）

**落地状态（2026-09-15 更新）：**

| 模块 | 设计目标 | 当前状态 | 位置 |
|------|---------|---------|------|
| ModuleRegistry + ModuleManifest | ✅ 热插拔 + 依赖解析 | ✅ 已实现 | `registry/module_registry.py` |
| StateMachineEngine | ✅ 无状态 + guards + hooks | ✅ 已实现 | `state_machine/state_machine.py` |
| RACIEngine | ✅ 能力原子 + 角色模板 + 冲突检测 | ✅ 已实现（内存版） | `raci/raci.py` |
| EventBus | ✅ Pub/Sub + 历史记录 | ✅ 已实现 | `event_bus/event_bus.py` |
| CLIFramework | ✅ 统一入口 + 命令自动注册 | ✅ 已实现 | `cli/cli.py` |
| BaseModel + TenantContext | ✅ 多租户 + 统一 CRUD | ✅ 已实现 | `models/base.py` |
| BaseRepository | ✅ SQLite + 租户隔离 | ✅ 已实现 | `repo/base_repo.py` |
| Project 模块 | ✅ 项目管理 | ✅ 模型已实现 | `project/project_model.py` |
| WorkItem 模块 | ✅ 工作项 | ✅ 模型已实现 | `work_item/work_item_model.py` |
| Stakeholder 模块 | ✅ 干系人 | ✅ 模型已实现 | `stakeholder/stakeholder_model.py` |
| ChangeLog 模块 | ✅ 变更日志 | ✅ 模型已实现 | `change_log/change_log_model.py` |
| Responsibility 模块 | ✅ 责任分配 | ✅ 模型已实现 | `responsibility/assignment_model.py` |
| ProjectMember 模块 | ✅ 项目成员 | ✅ 模型已实现 | `project_member/project_member_model.py` |
| WorkflowScheme 引擎 | 3 内置方案 + 项目级覆盖 | ⏳ 未实现（骨架版） | — |
| custom_fields 元数据表 | Metadata-driven 自定义字段 | ⏳ 未实现（骨架版） | — |
| Milestone / Deliverable / Risk 模块 | 5 个通用业务模块 | ⏳ 未实现（骨架版） | — |
| TenantRouter / AuthProvider | SaaS 多租户路由 | ⏳ 未实现（骨架版） | — |
| 迁移管理器 (MigrationManager) | Schema 版本控制 | ⏳ 未实现（骨架版） | — |

**实现版本说明：** 当前 `L3-business/components/delivery-management-framework/` 为**骨架版**（约 800 行核心代码 + 109 测试），核心引擎齐备，业务模块为数据模型级实现。完整版设计（11 模块 + SaaS + custom_fields）作为演进方向保留。

## 2. 背景

### 2.1 问题
Rex 要求建设"交付管理系统"，经过三轮对齐，确认：
- L3 层建设的**不是"一个具体的交付管理系统"**，而是**一套通用的交付管理框架**
- 该框架可被多个 L4 专有业务继承实例化（Bangcle 交付管理、未来其他业务交付管理）
- L4 合同审批（SCA-001）是交付管理框架的子模块，不是平级模块

### 2.2 核心约束
1. **统一入口**：统一 CLI 入口 `dms <module> <command>`，统一数据库 `delivery.db`
2. **热插拔**：功能模块通过 `ModuleManifest` 注册，运行时动态加载
3. **框架与业务分离**：L3 提供引擎 + 扩展点，L4 通过配置覆盖实例化
4. **角色-职责松耦合**：RACI 能力原子 + 项目级动态分配，不写死角色
5. **多租户就绪**：数据结构预埋 tenant_id，存储层 Repository 模式抽象

### 2.3 涉及层级
- **L3 通用业务层**：框架引擎 + 通用模块 + 知识库
- **L4 专有业务层**：继承框架 + 专有配置（未来建设）

## 3. 考虑的选项

### 选项 A: 建设"一个交付管理系统"
- 优点：开发简单，一次交付可用
- 缺点：不可复用，L4 要 fork 代码改；每个新业务重造轮子

### 选项 B: 建设框架，但模块平级独立
- 优点：模块独立开发
- 缺点：模块间集成成本高；合同审批与交付管理关系模糊

### 选项 C: 建设框架 + 模块注册 + 子模块嵌套（✅ 选择）
- 优点：框架可复用，模块热插拔，合同审批作为子模块关系清晰
- 缺点：初始开发成本高于单次系统

## 4. 决策
我们选择 **选项 C**。核心理由：
1. 符合分层架构设计原则（L3 通用 → L4 专有）
2. 业界最佳实践对齐（Spring/WordPress/Salesforce 都是框架 + 实例化模式）
3. Rex 明确：L3 须满足多个 L4 业务的继承开发

## 5. 后果

### 5.1 正面
- L4 建设成本显著降低：拿框架 + 配置专有流程即可
- 模块可热插拔：新增业务模块只注册不改框架
- 知识库可复用：L4 继承通用知识 + 叠加专有知识
- 统一维护：框架 bug fix 一次，所有 L4 受益

### 5.2 负面
- 初始开发成本高于单次系统
- 扩展点设计需要经验，过度设计/不足都有风险

### 5.3 风险
- **过度设计**：框架能力超出实际需求 → 缓解：基于实际需求设计扩展点
- **扩展点不足**：L4 实际扩展时发现要改框架 → 缓解：L4 建设时 review 扩展点

## 6. 实现计划（骨架版）

- [x] Phase 0: ADR-025 + DESIGN.md
- [x] Phase 1: 核心引擎（6 个）
  - [x] ModuleRegistry + ModuleManifest + 依赖解析
  - [x] StateMachineEngine（无状态 + guards + hooks）
  - [x] RACIEngine（12 能力原子 + 6 角色模板 + 冲突检测）
  - [x] EventBus（Pub/Sub + 历史记录）
  - [x] CLIFramework（命令自动注册）
  - [x] BaseModel + TenantContext + BaseRepository
- [x] Phase 2: 基础数据模型（6 个）
  - [x] Project / WorkItem / Stakeholder
  - [x] ChangeLog / Responsibility / ProjectMember
- [x] Phase 3: 测试覆盖（109 个测试全过）
- [ ] Phase 4: 知识库文档（进行中）
- [ ] 未来演进：WorkflowScheme + custom_fields + 更多业务模块 + SaaS

## 7. 验证标准

| 指标 | 标准 | 验证方式 | 当前状态 |
|------|------|---------|---------|
| 模块热插拔 | 注册即用，移除不影响框架 | 测试模块验证 | ✅ |
| 统一入口 | `dms <module> <command>` 访问所有模块 | CLI 实测 | ✅ |
| RACI 松耦合 | 同角色不同项目不同职责 | RACI 测试 | ✅ |
| 状态机可配置 | 不改引擎定义新状态流 | 配置覆盖测试 | ✅ |
| 多租户隔离 | tenant_id 过滤，数据互不可见 | Repository 测试 | ✅ |
| 事件解耦 | 模块间通过 EventBus 通信，不直接调用 | EventBus 测试 | ✅ |
| 测试覆盖 | 核心引擎 + 数据模型全覆盖 | pytest 109 passed | ✅ |

## 8. 相关决策
- supersedes: null
- superseded_by: null
- 相关 ADR:
  - ADR-006: L2 持久化适配（复用 SQLite + Repository 模式思路）
  - ADR-018: L4 销售合同审批模块（作为子模块集成的参考范例）

## 9. 引用
- 框架设计文档：`L3-business/components/delivery-management-framework/DESIGN.md`
- 框架 README：`L3-business/components/delivery-management-framework/README.md`
- 核心代码：`L3-business/components/delivery-management-framework/`
- 方法论参考：PMBOK 8th / RACI / ITIL 4

## 10. 变更历史
- 2026-09-03: proposed (v1.0 框架设计，完整版目标)
- 2026-09-03: v1.1 (SaaS 预埋设计 + 6 项业界优化)
- 2026-09-03: v1.2 (业界优化补充：Metadata-driven + Hybrid + RLS + Workflow Scheme)
- 2026-09-15: v1.3 (**落地状态校准** — 标注当前为骨架实现，完整版设计作为演进方向保留；移除未实现项的"已完成"标记；补充实际落地模块清单与验证状态)
