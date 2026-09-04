-- ============================================================================
-- DMS-Framework Database Schema
-- 版本: v1.1.0
-- 来源: dms-framework/core/migrations.py
-- 说明: 本文件从 migrations.py 提取完整 DDL，附加表用途注释
-- ============================================================================

-- ----------------------------------------------------------------------------
-- schema_version
-- 用途: Schema 版本追踪表，记录每次迁移的版本号和应用时间
--       用于增量迁移和版本回退判断
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_version (
    id INTEGER PRIMARY KEY AUTOINCREMENT,    -- 自增主键
    version TEXT NOT NULL,                    -- 语义化版本号 (如 1.0.0)
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  -- 迁移应用时间
);

-- ----------------------------------------------------------------------------
-- projects
-- 用途: 项目主表，存储项目的基本信息和生命周期状态
--       DMS 框架的核心实体，所有业务资源均挂在项目下
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,                      -- UUID 主键
    tenant_id TEXT NOT NULL DEFAULT 'system', -- 租户ID，单租户默认为 system
    name TEXT NOT NULL,                       -- 项目名称
    description TEXT,                         -- 项目描述
    status TEXT DEFAULT 'planning',           -- 项目状态 (见状态机文档)
    priority TEXT DEFAULT 'medium',           -- 优先级 (low/medium/high)
    start_date TEXT,                          -- 开始日期 (YYYY-MM-DD)
    end_date TEXT,                            -- 结束日期 (YYYY-MM-DD)
    owner_id TEXT,                            -- 项目负责人ID
    metadata TEXT,                            -- 扩展元数据 (JSON)
    proprietary_metadata TEXT,                -- 专有元数据 (隔离第三方扩展)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- work_items
-- 用途: 统一工作项表，存储里程碑、交付物、风险、任务等所有工作项
--       借鉴 GitHub Issues 单表多态模式，通过 type 字段区分类型
--       各类型特定字段存储于 metadata JSON 中
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS work_items (
    id TEXT PRIMARY KEY,                      -- UUID 主键
    tenant_id TEXT NOT NULL DEFAULT 'system', -- 租户ID
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,  -- 所属项目
    type TEXT NOT NULL,                       -- 工作项类型: milestone/deliverable/risk/task
    title TEXT NOT NULL,                      -- 标题
    description TEXT,                         -- 描述
    status TEXT DEFAULT 'draft',              -- 状态 (各类型独立状态机)
    priority TEXT DEFAULT 'medium',           -- 优先级
    assignee_id TEXT,                         -- 负责人ID
    due_date TEXT,                            -- 截止日期
    completed_at TEXT,                        -- 完成时间
    metadata TEXT,                            -- 扩展元数据 (JSON)，如 parent_id、risk_score 等
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- project_members
-- 用途: 项目成员表，记录用户与项目的关联关系和角色
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS project_members (
    id TEXT PRIMARY KEY,                      -- UUID 主键
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,                    -- 用户ID
    role TEXT NOT NULL,                       -- 角色: owner/member/viewer
    tenant_id TEXT NOT NULL DEFAULT 'system',
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, user_id)               -- 同一用户在同一项目中只能有一个角色
);

-- ----------------------------------------------------------------------------
-- stakeholders
-- 用途: 干系人表，记录项目的内外部干系人及其影响力/关注度
--       用于干系人管理和沟通规划
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stakeholders (
    id TEXT PRIMARY KEY,                      -- UUID 主键
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,                       -- 干系人姓名
    role TEXT,                                -- 干系人角色
    org TEXT,                                 -- 所属组织
    tenant_id TEXT NOT NULL DEFAULT 'system',
    influence TEXT DEFAULT 'medium',          -- 影响力 (low/medium/high)
    interest TEXT DEFAULT 'medium',           -- 关注度 (low/medium/high)
    notes TEXT                                -- 备注
);

-- ----------------------------------------------------------------------------
-- custom_fields
-- 用途: 自定义字段元数据表，支持租户级别的字段扩展
--       借鉴 Salesforce Custom Object 设计
--       字段值存储于对应实体的 metadata JSON 中
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS custom_fields (
    id TEXT PRIMARY KEY,                      -- UUID 主键
    tenant_id TEXT NOT NULL DEFAULT 'system',
    entity_type TEXT NOT NULL,                -- 实体类型: project/work_item/...
    field_name TEXT NOT NULL,                 -- 字段名
    field_type TEXT NOT NULL,                 -- 字段类型: text/number/select/date/checkbox
    field_options TEXT,                       -- 选项值 (JSON数组，用于 select 类型)
    required BOOLEAN DEFAULT 0,               -- 是否必填
    default_value TEXT,                       -- 默认值
    sort_order INTEGER DEFAULT 0,             -- 显示排序
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, entity_type, field_name)  -- 租户内同实体字段名唯一
);

-- ----------------------------------------------------------------------------
-- responsibility_assignments
-- 用途: RACI 职责分配表，记录项目或工作项上各成员的 RACI 角色
--       支持项目级和工作项级两种粒度
--       v1.1.0 新增: updated_at, role_template
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS responsibility_assignments (
    id TEXT PRIMARY KEY,                      -- UUID 主键
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    work_item_id TEXT REFERENCES work_items(id) ON DELETE CASCADE,  -- NULL 表示项目级
    member_id TEXT NOT NULL,                  -- 成员ID (对应用户或角色)
    tenant_id TEXT NOT NULL DEFAULT 'system',
    capability TEXT NOT NULL,                 -- 能力域
    raci_role TEXT NOT NULL,                  -- RACI 角色: Responsible/Accountable/Consulted/Informed
    notes TEXT,                               -- 备注
    role_template TEXT,                       -- 角色模板 (v1.1.0 新增)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,                          -- 更新时间 (v1.1.0 新增)
    UNIQUE(project_id, work_item_id, member_id, capability)  -- 同一能力域内唯一分配
);

-- ----------------------------------------------------------------------------
-- change_logs
-- 用途: 变更日志表，统一记录所有实体的创建、修改、删除操作
--       用于审计追踪和操作历史
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS change_logs (
    id TEXT PRIMARY KEY,                      -- UUID 主键
    tenant_id TEXT NOT NULL DEFAULT 'system',
    entity_type TEXT NOT NULL,                -- 实体类型 (project/work_item/...)
    entity_id TEXT NOT NULL,                  -- 实体ID
    action TEXT NOT NULL,                     -- 动作: create/update/delete
    old_value TEXT,                           -- 旧值 (JSON)
    new_value TEXT,                           -- 新值 (JSON)
    actor TEXT,                               -- 操作人ID
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 索引 (Indexes)
-- ============================================================================

-- projects 索引
CREATE INDEX IF NOT EXISTS idx_projects_tenant ON projects(tenant_id);

-- work_items 索引
CREATE INDEX IF NOT EXISTS idx_work_items_tenant ON work_items(tenant_id);
CREATE INDEX IF NOT EXISTS idx_work_items_project ON work_items(project_id);
CREATE INDEX IF NOT EXISTS idx_work_items_type ON work_items(type);
CREATE INDEX IF NOT EXISTS idx_work_items_status ON work_items(status);

-- project_members 索引
CREATE INDEX IF NOT EXISTS idx_project_members_tenant ON project_members(tenant_id);

-- stakeholders 索引
CREATE INDEX IF NOT EXISTS idx_stakeholders_tenant ON stakeholders(tenant_id);

-- custom_fields 索引
CREATE INDEX IF NOT EXISTS idx_custom_fields_tenant ON custom_fields(tenant_id, entity_type);

-- responsibility_assignments 索引
CREATE INDEX IF NOT EXISTS idx_raci_tenant ON responsibility_assignments(tenant_id);
CREATE INDEX IF NOT EXISTS idx_raci_project ON responsibility_assignments(project_id);

-- change_logs 索引
CREATE INDEX IF NOT EXISTS idx_change_logs_tenant ON change_logs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_change_logs_entity ON change_logs(entity_type, entity_id);
