"""
Approval workflow for knowledge base
Workflow: draft → pending → approved/rejected → published
Supports multi-step review, comments, change tracking
"""
import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from ai_kb.db import AIKB


# Entity status constants
STATUS_DRAFT = "draft"
STATUS_PENDING = "pending_review"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_PUBLISHED = "published"
STATUS_EXPIRED = "expired"


@dataclass
class ApprovalEvent:
    """Single approval workflow event"""
    id: int
    entity_id: int
    from_status: str
    to_status: str
    actor_id: str
    actor_name: str
    comment: Optional[str]
    created_at: str


class ApprovalWorkflow:
    """
    Approval workflow manager for knowledge entities.
    Tracks status transitions, events, comments.
    """

    def __init__(self, db: AIKB):
        self.db = db
        self._init_table()

    def _init_table(self):
        """Create approval_event table if missing"""
        # Table already created in init_db()? Let's check/init
        self.db.execute("""
        CREATE TABLE IF NOT EXISTS kb_approval_event (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id INTEGER NOT NULL,
            from_status TEXT NOT NULL,
            to_status TEXT NOT NULL,
            actor_id TEXT,
            actor_name TEXT,
            comment TEXT,
            created_at DATETIME NOT NULL,
            FOREIGN KEY (entity_id) REFERENCES entity (id)
        )
        """)
        self.db.commit()

    def transition(
        self,
        entity_id: int,
        from_status: str,
        to_status: str,
        actor_id: str,
        actor_name: str,
        comment: Optional[str] = None
    ) -> int:
        """
        Record a status transition and update entity status.
        Returns event_id.
        """
        now = self.db.get_now()

        # Record event
        cursor = self.db.execute("""
        INSERT INTO kb_approval_event (
            entity_id, from_status, to_status,
            actor_id, actor_name, comment, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            entity_id, from_status, to_status,
            actor_id, actor_name, comment, now
        ))
        event_id = cursor.lastrowid

        # Update entity status
        self.db.execute("""
        UPDATE entity SET status = ?, updated_at = ? WHERE id = ?
        """, (to_status, now, entity_id))
        self.db.commit()

        return event_id

    def submit_for_review(
        self,
        entity_id: int,
        current_status: str,
        submitter_id: str,
        submitter_name: str,
        comment: Optional[str] = None
    ) -> Optional[int]:
        """Submit entity for review: draft → pending_review"""
        if current_status != STATUS_DRAFT:
            return None
        return self.transition(
            entity_id=entity_id,
            from_status=current_status,
            to_status=STATUS_PENDING,
            actor_id=submitter_id,
            actor_name=submitter_name,
            comment=comment
        )

    def approve(
        self,
        entity_id: int,
        current_status: str,
        reviewer_id: str,
        reviewer_name: str,
        comment: Optional[str] = None,
        auto_publish: bool = True
    ) -> Optional[int]:
        """Approve pending entity: pending_review → approved (→ published if auto_publish)"""
        if current_status != STATUS_PENDING:
            return None
        to_status = STATUS_APPROVED
        if auto_publish:
            to_status = STATUS_PUBLISHED
        return self.transition(
            entity_id=entity_id,
            from_status=current_status,
            to_status=to_status,
            actor_id=reviewer_id,
            actor_name=reviewer_name,
            comment=comment
        )

    def reject(
        self,
        entity_id: int,
        current_status: str,
        reviewer_id: str,
        reviewer_name: str,
        comment: Optional[str] = None
    ) -> Optional[int]:
        """Reject pending entity: pending_review → rejected"""
        if current_status != STATUS_PENDING:
            return None
        return self.transition(
            entity_id=entity_id,
            from_status=current_status,
            to_status=STATUS_REJECTED,
            actor_id=reviewer_id,
            actor_name=reviewer_name,
            comment=comment
        )

    def publish(
        self,
        entity_id: int,
        current_status: str,
        publisher_id: str,
        publisher_name: str,
        comment: Optional[str] = None
    ) -> Optional[int]:
        """Publish approved entity: approved → published"""
        if current_status != STATUS_APPROVED:
            return None
        return self.transition(
            entity_id=entity_id,
            from_status=current_status,
            to_status=STATUS_PUBLISHED,
            actor_id=publisher_id,
            actor_name=publisher_name,
            comment=comment
        )

    def get_events(self, entity_id: int) -> List[ApprovalEvent]:
        """Get all approval events for an entity in order"""
        rows = self.db.execute("""
        SELECT * FROM kb_approval_event
        WHERE entity_id = ?
        ORDER BY id ASC
        """, (entity_id,)).fetchall()

        events = []
        for row in rows:
            events.append(ApprovalEvent(
                id=row['id'],
                entity_id=row['entity_id'],
                from_status=row['from_status'],
                to_status=row['to_status'],
                actor_id=row['actor_id'],
                actor_name=row['actor_name'],
                comment=row['comment'],
                created_at=row['created_at']
            ))
        return events

    def list_pending(self, domain_id: int, limit: int = 50) -> List[int]:
        """List all pending review entity ids for domain"""
        rows = self.db.execute("""
        SELECT id FROM entity
        WHERE domain_id = ? AND status = ?
        ORDER BY created_at DESC
        LIMIT ?
        """, (domain_id, STATUS_PENDING, limit)).fetchall()
        return [r['id'] for r in rows]

    def list_by_status(self, domain_id: int, status: str, limit: int = 50) -> List[int]:
        """List all entities with given status"""
        rows = self.db.execute("""
        SELECT id FROM entity
        WHERE domain_id = ? AND status = ?
        ORDER BY created_at DESC
        LIMIT ?
        """, (domain_id, status, limit)).fetchall()
        return [r['id'] for r in rows]
