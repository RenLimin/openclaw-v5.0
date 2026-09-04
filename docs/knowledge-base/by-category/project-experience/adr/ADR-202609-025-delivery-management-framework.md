---
type: adr
id: ADR-202609-025
date: 2026-09-03
title: L3 通用交付管理框架设计（DMS-Framework）
status: proposed
deciders: [Rex]
layers: [L3, L4]
tags: [delivery-management, framework, module-registry, raci, state-machine, saas, multi-tenant, metadata-driven]
supersedes: null
superseded_by: null
---

# [ADR-202609-025] L3 通用交付管理框架设计（DMS-Framework）

## 1. 状态
**proposed**

## 2. 背景

### 2.1 问题
Rex 要求建设"交付管理系统"，经过三轮对齐，确认：
- L3 层建设的**不是"一个具体的交付管理系统"**，而是**一套通用的交付管理框架**
- 该框架可被多个 L4 专有业务继承实例化（Bangcle 交付管理、未来其他业务交付管理）
- L4 合同审批（SCA-001）是交付管理框架的子模块，不是平级模块
- L4 Bangcle 交付管理系统将以 **SaaS 方式**提供互联网服务

### 2.2 核心约束
1. **统一入口**：统一 CLI 入口 `dms <module> <command>`，统一数据库 `delivery.db`
2. **热插拔**：功能模块通过 `ModuleManifest` 注册，运行时动态加载
3. **框架与业务分离**：L3 提供引擎 + 扩展点，L4 通过配置覆盖实例化
4. **角色-职责松耦合**：RACI 能力原子 + 项目级动态分配，不写死角色
5. **SaaS-ready**：数据结构预埋多租户，存储层可切换，认证接口抽象

### 2.3 涉及层级
- **L3 通用业务层**：框架引擎 + 通用模块 + 知识库
- **L4 专有业务层**：继承框架 + 专有配置（未来建设）

### 2.4 SaaS 目标
L4 Bangcle 交付管理系统将以 SaaS 方式提供互联网服务。L3 框架预埋：
- 多租户数据结构（tenant_id 所有表）
- 存储层抽象（SQLite → PostgreSQL → Citus）
- Hybrid 租户路由（Shared → Schema-per → Database-per）
- API 路由注册机制（RouteDef）
- 认证接口抽象（AuthProvider）
- PostgreSQL RLS 安全网

L4 实现具体 SaaS 业务逻辑：OAuth2/JWT、计费/配额、前端、部署。

### 2.5 业界调研（6 项优化）

深度调研 Salesforce / Jira / ONES / Plane.so / PostgreSQL RLS / Hybrid Tenancy 后，采纳 6 项优化：

| # | 优化 | 借鉴来源 | 纳入阶段 |
|---|------|---------|---------|
| 1 | Metadata-driven 自定义字段（custom_fields 元数据表） | Salesforce MT_Objects/MT_Fields | L3 |
| 2 | Hybrid 多租户路由（TenantRouter 三级路由） | Jira DB-per-tenant + 2026 trend | L3 接口 + L4 实现 |
| 3 | PostgreSQL RLS 数据库级安全网 | PostgreSQL RLS best practice | L4 |
| 4 | Workflow Scheme（Workflow ↔ 业务类型映射） | Jira Workflow Scheme | L3 |
| 5 | Schema diff/migrate 版本控制 | Plane.so schema diff/push | L3 |
| 6 | 租户迁移工具（共享 ↔ 独立） | Azure SQL Hybrid + Clerk | L4 |

## 3. 考虑的选项

### 选项 A: 建设"一个交付管理系统"
- 优点：开发简单，一次交付可用
- 缺点：不可复用，L4 要 fork 代码改；每个新业务重造轮子

### 选项 B: 建设框架，但模块平级独立
- 优点：模块独立开发
- 缺点：模块间集成成本高；合同审批与交付管理关系模糊

### 选项 C: 建设框架 + 模块注册 + 子模块嵌套 + SaaS-ready（✅ 选择）
- 优点：框架可复用，模块热插拔，合同审批作为子模块关系清晰，数据结构 SaaS-ready
- 缺点：开发成本高于单次系统（预估多 1.5-2 天）

## 4. 决策
我们选择 **选项 C**。核心理由：
1. 符合分层架构设计原则（L3 通用 → L4 专有）
2. 业界最佳实践对齐（Spring/WordPress/Salesforce 都是框架 + 实例化模式）
3. Rex 明确：L3 须满足多个 L4 业务的继承开发，最终 SaaS 化

## 5. 后果

### 5.1 正面
- L4 建设成本显著降低：拿框架 + 配置专有流程即可
- 模块可热插拔：新增业务模块只注册不改框架
- 知识库可复用：L4 继承通用知识 + 叠加专有知识
- 统一维护：框架 bug fix 一次，所有 L4 受益
- SaaS-ready：多租户数据结构 + 存储抽象 + RLS，L4 无需重构

### 5.2 负面
- 初始开发成本 +1.5-2 天
- 扩展点设计需要经验，过度设计/不足都有风险

### 5.3 风险
- **过度设计**：框架能力超出实际需求 → 缓解：基于实际需求设计扩展点
- **扩展点不足**：L4 实际扩展时发现要改框架 → 缓解：L4 建设时 review 扩展点
- **多租户性能**：共享 schema 大数据量 → 缓解：Hybrid 路由 + tenant_id 索引

## 6. 实现计划

- [ ] Phase 0: ADR-025 + DESIGN.md（本 ADR + 框架设计文档 v1.2）
- [ ] Phase 1: 框架引擎
  - [ ] ModuleRegistry + ModuleManifest
  - [ ] StateMachineEngine
  - [ ] RACIEngine
  - [ ] WorkflowScheme 引擎
  - [ ] EventBus
  - [ ] CLIFramework
  - [ ] BaseModel + Repository + 迁移（含 custom_fields + tenant_id）
  - [ ] TenantContext + AuthProvider 接口
  - [ ] RouteDef + API 路由注册
  - [ ] TenantRouter 接口（Hybrid 路由）
- [ ] Phase 2: 通用模块实现
  - [ ] project / milestone / deliverable / risk / raci
- [ ] Phase 3: 知识库
  - [ ] capabilities / methodologies / roles / templates / data-model / references
- [ ] Phase 4: 框架验证
  - [ ] 端到端测试 + 热插拔 + 扩展点 + Workflow Scheme 切换

## 7. 验证标准

| 指标 | 标准 | 验证方式 |
|------|------|---------|
| 框架可实例化 | 创建新项目无需改框架代码 | 端到端测试 |
| 模块热插拔 | 注册即用，移除不影响框架 | 测试模块验证 |
| 统一入口 | `dms <module> <command>` 访问所有模块 | CLI 实测 |
| 统一数据 | 共享 `delivery.db`，表命名隔离 | 数据库审查 |
| RACI 松耦合 | 同角色不同项目不同职责 | RACI 测试 |
| 状态机可配置 | 不改引擎定义新状态流 | 配置覆盖测试 |
| 自定义字段 | 注册 → 存储 → 检索全流程 | custom_fields CRUD |
| Workflow Scheme | 切换 Scheme 不丢数据 | Scheme 切换测试 |
| 知识召回率 | 业务问题召回相关知识 ≥ 80% | memory_search |
| L4 可扩展 | 模拟 L4 不改框架完成扩展 | 扩展点测试 |
| SaaS-ready | tenant_id 全表 + RLS 策略预留 | 数据库审查 |

## 8. 相关决策
- supersedes: null
- superseded_by: null
- 相关 ADR:
  - ADR-006: L2 持久化适配（复用 SQLite + Repository）
  - ADR-018: L4 销售合同审批模块（作为子模块集成）

## 9. 引用
- 框架设计文档：`docs/architecture/components/delivery-management-framework/DESIGN.md`
- 开源参考：
  - [Salesforce](https://architect.salesforce.com/docs/architect/fundamentals/guide/platform-multitenant-architecture.html) — Metadata-driven + multi-tenant
  - [Jira/Atlassian](https://www.atlassian.com/trust/reliability/cloud-architecture-and-operational-practices) — DB-per-tenant + TCS
  - [Plane.so](https://github.com/makeplane/plane) — Schema/Work 分离 + diff/push
  - [PostgreSQL RLS](https://learn.microsoft.com/en-us/azure/azure-sql/database/saas-tenancy-app-design-patterns) — Row-Level Security
  - [Hybrid Tenancy](https://www.arielsoftwares.com/multi-tenant-architecture-saas-guide) — 2026 best practice
- 方法论参考：PMBOK 8th / RACI / ITIL 4

## 10. 变更历史
- 2026-09-03: proposed (v1.0 框架设计)
- 2026-09-03: v1.1 (SaaS 预埋设计)
- 2026-09-03: v1.2 (6 项业界优化：Metadata-driven + Hybrid + RLS + Workflow Scheme + Schema 版本控制 + 租户迁移)
