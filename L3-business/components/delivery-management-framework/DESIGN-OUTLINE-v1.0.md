# delivery-management-framework — 设计大纲 (DESIGN-OUTLINE)

> 版本: v1.0 · 日期: 2026-09-28

## 1. 整体架构

```
dms_cli.py (CLI 入口)
    ↓
cli/ (命令注册/分发)
    ↓
models/base.py (BaseModel)
    ↓
project/ work_item/ stakeholder/ responsibility/
change_log/ raci/ state_machine/ event_bus/ registry/ repo/
migrations/
```

## 2. 模块划分

| 模块 | 职责 |
|---|---|
| models/base | BaseModel（tenant_id + CRUD） |
| project | 项目管理 |
| project_member | 项目成员 |
| work_item | 工作项管理 |
| stakeholder | 利益相关者 |
| responsibility | 责任分配 |
| change_log | 变更日志 |
| raci | RACI 引擎 |
| state_machine | 状态机引擎 |
| event_bus | 事件总线 |
| registry | 模块注册引擎 |
| repo | 通用仓储 |

## 3. 接口契约

- `BaseModel`: save / delete / to_dict
- `ModuleRegistry`: register / discover / resolve
- `EventBus`: publish / subscribe
- `StateMachineEngine`: transition
- `RACIEngine`: assign / query

## 4. 技术选型

- DDD 分层架构
- 统一 BaseModel + Repository
- 事件驱动通信
- 状态机显式定义

## 5. 分层约束

- L3 通用层：不绑定专有业务
