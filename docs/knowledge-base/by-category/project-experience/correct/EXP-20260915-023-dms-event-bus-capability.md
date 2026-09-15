---
title: "DMS 能力卡片：事件总线 (EventBus)"
id: EXP-20260915-023
date: 2026-09-15
type: correct
project: delivery-management-framework
category: project-experience
layers: [L3]
phase: manage
tags: [dms, capability, event-bus, pub-sub, decoupling]
---

# DMS 能力卡片：事件总线 (EventBus)

## 概述
事件总线是 DMS 框架的"模块间通信中枢"，实现发布/订阅（Pub/Sub）模式的解耦通信。模块之间不直接调用，而是通过发布和订阅事件来协作，降低模块间耦合度。

## 核心价值
- **解耦**：发布者不需要知道谁订阅了，订阅者也不需要知道谁发布的
- **可扩展**：新增订阅者不影响发布者代码，新增事件不影响现有订阅
- **可追溯**：事件历史持久化（内存），支持审计和调试
- **容错**：单个订阅者异常不影响其他订阅者，也不影响事件发布

## 核心组件

### Event（事件）
事件的标准数据结构：

| 字段 | 类型 | 说明 |
|------|------|------|
| `event_type` | str | 事件类型（如 "project.created", "work_item.updated"） |
| `payload` | Dict[str, Any] | 事件数据 |
| `created_at` | datetime | 事件创建时间（自动填充） |
| `entity_type` | Optional[str] | 实体类型（如 "project", "work_item"） |
| `entity_id` | Optional[str] | 实体 ID |

### EventBus（事件总线）
核心引擎，提供以下 API：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `subscribe(event_type, handler)` | str, Callable | None | 订阅事件 |
| `unsubscribe(event_type, handler)` | str, Callable | None | 取消订阅 |
| `publish(event)` | Event | None | 发布事件 |
| `get_history(event_type=None)` | Optional[str] | List[Event] | 获取历史事件 |
| `clear_history()` | — | None | 清空历史 |

## 关键特性

### 1. 发布/订阅模式
```
发布者 → EventBus.publish(event)
              ↓
         遍历订阅者
              ↓
订阅者 1 ← 订阅者 2 ← 订阅者 3 ...
```
- 一个事件可以有 0~N 个订阅者
- 发布者完全不感知订阅者
- 订阅顺序不保证（实际按注册顺序执行）

### 2. 异常隔离
单个订阅者抛出异常**不会**中断其他订阅者的执行，也不会导致 publish 失败：
```python
def buggy_handler(event):
    raise RuntimeError("oops")

bus.subscribe("test", buggy_handler)
bus.subscribe("test", normal_handler)  # 仍然会被调用
bus.publish(Event("test", {}))         # 不会抛异常，只记 error log
```
这是**重要的设计决策**——避免一个模块的 bug 级联影响整个系统。

### 3. 事件历史
所有发布过的事件都会存入 `_history` 列表：
- 支持按事件类型过滤查询
- 可用于调试、审计、重放
- 当前为内存存储，重启丢失（后续可持久化）

### 4. 事件命名约定
推荐使用 `entity.action` 格式：
- `project.created` / `project.updated` / `project.deleted`
- `work_item.status_changed` / `work_item.assigned`
- `raci.assignment_changed`
- `system.module_registered`

好处：
- 语义清晰，从名字就能看出是什么意思
- 可用前缀通配（未来扩展）
- 与 ModuleManifest.hooks 的声明对齐

## 使用示例

```python
from event_bus.event_bus import EventBus, Event

# 1. 创建总线
bus = EventBus()

# 2. 定义事件处理函数
def on_project_created(event):
    print(f"项目已创建: {event.payload['name']}")
    # 自动初始化里程碑、RACI 等

def on_project_cancelled(event):
    project_id = event.entity_id
    print(f"项目已取消: {project_id}")
    # 清理资源、通知干系人等

# 3. 订阅
bus.subscribe("project.created", on_project_created)
bus.subscribe("project.cancelled", on_project_cancelled)

# 4. 发布事件
bus.publish(Event(
    event_type="project.created",
    payload={"name": "新项目", "owner": "zhangsan"},
    entity_type="project",
    entity_id="proj-001"
))

# 5. 查看历史
history = bus.get_history("project.created")
print(f"已发布 {len(history)} 个 project.created 事件")
```

### 与 ModuleManifest 集成
模块可以通过 manifest 的 `hooks` 字段声明事件订阅，由框架自动绑定：

```python
manifest = ModuleManifest(
    name="milestone",
    hooks={
        "project.cancelled": "handle_project_cancelled",
        "project.deleted": "handle_project_deleted"
    }
)
```
框架在模块初始化时自动将这些钩子注册到 EventBus。

## 设计决策

### 为什么用事件总线而不是直接调用？

| 对比维度 | 直接调用 | 事件总线 |
|---------|---------|---------|
| 耦合度 | 高（需要 import 对方模块） | 低（只依赖事件格式） |
| 可扩展性 | 新增消费者要改发布者代码 | 新增消费者只需订阅 |
| 调试难度 | 简单（调用栈清晰） | 稍难（需要查事件历史） |
| 性能 | 直接函数调用，快 | 有遍历 + 异常捕获开销 |
| 容错 | 一个挂了全链路挂 | 异常隔离，不影响其他模块 |

**选择事件总线**：DMS 框架有 10+ 个模块，如果都直接调用，模块间依赖会变成意大利面。事件总线把模块间的依赖降到最低——只依赖事件格式，不依赖对方的实现。

### 为什么历史记录存在内存里？
- 简单，零依赖
- 对大多数场景够用（调试 / 审计不需要持久）
- 持久化可以后加（迁移到数据库或日志文件）
- 当前是骨架版，优先验证模式正确性

### 为什么 publish 是同步的？
同步发布的优点：
- 简单，不需要引入异步框架
- 调试方便（单步追踪）
- 骨架阶段够用

未来可扩展异步模式（后台线程 / 消息队列），但当前同步是正确选择。

## 测试覆盖
`tests/test_event_bus.py` — 约 15 个测试用例，覆盖：

| 测试组 | 覆盖点 |
|--------|--------|
| 基础 Pub/Sub | subscribe / publish / 多次发布 |
| 多个订阅者 | 多个 handler 都被调用 |
| 取消订阅 | unsubscribe 后不再收到事件 |
| 异常隔离 | handler 抛异常不影响其他 handler |
| 事件历史 | get_history 正确性 / 过滤 / 清空 |
| 事件数据 | payload / entity_type / entity_id |
| 空订阅 | 发布没人订阅的事件不报错 |

**测试状态：全部 passed**

## 扩展方向
- **异步发布**：支持同步 / 异步两种模式
- **事件持久化**：事件历史存入数据库
- **事件重放**：从历史事件重放，重建状态
- **通配符订阅**：支持 `project.*` / `*.created` 等
- **事件优先级**：高优先级事件优先处理
- **死信队列**：反复失败的事件进 DLQ
- **事件溯源（Event Sourcing）**：状态完全由事件推导

## 参考
- 代码：`L3-business/components/delivery-management-framework/event_bus/event_bus.py`
- 测试：`L3-business/components/delivery-management-framework/tests/test_event_bus.py`
- 相关 ADR：[ADR-025](../adr/ADR-202609-025-delivery-management-framework.md)
- 姊妹能力：[模块注册引擎](EXP-20260915-020-dms-module-registry-capability.md) / [RACI 引擎](EXP-20260915-022-dms-raci-capability.md)
- 模式参考：Enterprise Integration Patterns — Publish-Subscribe Channel
