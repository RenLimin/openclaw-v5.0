"""初始 schema — 版本 1。

创建 _schema_version 表和基础的系统表。
"""
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))

MIGRATION = """
-- 用户表 (L3 示例)
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT
);

-- 配置表 (系统级 KV)
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_config_key ON config(key);
"""
