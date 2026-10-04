# DMS 核心框架 — 详细设计

> 组件：dms-framework (L3)
> 版本：v1.0
> 日期：2026-09-03

## 1. 概述

DMS (Delivery Management System) 核心框架的详细设计，提供通用交付运营能力。

## 2. 接口契约

### 2.1 核心接口

| 接口 | 方法 | 输入 | 输出 |
|---|---|---|---|
| create_delivery | POST | delivery_data | delivery_id |
| update_progress | POST | delivery_id, progress | result |
| generate_report | GET | delivery_id, report_type | report |
| get_metrics | GET | filters | metrics |

## 3. 数据模型

### 3.1 交付数据模型

```python
@dataclass
class Delivery:
    id: str
    project_id: str
    phase: str
    status: DeliveryStatus
    metrics: Dict[str, float]
    created_at: datetime
    updated_at: datetime
```

## 4. 技术方案

### 4.1 工作流引擎

基于有限状态机，支持多阶段交付流程。

### 4.2 事件总线

发布/订阅模式，支持跨模块通信。

### 4.3 RACI 矩阵

责任分配矩阵，明确每个交付阶段的角色职责。

### 4.4 数据库迁移

版本化迁移脚本，支持 schema 演进。

## 5. 依赖关系

- L2 持久化适配
- L2 知识库
- L2 Office 文档生成

## 6. 测试方案

228 个测试用例，覆盖所有核心功能。
