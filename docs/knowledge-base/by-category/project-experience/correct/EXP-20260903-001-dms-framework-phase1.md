---
title: "DMS 框架 Phase 1 核心引擎建设经验"
id: EXP-20260903-001
date: 2026-09-03
type: correct
project: delivery-management-framework
tags: [dms, framework, phase1, core-engine, multi-tenant]
---

# DMS 框架 Phase 1 核心引擎建设经验

## 背景
建设 L3 通用交付管理框架 Phase 1（框架引擎），目标 11 个组件。

## 方案
9 个核心引擎模块 + 统一 CLI + 迁移系统 + 测试：

| 模块 | 行数 | 职责 |
|------|------|------|
| module.py | 221 | ModuleRegistry + ModuleManifest（热插拔） |
| state_machine.py | 269 | 无状态状态机 + Engine（guards + hooks） |
| raci.py | 374 | RACI 引擎（12 能力原子 + 6 角色模板 + 冲突检测） |
| workflow_scheme.py | 198 | WorkflowScheme（3 个内置方案 + 项目级覆盖） |
| event_bus.py | 173 | Pub/Sub 事件总线 + 历史记录 |
| cli.py | 297 | CLI 框架（统一入口 dms <module> <command>） |
| database.py | 309 | Database 抽象 + BaseModel + Repository + MigrationManager |
| saas.py | 235 | TenantContext + AuthProvider + TenantRouter + RouteDef |
| migrations.py | 201 | DDL 迁移（7 业务表 + 索引 + 自定义字段） |

总计 2404 行核心代码，46 个测试全部通过。

## 关键决策

### 1. 状态机无状态化
StateMachine 不持有 current_state，fire 方法接收 current_state 参数，返回 (from_state, to_state)。
- **优点**：纯函数、易测试、可并发、状态存储解耦（DB/Redis/内存随意）
- **代价**：调用方需自己维护状态

### 2. RACI 引擎纯内存版
Phase 1 用 dict 存储，不依赖 DB。Phase 2 加 Repository 持久化。
- 理由：先验证引擎逻辑正确性，再加存储
- 设计：`assign(key)` 是 upsert，不是 insert（幂等）

### 3. 3 个内置 Workflow Scheme
default（标准）/ agile（敏捷）/ waterfall（瀑布），开箱即用。
- 项目级覆盖：`set_project_scheme(project_id, scheme_name)`
- 全局激活 + 项目级覆盖的双层模式

### 4. custom_fields 元数据表
借鉴 Salesforce MT_Objects/MT_Fields 模式，租户级自定义字段。
- 6 种类型：text/number/date/boolean/select/multiselect
- UNIQUE(tenant_id, entity_type, field_name) 防重

## 验证
- 46 个单元 + 集成测试全过
- CLI end-to-end：init → create → list → schema diff 全链路
- 多租户隔离验证：tenant_a 和 tenant_b 数据互不可见

## 经验
1. **先写测试再对齐 API**：subagent 写的代码 API 与设计文档有偏差，靠测试快速对齐
2. **无状态状态机是正确选择**：比有状态灵活得多，存储层随便换
3. **RACI upsert > 唯一约束报错**：业务上更新分配比拒绝更合理
4. **DB 抽象要早做**：SQLite → PostgreSQL 切换只改 Database 类

## 下一步
Phase 2：5 个通用模块（project/milestone/deliverable/risk/raci）

## 参考
- [ADR-025](ADR-202609-025-delivery-management-framework.md)
- [DESIGN.md](../../../architecture/components/delivery-management-framework/DESIGN.md)
