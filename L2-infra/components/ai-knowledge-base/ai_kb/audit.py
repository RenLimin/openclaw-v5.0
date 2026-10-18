"""
Audit logging for AI Knowledge Base
All operations (query/ingest/feedback/admin) are recorded and traceable.
"""
import uuid
from typing import Optional, Dict, Any, List


class AuditLogger:
    """Wraps kb_audit_log table with convenience methods and query support."""

    def __init__(self, db):
        self.db = db

    def log(self, operation_type: str, user_id: str = None,
            object_type: str = None, object_id: int = None,
            risk_level: str = None, rule_triggered: str = None,
            action_taken: str = None, details: str = None,
            request_id: str = None) -> int:
        """Write one audit entry. Returns log id."""
        if not request_id:
            request_id = str(uuid.uuid4())[:12]
        return self.db.add_audit_log(
            operation_type=operation_type,
            user_id=user_id,
            object_type=object_type,
            object_id=object_id,
            request_id=request_id,
            risk_level=risk_level,
            rule_triggered=rule_triggered,
            action_taken=action_taken,
            details=details,
        )

    # --- Convenience wrappers ---

    def log_query(self, user_id: str, query: str, source_count: int,
                  request_id: str = None) -> int:
        return self.log(
            operation_type="query", user_id=user_id,
            object_type="query", risk_level="low",
            action_taken="answer",
            details=f"query={query!r} source_count={source_count}",
            request_id=request_id,
        )

    def log_ingest(self, user_id: str, file_name: str, doc_id: int,
                   chunks: int, success: bool, request_id: str = None) -> int:
        return self.log(
            operation_type="ingest", user_id=user_id,
            object_type="document", object_id=doc_id,
            risk_level="low" if success else "medium",
            action_taken="index" if success else "reject",
            details=f"file={file_name} chunks={chunks}",
            request_id=request_id,
        )

    def log_access_denied(self, user_id: str, operation: str,
                          object_type: str, object_id: int,
                          reason: str, request_id: str = None) -> int:
        return self.log(
            operation_type=operation, user_id=user_id,
            object_type=object_type, object_id=object_id,
            risk_level="medium", rule_triggered=reason,
            action_taken="deny",
            details=f"access denied: {reason}",
            request_id=request_id,
        )

    def log_risk_event(self, user_id: str, operation: str,
                       risk_level: str, rule_triggered: str,
                       action_taken: str, details: str,
                       request_id: str = None) -> int:
        return self.log(
            operation_type=operation, user_id=user_id,
            risk_level=risk_level, rule_triggered=rule_triggered,
            action_taken=action_taken, details=details,
            request_id=request_id,
        )

    # --- Query ---

    def query_logs(self, operation_type: Optional[str] = None,
                   user_id: Optional[str] = None,
                   risk_level: Optional[str] = None,
                   limit: int = 100) -> List[Dict[str, Any]]:
        """Query audit logs with optional filters."""
        sql = "SELECT * FROM kb_audit_log WHERE 1=1"
        params = []
        if operation_type:
            sql += " AND operation_type = ?"
            params.append(operation_type)
        if user_id:
            sql += " AND user_id = ?"
            params.append(user_id)
        if risk_level:
            sql += " AND risk_level = ?"
            params.append(risk_level)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = self.db.execute(sql, tuple(params)).fetchall()
        return [dict(r) for r in rows]

    def count_by_operation(self, days: int = 7) -> Dict[str, int]:
        """Count operations grouped by type over recent N days."""
        rows = self.db.execute("""
            SELECT operation_type, COUNT(*) as cnt
            FROM kb_audit_log
            WHERE timestamp >= datetime('now', ?)
            GROUP BY operation_type
        """, (f'-{days} days',)).fetchall()
        return {r['operation_type']: r['cnt'] for r in rows}
