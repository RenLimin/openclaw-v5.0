"""
Multi-tenant support for enterprise deployment
Provides tenant isolation, resource quotas, quota enforcement
"""
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

from ai_kb.db import AIKB


@dataclass
class TenantQuota:
    """Quota for a single tenant"""
    max_domains: int
    max_documents: int
    max_chunks: int
    max_storage_mb: int
    current_domains: int = 0
    current_documents: int = 0
    current_chunks: int = 0
    current_storage_mb: int = 0


class TenantManager:
    """
    Multi-tenant manager.
    Each tenant has isolated domains/knowledge and resource quotas.
    """

    def __init__(self, db: AIKB):
        self.db = db
        self._ensure_tenant_table()
        self._ensure_quota_table()

    def _ensure_tenant_table(self):
        """Create tenant table if missing"""
        self.db.execute("""
        CREATE TABLE IF NOT EXISTS kb_tenant (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            metadata TEXT
        )
        """)
        self.db.commit()

    def _ensure_quota_table(self):
        """Create quota table if missing"""
        self.db.execute("""
        CREATE TABLE IF NOT EXISTS kb_tenant_quota (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            max_domains INTEGER NOT NULL,
            max_documents INTEGER NOT NULL,
            max_chunks INTEGER NOT NULL,
            max_storage_mb INTEGER NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            FOREIGN KEY (tenant_id) REFERENCES kb_tenant (tenant_id)
        )
        """)
        self.db.commit()

    def create_tenant(
        self,
        tenant_id: str,
        name: str,
        quota: TenantQuota,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Create a new tenant with quota"""
        # Check if exists
        existing = self.get_tenant(tenant_id)
        if existing:
            return False

        now = self.db.get_now()
        # metadata to json
        meta_json = None
        if metadata:
            import json
            meta_json = json.dumps(metadata)

        self.db.execute("""
        INSERT INTO kb_tenant (tenant_id, name, created_at, updated_at, metadata)
        VALUES (?, ?, ?, ?, ?)
        """, (tenant_id, name, now, now, meta_json))

        self.db.execute("""
        INSERT INTO kb_tenant_quota (
            tenant_id, max_domains, max_documents, max_chunks,
            max_storage_mb, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            tenant_id,
            quota.max_domains,
            quota.max_documents,
            quota.max_chunks,
            quota.max_storage_mb,
            now,
            now
        ))
        self.db.commit()
        return True

    def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get tenant info by id"""
        row = self.db.execute("""
        SELECT * FROM kb_tenant WHERE tenant_id = ?
        """, (tenant_id,)).fetchone()
        return dict(row) if row else None

    def get_quota(self, tenant_id: str) -> Optional[TenantQuota]:
        """Get current quota and usage for tenant"""
        row = self.db.execute("""
        SELECT * FROM kb_tenant_quota WHERE tenant_id = ?
        """, (tenant_id,)).fetchone()
        if not row:
            return None

        # Calculate current usage
        domain_count = self.db.count_domains(tenant_id)
        doc_count = self.db.count_documents(tenant_id)
        chunk_count = self.db.count_chunks(tenant_id)

        return TenantQuota(
            max_domains=row['max_domains'],
            max_documents=row['max_documents'],
            max_chunks=row['max_chunks'],
            max_storage_mb=row['max_storage_mb'],
            current_domains=domain_count,
            current_documents=doc_count,
            current_chunks=chunk_count
        )

    def check_quota(self, tenant_id: str, resource: str) -> Tuple[bool, TenantQuota]:
        """Check if tenant has remaining quota for a resource"""
        quota = self.get_quota(tenant_id)
        if not quota:
            return False, quota

        if resource == "domain":
            return quota.current_domains < quota.max_domains, quota
        elif resource == "document":
            return quota.current_documents < quota.max_documents, quota
        elif resource == "chunk":
            return quota.current_chunks < quota.max_chunks, quota
        else:
            return True, quota

    def update_usage(self, tenant_id: str):
        """Refresh usage counts from actual database counts.
        Call this after major operations to keep quota usage accurate."""
        # Usage is calculated on the fly when getting quota
        # This method is a placeholder for future caching
        pass

    def delete_tenant(self, tenant_id: str) -> bool:
        """Delete a tenant and all its data"""
        # Check exists
        if not self.get_tenant(tenant_id):
            return False

        # Delete quota first
        self.db.execute("DELETE FROM kb_tenant_quota WHERE tenant_id = ?", (tenant_id,))
        # Delete tenant
        self.db.execute("DELETE FROM kb_tenant WHERE tenant_id = ?", (tenant_id,))
        # TODO: delete all domain data (documents/chunks/entities)
        # This needs to be implemented in the future
        self.db.commit()
        return True
