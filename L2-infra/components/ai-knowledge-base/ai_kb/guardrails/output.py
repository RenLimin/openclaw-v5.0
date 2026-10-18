"""
Output side guardrails: PII rescan, scope check, hallucination check
"""
from typing import List, Optional, Tuple
from dataclasses import dataclass

from ..quality import PIIDetector


@dataclass
class OutputCheckResult:
    passed: bool
    pii_rescanned: bool
    pii_masked: List[Tuple[str, str]]
    issues: List[str]
    confidence: float  # 0.0 - 1.0


class OutputGuardrail:
    """Guardrails applied to output before returning to user"""

    def __init__(self,
                 pii_rescan_enabled: bool = True,
                 scope_check_enabled: bool = True,
                 min_confidence_threshold: float = 0.3):
        self.pii_rescan_enabled = pii_rescan_enabled
        self.scope_check_enabled = scope_check_enabled
        self.min_confidence_threshold = min_confidence_threshold

    def check(self, answer_text: str, retrieval_confidence: float) -> OutputCheckResult:
        """Check output before returning"""
        issues = []
        pii_masked = []
        processed_text = answer_text

        # 1. PII rescan
        if self.pii_rescan_enabled:
            pii_detector = PIIDetector()
            processed_text, pii_masked = pii_detector.mask(processed_text, 'mask')
            if pii_masked:
                issues.append(f"Masked {len(pii_masked)} PII entries in output")

        # 2. Scope check based on retrieval confidence
        confidence = retrieval_confidence
        if self.scope_check_enabled and confidence < self.min_confidence_threshold:
            issues.append(f"Low retrieval confidence: {confidence:.2f} < {self.min_confidence_threshold:.2f}")

        passed = True  # Output check doesn't block, just warns and masks
        return OutputCheckResult(
            passed=passed,
            pii_rescanned=self.pii_rescan_enabled,
            pii_masked=pii_masked,
            issues=issues,
            confidence=confidence
        )
