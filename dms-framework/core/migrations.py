"""
DMS-Framework 数据库迁移管理
所有业务表均含 tenant_id,默认 'system'（单租户模式向后兼容）
"""
from __future__ import annotations

import sqlite3
import logging
from typing import Callable

logger = logging.getLogger(__name__)

# ── 迁移注册表 ──────────────────────────────────────────────
_MIGRATIONS: dict[str, Callable[[sqlite3.Connection], None]] = {}


def migration(version: str):
    """装饰器：注册迁移函数"""
    def decorator(fn: Callable[[sqlite3.Connection], None]):
        _MIGRATIONS[version] = fn
        return fn
    return decorator


def get_current_version(conn: sqlite3.Connection) -> str:
    """获取当前 schema 版本"""
    try:
        row = conn.execute(
            "SELECT version FROM schema_version ORDER BY applied_at DESC, version DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else "0.0.0"
    except sqlite3.OperationalError:
        return "0.0.0"


def migrate(conn: sqlite3.Connection, target: str = "latest") -> list[str]:
    """执行迁移，返回已应用的版本列表"""
    current = get_current_version(conn)
    versions = sorted(_MIGRATIONS.keys(), key=_version_key)

    if target != "latest":
        versions = [v for v in versions if _version_key(v) <= _version_key(target)]

    applied = []
    for version in versions:
        if _version_key(version) > _version_key(current):
            logger.info(f"迁移 {current} → {version}")
            _MIGRATIONS[version](conn)
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (version,)
            )
            conn.commit()
            applied.append(version)
            current = version

    return applied


def diff(conn: sqlite3.Connection) -> list[str]:
    """返回待执行的迁移版本"""
    current = get_current_version(conn)
    return [v for v in sorted(_MIGRATIONS.keys(), key=_version_key)
            if _version_key(v) > _version_key(current)]


def _version_key(v: str) -> tuple[int, ...]:
    """语义化版本排序键"""
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return (0,)


# ── 迁移 1.0.0: 初始化所有表 ─────────────────────────────────
@migration("1.0.0")
def _init_schema(conn: sqlite3.Connection):
    """创建 DMS-Framework v1.0.0 全部业务表"""

    conn.executescript("""
        -- Schema 版本追踪
        CREATE TABLE IF NOT EXISTS schema_version (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- ★ 项目表
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'system',
            name TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'planning',
            priority TEXT DEFAULT 'medium',
            start_date TEXT,
            end_date TEXT,
            owner_id TEXT,
            metadata TEXT,
            proprietary_metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- ★ 统一工作项表（task/milestone/deliverable/risk）
        CREATE TABLE IF NOT EXISTS work_items (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'system',
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'draft',
            priority TEXT DEFAULT 'medium',
            assignee_id TEXT,
            due_date TEXT,
            completed_at TEXT,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- ★ 项目成员表
        CREATE TABLE IF NOT EXISTS project_members (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            tenant_id TEXT NOT NULL DEFAULT 'system',
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(project_id, user_id)
        );

        -- ★ 干系人表
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

        -- ★ 自定义字段元数据表（Metadata-driven, 借鉴 Salesforce）
        CREATE TABLE IF NOT EXISTS custom_fields (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'system',
            entity_type TEXT NOT NULL,
            field_name TEXT NOT NULL,
            field_type TEXT NOT NULL,
            field_options TEXT,
            required BOOLEAN DEFAULT 0,
            default_value TEXT,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(tenant_id, entity_type, field_name)
        );

        -- ★ RACI 职责分配表
        CREATE TABLE IF NOT EXISTS responsibility_assignments (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            work_item_id TEXT REFERENCES work_items(id) ON DELETE CASCADE,
            member_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL DEFAULT 'system',
            capability TEXT NOT NULL,
            raci_role TEXT NOT NULL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(project_id, work_item_id, member_id, capability)
        );

        -- ★ 变更日志表
        CREATE TABLE IF NOT EXISTS change_logs (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'system',
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            action TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            actor TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- ── 索引 ──
        CREATE INDEX IF NOT EXISTS idx_projects_tenant ON projects(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_work_items_tenant ON work_items(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_work_items_project ON work_items(project_id);
        CREATE INDEX IF NOT EXISTS idx_work_items_type ON work_items(type);
        CREATE INDEX IF NOT EXISTS idx_work_items_status ON work_items(status);
        CREATE INDEX IF NOT EXISTS idx_project_members_tenant ON project_members(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_stakeholders_tenant ON stakeholders(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_custom_fields_tenant ON custom_fields(tenant_id, entity_type);
        CREATE INDEX IF NOT EXISTS idx_raci_tenant ON responsibility_assignments(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_raci_project ON responsibility_assignments(project_id);
        CREATE INDEX IF NOT EXISTS idx_change_logs_tenant ON change_logs(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_change_logs_entity ON change_logs(entity_type, entity_id);
    """)


@migration("1.1.0")
def upgrade_1_1_0(conn: "sqlite3.Connection") -> None:
    """v1.1.0：补全 RACI 表字段（updated_at + role_template）。"""
    try:
        conn.execute("ALTER TABLE responsibility_assignments ADD COLUMN updated_at TEXT")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE responsibility_assignments ADD COLUMN role_template TEXT")
    except Exception:
        pass
    conn.commit()


@migration("1.2.0")
def upgrade_1_2_0(conn: "sqlite3.Connection") -> None:
    """v1.2.0：租户管理表（tenants + tenant_config）。"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tenants (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'system',
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            tier TEXT DEFAULT 'free',
            status TEXT DEFAULT 'active',
            contact_email TEXT,
            max_projects INTEGER DEFAULT 10,
            max_users INTEGER DEFAULT 5,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS tenant_config (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'system',
            module_name TEXT NOT NULL,
            enabled BOOLEAN DEFAULT 1,
            config_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(tenant_id, module_name)
        );

        CREATE INDEX IF NOT EXISTS idx_tenants_slug ON tenants(slug);
        CREATE INDEX IF NOT EXISTS idx_tenant_config_tenant ON tenant_config(tenant_id);
    """)
    conn.commit()
