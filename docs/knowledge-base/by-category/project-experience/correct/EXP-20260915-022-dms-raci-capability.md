---
title: "DMS 能力卡片：RACI 职责矩阵引擎 (RACIEngine)"
id: EXP-20260915-022
date: 2026-09-15
type: correct
project: delivery-management-framework
category: project-experience
layers: [L3]
phase: manage
tags: [dms, capability, raci, responsibility, role-template]
---

# DMS 能力卡片：RACI 职责矩阵引擎 (RACIEngine)

## 概述
RACI 引擎是 DMS 框架的"角色-职责分配中枢"，基于 **能力原子 → 角色模板 → 实际分配** 三层模型，实现灵活的职责矩阵管理。解决交付项目中"谁负责什么"模糊不清的问题。

## 核心价值
- **能力原子化**：最小粒度职责单元，可灵活组合成角色
- **角色模板化**：预置 6 种标准角色，也可自定义
- **动态分配**：同一角色在不同项目可分配给不同的人
- **冲突检测**：自动发现 RACI 分配中的冲突和盲区
- **松耦合**：不写死角色，只写能力，业务变化无需改引擎

## 三层模型

```
Capability（能力原子）
    ↓ 组合
RoleTemplate（角色模板）
    ↓ 实例化
Assignment（实际分配，project + member + capability + raci_role）
```

### 第一层：Capability（能力原子）
最小粒度的职责单元，不可再分：

| ID | 名称 | 说明 |
|----|------|------|
| `scope_management` | 范围管理 | 范围定义、WBS、变更控制 |
| `schedule_management` | 进度计划 | 进度计划、关键路径、里程碑 |
| `risk_management` | 风险管理 | 风险识别、评估、应对 |
| `stakeholder_management` | 干系人管理 | 干系人识别、沟通计划 |
| `quality_management` | 质量管理 | 质量标准、验收、回顾 |
| `deliverable_management` | 交付物管理 | 交付物定义、评审、验收 |
| `resource_management` | 资源管理 | 人力、设备、预算分配 |
| `communication_management` | 沟通管理 | 沟通计划、报告、会议 |
| `procurement_management` | 采购管理 | 供应商、合同、采购流程 |
| `integration_management` | 整合管理 | 整体协调、变更控制 |
| `cost_management` | 成本管理 | 预算、成本控制、决算 |
| `issue_management` | 问题管理 | 问题跟踪、升级、闭环 |

共 12 个内置能力原子，开箱即用。

### 第二层：RoleTemplate（角色模板）
能力原子的组合，定义"某种角色应该具备哪些能力"：

| 角色 | 核心能力 |
|------|---------|
| `project_manager` | integration + scope + schedule + communication |
| `tech_lead` | quality + deliverable + issue |
| `business_analyst` | scope + stakeholder + communication |
| `qa_engineer` | quality + risk + deliverable |
| `product_owner` | scope + stakeholder + integration |
| `stakeholder_rep` | stakeholder + communication |

共 6 个内置角色模板。

### 第三层：Assignment（实际分配）
具体项目中的实际人员分配：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | str | 分配记录 ID |
| `project_id` | str | 所属项目 |
| `member_id` | str | 成员 ID |
| `capability` | str | 能力原子 ID |
| `raci_role` | str | RACI 角色：R/A/C/I |
| `work_item_id` | Optional[str] | 工作项级分配（可选） |
| `notes` | Optional[str] | 备注 |

**RACI 定义：**
- **R (Responsible)**：负责执行 — 实际干活的人
- **A (Accountable)**：最终担责 — 对结果最终负责的人（每个任务有且只有一个 A）
- **C (Consulted)**：咨询 — 需要被征求意见的人
- **I (Informed)**：知情 — 需要被告知结果的人

## 核心 API

| 方法 | 说明 |
|------|------|
| `assign(project_id, member_id, capability, raci_role, work_item_id=None)` | 分配职责（upsert） |
| `unassign(assignment_id)` | 取消分配 |
| `get_assignments_by_project(project_id)` | 获取项目所有分配 |
| `get_assignments_by_member(member_id, project_id=None)` | 获取成员的分配 |
| `get_assignments_by_capability(capability, project_id)` | 按能力查询分配 |
| `get_raci_matrix(project_id)` | 生成 RACI 矩阵表 |
| `detect_conflicts(project_id)` | 检测分配冲突 |
| `get_coverage(project_id)` | 获取能力覆盖情况 |
| `apply_role_template(project_id, member_id, template_name, raci_role)` | 按角色模板批量分配 |
| `register_role_template(template)` | 注册自定义角色模板 |
| `register_capability(capability)` | 注册自定义能力原子 |

## 关键特性

### 1. Upsert 语义
`assign()` 是 upsert 不是 insert——同一 project + member + capability + raci_role 组合重复调用会更新而不是报错。
- **业务合理性**：调整分配比拒绝重复更合理
- **幂等性**：同一个操作执行多次结果一致

### 2. 冲突检测
`detect_conflicts()` 自动检查：
- **Accountable 冲突**：同一个 capability 有多个 A（应该只有一个）
- **Responsible 缺失**：某个 capability 没有 R
- **角色重叠**：同一人在同一能力上既是 A 又是 R（通常没问题但值得关注）

### 3. 覆盖率检查
`get_coverage(project_id)` 返回：
- 已覆盖的能力数量 / 总能力数量
- 未覆盖的能力清单
- 每个能力的 R/A/C/I 完整性

### 4. 角色模板批量分配
```python
# 给张三分配"项目经理"角色的所有能力为 R
engine.apply_role_template("proj-001", "user-zhangsan", "project_manager", "R")
```
一次调用完成多个能力的批量分配，效率远高于逐个 assign。

## 使用示例

```python
from raci.raci import RACIEngine, Capability, RoleTemplate

# 1. 创建引擎（自动加载 12 个能力 + 6 个角色）
engine = RACIEngine()

# 2. 按角色模板分配
engine.apply_role_template("proj-001", "user-zhangsan", "project_manager", "A")
engine.apply_role_template("proj-001", "user-lisi", "tech_lead", "R")

# 3. 单独分配
engine.assign("proj-001", "user-wangwu", "quality_management", "C")

# 4. 查询矩阵
matrix = engine.get_raci_matrix("proj-001")
# 返回 { capability: { "R": [...], "A": [...], "C": [...], "I": [...] } }

# 5. 检测冲突
conflicts = engine.detect_conflicts("proj-001")
# 返回 [{ "type": "multiple_accountable", "capability": "scope_management", ... }]

# 6. 自定义能力
engine.register_capability(Capability(
    id="security_management",
    name="安全管理",
    description="安全审计、合规检查"
))
```

## 设计决策

### 为什么是"能力 → 角色"而不是"角色 → 权限"？
传统权限系统是 Role → Permission，但 RACI 矩阵的核心是**职责分配**，不是权限控制：
- 能力是面向交付的（"谁管范围"），不是面向系统的（"谁能点按钮"）
- 同一个人在不同项目可以有不同角色
- R/A/C/I 是职责类型，不是操作权限

### 为什么 RACI 引擎是内存版？
当前为纯内存实现，不依赖数据库。原因：
1. **先验证逻辑，再加存储**——引擎正确性比持久化更重要
2. **性能**——内存查询毫秒级，矩阵生成快
3. **简单**——纯数据结构，易测试、易调试
4. **持久化可后加**——RACI 模块提供 DB + 内存双写策略

## 测试覆盖
`tests/test_raci.py` — 约 30 个测试用例，覆盖：

| 测试组 | 覆盖点 |
|--------|--------|
| 基础 CRUD | assign / unassign / 查询 |
| Upsert 语义 | 重复 assign 不产生重复记录 |
| 查询 | 按项目 / 成员 / 能力查询 |
| 矩阵生成 | get_raci_matrix 输出正确性 |
| 冲突检测 | 多个 A / 缺少 R / 角色重叠 |
| 覆盖率 | coverage 计算正确性 |
| 角色模板 | apply_role_template 批量分配 |
| 自定义 | 注册自定义能力 / 角色 |

**测试状态：全部 passed**

## 扩展方向
- 持久化 RACI（DB + 内存双写）
- 工作项级 RACI（当前支持字段但深度不够）
- RACI 变更历史（审计追踪）
- 角色模板继承（单继承 / mixin）
- 与权限系统集成（RACI → 权限映射）
- RACI 模板导出/导入（JSON / YAML）

## 参考
- 代码：`L3-business/components/delivery-management-framework/raci/raci.py`
- 测试：`L3-business/components/delivery-management-framework/tests/test_raci.py`
- 相关 ADR：[ADR-025](../adr/ADR-202609-025-delivery-management-framework.md)
- 姊妹能力：[状态机引擎](EXP-20260915-021-dms-state-machine-capability.md) / [事件总线](EXP-20260915-023-dms-event-bus-capability.md)
- 方法论：PMBOK 8th / RACI Matrix 标准
