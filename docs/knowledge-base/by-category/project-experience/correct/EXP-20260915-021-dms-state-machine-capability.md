---
title: "DMS 能力卡片：状态机引擎 (StateMachineEngine)"
id: EXP-20260915-021
date: 2026-09-15
type: correct
project: delivery-management-framework
category: project-experience
layers: [L3]
phase: develop
tags: [dms, capability, state-machine, guards, hooks]
---

# DMS 能力卡片：状态机引擎 (StateMachineEngine)

## 概述
状态机引擎是 DMS 框架的"流程控制中枢"，提供可配置的状态定义、转移规则、守卫条件（guards）和钩子函数（hooks）。采用**无状态设计**——引擎本身不持有状态，状态由调用方维护，引擎只负责计算转移。

## 核心价值
- **无状态设计**：纯函数式，易测试、可并发、状态存储完全解耦
- **可配置**：不需要改引擎代码，只需要定义状态和转移
- **守卫条件**：转移前检查条件，不满足则阻止
- **钩子函数**：转移前后触发副作用，支持扩展
- **多状态机管理**：一个 Engine 实例管理多个命名状态机

## 核心组件

### Transition（转移定义）
描述一次状态转移：

| 字段 | 类型 | 说明 |
|------|------|------|
| `event` | str | 触发事件名 |
| `source` | str \| List[str] | 源状态（支持单个或多个） |
| `target` | str | 目标状态 |
| `guard` | Optional[str] | 守卫条件名（可选） |

### StateMachine（状态机定义）
一个完整的状态机：

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | str | 状态机唯一名称 |
| `states` | List[str] | 所有状态集合 |
| `initial` | str | 初始状态（必须在 states 中） |
| `transitions` | List[Transition] | 转移规则列表 |
| `guards` | Dict[str, Callable] | 守卫条件函数字典 |
| `hooks` | Dict[str, List[Callable]] | 钩子函数字典 |

### StateMachineEngine（引擎）
管理多个状态机的执行：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `register(sm)` | StateMachine | None | 注册状态机 |
| `get_state_machine(name)` | str | Optional[StateMachine] | 获取状态机定义 |
| `trigger(sm_name, current_state, event, context)` | str, str, str, Any | Optional[str] | 触发事件，返回新状态 |
| `add_guard(sm_name, guard_name, guard_fn)` | str, str, Callable | bool | 动态添加守卫 |
| `add_hook(sm_name, event, hook_fn)` | str, str, Callable | bool | 动态添加钩子 |

## 关键特性

### 1. 无状态设计（核心）
```
调用方持有 current_state
        ↓
  engine.trigger(sm_name, current_state, event)
        ↓
返回 new_state（或 None 表示不能转移）
```
- 状态存在哪里完全由调用方决定（DB / Redis / 内存 / 文件）
- 同一个状态机定义可以服务无限多个实体实例
- 天然支持并发——没有共享可变状态

### 2. 守卫条件 (Guards)
转移前执行的检查函数，返回 `True` 才允许转移：
```python
def can_approve(context):
    return context.get("role") == "manager"

transition = Transition(
    event="approve",
    source="pending",
    target="approved",
    guard="is_manager"
)
```
- 守卫名与函数通过 `guards` 字典映射
- 守卫接收 context 参数，可访问任意业务数据
- 多个转移可以共享同一个守卫

### 3. 钩子函数 (Hooks)
转移成功后自动触发的副作用：
```python
def on_approved(from_state, to_state, context):
    send_notification(f"已批准: {context['item_id']}")

sm.hooks["approve"].append(on_approved)
```
- 按事件名组织钩子列表
- 钩子接收 `(from_state, to_state, context)` 参数
- 钩子异常不影响转移结果（但会记录 error log）

### 4. 多源状态转移
一个转移可以从多个源状态出发：
```python
Transition(event="cancel", source=["draft", "pending"], target="cancelled")
```
避免为每个源状态重复写相同的转移定义。

## 使用示例

```python
from state_machine.state_machine import (
    StateMachineEngine, StateMachine, Transition
)

# 1. 创建引擎
engine = StateMachineEngine()

# 2. 定义状态机
project_sm = StateMachine(
    name="project",
    states=["planning", "in_progress", "paused", "completed", "cancelled"],
    initial="planning",
    transitions=[
        Transition(event="start", source="planning", target="in_progress"),
        Transition(event="pause", source="in_progress", target="paused"),
        Transition(event="resume", source="paused", target="in_progress"),
        Transition(event="complete", source="in_progress", target="completed"),
        Transition(event="cancel", source=["planning", "paused"], target="cancelled"),
    ]
)

# 3. 注册
engine.register(project_sm)

# 4. 触发转移
new_state = engine.trigger("project", "planning", "start")
print(new_state)  # "in_progress"

# 无效转移返回 None
new_state = engine.trigger("project", "completed", "start")
print(new_state)  # None
```

## 设计决策

### 为什么引擎不持有状态？
这是最核心的设计决策。权衡：

| 方案 | 优点 | 缺点 |
|------|------|------|
| 有状态（引擎持有 state） | API 简单，调用方不用管存储 | 引擎变重、难并发、与存储耦合 |
| 无状态（调用方持有 state） | 纯函数、易测试、可并发、存储解耦 | 调用方需要自己维护状态 |

**选择无状态**：框架的职责是"计算转移规则"，不是"管理业务状态"。状态存储属于业务模块的职责，引擎不应越界。

### 为什么转移返回 str 而不是对象？
- 状态本身就是字符串标识，没必要包装成对象
- 返回 `None` 语义清晰：转移不合法
- 调用方直接用返回值更新自己的状态存储即可

## 测试覆盖
`tests/test_state_machine.py` — 20 个测试用例，覆盖：

| 测试组 | 用例数 | 覆盖点 |
|--------|--------|--------|
| 状态机定义 | 2 | 初始状态校验、有效定义 |
| 引擎 CRUD | 2 | 注册、获取不存在的 |
| 基础转移 | 4 | 基本转移、完整流程、拒绝路径、无效转移 |
| 多源状态 | 1 | 一个转移多个源状态 |
| Guards | 3 | 守卫阻止、无守卫通过、动态添加守卫 |
| Hooks | 2 | 转移触发钩子、添加不存在的钩子 |
| 覆盖/异常 | 6 | 不存在的状态机、重复注册、各种边界 |

**测试状态：20/20 passed**

## 扩展方向
- 并行/分叉状态（Fork/Join）
- 超时自动转移（timer-based transitions）
- 转移历史记录（审计追踪）
- 状态机可视化导出（DOT / Mermaid）
- 状态机定义持久化（当前仅代码定义）
- 层次状态机（Hierarchical State Machine）

## 参考
- 代码：`L3-business/components/delivery-management-framework/state_machine/state_machine.py`
- 测试：`L3-business/components/delivery-management-framework/tests/test_state_machine.py`
- 相关 ADR：[ADR-025](../adr/ADR-202609-025-delivery-management-framework.md)
- 姊妹能力：[模块注册引擎](EXP-20260915-020-dms-module-registry-capability.md) / [RACI 引擎](EXP-20260915-022-dms-raci-capability.md)
