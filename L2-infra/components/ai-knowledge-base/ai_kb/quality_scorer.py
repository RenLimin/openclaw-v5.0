"""
Knowledge quality composite scorer
Combines multiple quality signals into one composite score:
  - content length
  - PII found count
  - user feedback stats
  - approval status
  - recency
  - citation count (knowledge graph)
"""
from typing import Dict, Any, Optional
from dataclasses import dataclass

from ai_kb.db import AIKB


@dataclass
class QualityScore:
    composite: float        # 0-1 overall score
    components: Dict[str, float]  # individual component scores


class CompositeQualityScorer:
    """
    Composite quality scorer that combines multiple signals.
    Weights can be configured per domain.
    """

    DEFAULT_WEIGHTS = {
        "content_length": 0.15,
        "pii_penalty": 0.15,
        "feedback_score": 0.25,
        "approval_status": 0.20,
        "recency": 0.10,
        "relation_count": 0.15
    }

    def __init__(self, db: AIKB, weights: Optional[Dict[str, float]] = None):
        self.db = db
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        # Normalize weights to sum to 1
        total = sum(self.weights.values())
        if total != 0:
            for k in self.weights:
                self.weights[k] /= total

    def score_entity(self, entity_id: int) -> QualityScore:
        """Calculate composite quality score for an entity"""
        # Get entity basics
        entity = self.db.get_entity_by_id(entity_id)
        if not entity:
            return QualityScore(composite=0.0, components={})

        components: Dict[str, float] = {}

        # 1. content length score
        text_length = entity.get('summary_length', 0)
        if text_length >= 500:
            components['content_length'] = 1.0
        elif text_length >= 100:
            components['content_length'] = 0.5 + (text_length / 1000)
        elif text_length >= 50:
            components['content_length'] = 0.3
        else:
            components['content_length'] = 0.1

        # 2. PII penalty (lower score when more PII found)
        # PII should be masked, but still penalize if many found
        pii_count = entity.get('pii_count', 0)
        if pii_count == 0:
            components['pii_penalty'] = 1.0
        elif pii_count <= 3:
            components['pii_penalty'] = 0.8
        elif pii_count <= 10:
            components['pii_penalty'] = 0.5
        else:
            components['pii_penalty'] = 0.2

        # 3. feedback score (from user feedback stats)
        stats = self.db.get_feedback_stats_for_entity(entity_id)
        useful = stats.get('useful', 0)
        not_useful = stats.get('not_useful', 0)
        total = useful + not_useful
        if total == 0:
            components['feedback_score'] = 0.5  # neutral when no feedback
        else:
            components['feedback_score'] = useful / total

        # 4. approval status score
        status = entity.get('status', 'draft')
        status_scores = {
            'published': 1.0,
            'approved': 0.8,
            'pending_review': 0.5,
            'rejected': 0.2,
            'draft': 0.3,
            'expired': 0.1
        }
        components['approval_status'] = status_scores.get(status, 0.5)

        # 5. recency score (newer = better)
        # Last updated in last 3 months = 1.0, last 1 year = 0.5, older = 0.2
        from datetime import datetime, timedelta
        updated_at = entity.get('updated_at')
        if updated_at:
            try:
                dt = datetime.fromisoformat(updated_at)
                now = datetime.now()
                delta = now - dt
                if delta < timedelta(days=90):
                    components['recency'] = 1.0
                elif delta < timedelta(days=365):
                    components['recency'] = 0.5
                else:
                    components['recency'] = 0.2
            except Exception:
                components['recency'] = 0.5
        else:
            components['recency'] = 0.5

        # 6. relation count score (more relations = richer knowledge)
        rel_count = self.db.count_entity_relations(entity_id)
        if rel_count >= 5:
            components['relation_count'] = 1.0
        elif rel_count >= 2:
            components['relation_count'] = 0.6
        elif rel_count >= 1:
            components['relation_count'] = 0.3
        else:
            components['relation_count'] = 0.1

        # Calculate composite
        composite = sum(
            score * self.weights[name]
            for name, score in components.items()
        )
        composite = max(0.0, min(1.0, composite))  # clamp to 0-1

        return QualityScore(
            composite=composite,
            components=components
        )
