"""业务数据表 —— 动态宽表存储。

设计决策：
交付月报的 Sheet 是 83/84/38/23/27 列的宽表，且列定义会随业务演进。
硬编码 83 个字段 → schema 迁移噩梦。因此采用「宽表 JSON 行」模式：

  dr_sheet_row(sheet, month, row_index, data JSON)

优点：
- 列定义变化无需 DDL
- Excel 导出直接还原原始列序
- 统计查询用 SQLite json_extract（够用）

确收模块同理：rr_sheet_row(sheet, period, row_index, data JSON)
但确收有明确的强类型关键字段（contract_no 等），因此额外建索引列。
"""

# 业务表 schema（追加到 core/db.py 的 SCHEMA 之外，按模块加载）

DR_SCHEMA = """
-- ===== 交付月报模块（模块1）=====

-- 明细/统计 Sheet 行存储
CREATE TABLE IF NOT EXISTS dr_sheet_row (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,               -- YYYYMM
    sheet TEXT NOT NULL,               -- 签约 | POC&提前实施 | 异常项目 | ...
    row_index INTEGER NOT NULL,
    data TEXT NOT NULL,                -- JSON object
    UNIQUE(month, sheet, row_index)
);
CREATE INDEX IF NOT EXISTS idx_dr_sheet ON dr_sheet_row(month, sheet);

-- Sheet 元信息（列序、行数）
CREATE TABLE IF NOT EXISTS dr_sheet_meta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    sheet TEXT NOT NULL,
    columns TEXT NOT NULL,             -- JSON array: 列名有序列表
    row_count INTEGER DEFAULT 0,
    UNIQUE(month, sheet)
);
"""

RR_SCHEMA = """
-- ===== 确认收入模块（模块2）=====

-- 确收报表 Sheet 行存储（含索引列便于查询）
CREATE TABLE IF NOT EXISTS rr_sheet_row (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,              -- YYYYMM
    sheet TEXT NOT NULL,
    row_index INTEGER NOT NULL,
    contract_no TEXT,                  -- 索引列：合同编号
    category TEXT,                     -- 索引列：分类（递延/新签）
    archive_month TEXT,                -- 索引列：归档月份
    perf_id TEXT,                      -- 索引列：履约ID
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
"""

DASHBOARD_SCHEMA = """
-- ===== 统计看板模块（模块4）=====

-- 看板快照：按月缓存的聚合结果（避免每次实时计算）
CREATE TABLE IF NOT EXISTS db_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    metric TEXT NOT NULL,              -- e.g. delivery_status_dist
    dimension TEXT,                    -- JSON: 维度键值
    value REAL,                        -- 数值
    extra TEXT,                        -- JSON
    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(month, metric, dimension)
);
CREATE INDEX IF NOT EXISTS idx_db_snap ON db_snapshot(month, metric);
"""
