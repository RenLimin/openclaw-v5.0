---
title: "DMS 框架 Phase 2 通用模块建设经验"
id: EXP-20260903-007
date: 2026-09-03
type: correct
project: delivery-management-framework
tags: [dms, framework, phase2, modules, multi-tenant]
---

# DMS 框架 Phase 2 通用模块建设经验

## 背景
Phase 1 完成 9 个核心引擎模块后，Phase 2 建设 5 个通用业务模块。

## 方案
5 个模块，全部基于 BaseModule + Repository + StateMachine + EventBus 构建：

| 模块 | 行数 | 状态数 | 迁移数 | 表 |
|------|------|--------|--------|-----|
| project | 236 | 6 | 7 | projects |
| milestone | 438 | 5 | 5 | work_items (type=milestone) |
| deliverable | 225 | 5 | 5 | work_items (type=deliverable) |
| risk | 284 | 7 | 7 | work_items (type=risk) |
| raci | 299 | — | — | responsibility_assignments |

## 关键设计

### 1. 统一工作项模型（discriminator pattern）
milestone / deliverable / risk 共用 `work_items` 表，通过 `type` 字段区分。
- **优点**：减少表数量，统一查询模式
- **代价**：特有字段存 JSON（custom_data），类型安全靠应用层
- **参考**：Jira / Plane.so 都采用类似模式

### 2. 跨模块通信：EventBus，不直接调用
- project.cancelled → milestone/deliverable/risk 自动处理
- project.deleted → raci 自动清理
- 模块间不直接 import，靠事件解耦

### 3. 双写策略（RACI 模块）
持久化 RACI 采用 DB + 内存双写：
- 写操作：先 DB 后内存
- 读操作：走内存（快）
- 启动时：从 DB 加载到内存
- 事件：变更后发布事件

### 4. 模块生命周期
register → initialize（建表+注册状态机+初始化仓储）→ on_ready（跨模块订阅）

## 踩过的坑

### 1. Database.save() 没有 commit
- **问题**：create 成功但 get 查不到
- **根因**：BaseModel.save() 只执行 INSERT/UPDATE，不 commit
- **修复**：save() / delete() 末尾加 `db.commit()`

### 2. Database._tenant 与 TenantContext 脱节
- **问题**：测试里 `TenantContext.set("test")` 但查询仍用 "system"
- **根因**：Database 有自己的 `_tenant` 变量，不读 TenantContext
- **修复**：`get_current_tenant()` 优先读 TenantContext，回退到 `_tenant`

### 3. Python 3.12+ sqlite3 timestamp converter 弃用
- **问题**：ISO 格式时间戳（带 T）触发 ValueError
- **根因**：sqlite3 默认 timestamp converter 期望 `YYYY-MM-DD HH:MM:SS`
- **修复**：模块加载时清除默认 converter，时间统一存 ISO 字符串

### 4. RACI 外键约束 + 空字符串
- **问题**：work_item_id 默认 ""，触发外键约束失败
- **根因**：空字符串 ≠ NULL，SQLite 外键约束对空串也检查
- **修复**：默认值改为 None，数据库存 NULL

### 5. 5 个 subagent 并行开发的 API 不一致
- **问题**：transition 返回值不统一（有的返回对象，有的返回元组）
- **教训**：并行开发必须先给精确的 API 契约，包括返回值类型

## 验证
- 63 个测试全过（单元 + 集成 + 模块）
- CLI 端到端可用
- 端到端交付全流程验证通过（建项目→建里程碑→建交付物→建风险→分配RACI→流转→验收）

## 下一步
Phase 3：知识库（12 能力 + 6 角色 + 8 模板 + 方法论）

## 参考
- [ADR-025](ADR-202609-025-delivery-management-framework.md)
- [DESIGN.md](../../../architecture/components/delivery-management-framework/DESIGN.md)
- [EXP-001](EXP-20260903-001-dms-framework-phase1.md)
