-- L3 交付管理框架初始版本 DDL
-- 这个文件是模板，实际初始化由 CLI 执行，生成交付数据库时创建这些表

-- 框架版本表
CREATE TABLE IF NOT EXISTS schema_version (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

-- 模块注册表
CREATE TABLE IF NOT EXISTS module_registry (
    name TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    description TEXT,
    tables TEXT NOT NULL,           -- JSON array
    commands TEXT NOT NULL,         -- JSON array
    dependencies TEXT NOT NULL,     -- JSON array
    hooks TEXT NOT NULL,            -- JSON object
    installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 项目表
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    type TEXT DEFAULT 'generic',            -- generic|software_delivery|construction|...
    status TEXT DEFAULT 'initiated',
    priority TEXT DEFAULT 'medium',
    planned_start DATE,
    planned_end DATE,
    actual_start DATE,
    actual_end DATE,
    budget REAL,
    currency TEXT DEFAULT 'CNY',
    owner_id TEXT,
    tenant_id TEXT NOT NULL DEFAULT 'system',
    proprietary_metadata TEXT,              -- L4 扩展点（JSON）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 工作项表（统一模型: task/milestone/deliverable/risk/decision）
CREATE TABLE IF NOT EXISTS work_items (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    type TEXT NOT NULL,                     -- task|milestone|deliverable|risk|decision
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'draft',
    priority TEXT DEFAULT 'medium',
    assignee_id TEXT,
    reviewer_id TEXT,
    planned_date DATE,
    actual_date DATE,
    due_date DATE,
    estimated_hours REAL,
    actual_hours REAL,
    parent_id TEXT REFERENCES work_items(id),
    metadata TEXT,                          -- JSON 类型特有属性
    tenant_id TEXT NOT NULL DEFAULT 'system',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 项目成员表
CREATE TABLE IF NOT EXISTS project_members (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    member_id TEXT NOT NULL,
    member_name TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT 'system',
    role_template TEXT,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (project_id, member_id)
);

-- 干系人表
CREATE TABLE IF NOT EXISTS stakeholders (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    role TEXT,
    org TEXT,
    tenant_id TEXT NOT NULL DEFAULT 'system',
    influence TEXT DEFAULT 'medium',
    interest TEXT DEFAULT 'medium',
    notes TEXT
);

-- 自定义字段表 — Metadata-driven 扩展
CREATE TABLE IF NOT EXISTS custom_fields (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'system',
    entity_type TEXT NOT NULL,         -- project | work_item | member
    field_name TEXT NOT NULL,
    field_type TEXT NOT NULL,          -- text | number | date | boolean | select | multiselect
    field_options TEXT,                -- select 选项（JSON）
    required BOOLEAN DEFAULT FALSE,
    default_value TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, entity_type, field_name)
);

-- RACI 职责分配表
CREATE TABLE IF NOT EXISTS responsibility_assignments (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    work_item_id TEXT REFERENCES work_items(id) ON DELETE CASCADE,
    member_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT 'system',
    capability TEXT NOT NULL,
    raci_role TEXT NOT NULL,                -- R|A|C|I
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, work_item_id, member_id, capability)
);

-- 变更日志表
CREATE TABLE IF NOT EXISTS change_logs (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    field_name TEXT,
    old_value TEXT,
    new_value TEXT,
    actor_id TEXT,
    tenant_id TEXT NOT NULL DEFAULT 'system',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_work_items_project ON work_items(project_id);
CREATE INDEX IF NOT EXISTS idx_work_items_type ON work_items(type);
CREATE INDEX IF NOT EXISTS idx_work_items_status ON work_items(status);
CREATE INDEX IF NOT EXISTS idx_work_items_assignee ON work_items(assignee_id);
CREATE INDEX IF NOT EXISTS idx_work_items_parent ON work_items(parent_id);
CREATE INDEX IF NOT EXISTS idx_raci_project ON responsibility_assignments(project_id);
CREATE INDEX IF NOT EXISTS idx_raci_member ON responsibility_assignments(member_id);
CREATE INDEX IF NOT EXISTS idx_raci_capability ON responsibility_assignments(capability);
CREATE INDEX IF NOT EXISTS idx_change_logs_entity ON change_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_stakeholders_project ON stakeholders(project_id);
CREATE INDEX IF NOT EXISTS idx_projects_tenant ON projects(tenant_id);
CREATE INDEX IF NOT EXISTS idx_work_items_tenant ON work_items(tenant_id);
CREATE INDEX IF NOT EXISTS idx_raci_tenant ON responsibility_assignments(tenant_id);
CREATE INDEX IF NOT EXISTS idx_change_logs_tenant ON change_logs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_custom_fields_tenant ON custom_fields(tenant_id, entity_type);
