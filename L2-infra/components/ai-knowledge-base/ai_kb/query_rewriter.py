"""
Query rewriter: expand query with synonyms, correct spelling, disambiguate
Supports:
  - Synonym expansion from dictionary
  - Spell correction (SymSpell)
  - Abbreviation expansion
  - Query expansion with candidate terms from retrieval
"""
import re
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass

import string


@dataclass
class RewriteResult:
    original_query: str
    rewritten_query: str
    expansions: List[str]
    corrections: List[Tuple[str, str]]
    expansions_added: bool


class QueryRewriter:
    """
    Query rewriter for improving retrieval quality.
    Provides synonym expansion, abbreviation expansion, spell correction.
    """

    def __init__(
        self,
        synonyms: Dict[str, List[str]] = None,
        abbreviations: Dict[str, str] = None,
        symspell=None,
        min_similarity: float = 0.8
    ):
        """
        Initialize query rewriter.
        Args:
            synonyms: {term: [list of synonyms]}
            abbreviations: {abbr: full form}
            symspell: pre-initialized SymSpell instance for spell correction
            min_similarity: minimum similarity for spell correction
        """
        self.synonyms = synonyms or {}
        self.abbreviations = abbreviations or {}
        self.symspell = symspell
        self.min_similarity = min_similarity
        self._word_pattern = re.compile(r'\b\w+\b')

    def rewrite(
        self,
        query: str,
        retrieval_candidates: Optional[List[Dict]] = None
    ) -> RewriteResult:
        """
        Rewrite query with expansions and corrections.
        Args:
            query: original user query
            retrieval_candidates: optional initial retrieval candidates to get more terms
        Returns:
            RewriteResult with original, rewritten, expansions, corrections
        """
        original = query.strip()
        words = self._word_pattern.findall(original.lower())
        expansions = []
        corrections = []
        rewritten = original
        expanded = False

        # 1. Correct spelling
        if self.symspell is not None:
            corrected_words = []
            for word in words:
                if len(word) <= 2:
                    corrected_words.append(word)
                    continue
                suggestions = self.symspell.lookup(word, self.min_similarity)
                if suggestions and suggestions[0].term != word:
                    corrections.append((word, suggestions[0].term))
                    corrected_words.append(suggestions[0].term)
                    expanded = True
                else:
                    corrected_words.append(word)
            # Replace words with corrected ones
            corrected_query = " ".join(corrected_words)
            # Preserve original punctuation and capitalization roughly
            for old, new in corrections:
                pattern = re.compile(re.escape(old), re.IGNORECASE)
                corrected_query = pattern.sub(new, corrected_query)
            rewritten = corrected_query
            expanded = expanded or len(corrections) > 0

        # 2. Expand abbreviations
        for abbr, full in self.abbreviations.items():
            pattern = re.compile(r'\b' + re.escape(abbr) + r'\b', re.IGNORECASE)
            if pattern.search(rewritten):
                if full.lower() not in rewritten.lower():
                    rewritten = pattern.sub(f"{abbr} ({full})", rewritten)
                    expansions.append(f"{abbr} → {full}")
                    expanded = True

        # 3. Expand synonyms
        for term, syns in self.synonyms.items():
            pattern = re.compile(r'\b' + re.escape(term) + r'\b', re.IGNORECASE)
            matches = list(pattern.finditer(rewritten))
            if matches:
                # Keep the original, add synonyms to end of query
                all_syns = [s for s in syns if s.lower() not in rewritten.lower()]
                if all_syns:
                    rewritten = rewritten + " " + " ".join(all_syns)
                    expansions.extend([f"{term} → {s}" for s in all_syns])
                    expanded = True

        # 4. Expand with terms from initial retrieval if available
        if retrieval_candidates is not None and len(retrieval_candidates) > 0:
            extra_terms = self._extract_entity_terms(retrieval_candidates)
            extra_terms = [t for t in extra_terms if t.lower() not in rewritten.lower()]
            if extra_terms:
                rewritten = rewritten + " " + " ".join(extra_terms)
                expansions.extend([f"from retrieval: {t}" for t in extra_terms])
                expanded = True

        # Deduplicate expansions
        expansions = list(sorted(set(expansions)))

        return RewriteResult(
            original_query=original,
            rewritten_query=rewritten.strip(),
            expansions=expansions,
            corrections=corrections,
            expansions_added=expanded
        )

    def _extract_entity_terms(self, candidates: List[Dict]) -> List[str]:
        """Extract entity names from top retrieval candidates for expansion"""
        terms: Set[str] = set()
        for candidate in candidates[:5]:  # only top 5 to avoid noise
            if "entity" in candidate and candidate["entity"]:
                entity = candidate["entity"]
                if "name" in entity and entity["name"]:
                    # Split into words and add single words if length > 3
                    name_words = self._word_pattern.findall(entity["name"].lower())
                    for word in name_words:
                        if len(word) > 3:
                            terms.add(word)
        return sorted(terms)

    def add_synonyms(self, new_synonyms: Dict[str, List[str]]):
        """Add new synonyms to dictionary"""
        for term, syns in new_synonyms.items():
            if term in self.synonyms:
                self.synonyms[term].extend(syns)
                # Deduplicate
                self.synonyms[term] = list(set(self.synonyms[term]))
            else:
                self.synonyms[term] = syns

    def add_abbreviations(self, new_abbr: Dict[str, str]):
        """Add new abbreviation mappings"""
        self.abbreviations.update(new_abbr)
