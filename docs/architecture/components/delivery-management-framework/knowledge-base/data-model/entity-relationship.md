---
title: "实体关系图 (ER Diagram)"
description: "DMS 框架数据库实体关系模型，包含所有业务表的字段、约束、索引及表间关系"
source: "dms-framework/core/migrations.py v1.1.0"
category: "business"
dimension: "delivery-management"
sub_area: "data-model"
type: "technical"
tags: ["data-model", "er-diagram", "database", "schema"]
last_reviewed: "2026-09-03"
---

# 实体关系图

基于 `dms-framework/core/migrations.py` v1.0.0 + v1.1.0 实际 DDL 生成。

## ER 图（Mermaid）

```mermaid
erDiagram
    projects ||--o{ work_items : "contains"
    projects ||--o{ project_members : "has"
    projects ||--o{ stakeholders : "has"
    projects ||--o{ responsibility_assignments : "has"
    work_items ||--o{ responsibility_assignments : "assigned"
    custom_fields }o--|| projects : "extends (entity_type)"
    change_logs ||--o| projects : "tracks (entity)"
    change_logs ||--o| work_items : "tracks (entity)"

    projects {
        text id PK "UUID 主键"
        text tenant_id UK "租户ID，默认system"
        text name "项目名称"
        text description "项目描述"
        text status "状态: planning/in_progress/on_hold/review/completed/cancelled"
        text priority "优先级: low/medium/high"
        text start_date "开始日期"
        text end_date "结束日期"
        text owner_id "负责人ID"
        text metadata "元数据(JSON)"
        text proprietary_metadata "专有元数据"
        timestamp created_at "创建时间"
        timestamp updated_at "更新时间"
    }

    work_items {
        text id PK "UUID 主键"
        text tenant_id UK "租户ID"
        text project_id FK "→ projects.id，级联删除"
        text type "类型: milestone/deliverable/risk/task"
        text title "标题"
        text description "描述"
        text status "状态（各类型状态机管理）"
        text priority "优先级"
        text assignee_id "负责人ID"
        text due_date "截止日期"
        text completed_at "完成时间"
        text metadata "扩展元数据(JSON)"
        timestamp created_at "创建时间"
        timestamp updated_at "更新时间"
    }

    project_members {
        text id PK "UUID 主键"
        text project_id FK "→ projects.id，级联删除"
        text user_id "用户ID"
        text role "角色: owner/member/viewer"
        text tenant_id "租户ID"
        timestamp joined_at "加入时间"
    }

    stakeholders {
        text id PK "UUID 主键"
        text project_id FK "→ projects.id，级联删除"
        text name "干系人姓名"
        text role "角色"
        text org "所属组织"
        text tenant_id "租户ID"
        text influence "影响力: low/medium/high"
        text interest "关注度: low/medium/high"
        text notes "备注"
    }

    custom_fields {
        text id PK "UUID 主键"
        text tenant_id UK "租户ID"
        text entity_type UK "实体类型: project/work_item/..."
        text field_name UK "字段名"
        text field_type "字段类型: text/number/select/date/..."
        text field_options "选项(JSON)"
        boolean required "是否必填"
        text default_value "默认值"
        integer sort_order "排序"
        timestamp created_at "创建时间"
    }

    responsibility_assignments {
        text id PK "UUID 主键"
        text project_id FK "→ projects.id，级联删除"
        text work_item_id FK "→ work_items.id，级联删除"
        text member_id "成员ID"
        text tenant_id "租户ID"
        text capability "能力域"
        text raci_role "RACI角色: R/A/C/I"
        text notes "备注"
        text role_template "角色模板 (v1.1.0)"
        timestamp created_at "创建时间"
        text updated_at "更新时间 (v1.1.0)"
    }

    change_logs {
        text id PK "UUID 主键"
        text tenant_id UK "租户ID"
        text entity_type "实体类型"
        text entity_id "实体ID"
        text action "动作: create/update/delete"
        text old_value "旧值(JSON)"
        text new_value "新值(JSON)"
        text actor "操作人"
        timestamp created_at "创建时间"
    }

    schema_version {
        integer id PK "自增主键"
        text version "版本号"
        timestamp applied_at "应用时间"
    }
```

## 表清单

| 表名 | 用途 | 主键 | 外键数 | 版本 |
|------|------|------|--------|------|
| `schema_version` | Schema 版本追踪 | id (INTEGER AUTOINCREMENT) | 0 | 1.0.0 |
| `projects` | 项目主表 | id (TEXT UUID) | 0 | 1.0.0 |
| `work_items` | 统一工作项表（里程碑/交付物/风险/任务） | id (TEXT UUID) | 1 → projects | 1.0.0 |
| `project_members` | 项目成员 | id (TEXT UUID) | 1 → projects | 1.0.0 |
| `stakeholders` | 干系人 | id (TEXT UUID) | 1 → projects | 1.0.0 |
| `custom_fields` | 自定义字段元数据 | id (TEXT UUID) | 0 | 1.0.0 |
| `responsibility_assignments` | RACI 职责分配 | id (TEXT UUID) | 2 → projects, work_items | 1.0.0 + 1.1.0 |
| `change_logs` | 变更日志 | id (TEXT UUID) | 0 (逻辑关联) | 1.0.0 |

## 核心关系说明

### 1. 项目 → 工作项（一对多）
- `work_items.project_id` → `projects.id`，`ON DELETE CASCADE`
- 通过 `type` 字段区分：`milestone` / `deliverable` / `risk` / `task`
- 统一表设计（借鉴 GitHub Issues 模式），减少表数量

### 2. 项目 → 成员（一对多）
- `project_members.project_id` → `projects.id`，`ON DELETE CASCADE`
- 唯一约束：`UNIQUE(project_id, user_id)`

### 3. 项目 → RACI 分配（一对多）
- `responsibility_assignments.project_id` → `projects.id`
- `responsibility_assignments.work_item_id` → `work_items.id`（可空，空则为项目级）
- 唯一约束：`UNIQUE(project_id, work_item_id, member_id, capability)`

### 4. 自定义字段（元数据驱动）
- 参考 Salesforce Custom Field 模式
- 唯一约束：`UNIQUE(tenant_id, entity_type, field_name)`
- 字段值存储于各实体的 `metadata` JSON 字段中

## 索引清单

| 表 | 索引名 | 字段 | 用途 |
|----|--------|------|------|
| projects | idx_projects_tenant | tenant_id | 租户过滤 |
| work_items | idx_work_items_tenant | tenant_id | 租户过滤 |
| work_items | idx_work_items_project | project_id | 项目查询 |
| work_items | idx_work_items_type | type | 类型过滤 |
| work_items | idx_work_items_status | status | 状态过滤 |
| project_members | idx_project_members_tenant | tenant_id | 租户过滤 |
| stakeholders | idx_stakeholders_tenant | tenant_id | 租户过滤 |
| custom_fields | idx_custom_fields_tenant | tenant_id, entity_type | 租户+实体查询 |
| responsibility_assignments | idx_raci_tenant | tenant_id | 租户过滤 |
| responsibility_assignments | idx_raci_project | project_id | 项目查询 |
| change_logs | idx_change_logs_tenant | tenant_id | 租户过滤 |
| change_logs | idx_change_logs_entity | entity_type, entity_id | 变更历史查询 |

## 设计特点

1. **单租户兼容多租户**：所有表含 `tenant_id`，默认 `'system'`，单租户模式透明
2. **统一工作项表**：里程碑/交付物/风险/任务共用 `work_items`，通过 `type` 区分
3. **JSON 扩展字段**：`metadata` + `proprietary_metadata` 应对个性化需求
4. **级联删除**：项目删除时级联删除所有子资源
5. **变更审计**：`change_logs` 统一记录所有实体的变更历史
