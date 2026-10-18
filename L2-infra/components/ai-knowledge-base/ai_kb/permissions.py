"""
ABAC (Attribute-Based Access Control) for L2 AI KB
Enforces document-level permissions at retrieval time, not just app layer
"""
from typing import List, Dict, Optional, Set
from .db import AIKB


class PermissionChecker:
    """
    ABAC permission checker for knowledge base access control.
    
    Key design principle: permissions are enforced at retrieval time,
    not just at the application layer. Every chunk and doc carries
    permission metadata that is checked before returning results.
    """
    
    def __init__(self, kb: AIKB):
        self.kb = kb

    def can_access_doc(self, user_attrs: Dict, doc_permissions: Optional[str]) -> bool:
        """Check if user can access a document based on ABAC attributes.
        
        Permission format (JSON string):
        {
            "allowed_roles": ["admin", "sales"],
            "allowed_departments": ["product", "engineering"],
            "confidence_level": "internal",  # public / internal / confidential / restricted
            "allowed_users": ["user1", "user2"]
        }
        """
        import json
        
        # No permission metadata means public within the domain
        if not doc_permissions:
            return True
        
        try:
            perms = json.loads(doc_permissions)
        except (json.JSONDecodeError, TypeError):
            # Invalid permission format => deny (fail-closed)
            return False
        
        user_role = user_attrs.get('role', '')
        user_dept = user_attrs.get('department', '')
        user_id = user_attrs.get('user_id', '')
        user_clearance = user_attrs.get('clearance', 'internal')
        
        clearance_levels = ['public', 'internal', 'confidential', 'restricted']
        doc_clearance = perms.get('confidence_level', 'internal')
        
        # Clearance check: user clearance must be >= doc clearance
        try:
            user_level = clearance_levels.index(user_clearance)
            doc_level = clearance_levels.index(doc_clearance)
            if user_level < doc_level:
                return False
        except ValueError:
            return False
        
        # Role check
        allowed_roles = perms.get('allowed_roles', [])
        if allowed_roles and user_role not in allowed_roles:
            return False
        
        # Department check
        allowed_depts = perms.get('allowed_departments', [])
        if allowed_depts and user_dept not in allowed_depts:
            return False
        
        # User-level allowlist
        allowed_users = perms.get('allowed_users', [])
        if allowed_users and user_id not in allowed_users:
            return False
        
        return True

    def filter_results_by_permissions(self, results: List[Dict], user_attrs: Dict) -> List[Dict]:
        """Filter retrieval results by user permissions.
        This is the main enforcement point: called on every search result.
        """
        filtered = []
        for r in results:
            doc = r.get('doc', {})
            chunk = r.get('chunk', {})
            # Check doc-level permissions first, then chunk-level (chunk overrides if set)
            perms = chunk.get('permissions') or doc.get('permissions')
            if self.can_access_doc(user_attrs, perms):
                filtered.append(r)
        return filtered

    def set_doc_permissions(self, doc_id: int, permissions: Dict):
        """Set permission metadata for a document"""
        import json
        now = self.kb.get_now()
        self.kb.execute(
            "UPDATE doc_asset SET permissions = ?, updated_at = ? WHERE id = ?",
            (json.dumps(permissions, ensure_ascii=False), now, doc_id)
        )
        self.kb.commit()

    def set_chunk_permissions(self, chunk_id: int, permissions: Dict):
        """Set permission metadata for a specific chunk (overrides doc-level)"""
        import json
        now = self.kb.get_now()
        self.kb.execute(
            "UPDATE doc_chunk SET permissions = ?, updated_at = ? WHERE id = ?",
            (json.dumps(permissions, ensure_ascii=False), now, chunk_id)
        )
        self.kb.commit()
