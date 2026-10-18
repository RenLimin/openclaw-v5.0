"""
Retrieval side guardrails: permission filtering, expired filtering, threshold filtering
"""
from typing import List, Optional

from ..permissions import PermissionChecker


class RetrievalGuardrail:
    """Guardrails applied during retrieval"""

    def __init__(self,
                 permission_checker: Optional[PermissionChecker] = None,
                 filter_expired: bool = True,
                 min_similarity_threshold: float = 0.3):
        self.permission_checker = permission_checker
        self.filter_expired = filter_expired
        self.min_similarity_threshold = min_similarity_threshold

    def is_visible(self, entity_status: Optional[str], similarity_score: float, chunk) -> bool:
        """Check if a result should be visible based on guardrails"""

        # 1. Filter expired
        if self.filter_expired and entity_status == 'expired':
            return False

        # 2. Filter by similarity threshold
        if similarity_score < self.min_similarity_threshold:
            return False

        # 3. Permission check
        if self.permission_checker and not self.permission_checker.can_access(chunk):
            return False

        return True
