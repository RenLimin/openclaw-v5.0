-- ============================================================
-- 销售合同审批模块 — 数据库 Schema
-- 组件: SCA-001 (L4)
-- 持久化: SQLite (复用 L2 持久化适配)
-- ============================================================

-- 合同主表
CREATE TABLE IF NOT EXISTS contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_no TEXT UNIQUE NOT NULL,           -- 合同编号 CON-YYYY-NNN
    title TEXT NOT NULL,                         -- 合同名称
    contract_type TEXT NOT NULL,                 -- 类型：tech_service / software_license / sow
    party_a TEXT NOT NULL,                       -- 甲方（我方）
    party_a_address TEXT,                        -- 甲方地址
    party_a_contact TEXT,                        -- 甲方联系人
    party_a_phone TEXT,                          -- 甲方电话
    party_b TEXT NOT NULL,                       -- 乙方（客户）
    party_b_address TEXT,                        -- 乙方地址
    party_b_contact TEXT,                        -- 乙方联系人
    party_b_phone TEXT,                          -- 乙方电话
    amount REAL NOT NULL,                        -- 合同金额（元）
    tax_rate REAL DEFAULT 0.06,                  -- 税率（默认 6%）
    effective_date DATE,                         -- 生效日期
    expiry_date DATE,                            -- 到期日期
    status TEXT DEFAULT 'draft',                 -- 状态：draft/review1/review2/review3/approved/signed/archived/rejected
    current_approver TEXT,                       -- 当前审批人
    created_by TEXT NOT NULL,                    -- 创建人
    file_path TEXT,                              -- 合同文件路径
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 合同索引
CREATE INDEX IF NOT EXISTS idx_contracts_status ON contracts(status);
CREATE INDEX IF NOT EXISTS idx_contracts_type ON contracts(contract_type);
CREATE INDEX IF NOT EXISTS idx_contracts_no ON contracts(contract_no);

-- 审批流表
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    approval_level INTEGER NOT NULL,             -- 审批层级（1/2/3/4）
    approver_role TEXT NOT NULL,                 -- 审批角色
    approver_name TEXT NOT NULL,                 -- 审批人
    action TEXT NOT NULL,                        -- 动作：approve / reject / delegate
    comment TEXT,                                -- 审批意见
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contract_id) REFERENCES contracts(id)
);

-- 审批索引
CREATE INDEX IF NOT EXISTS idx_approvals_contract ON approvals(contract_id);
CREATE INDEX IF NOT EXISTS idx_approvals_level ON approvals(approval_level);

-- 审计日志表
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    action TEXT NOT NULL,                        -- 操作类型
    operator TEXT NOT NULL,                      -- 操作人
    from_status TEXT,                            -- 变更前状态
    to_status TEXT,                              -- 变更后状态
    detail TEXT,                                 -- 详情（JSON）
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contract_id) REFERENCES contracts(id)
);

-- 审计索引
CREATE INDEX IF NOT EXISTS idx_audit_contract ON audit_logs(contract_id);
CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs(created_at);
