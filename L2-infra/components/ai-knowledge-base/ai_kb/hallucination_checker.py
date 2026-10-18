"""
Hallucination checker: check answer consistency against retrieved sources
Detects when answer includes information not present in any retrieved source
"""
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass

from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
import string


@dataclass
class CheckResult:
    hallucination_score: float  # 0 = no hallucination, 1 = full hallucination
    out_of_source_words: int
    total_words: int
    out_of_source_phrases: List[str]
    coverage: float  # percentage of content covered by sources
    passed: bool


class HallucinationChecker:
    """
    Check generated answer against retrieved source snippets.
    Uses simple word overlap to detect information not in any source.
    """

    def __init__(self, min_coverage: float = 0.7, max_hallucination_score: float = 0.2):
        """
        Initialize checker.
        Args:
            min_coverage: minimum percentage of words that must be covered by sources
            max_hallucination_score: maximum allowed hallucination score
        """
        self.min_coverage = min_coverage
        self.max_hallucination_score = max_hallucination_score
        self._stop_words = set(stopwords.words('english'))
        # Add chinese stop words if available
        try:
            from nltk.corpus import chinese_stopwords
            self._stop_words.update(chinese_stopwords.words())
        except ImportError:
            pass

    def check(
        self,
        answer: str,
        sources: List[Dict[str, Any]]
    ) -> CheckResult:
        """
        Check answer against retrieved sources.
        Args:
            answer: generated answer to check
            sources: list of retrieved sources with "text" or "snippet" key
        Returns:
            CheckResult with score and coverage
        """
        # Extract all text from sources
        source_texts = []
        for s in sources:
            txt = s.get('text', s.get('snippet', ''))
            if txt:
                source_texts.append(txt)
        source_vocab = self._extract_vocab("\n".join(source_texts))

        # Tokenize answer
        answer_tokens = self._tokenize(answer)
        if len(answer_tokens) == 0:
            return CheckResult(
                hallucination_score=0.0,
                out_of_source_words=0,
                total_words=0,
                out_of_source_phrases=[],
                coverage=1.0,
                passed=True
            )

        # Find words not in source vocab
        out_of_source = []
        out_of_source_count = 0
        for token in answer_tokens:
            if token not in source_vocab:
                out_of_source.append(token)
                out_of_source_count += 1

        # Calculate scores
        total_count = len(answer_tokens)
        hallucination_score = out_of_source_count / total_count if total_count > 0 else 0
        coverage = (total_count - out_of_source_count) / total_count if total_count > 0 else 0

        # Check if passes thresholds
        passed = (
            coverage >= self.min_coverage and
            hallucination_score <= self.max_hallucination_score
        )

        # Find multi-word phrases out of source
        out_of_source_phrases = self._find_out_of_source_phrases(answer_tokens, source_vocab)

        return CheckResult(
            hallucination_score=hallucination_score,
            out_of_source_words=out_of_source_count,
            total_words=total_count,
            out_of_source_phrases=out_of_source_phrases,
            coverage=coverage,
            passed=passed
        )

    def _extract_vocab(self, text: str) -> set:
        """Extract vocabulary from text, lowercase, remove stopwords and punctuation"""
        tokens = self._tokenize(text)
        return set(tokens)

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text, clean"""
        # Lowercase
        text = text.lower()
        # Remove punctuation
        text = text.translate(str.maketrans('', '', string.punctuation))
        # Tokenize
        tokens = word_tokenize(text)
        # Remove stopwords and short tokens
        tokens = [
            t for t in tokens
            if t not in self._stop_words and len(t) > 2
        ]
        return tokens

    def _find_out_of_source_phrases(self, tokens: List[str], source_vocab: set) -> List[str]:
        """Find consecutive phrases of 2+ words that are all out of source"""
        phrases = []
        current = []
        for token in tokens:
            if token not in source_vocab:
                current.append(token)
            else:
                if len(current) >= 2:
                    phrases.append(" ".join(current))
                current = []
        if len(current) >= 2:
            phrases.append(" ".join(current))
        return phrases[:10]  # limit to first 10
