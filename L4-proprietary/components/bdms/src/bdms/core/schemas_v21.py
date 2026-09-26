"""BDMS v2.1 新增模块表 — 合同/项目/售后/集成/知识库/看板。

设计约定：
- 所有业务表包含审计字段：created_at, updated_at, created_by, updated_by
- 所有业务表支持软删除：deleted_at（NULL = 未删除）
- 模块前缀：cr_ / pm_ / ct_ / rk_ / as_ / int_ / kb_ / dash_ / ch_
"""

# ===== 合同管理模块 =====

CR_SCHEMA = """
CREATE TABLE IF NOT EXISTS cr_contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_no TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    contract_type TEXT,
    party_a TEXT,
    party_b TEXT,
    amount REAL NOT NULL DEFAULT 0,
    currency TEXT DEFAULT 'CNY',
    effective_date TEXT,
    expiry_date TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    approval_level INTEGER DEFAULT 1,
    signed_date TEXT,
    archive_date TEXT,
    source TEXT DEFAULT 'manual',         -- manual / oa_fetch / oa_approval / ocr_import
    oa_process_id TEXT,                   -- OA 流程 ID（OA 获取时记录）
    impl_owner TEXT,                      -- 实施负责人（v2.1 P1）
    impl_status TEXT DEFAULT 'not_started', -- 实施状态: not_started/in_progress/completed/suspended（v2.1 P1）
    -- 审计字段
    created_by TEXT,
    updated_by TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
    -- 软删除
    deleted_at TEXT DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS idx_cr_status ON cr_contracts(status);
CREATE INDEX IF NOT EXISTS idx_cr_deleted ON cr_contracts(deleted_at);
CREATE INDEX IF NOT EXISTS idx_cr_no_prefix ON cr_contracts(substr(contract_no, 1, 14));
CREATE INDEX IF NOT EXISTS idx_cr_impl_owner ON cr_contracts(impl_owner);
CREATE INDEX IF NOT EXISTS idx_cr_impl_status ON cr_contracts(impl_status);

CREATE TABLE IF NOT EXISTS cr_contract_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    file_path TEXT,
    file_hash TEXT,
    watermark TEXT,
    created_by TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (contract_id) REFERENCES cr_contracts(id) ON DELETE CASCADE,
    UNIQUE(contract_id, version)
);

CREATE TABLE IF NOT EXISTS cr_contract_clauses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    clause_type TEXT NOT NULL,
    clause_title TEXT,
    clause_content TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    deleted_at TEXT DEFAULT NULL,
    FOREIGN KEY (contract_id) REFERENCES cr_contracts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cr_risk_scan_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    scan_batch TEXT NOT NULL,
    risk_category TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    issue_summary TEXT,
    suggestion TEXT,
    status TEXT DEFAULT 'open',
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    deleted_at TEXT DEFAULT NULL,
    FOREIGN KEY (contract_id) REFERENCES cr_contracts(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_cr_risk_level ON cr_risk_scan_results(risk_level);

CREATE TABLE IF NOT EXISTS cr_approval_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    action TEXT NOT NULL,
    approver_name TEXT NOT NULL,
    approver_role TEXT,
    comment TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (contract_id) REFERENCES cr_contracts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cr_audit_trail (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    operation TEXT NOT NULL,
    field_name TEXT,
    old_value TEXT,
    new_value TEXT,
    operator TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (contract_id) REFERENCES cr_contracts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cr_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_code TEXT UNIQUE NOT NULL,
    template_name TEXT NOT NULL,
    contract_type TEXT,
    file_path TEXT NOT NULL,
    version TEXT DEFAULT '1.0',
    is_default INTEGER DEFAULT 0,
    enabled INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
    deleted_at TEXT DEFAULT NULL
);

-- 条款库（P0 优化：条款解耦）
CREATE TABLE IF NOT EXISTS cr_clause_library (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clause_code TEXT UNIQUE NOT NULL,
    clause_name TEXT NOT NULL,
    clause_type TEXT NOT NULL,
    content TEXT NOT NULL,
    risk_level TEXT DEFAULT 'medium',
    applicable_contract_types TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
    deleted_at TEXT DEFAULT NULL
);

-- 合同关联关系表
CREATE TABLE IF NOT EXISTS cr_contract_relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_contract_id INTEGER NOT NULL,   -- 源合同
    target_contract_id INTEGER NOT NULL,   -- 目标合同
    relation_type TEXT NOT NULL,           -- supplement / termination / order / amendment
    match_rule TEXT NOT NULL,              -- prefix_14 / bc_prefix / zz_prefix / dash_order
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (source_contract_id) REFERENCES cr_contracts(id),
    FOREIGN KEY (target_contract_id) REFERENCES cr_contracts(id),
    UNIQUE(source_contract_id, target_contract_id, relation_type)
);
"""


# ===== 项目管理模块 =====

PM_SCHEMA = """
CREATE TABLE IF NOT EXISTS pm_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_no TEXT UNIQUE NOT NULL,
    project_name TEXT NOT NULL,
    contract_id INTEGER,
    project_type TEXT,
    dept TEXT,
    pm TEXT,
    status TEXT DEFAULT 'initiating',
    start_date TEXT,
    end_date TEXT,
    budget REAL DEFAULT 0,
    -- 实施类型标记
    impl_product INTEGER DEFAULT 0,       -- 产品实施 0/1
    impl_security INTEGER DEFAULT 0,      -- 安服实施 0/1
    impl_custom INTEGER DEFAULT 0,        -- 定制开发 0/1
    impl_outsourcing INTEGER DEFAULT 0,   -- 外包/外采 0/1
    -- 实施管理字段（v2.1 P2）
    impl_owner TEXT,                      -- 实施负责人
    impl_status TEXT DEFAULT 'not_started', -- 实施状态: not_started/in_progress/delayed/completed
    impl_start_date TEXT,                 -- 实际开始日期
    impl_end_date TEXT,                   -- 实际结束日期
    -- 审计字段
    created_by TEXT,
    updated_by TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
    deleted_at TEXT DEFAULT NULL,
    FOREIGN KEY (contract_id) REFERENCES cr_contracts(id)
);
CREATE INDEX IF NOT EXISTS idx_pm_status ON pm_projects(status);
CREATE INDEX IF NOT EXISTS idx_pm_pm ON pm_projects(pm);
CREATE INDEX IF NOT EXISTS idx_pm_type ON pm_projects(project_type);
CREATE INDEX IF NOT EXISTS idx_pm_deleted ON pm_projects(deleted_at);
CREATE INDEX IF NOT EXISTS idx_pm_contract ON pm_projects(contract_id);

CREATE TABLE IF NOT EXISTS pm_phases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    phase_name TEXT NOT NULL,
    phase_order INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',
    planned_start TEXT,
    planned_end TEXT,
    actual_start TEXT,
    actual_end TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (project_id) REFERENCES pm_projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pm_team_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    member_name TEXT NOT NULL,
    role TEXT,
    allocation REAL DEFAULT 1.0,
    start_date TEXT,
    end_date TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (project_id) REFERENCES pm_projects(id) ON DELETE CASCADE,
    UNIQUE(project_id, member_name, role)
);

CREATE TABLE IF NOT EXISTS pm_milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    milestone_name TEXT NOT NULL,
    planned_date TEXT,
    actual_date TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (project_id) REFERENCES pm_projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pm_delivery_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    report_type TEXT,
    title TEXT NOT NULL,
    content TEXT,
    attachments TEXT DEFAULT '',
    status TEXT DEFAULT 'draft',
    created_by TEXT DEFAULT '',
    submitted_at TEXT,
    reviewed_at TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    deleted_at TEXT DEFAULT NULL,
    FOREIGN KEY (project_id) REFERENCES pm_projects(id) ON DELETE CASCADE
);
"""


# ===== 成本管理模块 =====

CT_SCHEMA = """
CREATE TABLE IF NOT EXISTS ct_timesheets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    person_id TEXT NOT NULL,
    work_date TEXT NOT NULL,
    hours REAL NOT NULL DEFAULT 0,
    work_type TEXT,
    description TEXT,
    status TEXT DEFAULT 'pending',
    approver TEXT,
    approved_by TEXT,
    approved_at TEXT,
    created_by TEXT,
    updated_by TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
    deleted_at TEXT DEFAULT NULL,
    FOREIGN KEY (project_id) REFERENCES pm_projects(id)
);
CREATE INDEX IF NOT EXISTS idx_ct_ts_project ON ct_timesheets(project_id);
CREATE INDEX IF NOT EXISTS idx_ct_ts_deleted ON ct_timesheets(deleted_at);

CREATE TABLE IF NOT EXISTS ct_staff_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL,
    level TEXT DEFAULT '',
    rate REAL NOT NULL DEFAULT 0,
    currency TEXT DEFAULT 'CNY',
    effective_date TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    deleted_at TEXT DEFAULT NULL,
    UNIQUE(person_name, role, effective_date)
);

CREATE TABLE IF NOT EXISTS ct_device_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    device_name TEXT NOT NULL,
    start_date TEXT,
    end_date TEXT,
    cost_per_day REAL DEFAULT 0,
    total_cost REAL DEFAULT 0,
    status TEXT DEFAULT 'in_use',
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (project_id) REFERENCES pm_projects(id)
);

CREATE TABLE IF NOT EXISTS ct_travel_costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    employee_name TEXT NOT NULL,
    travel_date TEXT NOT NULL,
    cost_type TEXT,
    amount REAL DEFAULT 0,
    description TEXT,
    status TEXT DEFAULT 'submitted',
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (project_id) REFERENCES pm_projects(id)
);
"""



# ===== 利润管理模块 =====

PF_SCHEMA = """
-- 工时记录（ct_timesheets 迁移目标，迁移后 ct_timesheets 转为 VIEW）
CREATE TABLE IF NOT EXISTS pf_timesheet (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    person_id TEXT NOT NULL,
    work_date TEXT NOT NULL,               -- YYYY-MM-DD
    hours REAL NOT NULL CHECK (hours > 0 AND hours <= 24),
    work_type TEXT,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'submitted',  -- submitted/approved/rejected
    approver TEXT,
    approved_by TEXT,
    approved_at TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    deleted_at TEXT DEFAULT NULL,
    FOREIGN KEY (project_id) REFERENCES pm_projects(id)
);
CREATE INDEX IF NOT EXISTS idx_pf_ts_project ON pf_timesheet(project_id);
CREATE INDEX IF NOT EXISTS idx_pf_ts_date ON pf_timesheet(work_date);
CREATE INDEX IF NOT EXISTS idx_pf_ts_status ON pf_timesheet(status);
CREATE INDEX IF NOT EXISTS idx_pf_ts_person ON pf_timesheet(person_id);
CREATE INDEX IF NOT EXISTS idx_pf_ts_deleted ON pf_timesheet(deleted_at);

-- 设备使用（ct_device_usage 迁移目标）
CREATE TABLE IF NOT EXISTS pf_device_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    device_name TEXT NOT NULL,
    start_date TEXT,
    end_date TEXT,
    cost_per_day REAL DEFAULT 0,
    total_cost REAL DEFAULT 0,
    status TEXT DEFAULT 'in_use',
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    deleted_at TEXT DEFAULT NULL,
    FOREIGN KEY (project_id) REFERENCES pm_projects(id)
);
CREATE INDEX IF NOT EXISTS idx_pf_du_project ON pf_device_usage(project_id);
CREATE INDEX IF NOT EXISTS idx_pf_du_status ON pf_device_usage(status);

-- 差旅费用（ct_travel_costs 迁移目标）
CREATE TABLE IF NOT EXISTS pf_travel_cost (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    employee_name TEXT NOT NULL,
    travel_date TEXT NOT NULL,
    cost_type TEXT,
    amount REAL DEFAULT 0,
    description TEXT,
    status TEXT DEFAULT 'submitted',
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    deleted_at TEXT DEFAULT NULL,
    FOREIGN KEY (project_id) REFERENCES pm_projects(id)
);
CREATE INDEX IF NOT EXISTS idx_pf_tc_project ON pf_travel_cost(project_id);
CREATE INDEX IF NOT EXISTS idx_pf_tc_date ON pf_travel_cost(travel_date);
CREATE INDEX IF NOT EXISTS idx_pf_tc_status ON pf_travel_cost(status);

-- 人员费率（ct_staff_rates 迁移目标）
CREATE TABLE IF NOT EXISTS pf_staff_rate (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL,
    level TEXT DEFAULT '',
    rate REAL NOT NULL DEFAULT 0,
    currency TEXT DEFAULT 'CNY',
    effective_date TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    deleted_at TEXT DEFAULT NULL,
    UNIQUE(person_name, role, effective_date)
);
CREATE INDEX IF NOT EXISTS idx_pf_sr_person ON pf_staff_rate(person_name);
CREATE INDEX IF NOT EXISTS idx_pf_sr_role ON pf_staff_rate(role);

-- 成本项明细表（成本归集中间表）
CREATE TABLE IF NOT EXISTS pf_cost_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    period TEXT NOT NULL,                   -- 所属期间 YYYY-MM
    cost_type TEXT NOT NULL,                -- labor / device / travel
    source_table TEXT NOT NULL,             -- 来源表名
    source_id INTEGER NOT NULL,             -- 来源记录 ID
    amount REAL NOT NULL DEFAULT 0,         -- 成本金额（元）
    currency TEXT DEFAULT 'CNY',
    description TEXT,
    allocated_at TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (project_id) REFERENCES pm_projects(id)
);
CREATE INDEX IF NOT EXISTS idx_pf_cost_project ON pf_cost_item(project_id);
CREATE INDEX IF NOT EXISTS idx_pf_cost_period ON pf_cost_item(period);
CREATE INDEX IF NOT EXISTS idx_pf_cost_type ON pf_cost_item(cost_type);
CREATE INDEX IF NOT EXISTS idx_pf_cost_source ON pf_cost_item(source_table, source_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pf_cost_unique
    ON pf_cost_item(project_id, period, cost_type, source_table, source_id);

-- 利润快照
CREATE TABLE IF NOT EXISTS pf_profit_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    period TEXT NOT NULL,                   -- 会计期间 YYYY-MM
    -- 收入
    revenue REAL NOT NULL DEFAULT 0,
    revenue_source TEXT,
    revenue_synced_at TEXT,
    -- 成本
    cost_labor REAL NOT NULL DEFAULT 0,
    cost_device REAL NOT NULL DEFAULT 0,
    cost_travel REAL NOT NULL DEFAULT 0,
    cost_total REAL NOT NULL DEFAULT 0,
    -- 利润
    profit REAL NOT NULL DEFAULT 0,
    profit_margin REAL DEFAULT 0,
    -- 预算
    budget REAL DEFAULT 0,
    budget_usage REAL DEFAULT 0,
    -- PMP/EVM 核心要素（v2.1 实现）
    pv REAL DEFAULT 0,                      -- Planned Value 计划值
    ev REAL DEFAULT 0,                      -- Earned Value 挣值
    ac REAL DEFAULT 0,                      -- Actual Cost 实际成本
    -- 元数据
    status TEXT DEFAULT 'draft',            -- draft / confirmed / archived
    computed_at TEXT NOT NULL,
    confirmed_by TEXT,
    confirmed_at TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (project_id) REFERENCES pm_projects(id),
    UNIQUE(project_id, period)
);
CREATE INDEX IF NOT EXISTS idx_pf_snapshot_project ON pf_profit_snapshot(project_id);
CREATE INDEX IF NOT EXISTS idx_pf_snapshot_period ON pf_profit_snapshot(period);
CREATE INDEX IF NOT EXISTS idx_pf_snapshot_status ON pf_profit_snapshot(status);

-- 预算告警记录
CREATE TABLE IF NOT EXISTS pf_budget_alert (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    period TEXT NOT NULL,
    alert_level TEXT NOT NULL,              -- warning / critical
    budget REAL NOT NULL,
    actual_cost REAL NOT NULL,
    over_budget_pct REAL NOT NULL,
    threshold REAL NOT NULL,
    message TEXT,
    status TEXT DEFAULT 'open',             -- open / acknowledged / resolved
    acknowledged_by TEXT,
    acknowledged_at TEXT,
    resolved_by TEXT,
    resolved_at TEXT,
    resolution_note TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (project_id) REFERENCES pm_projects(id)
);
CREATE INDEX IF NOT EXISTS idx_pf_alert_project ON pf_budget_alert(project_id);
CREATE INDEX IF NOT EXISTS idx_pf_alert_status ON pf_budget_alert(status);
CREATE INDEX IF NOT EXISTS idx_pf_alert_period ON pf_budget_alert(period);

-- 现金流（v2.2 占位表）
CREATE TABLE IF NOT EXISTS pf_cash_flow (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    period TEXT NOT NULL,
    plan_inflow REAL DEFAULT 0,
    actual_inflow REAL DEFAULT 0,
    plan_outflow REAL DEFAULT 0,
    actual_outflow REAL DEFAULT 0,
    net_cash_flow REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (project_id) REFERENCES pm_projects(id),
    UNIQUE(project_id, period)
);

-- 间接成本分摊（v2.2 占位表）
CREATE TABLE IF NOT EXISTS pf_cost_overhead (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    overhead_type TEXT NOT NULL,            -- management / shared / facility
    total_amount REAL NOT NULL,
    allocation_rule TEXT NOT NULL,          -- revenue_ratio / headcount_ratio / custom
    allocation_basis TEXT,                  -- 分摊基数 JSON
    created_at TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(period, overhead_type)
);
"""

# ===== 风险管理模块 =====

RK_SCHEMA = """
CREATE TABLE IF NOT EXISTS rk_risks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    risk_no TEXT UNIQUE NOT NULL,
    project_id INTEGER NOT NULL,
    risk_type TEXT NOT NULL,
    risk_level TEXT DEFAULT 'medium',
    title TEXT NOT NULL,
    description TEXT,
    impact TEXT,
    probability TEXT,   -- high / medium / low
    reporter TEXT NOT NULL,
    status TEXT DEFAULT 'open',
    owner TEXT,
    due_date TEXT,
    closed_at TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
    deleted_at TEXT DEFAULT NULL,
    FOREIGN KEY (project_id) REFERENCES pm_projects(id)
);
CREATE INDEX IF NOT EXISTS idx_rk_project ON rk_risks(project_id);
CREATE INDEX IF NOT EXISTS idx_rk_status ON rk_risks(status);
CREATE INDEX IF NOT EXISTS idx_rk_deleted ON rk_risks(deleted_at);

CREATE TABLE IF NOT EXISTS rk_risk_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    risk_id INTEGER NOT NULL,
    from_status TEXT,
    to_status TEXT,
    action TEXT NOT NULL,
    operator TEXT NOT NULL,
    comment TEXT,
    detail TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (risk_id) REFERENCES rk_risks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS rk_risk_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    risk_id INTEGER NOT NULL,
    action_type TEXT NOT NULL,
    description TEXT,
    owner TEXT,
    due_date TEXT,
    status TEXT DEFAULT 'pending',
    completed_at TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (risk_id) REFERENCES rk_risks(id) ON DELETE CASCADE
);
"""


# ===== 售后管理模块 =====

AS_SCHEMA = """
CREATE TABLE IF NOT EXISTS as_tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_no TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    description TEXT,                     -- 问题描述
    ticket_type TEXT,
    priority TEXT DEFAULT 'medium',       -- low/medium/high/critical
    state TEXT DEFAULT 'open',            -- 工单状态: open/assigned/in_progress/resolved/closed
    project_id INTEGER,
    customer_name TEXT,
    customer_contact TEXT,                -- 客户联系人
    customer_phone TEXT,                  -- 客户电话
    product_id TEXT,
    product_version TEXT,
    assignee TEXT,
    service_level TEXT DEFAULT 'silver',  -- gold/silver/bronze
    source TEXT DEFAULT 'warranty',       -- warranty/paid/free/other
    response_deadline TEXT,               -- SLA 响应截止
    resolution_deadline TEXT,             -- SLA 解决截止
    response_at TEXT,                     -- 首次响应时间
    resolved_at TEXT,
    closed_at TEXT,
    close_note TEXT,
    resolution TEXT,                      -- 解决方案
    resolution_type TEXT,                 -- fixed/workaround/duplicate/wont_fix
    satisfaction_score INTEGER,
    -- 审计字段
    created_by TEXT,
    updated_by TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
    deleted_at TEXT DEFAULT NULL,
    FOREIGN KEY (project_id) REFERENCES pm_projects(id)
);
CREATE INDEX IF NOT EXISTS idx_as_state ON as_tickets(state);
CREATE INDEX IF NOT EXISTS idx_as_priority ON as_tickets(priority);
CREATE INDEX IF NOT EXISTS idx_as_project ON as_tickets(project_id);
CREATE INDEX IF NOT EXISTS idx_as_assignee ON as_tickets(assignee);
CREATE INDEX IF NOT EXISTS idx_as_deleted ON as_tickets(deleted_at);

CREATE TABLE IF NOT EXISTS as_ticket_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,
    from_state TEXT,                       -- 原状态
    to_state TEXT,                         -- 新状态
    action TEXT NOT NULL,
    operator TEXT NOT NULL,
    comment TEXT,                          -- 备注
    detail TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (ticket_id) REFERENCES as_tickets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS as_warranty_contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_no TEXT,                     -- 维保合同号 WC-PROJID-NNN
    project_id INTEGER NOT NULL,
    warranty_start DATE,
    warranty_end DATE,
    service_level TEXT DEFAULT 'silver',
    remaining_tickets INTEGER DEFAULT 0,
    customer_contact TEXT,
    customer_phone TEXT,
    status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (project_id) REFERENCES pm_projects(id) ON DELETE CASCADE,
    UNIQUE(project_id)
);

CREATE TABLE IF NOT EXISTS as_sla_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    sla_level TEXT NOT NULL,
    total_tickets INTEGER DEFAULT 0,
    on_time_response INTEGER DEFAULT 0,
    on_time_resolve INTEGER DEFAULT 0,
    response_breach_rate REAL DEFAULT 0,
    resolve_breach_rate REAL DEFAULT 0,
    avg_response_hours REAL DEFAULT 0,
    avg_resolve_hours REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(snapshot_date, sla_level)
);
"""


# ===== 变更管理模块 =====

CH_SCHEMA = """
CREATE TABLE IF NOT EXISTS ch_change_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    change_type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    reason TEXT,
    proposed_changes TEXT,
    status TEXT DEFAULT 'draft',
    impact_delivery_days INTEGER DEFAULT 0,
    impact_cost_delta REAL DEFAULT 0,
    impact_revenue_delta REAL DEFAULT 0,
    submitted_by TEXT,
    submitted_at TEXT,
    approved_by TEXT,
    approved_at TEXT,
    executed_at TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
    deleted_at TEXT DEFAULT NULL,
    FOREIGN KEY (project_id) REFERENCES pm_projects(id)
);
CREATE INDEX IF NOT EXISTS idx_ch_project ON ch_change_requests(project_id);
CREATE INDEX IF NOT EXISTS idx_ch_status ON ch_change_requests(status);
CREATE INDEX IF NOT EXISTS idx_ch_deleted ON ch_change_requests(deleted_at);
"""


# ===== 数据集成模块 =====

INT_SCHEMA = """
CREATE TABLE IF NOT EXISTS int_staging (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connector_name TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    source_data TEXT,
    normalized_data TEXT,
    target_module TEXT NOT NULL,
    target_table TEXT,
    error_msg TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    processed_at TEXT,
    UNIQUE(connector_name, batch_id, source_id)
);
CREATE INDEX IF NOT EXISTS idx_int_staging_lookup
    ON int_staging(connector_name, batch_id, status);
CREATE INDEX IF NOT EXISTS idx_int_staging_target
    ON int_staging(target_module, target_table, status);

CREATE TABLE IF NOT EXISTS int_sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connector_name TEXT NOT NULL,
    batch_id TEXT NOT NULL UNIQUE,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    total_fetched INTEGER DEFAULT 0,
    new_count INTEGER DEFAULT 0,
    updated_count INTEGER DEFAULT 0,
    unchanged_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    params TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    error_msg TEXT
);
CREATE INDEX IF NOT EXISTS idx_int_sync_log_connector
    ON int_sync_log(connector_name, started_at DESC);

-- 频率配置表
CREATE TABLE IF NOT EXISTS int_frequency_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connector_name TEXT NOT NULL UNIQUE,
    schedule TEXT NOT NULL DEFAULT 'manual',  -- manual | cron | event
    cron_expr TEXT,
    event_triggers TEXT,                      -- JSON array
    enabled INTEGER DEFAULT 1,
    last_triggered_at TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_int_freq_connector ON int_frequency_config(connector_name);

-- 死信队列表
CREATE TABLE IF NOT EXISTS int_dead_letter (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connector_name TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_data TEXT,
    error_msg TEXT NOT NULL,
    error_type TEXT,                          -- auth | network | parse | validate | system
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    status TEXT DEFAULT 'pending',            -- pending | retrying | resolved | abandoned
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    resolved_at TEXT,
    resolved_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_int_dl_status ON int_dead_letter(status);
CREATE INDEX IF NOT EXISTS idx_int_dl_connector ON int_dead_letter(connector_name);

-- 字段映射配置表
CREATE TABLE IF NOT EXISTS int_field_mapping (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connector_name TEXT NOT NULL,
    target_module TEXT NOT NULL,
    target_table TEXT NOT NULL,
    source_field TEXT NOT NULL,
    target_field TEXT NOT NULL,
    transform_rule TEXT,
    is_required INTEGER DEFAULT 0,
    default_value TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(connector_name, target_module, target_table, source_field, target_field)
);
CREATE INDEX IF NOT EXISTS idx_int_fm_target ON int_field_mapping(target_module, target_table);
"""




# ===== 交付月报 v2.1 新增表 =====

DR_EXT_SCHEMA = """
-- 导入校验结果表
CREATE TABLE IF NOT EXISTS dr_import_validation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    sheet TEXT NOT NULL,               -- 签约 / POC&提前实施 / 异常项目 / 确收交接 / 验收交接
    row_index INTEGER NOT NULL,
    column_name TEXT,
    rule_code TEXT NOT NULL,           -- V01 ~ V10
    severity TEXT NOT NULL,            -- ERROR / WARNING
    message TEXT NOT NULL,
    original_value TEXT,
    corrected_value TEXT,
    status TEXT DEFAULT 'pending',     -- pending / confirmed / rejected
    operator TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_dr_val_month ON dr_import_validation(month, status);
"""

# ===== 确收分析 v2.1 新增表 =====

RR_EXT_SCHEMA = """
-- 手工调整留痕表
CREATE TABLE IF NOT EXISTS rr_edit_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    sheet TEXT NOT NULL,
    row_index INTEGER NOT NULL,
    column_name TEXT NOT NULL,
    original_value TEXT,
    new_value TEXT,
    edit_type TEXT NOT NULL,           -- dropdown / text / date / auto_fill
    operator TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_rr_edit_month ON rr_edit_history(month, sheet);
CREATE INDEX IF NOT EXISTS idx_rr_edit_row ON rr_edit_history(month, sheet, row_index);

-- 导入校验结果表
CREATE TABLE IF NOT EXISTS rr_import_validation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    sheet TEXT NOT NULL,
    row_index INTEGER NOT NULL,
    column_name TEXT,
    rule_code TEXT NOT NULL,           -- V01 ~ V12
    severity TEXT NOT NULL,            -- ERROR / WARNING
    message TEXT NOT NULL,
    original_value TEXT,
    corrected_value TEXT,
    status TEXT DEFAULT 'pending',     -- pending / confirmed / rejected
    operator TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_rr_val_month ON rr_import_validation(month, status);
"""

# ===== 知识库模块 =====

KB_SCHEMA = """
CREATE TABLE IF NOT EXISTS kb_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kb_id TEXT NOT NULL UNIQUE,
    knowledge_type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    summary TEXT DEFAULT '',
    product_code TEXT DEFAULT '',
    service_level TEXT DEFAULT '',
    applicable_version TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    current_version INTEGER NOT NULL DEFAULT 0,
    published_version INTEGER NOT NULL DEFAULT 0,
    author TEXT NOT NULL DEFAULT '',
    last_editor TEXT NOT NULL DEFAULT '',
    reviewer TEXT DEFAULT '',
    review_comment TEXT DEFAULT '',
    view_count INTEGER NOT NULL DEFAULT 0,
    reference_count INTEGER NOT NULL DEFAULT 0,
    helpful_count INTEGER NOT NULL DEFAULT 0,
    metadata TEXT DEFAULT '{}',
    -- 审计字段
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    published_at TEXT DEFAULT '',
    archived_at TEXT DEFAULT '',
    deleted_at TEXT DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS idx_kb_item_type ON kb_item(knowledge_type);
CREATE INDEX IF NOT EXISTS idx_kb_item_status ON kb_item(status);
CREATE INDEX IF NOT EXISTS idx_kb_item_product ON kb_item(product_code);
CREATE INDEX IF NOT EXISTS idx_kb_item_deleted ON kb_item(deleted_at);

CREATE TABLE IF NOT EXISTS kb_version (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kb_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    summary TEXT DEFAULT '',
    product_code TEXT DEFAULT '',
    metadata TEXT DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'draft',
    change_note TEXT DEFAULT '',
    publisher TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    published_at TEXT DEFAULT '',
    FOREIGN KEY (kb_id) REFERENCES kb_item(kb_id) ON DELETE CASCADE,
    UNIQUE(kb_id, version)
);
CREATE INDEX IF NOT EXISTS idx_kb_version_kb_id ON kb_version(kb_id);

CREATE TABLE IF NOT EXISTS kb_tag (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_name TEXT NOT NULL UNIQUE,
    tag_category TEXT DEFAULT 'general',
    usage_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS kb_item_tag (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kb_id TEXT NOT NULL,
    tag_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (kb_id) REFERENCES kb_item(kb_id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES kb_tag(id) ON DELETE CASCADE,
    UNIQUE(kb_id, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_kb_item_tag_kb ON kb_item_tag(kb_id);
CREATE INDEX IF NOT EXISTS idx_kb_item_tag_tag ON kb_item_tag(tag_id);

CREATE TABLE IF NOT EXISTS kb_item_embedding (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kb_id TEXT NOT NULL UNIQUE,
    version INTEGER NOT NULL DEFAULT 0,
    title_embedding BLOB NOT NULL,
    content_embedding BLOB NOT NULL,
    combined_embedding BLOB NOT NULL,
    model_version TEXT NOT NULL DEFAULT 'embeddinggemma-300m-qat-Q8_0',
    dim INTEGER NOT NULL DEFAULT 768,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (kb_id) REFERENCES kb_item(kb_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_kb_embed_kb_id ON kb_item_embedding(kb_id);

CREATE TABLE IF NOT EXISTS kb_review_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kb_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    action TEXT NOT NULL,
    operator TEXT NOT NULL,
    comment TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (kb_id) REFERENCES kb_item(kb_id) ON DELETE CASCADE
);

-- 知识图谱关联（P0 优化）
CREATE TABLE IF NOT EXISTS kb_relation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_kb_id TEXT NOT NULL,
    to_kb_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,       -- related / depends_on / references / parent_child
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (from_kb_id) REFERENCES kb_item(kb_id) ON DELETE CASCADE,
    FOREIGN KEY (to_kb_id) REFERENCES kb_item(kb_id) ON DELETE CASCADE,
    UNIQUE(from_kb_id, to_kb_id, relation_type)
);
CREATE INDEX IF NOT EXISTS idx_kb_rel_from ON kb_relation(from_kb_id);
CREATE INDEX IF NOT EXISTS idx_kb_rel_to ON kb_relation(to_kb_id);

-- FTS5 全文检索虚拟表
CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5(
    kb_id UNINDEXED,
    title,
    summary,
    content,
    tags,
    product_name,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""


# ===== 看板模块 =====

DASH_V2_SCHEMA = """
-- 指标快照缓存
CREATE TABLE IF NOT EXISTS dash_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_key TEXT NOT NULL,
    period TEXT NOT NULL,
    dimension TEXT DEFAULT 'total',
    dim_value TEXT DEFAULT 'all',
    value REAL NOT NULL,
    source_module TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    UNIQUE(metric_key, period, dimension, dim_value)
);
CREATE INDEX IF NOT EXISTS idx_dash_snapshot_lookup
    ON dash_snapshot(metric_key, period, dimension);

-- 用户自定义看板配置
CREATE TABLE IF NOT EXISTS dash_user_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    view_id TEXT NOT NULL UNIQUE,
    view_name TEXT NOT NULL,
    config TEXT NOT NULL,
    is_default INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_dash_user_config_user
    ON dash_user_config(user_id);

-- 视图配置表（多看板/多驾驶舱）
CREATE TABLE IF NOT EXISTS db_view_config (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    view_id     TEXT UNIQUE NOT NULL,
    view_name   TEXT NOT NULL,
    user_id     TEXT,
    is_default  INTEGER DEFAULT 0,
    is_system   INTEGER DEFAULT 0,
    layout      TEXT NOT NULL DEFAULT '{}',
    filters     TEXT DEFAULT '{}',
    chart_types TEXT DEFAULT '{}',
    created_at  TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT DEFAULT (datetime('now', 'localtime')),
    deleted_at  TEXT DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS idx_db_view_user ON db_view_config(user_id);
CREATE INDEX IF NOT EXISTS idx_db_view_default ON db_view_config(user_id, is_default);

-- 编辑历史表（驾驶舱明细编辑）
CREATE TABLE IF NOT EXISTS db_edit_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id   INTEGER NOT NULL,
    table_name  TEXT NOT NULL,
    field       TEXT NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    operator    TEXT NOT NULL,
    is_undo     INTEGER DEFAULT 0,
    batch_id    TEXT,
    created_at  TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_db_edit_record ON db_edit_history(record_id, table_name);

-- 数据源注册表
CREATE TABLE IF NOT EXISTS dashboard_data_source (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key    TEXT UNIQUE NOT NULL,
    module        TEXT NOT NULL,
    title         TEXT NOT NULL,
    description   TEXT,
    category      TEXT NOT NULL,                -- kpi / chart / table
    aggregate_sql TEXT NOT NULL,
    refresh_mode  TEXT DEFAULT 'realtime',
    enabled       INTEGER DEFAULT 1,
    created_at    TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at    TEXT DEFAULT (datetime('now', 'localtime'))
);
"""


# ===== 领域事件（Outbox） =====

OUTBOX_SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    published_at TEXT DEFAULT NULL,
    status TEXT NOT NULL DEFAULT 'pending'  -- pending | published | failed
);
CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox_events(status);
CREATE INDEX IF NOT EXISTS idx_outbox_created ON outbox_events(created_at);
"""


# ===== 系统级：导入校验错误（v2.1 P2，ProjectValidator 依赖）=====

IMPORT_ERRORS_SCHEMA = """
CREATE TABLE IF NOT EXISTS sys_import_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_no TEXT NOT NULL,
    sheet TEXT,
    row_index INTEGER,
    field_name TEXT,
    error_type TEXT NOT NULL,             -- missing/invalid/duplicate/format
    error_message TEXT NOT NULL,
    severity TEXT DEFAULT 'error',        -- error/warning
    raw_value TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_sys_import_errors_batch ON sys_import_errors(batch_no);
"""
