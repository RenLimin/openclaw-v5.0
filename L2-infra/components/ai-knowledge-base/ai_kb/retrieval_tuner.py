"""
Automatic retrieval strategy tuner based on user feedback
Tunes channel weights (entity/fts/vector) based on feedback
"""
from typing import Dict, List, Any, Tuple, Optional
import math

from ai_kb.db import AIKB


class RetrievalStrategyTuner:
    """
    Automatic tuner for retrieval channel weights.
    Uses user feedback to adjust the blend weights for each channel.
    """

    # Default weights
    DEFAULT_WEIGHTS = {
        "entity": 0.4,
        "fts": 0.3,
        "vector": 0.3
    }

    # Learning rate for weight updates
    LEARNING_RATE = 0.05
    MIN_WEIGHT = 0.1
    MAX_WEIGHT = 0.6

    def __init__(self, db: AIKB, domain_id: int):
        self.db = db
        self.domain_id = domain_id
        self._current_weights = self.DEFAULT_WEIGHTS.copy()
        self._load_weights()

    def _load_weights(self):
        """Load saved weights from database metadata"""
        # TODO: store and retrieve weights from domain metadata
        # For now, use defaults
        pass

    def _save_weights(self):
        """Save current weights to database"""
        # TODO: save to domain metadata
        pass

    def get_current_weights(self) -> Dict[str, float]:
        """Get current normalized weights"""
        total = sum(self._current_weights.values())
        if total == 0:
            return self.DEFAULT_WEIGHTS
        # Normalize
        return {
            k: w / total
            for k, w in self._current_weights.items()
        }

    def record_feedback(
        self,
        result_channels: Dict[str, float],
        feedback_useful: bool
    ):
        """
        Record feedback for a retrieval result.
        Args:
            result_channels: {channel: score} contribution of each channel to this result
            feedback_useful: whether the result was useful
        """
        # If useful: increase weights of channels that contributed
        # If not useful: decrease weights
        direction = 1.0 if feedback_useful else -1.0

        for channel, score in result_channels.items():
            if channel not in self._current_weights:
                continue
            # Update proportional to channel contribution
            delta = direction * self.LEARNING_RATE * score
            self._current_weights[channel] += delta
            # Clamp to min/max
            self._current_weights[channel] = max(
                self.MIN_WEIGHT,
                min(self.MAX_WEIGHT, self._current_weights[channel])
            )

        # Normalize after update
        self._normalize_weights()
        self._save_weights()

    def _normalize_weights(self):
        """Normalize weights so they sum to 1.0"""
        total = sum(self._current_weights.values())
        if total <= 0:
            # Reset to defaults if something goes wrong
            self._current_weights = self.DEFAULT_WEIGHTS.copy()
            return
        for k in self._current_weights:
            self._current_weights[k] /= total

    def get_entropy(self) -> float:
        """Calculate entropy of weight distribution.
        Higher entropy = more uniform (more exploration)
        Lower entropy = more focused (more exploitation)"""
        entropy = 0.0
        weights = self.get_current_weights()
        for _, w in weights.items():
            if w > 0:
                entropy -= w * math.log(w)
        return entropy
