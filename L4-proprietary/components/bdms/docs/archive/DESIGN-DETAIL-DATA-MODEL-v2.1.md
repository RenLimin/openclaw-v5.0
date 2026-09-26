# BDMS v2.1 数据模型详细设计

> 版本：v2.1 Detail（2026-09-19）
> 层级：L4 专有业务层 — 数据架构
> 状态：设计阶段，待 Rex 审核

---

## 1. 概述

### 1.1 设计原则

| 原则             | 说明                                   |
| -------------- | ------------------------------------ |
| **单库多表**       | 所有模块共享 `data/bdms.db`，按模块前缀隔离        |
| **模块前缀隔离**     | 每个模块的表有唯一前缀（dr_/rr_/cr_/pm_/as_/...） |
| **宽表 + 强类型混合** | 报表类用宽表 JSON 行，交易类用强类型表               |
| **幂等键明确**      | 每个业务表有唯一约束，支持 INSERT OR REPLACE      |
| **按月为粒度**      | 所有业务数据按 month/period（YYYYMM）分区       |
| **索引分层**       | 按月 + 模块前缀建主索引；按业务字段建辅助索引             |

### 1.2 表总数（v2.1）

| 类别 | 表数 | 说明 |
|---|---|---|
| 元数据/核心表 | 5 | job / report_month / md_reference / sys_settings / import_log |
| 交付月报（dr_） | 2 | dr_sheet_row / dr_sheet_meta |
| 确收（rr_） | 2 | rr_sheet_row / rr_sheet_meta |
| 合同管理（cr_） | 6 | cr_contract / cr_contract_clause / cr_risk_item / cr_approval_log / cr_audit_trail / cr_template |
| 项目管理（pm_） | 5 | pm_project / pm_scope / pm_milestone / pm_member / pm_doc |
| 售后（as_） | 3 | as_ticket / as_ticket_log / as_sla_snapshot |
| 成本（ct_） | 4 | ct_timesheet / ct_timesheet_approval / ct_device_usage / ct_travel_cost |
| 风险（rk_） | 3 | rk_risk_item / rk_risk_review / rk_risk_summary |
| 看板快照（db_） | 1 | db_snapshot |
| 集成 staging（st_） | 6 | st_staging_ones / st_staging_oa / st_staging_timesheet / st_staging_finance / st_staging_wecom / st_sync_log |
| 知识库（kb_） | 2 | kb_item / kb_item_embedding |
| **合计** | **33** | 张表 |

---

## 2. 技术方案

### 2.1 技术选型

| 维度 | 选型 | 依据 |
|---|---|---|
| 数据库 | SQLite 3 | 现有 BDMS 已用，零运维，单文件便于备份 |
| ORM | 无（原生 SQL + 轻量封装） | 报表场景重，ORM 增加复杂度 |
| 宽表存储 | JSON 行 + 索引列 | 列定义随业务演进，避免频繁 DDL |
| 强类型表 | 标准关系表 | 交易/审批类数据需强约束 |
| 全文检索 | SQLite FTS5 | 合同/知识库文本检索，零额外依赖 |

### 2.2 与现有代码的关系

- 现有 5 张核心表 + dr_* + rr_* + db_snapshot 保持不变
- 新增表全部按模块前缀隔离，不影响现有表
- schema 初始化从 `db.init_db()` 扩展，保持幂等（IF NOT EXISTS）

### 2.3 迁移策略

| 阶段 | 操作 | 风险 |
|---|---|---|
| v2.1 初期 | 新建表（不修改现有表） | 低 |
| v2.1 中期 | 新增索引（CREATE INDEX IF NOT EXISTS） | 低 |
| v2.1 后期 | 可选：rr_sheet_row 结构优化（需数据迁移脚本） | 中 |
| v3.0 | 大版本升级（独立迁移脚本） | 高 |

---

## 3. 核心元数据表（已存在）

### 3.1 job — 任务记录

```sql
CREATE TABLE IF NOT EXISTS job (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    module TEXT NOT NULL,
    month TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'auto',
    status TEXT NOT NULL DEFAULT 'pending',
    progress INTEGER DEFAULT 0,
    message TEXT,
    output_path TEXT,
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_job_module_month ON job(module, month);
```

### 3.2 report_month — 月度数据登记

```sql
CREATE TABLE IF NOT EXISTS report_month (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    module TEXT NOT NULL,
    month TEXT NOT NULL,
    source_path TEXT,
    generated_at TEXT DEFAULT (datetime('now', 'localtime')),
    row_counts TEXT,
    UNIQUE(module, month)
);
```

### 3.3 md_reference — 参考数据/字典

```sql
CREATE TABLE IF NOT EXISTS md_reference (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_type TEXT NOT NULL,
    code TEXT NOT NULL,
    label TEXT NOT NULL,
    extra TEXT,
    sort_order INTEGER DEFAULT 0,
    enabled INTEGER DEFAULT 1,
    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(data_type, code)
);
CREATE INDEX IF NOT EXISTS idx_md_ref_type ON md_reference(data_type);
```

### 3.4 sys_settings — 系统设置

```sql
CREATE TABLE IF NOT EXISTS sys_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);
```

### 3.5 import_log — 导入日志

```sql
CREATE TABLE IF NOT EXISTS import_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    module TEXT NOT NULL,
    month TEXT NOT NULL,
    source_type TEXT,
    source_path TEXT,
    data_type TEXT,
    row_count INTEGER,
    status TEXT,
    message TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
```

---

## 4. 交付月报模块（dr_）— 已存在

```sql
CREATE TABLE IF NOT EXISTS dr_sheet_row (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    sheet TEXT NOT NULL,
    row_index INTEGER NOT NULL,
    data TEXT NOT NULL,
    UNIQUE(month, sheet, row_index)
);
CREATE INDEX IF NOT EXISTS idx_dr_sheet ON dr_sheet_row(month, sheet);

CREATE TABLE IF NOT EXISTS dr_sheet_meta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    sheet TEXT NOT NULL,
    columns TEXT NOT NULL,
    row_count INTEGER DEFAULT 0,
    UNIQUE(month, sheet)
);
```

---

## 5. 确收模块（rr_）— 已存在

```sql
CREATE TABLE IF NOT EXISTS rr_sheet_row (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    sheet TEXT NOT NULL,
    row_index INTEGER NOT NULL,
    contract_no TEXT,
    category TEXT,
    archive_month TEXT,
    perf_id TEXT,
    data TEXT NOT NULL,
    UNIQUE(period, sheet, row_index)
);
CREATE INDEX IF NOT EXISTS idx_rr_sheet ON rr_sheet_row(period, sheet);
CREATE INDEX IF NOT EXISTS idx_rr_contract ON rr_sheet_row(contract_no);
CREATE INDEX IF NOT EXISTS idx_rr_archive ON rr_sheet_row(archive_month);

CREATE TABLE IF NOT EXISTS rr_sheet_meta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    sheet TEXT NOT NULL,
    columns TEXT NOT NULL,
    row_count INTEGER DEFAULT 0,
    UNIQUE(period, sheet)
);
```

---

## 6. 合同管理模块（cr_）— 新增

### 6.1 cr_contract — 合同主表

```sql
CREATE TABLE IF NOT EXISTS cr_contract (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_no TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    contract_type TEXT,
    party_a TEXT,
    party_b TEXT,
    amount REAL NOT NULL DEFAULT 0,
    amount_cn TEXT,
    currency TEXT DEFAULT 'CNY',
    effective_date TEXT,
    expiry_date TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    approval_level INTEGER DEFAULT 1,
    signed_date TEXT,
    archive_date TEXT,
    created_by TEXT,
    updated_by TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_cr_status ON cr_contract(status);
CREATE INDEX IF NOT EXISTS idx_cr_amount ON cr_contract(amount);
```

**幂等键**：`contract_no`（UNIQUE）

### 6.2 cr_contract_clause — 合同条款明细

```sql
CREATE TABLE IF NOT EXISTS cr_contract_clause (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    clause_type TEXT NOT NULL,
    clause_title TEXT,
    clause_content TEXT,
    summary TEXT,
    key_terms TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (contract_id) REFERENCES cr_contract(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_cr_clause_contract ON cr_contract_clause(contract_id);
```

### 6.3 cr_risk_item — 风险扫描结果

```sql
CREATE TABLE IF NOT EXISTS cr_risk_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    scan_batch TEXT NOT NULL,
    risk_category TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    clause_type TEXT,
    issue_summary TEXT,
    evidence TEXT,
    legal_basis TEXT,
    suggestion TEXT,
    status TEXT DEFAULT 'open',
    resolved_by TEXT,
    resolved_at TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (contract_id) REFERENCES cr_contract(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_cr_risk_contract ON cr_risk_item(contract_id);
CREATE INDEX IF NOT EXISTS idx_cr_risk_level ON cr_risk_item(risk_level);
```

### 6.4 cr_approval_log — 审批日志

```sql
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
    FOREIGN KEY (contract_id) REFERENCES cr_contract(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_cr_appr_contract ON cr_approval_log(contract_id);
```

### 6.5 cr_audit_trail — 操作审计

```sql
CREATE TABLE IF NOT EXISTS cr_audit_trail (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    operation TEXT NOT NULL,
    field_name TEXT,
    old_value TEXT,
    new_value TEXT,
    operator TEXT NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (contract_id) REFERENCES cr_contract(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_cr_audit_contract ON cr_audit_trail(contract_id);
```

### 6.6 cr_template — 合同模板

```sql
CREATE TABLE IF NOT EXISTS cr_template (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_code TEXT UNIQUE NOT NULL,
    template_name TEXT NOT NULL,
    contract_type TEXT,
    file_path TEXT NOT NULL,
    version TEXT DEFAULT '1.0',
    is_default INTEGER DEFAULT 0,
    enabled INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);
```

---

## 7. 项目管理模块（pm_）— 新增

### 7.1 pm_project — 项目主表

```sql
CREATE TABLE IF NOT EXISTS pm_project (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_no TEXT UNIQUE NOT NULL,
    project_name TEXT NOT NULL,
    contract_id INTEGER,
    project_type TEXT,
    dept TEXT,
    pm TEXT,
    status TEXT DEFAULT 'init',
    start_date TEXT,
    end_date TEXT,
    actual_start_date TEXT,
    actual_end_date TEXT,
    budget REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (contract_id) REFERENCES cr_contract(id)
);
CREATE INDEX IF NOT EXISTS idx_pm_status ON pm_project(status);
CREATE INDEX IF NOT EXISTS idx_pm_pm ON pm_project(pm);
```

**幂等键**：`project_no`（UNIQUE）

### 7.2 pm_scope — 项目范围/履约项

```sql
CREATE TABLE IF NOT EXISTS pm_scope (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    perf_id TEXT,
    scope_name TEXT NOT NULL,
    scope_type TEXT,
    amount REAL DEFAULT 0,
    planned_start TEXT,
    planned_end TEXT,
    actual_start TEXT,
    actual_end TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (project_id) REFERENCES pm_project(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_pm_scope_project ON pm_scope(project_id);
CREATE INDEX IF NOT EXISTS idx_pm_scope_perf ON pm_scope(perf_id);
```

### 7.3 pm_milestone — 里程碑

```sql
CREATE TABLE IF NOT EXISTS pm_milestone (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    milestone_name TEXT NOT NULL,
    planned_date TEXT,
    actual_date TEXT,
    status TEXT DEFAULT 'pending',
    description TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (project_id) REFERENCES pm_project(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_pm_milestone_project ON pm_milestone(project_id);
```

### 7.4 pm_member — 项目成员

```sql
CREATE TABLE IF NOT EXISTS pm_member (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    member_name TEXT NOT NULL,
    role TEXT,
    allocation REAL DEFAULT 1.0,
    start_date TEXT,
    end_date TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (project_id) REFERENCES pm_project(id) ON DELETE CASCADE,
    UNIQUE(project_id, member_name, role)
);
```

### 7.5 pm_doc — 项目文档

```sql
CREATE TABLE IF NOT EXISTS pm_doc (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    doc_type TEXT,
    doc_title TEXT NOT NULL,
    file_path TEXT,
    uploaded_by TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (project_id) REFERENCES pm_project(id) ON DELETE CASCADE
);
```

---

## 8. 售后管理模块（as_）— 新增

### 8.1 as_ticket — 工单主表

```sql
CREATE TABLE IF NOT EXISTS as_ticket (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_no TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    ticket_type TEXT,
    priority TEXT DEFAULT 'medium',
    status TEXT DEFAULT 'open',
    project_id INTEGER,
    customer_name TEXT,
    contact_person TEXT,
    contact_phone TEXT,
    assignee TEXT,
    sla_level TEXT DEFAULT 'P2',
    sla_response_hours INTEGER DEFAULT 4,
    sla_resolve_hours INTEGER DEFAULT 24,
    first_response_at TEXT,
    resolved_at TEXT,
    closed_at TEXT,
    created_by TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_as_status ON as_ticket(status);
CREATE INDEX IF NOT EXISTS idx_as_priority ON as_ticket(priority);
CREATE INDEX IF NOT EXISTS idx_as_assignee ON as_ticket(assignee);
```

**幂等键**：`ticket_no`（UNIQUE）

### 8.2 as_ticket_log — 工单操作日志

```sql
CREATE TABLE IF NOT EXISTS as_ticket_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    operator TEXT NOT NULL,
    detail TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (ticket_id) REFERENCES as_ticket(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_as_log_ticket ON as_ticket_log(ticket_id);
```

### 8.3 as_sla_snapshot — SLA 统计快照

```sql
CREATE TABLE IF NOT EXISTS as_sla_snapshot (
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
```

---

## 9. 成本管理模块（ct_）— 新增

### 9.1 ct_timesheet — 工时填报

```sql
CREATE TABLE IF NOT EXISTS ct_timesheet (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    employee_name TEXT NOT NULL,
    work_date TEXT NOT NULL,
    hours REAL NOT NULL DEFAULT 0,
    work_type TEXT,
    description TEXT,
    status TEXT DEFAULT 'submitted',
    approver TEXT,
    approved_at TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (project_id) REFERENCES pm_project(id)
);
CREATE INDEX IF NOT EXISTS idx_ct_ts_project ON ct_timesheet(project_id);
CREATE INDEX IF NOT EXISTS idx_ct_ts_employee ON ct_timesheet(employee_name);
CREATE INDEX IF NOT EXISTS idx_ct_ts_date ON ct_timesheet(work_date);
```

### 9.2 ct_timesheet_approval — 工时审批记录

```sql
CREATE TABLE IF NOT EXISTS ct_timesheet_approval (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timesheet_id INTEGER NOT NULL,
    approver TEXT NOT NULL,
    action TEXT NOT NULL,
    comment TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (timesheet_id) REFERENCES ct_timesheet(id) ON DELETE CASCADE
);
```

### 9.3 ct_device_usage — 设备领用

```sql
CREATE TABLE IF NOT EXISTS ct_device_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    device_name TEXT NOT NULL,
    device_type TEXT,
    start_date TEXT,
    end_date TEXT,
    cost_per_day REAL DEFAULT 0,
    total_cost REAL DEFAULT 0,
    status TEXT DEFAULT 'in_use',
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (project_id) REFERENCES pm_project(id)
);
CREATE INDEX IF NOT EXISTS idx_ct_dev_project ON ct_device_usage(project_id);
```

### 9.4 ct_travel_cost — 差旅费用

```sql
CREATE TABLE IF NOT EXISTS ct_travel_cost (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    employee_name TEXT NOT NULL,
    travel_date TEXT NOT NULL,
    cost_type TEXT,
    amount REAL DEFAULT 0,
    currency TEXT DEFAULT 'CNY',
    description TEXT,
    status TEXT DEFAULT 'submitted',
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (project_id) REFERENCES pm_project(id)
);
CREATE INDEX IF NOT EXISTS idx_ct_travel_project ON ct_travel_cost(project_id);
```

---

## 10. 风险管理模块（rk_）— 新增

### 10.1 rk_risk_item — 风险项

```sql
CREATE TABLE IF NOT EXISTS rk_risk_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    risk_no TEXT UNIQUE NOT NULL,
    project_id INTEGER NOT NULL,
    risk_type TEXT NOT NULL,
    risk_level TEXT DEFAULT 'medium',
    title TEXT NOT NULL,
    description TEXT,
    impact TEXT,
    likelihood TEXT,
    reporter TEXT NOT NULL,
    status TEXT DEFAULT 'open',
    owner TEXT,
    due_date TEXT,
    closed_at TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (project_id) REFERENCES pm_project(id)
);
CREATE INDEX IF NOT EXISTS idx_rk_project ON rk_risk_item(project_id);
CREATE INDEX IF NOT EXISTS idx_rk_level ON rk_risk_item(risk_level);
CREATE INDEX IF NOT EXISTS idx_rk_status ON rk_risk_item(status);
```

### 10.2 rk_risk_review — 风险审核记录

```sql
CREATE TABLE IF NOT EXISTS rk_risk_review (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    risk_id INTEGER NOT NULL,
    reviewer TEXT NOT NULL,
    action TEXT NOT NULL,
    decision TEXT,
    comment TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (risk_id) REFERENCES rk_risk_item(id) ON DELETE CASCADE
);
```

### 10.3 rk_risk_summary — 风险台账快照

```sql
CREATE TABLE IF NOT EXISTS rk_risk_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_month TEXT NOT NULL,
    project_id INTEGER,
    risk_level TEXT NOT NULL,
    open_count INTEGER DEFAULT 0,
    closed_count INTEGER DEFAULT 0,
    new_count INTEGER DEFAULT 0,
    resolved_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(snapshot_month, project_id, risk_level)
);
```

---

## 11. 数据集成模块（st_）— 新增

### 11.1 通用 staging 表结构

```sql
CREATE TABLE IF NOT EXISTS st_staging_{connector} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    raw_data TEXT NOT NULL,
    normalized_data TEXT,
    sync_status TEXT DEFAULT 'pending',
    error_message TEXT,
    synced_at TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(batch_id, source_id)
);
CREATE INDEX IF NOT EXISTS idx_st_{conn}_batch ON st_staging_{connector}(batch_id);
CREATE INDEX IF NOT EXISTS idx_st_{conn}_status ON st_staging_{connector}(sync_status);
```

### 11.2 连接器清单

| 表名 | 连接器 | 数据源 | 落地目标 |
|---|---|---|---|
| st_staging_ones | ones | ONES 项目管理 | project_management / delivery_report |
| st_staging_oa | oa | OA 系统 | contract_management / project_management |
| st_staging_timesheet | timesheet | 工时门户 | project_management → cost |
| st_staging_finance | finance | 财务报表 | project_management → revenue |
| st_staging_wecom | wecom | 企业微信文档 | after_sales / risk |

### 11.3 st_sync_log — 同步日志

```sql
CREATE TABLE IF NOT EXISTS st_sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connector_name TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    sync_mode TEXT DEFAULT 'incremental',
    total_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running',
    error_message TEXT,
    started_at TEXT DEFAULT (datetime('now', 'localtime')),
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_st_log_connector ON st_sync_log(connector_name);
```

---

## 12. 知识库模块（kb_）— 新增

### 12.1 kb_item — 知识条目主表

```sql
CREATE TABLE IF NOT EXISTS kb_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kb_id TEXT UNIQUE NOT NULL,
    product_id TEXT,
    knowledge_type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT,
    author TEXT,
    version TEXT DEFAULT '1.0',
    enabled INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_kb_type ON kb_item(knowledge_type);
CREATE INDEX IF NOT EXISTS idx_kb_product ON kb_item(product_id);

-- FTS5 全文检索虚拟表
CREATE VIRTUAL TABLE IF NOT EXISTS kb_item_fts USING fts5(
    title, content,
    content='kb_item', content_rowid='id',
    tokenize='unicode61'
);
```

### 12.2 kb_item_embedding — 语义向量索引

```sql
CREATE TABLE IF NOT EXISTS kb_item_embedding (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kb_id TEXT NOT NULL,
    chunk_index INTEGER DEFAULT 0,
    chunk_text TEXT NOT NULL,
    embedding BLOB,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (kb_id) REFERENCES kb_item(kb_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_kb_emb_kb ON kb_item_embedding(kb_id);
```

---

## 13. 看板快照（db_）— 已存在

```sql
CREATE TABLE IF NOT EXISTS db_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    metric TEXT NOT NULL,
    dimension TEXT,
    value REAL,
    extra TEXT,
    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(month, metric, dimension)
);
CREATE INDEX IF NOT EXISTS idx_db_snap ON db_snapshot(month, metric);
```

---

## 14. 索引策略

### 14.1 索引分层

| 层级 | 索引类型 | 适用表 | 说明 |
|---|---|---|---|
| L1 | 主索引 (month, ...) | 所有带 month/period 字段的表 | 按月分区查询 |
| L2 | 业务字段索引 | 合同/项目/工单等 | 状态/负责人/类型等常用过滤 |
| L3 | 全文索引 (FTS5) | kb_item | 知识检索 |
| L4 | 向量索引（应用层） | kb_item_embedding | 语义检索（Python 层计算） |

### 14.2 索引命名规范

```
idx_{表前缀}_{字段名}
```

---

## 15. 实现路径

### Step 1：扩展 init_db()（0.5 天）

| 步骤 | 产出物 | 验证方式 |
|---|---|---|
| 1.1 创建各模块 schema 文件 | schemas/cr_schema.py / pm_schema.py / ... | import 无报错 |
| 1.2 扩展 db.init_db() 加载所有 schema | init_db() 更新 | 初始化后 33 张表全存在 |
| 1.3 编写 schema 版本检查脚本 | verify_schema.py | 表名/字段/索引全对齐 |

### Step 2：核心模块表上线（0.5 天）

| 步骤 | 产出物 | 验证方式 |
|---|---|---|
| 2.1 contract_management 6 张表 | cr_* 表 | DDL 执行成功 |
| 2.2 project_management 5 张表 | pm_* 表 | DDL 执行成功 |
| 2.3 外键约束验证 | 外键测试 | ON DELETE CASCADE 生效 |

### Step 3：横切模块表上线（0.5 天）

| 步骤 | 产出物 | 验证方式 |
|---|---|---|
| 3.1 after_sales 3 张表 | as_* 表 | DDL 执行成功 |
| 3.2 cost 4 张表 | ct_* 表 | DDL 执行成功 |
| 3.3 risk 3 张表 | rk_* 表 | DDL 执行成功 |
| 3.4 integration 6 张表 | st_* 表 | DDL 执行成功 |
| 3.5 knowledge_base 2 张表 + FTS5 | kb_* 表 | DDL 执行成功，FTS5 可用 |

### Step 4：数据迁移脚本（0.5 天）

| 步骤 | 产出物 | 验证方式 |
|---|---|---|
| 4.1 历史数据迁移工具 | migrate_from_v1.py | 现有数据无损迁移 |
| 4.2 回滚脚本 | rollback_v21.py | 可回退到 v1 状态 |

**依赖关系**：Step 1 → Step 2/3（可并行） → Step 4

**回滚方案**：
- 所有表 CREATE TABLE IF NOT EXISTS，失败不影响现有表
- 整体失败 → 删新建表前缀的所有表

---

## 16. 表类型分类与维护策略

### 16.1 表类型分类

| 表类型 | 特征 | 维护策略 | 代表表 |
|---|---|---|---|
| **业务数据表** | 核心交易数据，随业务持续增长，有幂等键 | 定期归档（>12 个月迁移至归档表），按月分区查询 | cr_contract / pm_project / as_ticket / ct_timesheet / rk_risk_item |
| **报表数据表** | 按月聚合的报表数据，只读为主，历史月份不修改 | 按月切片，历史月份只读；年度末可归档至独立 db 文件 | dr_sheet_row / rr_sheet_row / dr_sheet_meta / rr_sheet_meta |
| **配置/字典表** | 低频变更的字典/配置数据，数据量小 | 全量缓存到内存，变更时刷新缓存；无需归档 | sys_settings / md_reference / cr_template |
| **快照/汇总表** | 预计算的汇总数据，可重算，有 TTL | 定时刷新或事件驱动刷新；过期数据可清理 | db_snapshot / as_sla_snapshot / rk_risk_summary / dash_snapshot |
| **日志/审计表** | 只追加不修改，数据量持续增长 | 定期归档（>6 个月迁移至归档表），按时间分区 | cr_audit_trail / cr_approval_log / as_ticket_log / st_sync_log / import_log / job |
| **Staging 表** | 临时数据，处理后即清理 | 每次同步前清空或按 batch_id 清理，保持表体积小 | st_staging_* |
| **知识库表** | 知识文档 + 向量索引，中等数据量 | 知识条目软删除 + 定期清理；向量索引随知识更新 | kb_item / kb_item_embedding / kb_item_fts |

### 16.2 各类型表的维护规则

| 表类型 | 归档阈值 | 归档方式 | 清理策略 | 备份优先级 |
|---|---|---|---|---|
| 业务数据表 | > 12 个月 | 迁移至 `archive_` 前缀表或独立 db 文件 | 不清理，只归档 | 高（每日备份） |
| 报表数据表 | > 24 个月 | 导出 Excel 后迁移至年度归档 db | 不清理，只归档 | 中（每周备份，因可重算） |
| 配置/字典表 | 不归档 | — | 不清理 | 高（变更时即时备份） |
| 快照/汇总表 | 不归档 | — | 定时刷新覆盖，无需清理 | 低（可重算） |
| 日志/审计表 | > 6 个月 | 迁移至 `archive_` 前缀表 | 自动清理已归档数据 | 中（每月备份） |
| Staging 表 | 每次同步后 | — | 每次同步前清空上一批次 | 低（无需备份） |
| 知识库表 | 不归档 | — | 软删除 30 天后物理清理 | 高（每日备份） |

### 16.3 业务数据表的归档实现

```sql
-- 归档表命名规范：{原表名}_archive
CREATE TABLE IF NOT EXISTS cr_contract_archive (
    LIKE cr_contract INCLUDING ALL,
    archived_at TEXT DEFAULT (datetime('now', 'localtime')),
    archive_reason TEXT DEFAULT 'age'
);

-- 归档操作（每月由定时任务执行）
INSERT INTO cr_contract_archive
    SELECT *, datetime('now', 'localtime'), 'age'
    FROM cr_contract
    WHERE created_at < date('now', '-12 months');

DELETE FROM cr_contract
    WHERE created_at < date('now', '-12 months');
```

---

## 17. 数据增长与分片策略

### 17.1 数据增长预估

| 表 | 当前月增量 | 12 个月预估 | 24 个月预估 | 增长类型 |
|---|---|---|---|---|
| cr_contract | ~50 份 | ~600 份 | ~1200 份 | 低（合同审批周期长） |
| pm_project | ~30 个 | ~360 个 | ~720 个 | 中（项目周期 3-6 个月） |
| as_ticket | ~200 单 | ~2400 单 | ~4800 单 | 高（持续产生） |
| ct_timesheet | ~500 条 | ~6000 条 | ~12000 条 | **极高**（每月工时填报） |
| rk_risk_item | ~20 条 | ~240 条 | ~480 条 | 低 |
| cr_audit_trail | ~500 条 | ~6000 条 | ~12000 条 | **极高**（每次操作留痕） |
| st_staging_* | 每批次 ~100-500 | — | — | 临时（处理后清理） |

### 17.2 分片策略：按月分区 + 按模块分库

**当前阶段（< 100 万行/表）**：SQLite 单库 + 按月索引即可，无需分片。

**增长阶段（100 万-1000 万行/表）**：按月份分表（表名后缀 `_YYYYMM`），查询时按月份路由。

```sql
-- 按月分表示例：ct_timesheet_202601, ct_timesheet_202602, ...
CREATE TABLE IF NOT EXISTS ct_timesheet_{yyyymm} (
    LIKE ct_timesheet INCLUDING ALL
);

-- 查询时按月份路由到对应分表
-- 跨月查询：UNION ALL 合并多个月份分表
```

**未来阶段（> 1000 万行/表）**：按模块分库（独立 db 文件），每个模块一个数据库。

```
project_management.db  -- pm_*, ct_*, rk_*
contract_management.db  -- cr_*
after_sales.db         -- as_*
integration.db         -- st_*
knowledge_base.db      -- kb_*
core.db                -- job, report_month, md_reference, sys_settings
```

### 17.3 分片演进路径

| 阶段 | 触发条件 | 方案 | 迁移成本 |
|---|---|---|---|
| Phase 1 | 当前 | 单库 + 索引优化 | 零 |
| Phase 2 | 单表 > 100 万行 | 按月分表（表后缀） | 中（写迁移脚本，双跑验证） |
| Phase 3 | 单库 > 500MB | 按模块分库 | 中（分库 + 跨库查询适配） |
| Phase 4 | 单表 > 1000 万行 | 迁移至 PostgreSQL | 高（SQL 方言差异 + 迁移） |

### 17.4 当前阶段的优化措施（v2.1 立即执行）

1. **索引优化**：确保所有高频查询字段有索引（已在 §14 定义）
2. **WAL 模式**：SQLite 开启 WAL（Write-Ahead Logging），提升并发读写性能
3. **定期 VACUUM**：每月执行 `VACUUM` 回收已删除空间
4. **快照/汇总表**：Dashboard 和统计走预计算快照，避免实时全表聚合
5. **归档定时任务**：每月 1 日自动归档 > 12 个月的业务数据

---

## 18. 报表配置表与归档表

### 18.1 报表配置表（已在本文档中定义）

| 表名 | 用途 | 所在章节 |
|---|---|---|
| `dr_sheet_meta` | 交付月报的 Sheet 结构定义（列名、行数、图例） | §4 |
| `rr_sheet_meta` | 确收月报的 Sheet 结构定义（列名、行数、图例） | §5 |

这两张表存储了每个 Sheet 的**元数据**（列定义、行数、图例配置），是报表渲染的依据。

### 18.2 报表数据表

| 表名 | 用途 | 所在章节 |
|---|---|---|
| `dr_sheet_row` | 交付月报的每行数据（JSON 格式） | §4 |
| `rr_sheet_row` | 确收月报的每行数据（JSON 格式） | §5 |

### 18.3 报表相关的配置表（在各模块详细设计中定义）

| 配置 | 说明 | 所在文档 |
|---|---|---|
| 图例定义 | 交付/确收各场景的图例配置 | DELIVERY-REPORT.md §3 + REVENUE.md（待补充） |
| Sheet 模板 | Excel 模板文件（.xlsx） | DELIVERY-REPORT.md §2 |
| 输出格式 | 报表样式/颜色/字体 | BASE.md §3.3 BaseExporter |

> **结论**：报表的配置表和数据表已在 DATA-MODEL 中完整定义（§4/§5）。图例的具体内容属于各模块的业务逻辑，在对应模块的详细设计中定义。

---

## 19. 与业界数据模型最佳实践的对比与优化

### 19.1 对标标准

| 业界实践 | 核心思想 | BDMS 当前做法 | 差距 | 优化建议 |
|---|---|---|---|---|
| **Temporal Tables** | 系统版本化表，自动记录历史行 | 审计表手动实现（cr_audit_trail） | 审计表覆盖不全 | 核心业务表增加 `valid_from/valid_to` 时间戳，支持时间旅行查询 |
| **Soft Delete** | 标记删除 + 定期清理 | 部分表有 deleted 字段 | 不统一 | 所有业务表统一增加 `deleted_at` 字段，统一软删除模式 |
| **Audit Columns** | 每张表加 created_at/updated_at/created_by/updated_by | 部分表有，部分表没有 | 不统一 | **所有表**强制包含 4 个审计字段（created_at, updated_at, created_by, updated_by） |
| **Row Versioning** | 行版本号，乐观锁 | 无 | 并发更新可能冲突 | 核心业务表增加 `version INTEGER` 字段，更新时 WHERE version = ? |
| **Schema Registry** | 集中管理 schema 变更 | schema 定义分散在各模块 | 缺乏集中管控 | 建立 `schema_registry.py`，集中管理所有表 DDL 和变更历史 |
| **Data Classification** | 数据分级（公开/内部/机密/绝密） | 无分级 | 敏感数据保护不足 | 按数据分级定义访问控制策略（合同金额=机密，项目信息=内部） |
| **Encryption at Rest** | 静态数据加密 | 部分字段 AES-256 加密 | 不统一 | 明确哪些字段加密、哪些不加密，统一加密工具函数 |
| **Backup & PITR** | 时间点恢复 | 全量备份 | 缺 PITR | SQLite WAL 归档 + 定期 base backup，支持时间点恢复 |

### 19.2 建议的优化项

#### P0（v2.1 必须做）

1. **统一审计字段**
   - 问题：部分表缺少 created_by/updated_by
   - 方案：所有业务表增加 4 个审计字段，Base 层提供 `AuditMixin`
   - 成本：低（每个表 +4 字段）
   - 收益：高（统一审计追踪）

2. **统一软删除**
   - 问题：deleted 字段不统一，部分表无软删除
   - 方案：所有业务表增加 `deleted_at` 字段，BaseRepository 自动过滤已删除记录
   - 成本：低
   - 收益：高（防止数据误删）

#### P1（v2.2 可做）

3. **乐观锁（Row Versioning）**
   - 问题：并发更新同一记录可能冲突
   - 方案：核心业务表增加 `version` 字段，BaseService 自动处理版本检查
   - 成本：中
   - 收益：中（当前并发量不大）

4. **Schema Registry**
   - 问题：schema 定义分散，变更难以追踪
   - 方案：建立 `schema_registry.py`，集中管理 DDL
   - 成本：中
   - 收益：中（便于维护和审计）

#### P2（远期）

5. **Temporal Tables**
   - 问题：历史数据追踪依赖手动审计表
   - 方案：核心业务表增加时间戳，支持时间旅行
   - 成本：高
   - 收益：低（当前需求不迫切）

6. **数据分级 + 动态脱敏**
   - 问题：敏感数据保护依赖手动脱敏
   - 方案：按数据分级自动应用脱敏规则
   - 成本：中
   - 收益：中（合规要求）

---

## 20. 预期效果 + 验收标准

### 16.1 预期效果

**功能**：
- 33 张表覆盖 8 个模块全部数据需求
- 所有表有明确幂等键和索引策略
- 字段级加密支持（合同敏感信息）

**性能**：
- 单表 10 万行级查询 < 50ms（主索引命中）
- FTS5 全文检索 < 100ms（万级文档）
- 语义向量检索在应用层处理，不影响 DB 性能

**质量**：
- 所有表 DDL 幂等（IF NOT EXISTS）
- 外键约束生效，数据完整性有保障
- schema 版本检查脚本可一键验证

### 16.2 验收标准

| 类别 | 标准 | 验证方式 |
|---|---|---|
| **功能验收** | 33 张表全部创建成功 | verify_schema.py |
| **功能验收** | 所有幂等键（UNIQUE 约束）生效 | 插入重复数据测试 |
| **功能验收** | 外键约束 + ON DELETE CASCADE 生效 | 删除父表行测试 |
| **功能验收** | FTS5 全文检索可用 | MATCH 查询测试 |
| **数据验收** | 现有表（dr_/rr_/核心表）数据零影响 | 迁移前后 count 对比 |
| **性能验收** | 主索引查询 < 50ms（10 万行级） | EXPLAIN QUERY PLAN |
| **幂等验收** | init_db() 重复执行结果一致 | 连续执行 3 次，表结构不变 |
| **文档验收** | 33 张表全部有字段说明、索引说明 | 本文档完整性检查 |

### 16.3 交付验收 7 步法映射

| 步骤 | 本模块映射 |
|---|---|
| 独立审计 | 33 张表 DDL 独立 review |
| 契约对齐 | 与 v2.1 大纲 §5 表设计原则完全对齐 |
| 全入口执行 | init_db() + verify_schema.py 全量执行 |
| 黄金基准 | 现有 dr_/rr_ 表数据零变更 |
| 幂等测试 | init_db() 重复执行结果一致 |
| 调用点扫描 | 所有模块代码引用的表名与 DDL 对齐 |
| 回归锁定 | 现有测试全通过 |

---

## 变更历史

- 2026-09-19: v2.1 Detail 初版（33 张表完整设计）
- 2026-09-19: 新增表类型分类（§16）、数据增长与分片策略（§17）、报表配置表说明（§18）、业界最佳实践对比（§19）
