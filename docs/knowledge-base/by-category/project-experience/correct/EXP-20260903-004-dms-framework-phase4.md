---
id: EXP-20260903-004
title: DMS 框架 Phase 4 端到端验证经验
date: 2026-09-03
type: correct
project: delivery-management-framework
tags: [dms, framework, phase4, e2e, validation]
---

# DMS 框架 Phase 4 端到端验证经验

## 背景
Phase 3 知识库完成后，Phase 4 用虚拟项目跑通全流程，验证框架真能用、不是空壳。

## 成果
- **CLI 重写**：`dms.py` 从手写桩函数 → `ModuleRegistry` 自动注册 + `Manifest` 命令聚合
- **E2E 测试**：`phase4_e2e_test.py`，10 阶段 54 项断言，100% 通过
- **L4 扩展验证**：proprietary_metadata + custom_fields 元数据表，不改 L3 代码
- **事件联动验证**：project.cancelled → 里程碑 deferred / 交付物 withdrawn / 风险 closed

## 关键架构

### FrameworkRegistry 模式
```
ModuleRegistry (基类)
  └─ +_state_machine_engine
  └─ +_event_bus
  └─ register(manifest, factory)
  └─ initialize_all(db, config)  # 拓扑排序
  └─ get(module_name) → module instance
```

模块通过 `container._state_machine_engine.register()` 和 `container._event_bus.publish()` 获取全局组件，而不是直接依赖具体实现。

### CLI 命令聚合
- 每个模块在 `manifest.commands` 声明 `CommandDef`
- `dms.py` 的 `build_parser()` 遍历所有模块 manifest，动态构建 argparse 子命令树
- 执行时注入 `ctx = {"module": instance, "container": registry}`
- 新增模块零侵入：只需要 `register()`，CLI 自动出现对应命令

## 虚拟项目验证清单

| 阶段 | 内容 | 关键验证点 |
|------|------|-----------|
| S1 | 初始化 | 迁移执行、模块注册 |
| S2 | 创建项目 | project 模块 CRUD |
| S3 | 里程碑 | milestone 模块 + work_items 表 |
| S4 | 交付物 | deliverable 模块 + type 区分 |
| S5 | 风险 | risk 模块 + metadata JSON |
| S6 | RACI 分配 | raci 模块双写（DB + 内存引擎） |
| S7 | 状态流转 | 4 个状态机 + 事件发布 |
| S8 | 查询验证 | get/list/matrix/conflicts/coverage |
| S9 | 模块注册 | 5 模块全注册 |
| S10 | 事件总线 | 订阅者/历史事件 |

## L4 扩展的两种路径

### 1. proprietary_metadata（实体级扩展）
- 每个项目/工作项有一个 JSON 字段
- L4 可以存任意专有数据
- 不需要改 L3 schema
- 适合：项目属性、业务字段、自定义标签

### 2. custom_fields（元数据驱动）
- 借鉴 Salesforce 的 Flex Columns 模式
- 通过 `custom_fields` 元数据表定义字段
- L4 可以动态增加字段定义
- 不需要改 L3 schema
- 适合：租户级自定义字段、表单配置

## 事件跨模块联动验证
项目取消事件触发 3 个子模块响应：

| 模块 | 订阅事件 | 响应动作 |
|------|---------|---------|
| milestone | project.cancelled | pending→deferred, in_progress→missed |
| deliverable | project.cancelled | draft→withdrawn |
| risk | project.cancelled | identified→closed |
| raci | project.deleted | 清理该项目所有 RACI 分配 |

验证了 EventBus 的解耦能力——模块间只通过事件通信，不直接调用。

## 教训

### 1. subagent 写的代码要自己跑一遍验证
方法论 subagent 幻觉的前车之鉴，E2E 测试脚本 subagent 产出后必须自己执行一遍。

### 2. CLI 接入模块系统的正确姿势
不要手写每个模块的命令分发，从 manifest 自动聚合才是热插拔的正确做法。新增模块 = 新增 manifest = 自动出现在 CLI 里。

### 3. 事件联动要测级联效应
单元测试只能测单个模块，E2E 才能发现"项目取消后子项是不是真的联动了"这种跨模块问题。

## 参考
- [EXP-001](EXP-20260903-001-dms-framework-phase1.md)
- [EXP-002](EXP-20260903-002-dms-framework-phase2.md)
- [EXP-003](EXP-20260903-003-dms-framework-phase3.md)
- [ADR-025](../../adr/ADR-202609-025-delivery-management-framework.md)
