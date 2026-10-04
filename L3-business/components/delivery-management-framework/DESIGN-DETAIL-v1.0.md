# 交付管理框架 — 详细设计

> 组件：delivery-management-framework (L3)
> 版本：v1.0
> 日期：2026-09-03

## 1. 概述

交付管理框架的详细设计，包含工作流引擎、状态机、事件总线和RACI责任矩阵。

## 2. 接口契约

### 2.1 工作流接口

| 接口 | 方法 | 输入 | 输出 |
|---|---|---|---|
| create_project | POST | project_data | project_id |
| update_status | POST | project_id, status | result |
| assign_task | POST | task_id, assignee | result |
| get_dashboard | GET | project_id | dashboard_data |

### 2.2 状态机接口

| 接口 | 方法 | 输入 | 输出 |
|---|---|---|---|
| transition | POST | entity_id, event | new_state |
| get_history | GET | entity_id | state_history |

## 3. 数据模型

### 3.1 项目数据模型

```python
@dataclass
class Project:
    id: str
    name: str
    status: ProjectStatus
    phases: List[Phase]
    stakeholders: List[Stakeholder]
    created_at: datetime
    updated_at: datetime
```

### 3.2 任务数据模型

```python
@dataclass
class Task:
    id: str
    project_id: str
    title: str
    assignee: str
    status: TaskStatus
    due_date: datetime
    dependencies: List[str]
```

## 4. 技术方案

### 4.1 工作流引擎

基于状态机模式，支持：
- 项目生命周期管理（启动→规划→执行→监控→收尾）
- 任务依赖排序
- 自动状态流转
- 事件驱动架构

### 4.2 RACI 责任矩阵

| 角色 | 项目决策 | 任务执行 | 质量审核 | 进度汇报 |
|---|---|---|---|---|
| PM | R | A | C | R |
| Dev | C | R | A | C |
| QA | C | C | R | C |
| Stakeholder | A | I | I | R |

### 4.3 事件总线

发布/订阅模式，支持：
- 状态变更事件
- 任务分配事件
- 风险预警事件
- SLA 违规事件

## 5. 依赖关系

- L2 持久化适配 (SQLite)
- L2 知识库 (模板存储)
- L2 Office 文档生成 (报告)

## 6. 测试方案

- 单元测试：状态机转换
- 集成测试：工作流引擎
- E2E 测试：完整项目生命周期
