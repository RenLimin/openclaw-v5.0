"""
Input side guardrails: quality check, PII detection, injection detection
"""
import re
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass

from ..quality import check_quality, PIIDetector


@dataclass
class InputGuardrailResult:
    passed: bool
    risk_level: str  # green / yellow / orange / red
    action: str  # accept / warn / block
    issues: List[str]
    metadata: Dict[str, Any]


class InputGuardrail:
    """Input guardrails for document ingestion and query"""

    # Injection patterns to detect prompt injection
    INJECTION_PATTERNS = [
        r'ignore.*(above|previous|instructions|prompt)',
        r'forget.*(above|previous|instructions|prompt)',
        r'(you are|you\'re|act as|now you are).*',
        r'display.*(prompt|system prompt|instructions)',
        r'output.*(prompt|system prompt|instructions)',
        r'\[.*INST\].*',
        r'<\|.*system.*\|>',
    ]

    def __init__(self,
                 enabled: bool = True,
                 min_quality_score: float = 0.5,
                 pii_detection_enabled: bool = True,
                 pii_mask_action: str = 'mask',
                 injection_detection_enabled: bool = True,
                 injection_action: str = 'block'):
        self.enabled = enabled
        self.min_quality_score = min_quality_score
        self.pii_detection_enabled = pii_detection_enabled
        self.pii_mask_action = pii_mask_action
        self.injection_detection_enabled = injection_detection_enabled
        self.injection_action = injection_action

    def check_document(self, content: str) -> InputGuardrailResult:
        """Check document content before ingestion"""
        if not self.enabled:
            return InputGuardrailResult(
                passed=True,
                risk_level="green",
                action="accept",
                issues=[],
                metadata={}
            )

        issues = []
        metadata = {}
        risk_level = "green"
        action = "accept"

        # 1. Quality check
        quality_result = check_quality(content, min_quality_score=self.min_quality_score)
        if quality_result.issues:
            issues.extend(quality_result.issues)
            metadata['quality_score'] = quality_result.quality_score
            if not quality_result.is_acceptable:
                risk_level = "yellow"
                action = "warn"

        # 2. PII detection
        if self.pii_detection_enabled:
            pii_detector = PIIDetector()
            pii_found = pii_detector.detect(content)
            if pii_found:
                issues.append(f"Found {len(pii_found)} PII entries")
                metadata['pii_found'] = pii_found
                # PII just warns, masking happens regardless
                if risk_level == "green":
                    risk_level = "yellow"

        # 3. Prompt injection detection (in document content)
        if self.injection_detection_enabled:
            injection_hits = self.detect_injection(content)
            if injection_hits:
                issues.append(f"Found {len(injection_hits)} potential prompt injection patterns")
                metadata['injection_hits'] = injection_hits
                risk_level = "orange"
                if self.injection_action == "block":
                    action = "block"
                else:
                    action = "warn"

        # Determine final result
        passed = action != "block"
        return InputGuardrailResult(
            passed=passed,
            risk_level=risk_level,
            action=action,
            issues=issues,
            metadata=metadata
        )

    def check_query(self, query: str) -> InputGuardrailResult:
        """Check user query before processing"""
        if not self.enabled:
            return InputGuardrailResult(
                passed=True,
                risk_level="green",
                action="accept",
                issues=[],
                metadata={}
            )

        issues = []
        metadata = {}
        risk_level = "green"
        action = "accept"

        # 1. Prompt injection detection
        if self.injection_detection_enabled:
            injection_hits = self.detect_injection(query)
            if injection_hits:
                issues.append(f"Found {len(injection_hits)} potential prompt injection patterns")
                metadata['injection_hits'] = injection_hits
                risk_level = "orange"
                if self.injection_action == "block":
                    action = "block"
                else:
                    action = "warn"

        # 2. Check for suspicious length
        if len(query) > 10000:
            issues.append("Query extremely long, possible injection attempt")
            risk_level = "yellow"
            if action != "block":
                action = "warn"

        passed = action != "block"
        return InputGuardrailResult(
            passed=passed,
            risk_level=risk_level,
            action=action,
            issues=issues,
            metadata=metadata
        )

    def detect_injection(self, text: str) -> List[str]:
        """Detect potential prompt injection patterns"""
        hits = []
        for pattern in self.INJECTION_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                hits.extend(matches)
        return hits
