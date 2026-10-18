"""
Quality detection and PII detection / masking
"""
import re
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass


@dataclass
class QualityCheckResult:
    """Result of quality check"""
    quality_score: float
    pii_found: List[Tuple[str, str]]  # (type, matched_text)
    issues: List[str]
    is_acceptable: bool


class PIIDetector:
    """Detect and mask Personally Identifiable Information"""

    # Patterns for common PII types
    PATTERNS = {
        'phone': r'(?:\+?86[-\s]?)?1[3-9]\d{9}',
        'id_card': r'[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]',
        'email': r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        'bank_card': r'\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}',
        'api_key': r'sk-[A-Za-z0-9]{32,}',
        'ip_address': r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
    }

    def __init__(self, enabled_types: Optional[List[str]] = None):
        self.enabled_types = enabled_types or list(self.PATTERNS.keys())

    def detect(self, text: str) -> List[Tuple[str, str]]:
        """Detect PII in text, returns list of (type, match)"""
        results = []
        for pii_type, pattern in self.PATTERNS.items():
            if pii_type not in self.enabled_types:
                continue
            matches = re.findall(pattern, text)
            for match in matches:
                results.append((pii_type, match if isinstance(match, str) else match[0]))
        return results

    def mask(self, text: str, action: str = 'mask') -> Tuple[str, List[Tuple[str, str]]]:
        """
        Mask detected PII in text.
        Actions:
        - mask: replace with asterisks
        - remove: remove the matched text
        - flag_only: just return detections, don't change text
        """
        pii_found = self.detect(text)
        if action == 'flag_only' or not pii_found:
            return text, pii_found

        for pii_type, match in pii_found:
            if action == 'mask':
                if pii_type == 'phone':
                    # 138****1234
                    masked = match[:3] + '****' + match[-4:]
                elif pii_type == 'id_card':
                    # 110101********1234
                    masked = match[:6] + '********' + match[-4:]
                elif pii_type == 'email':
                    # a***@example.com
                    parts = match.split('@')
                    username = parts[0]
                    if len(username) > 1:
                        masked = username[0] + '***@' + parts[1]
                    else:
                        masked = '***@' + parts[1]
                elif pii_type == 'bank_card':
                    # **** **** **** 1234
                    masked = '**** **** **** ' + match[-4:]
                elif pii_type == 'ip_address':
                    # 192.168.***.***
                    parts = match.split('.')
                    masked = f"{parts[0]}.{parts[1]}.***.***"
                elif pii_type == 'api_key':
                    # ******** (full mask)
                    masked = '***API_KEY***'
                text = text.replace(match, masked)
            elif action == 'remove':
                text = text.replace(match, '')

        return text, pii_found


def check_quality(content: str, min_word_count: int = 50, min_quality_score: float = 0.3) -> QualityCheckResult:
    """
    Check document content quality.
    Returns quality score between 0 and 1, and list of issues.
    """
    issues = []
    score = 1.0

    # Check word count
    # CJK text has no spaces; count CJK chars as words for fair length check
    cjk_chars = sum(1 for c in content if '\u4e00' <= c <= '\u9fff')
    words = content.split()
    effective_words = len(words) + cjk_chars // 2
    if effective_words < min_word_count:
        issues.append(f"Content too short: {effective_words} words (min {min_word_count})")
        score -= 0.5

    # Check for garbled text
    weird_chars = sum(1 for c in content if ord(c) < 32 and c not in '\n\r\t')
    weird_ratio = weird_chars / len(content) if len(content) > 0 else 1
    if weird_ratio > 0.05:
        issues.append(f"High ratio of control characters: {weird_ratio:.1%}")
        score -= weird_ratio * 2

    # Check empty lines
    lines = content.splitlines()
    empty_lines = sum(1 for line in lines if not line.strip())
    empty_ratio = empty_lines / len(lines) if len(lines) > 0 else 1
    if empty_ratio > 0.8:
        issues.append(f"High ratio of empty lines: {empty_ratio:.1%}")
        score -= (empty_ratio - 0.5)

    # PII detection
    pii_detector = PIIDetector()
    pii_found = pii_detector.detect(content)

    score = max(0.0, min(1.0, score))
    return QualityCheckResult(
        quality_score=score,
        pii_found=pii_found,
        issues=issues,
        is_acceptable=score >= min_quality_score
    )
