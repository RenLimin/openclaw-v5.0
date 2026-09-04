---
title: "DMS Framework L3 Complete"
id: EXP-20260903-010
date: 2026-09-03
type: correct
project: delivery-management-framework
tags: [dms, framework, l3, modules, complete]
---

# DMS 框架 L3 全模块建设经验

## 背景
Phase 4 端到端验证通过后，Rex 拍板完整完成 L3 建设。在已有 5 模块（project/milestone/deliverable/risk/raci）基础上，补齐剩余 6 个能力域模块。

## 成果
**11 个模块全部完成**，覆盖 12 个能力域：

| # | 模块 | 能力域 | 行数 | 状态 |
|---|------|--------|------|------|
| 1 | project | scope_management | 236 | ✅ |
| 2 | milestone | schedule_management + milestone_tracking | 438 | ✅ |
| 3 | deliverable | deliverable_management | 225 | ✅ |
| 4 | risk | risk_management | 284 | ✅ |
| 5 | raci | stakeholder_management（部分） | 303 | ✅ |
| 6 | quality | quality_management | 360 | ✅ |
| 7 | resource | resource_management | 320 | ✅ |
| 8 | budget | budget_management | 316 | ✅ |
| 9 | communication | communication_management | 312 | ✅ |
| 10 | contract | contract_interface | 316 | ✅ |
| 11 | sla | sla_tracking | 357 | ✅ |

**总计：3,467 行代码**

## 统一架构模式

所有 10 个子模块完全一致的架构模式：

```
BaseModel (dataclass, __tablename__="work_items", type=xxx)
  ↓
_build_state_machine() → StateMachine（6-7 状态 + 6-8 迁移）
  ↓
BaseModule 子类（initialize / on_ready / _bus / _publish）
  ↓
6 个 CLI 命令（create/list/get/transition/delete/<feature>）
  ↓
ModuleManifest + _factory(m)
```

**统一约定**：
- 数据存在 `work_items` 表，用 `type` 字段区分模块
- 专有字段存 `metadata` JSON，通过 `@property` 访问器暴露
- 每个模块订阅 `project.cancelled` 事件，自动处理子项联动
- 版本迁移：`@migration("1.2.0")` 添加部分索引
- 依赖：`dependencies=["project"]`

## 状态机模式

| 模块 | 起始状态 | 终态 | 关键迁移 |
|------|---------|------|---------|
| project | planning | completed/cancelled | start/pause/resume/submit/accept/cancel |
| milestone | pending | achieved/missed/cancelled/deferred | start/achieve/miss/defer/restart |
| deliverable | draft | accepted/rejected/withdrawn | submit/approve/reject/revise/withdraw |
| risk | identified | resolved/accepted/closed | analyze/plan/resolve/occur/accept/close |
| quality | identified | verified/closed | start_review/pass/fail/re_review/verify/close |
| resource | requested | released/cancelled | allocate/release/reallocate/cancel |
| budget | draft | closed/cancelled | approve/execute/overrun/revise/close |
| communication | planned | completed/cancelled | start/complete/escalate/cancel |
| contract | draft | fulfilled/rejected/terminated | submit/approve/reject/fulfill/dispute/terminate |
| sla | defined | —（持续监控） | start_monitoring/meet/breach/escalate/close |

## 事件联动机制

`project.cancelled` 事件触发 10 个子模块自动响应：

| 模块 | 响应动作 |
|------|---------|
| milestone | pending→deferred, in_progress→missed |
| deliverable | draft→withdrawn |
| risk | identified→closed |
| quality | identified→closed |
| resource | allocated→released, requested→cancelled |
| budget | draft→cancelled, executing→closed |
| communication | planned→cancelled |
| contract | draft→terminated, active→terminated |
| sla | 非终态→closed |
| raci | 订阅 project.deleted，清理分配 |

证明 EventBus 解耦架构有效——模块间零直接调用。

## 开发效率

**6 个新模块并行开发，约 22 分钟完成**（受 subagent 并发上限 5 限制）：
- quality: 5m10s
- resource: 17m13s
- budget: 10m56s
- communication: 20m29s
- contract: 21m57s
- sla: 13m10s

**关键经验**：
1. 统一的架构模式让并行开发效率极高——每个 subagent 拿到相同模板就能产出
2. `work_items` 单表 + type 区分的设计让新模块零 schema 变更（只加索引）
3. 每个模块约 300 行，符合 150-250 的软目标（因 metadata 属性访问器 + 额外查询命令略超）

## 教训

### 1. 不要信 subagent 的完成报告，自己跑验证
方法论 subagent 幻觉的教训：每个 subagent 完成后必须 `ls + python3 -c "from modules.xxx import manifest"` 验证。

### 2. ID 提取正则要统一
deliverable 的 create 输出格式跟其他模块不同（ID 和状态在同一对括号里），导致 sed 提取 ID 时截错。
**修正**：用 `grep -oE 'ID: [a-f0-9-]+'` 统一提取，不依赖括号位置。

### 3. 状态机迁移名是契约
每个模块的迁移名不完全一致（有的叫 `start`，有的叫 `start_review`），上层调用方必须从 manifest 或状态机查询，不能硬编码猜测。

## 下一步
- L4 实例化：把 Bangcle SCA-001 合同审批迁移为 DMS 的 L4 模块
- 更多模块：task（任务管理）、issue（问题管理）、decision（决策记录）
- API 层：FastAPI 封装，支持 HTTP 调用

## 参考
- [EXP-001](EXP-20260903-001-dms-framework-phase1.md)
- [EXP-002](EXP-20260903-002-dms-framework-phase2.md)
- [EXP-003](EXP-20260903-003-dms-framework-phase3.md)
- [EXP-004](EXP-20260903-004-dms-framework-phase4.md)
- [ADR-025](../../adr/ADR-202609-025-delivery-management-framework.md)
