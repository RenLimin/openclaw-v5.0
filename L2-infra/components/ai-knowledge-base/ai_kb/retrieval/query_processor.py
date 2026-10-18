"""
Query preprocessing and rewriting
"""
import re
from typing import List, Tuple, Optional
from dataclasses import dataclass

from .catalog_normalizer import CatalogNormalizer


@dataclass
class ProcessedQuery:
    """Result of query processing"""
    original_query: str
    rewritten_query: str
    expanded_terms: List[str]
    cleaned_query: str
    detected_entities: List[str]
    normalized_query: str  # 经过标准产品目录归一化的查询
    matched_catalog_names: List[str]  # 命中的标准产品/服务名称
    confidence: float  # How confident we are about the query being well-formed
    issues: List[str]


class QueryProcessor:
    """Process and rewrite user queries"""

    def __init__(self, synonyms: Optional[Dict[str, List[str]]] = None,
                 catalog_normalizer: Optional[CatalogNormalizer] = None):
        self.synonyms = synonyms or {}
        self.catalog_normalizer = catalog_normalizer or CatalogNormalizer()

    def clean(self, query: str) -> str:
        """Clean query: remove extra whitespace, control characters"""
        # Remove control characters
        cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', query)
        # Collapse multiple spaces
        cleaned = re.sub(r'\s+', ' ', cleaned)
        return cleaned.strip()

    def expand_synonyms(self, query: str) -> Tuple[str, List[str]]:
        """Expand query with synonyms"""
        expanded_terms = []
        result_terms = []
        words = re.findall(r'\b\w+\b', query.lower())

        for word in words:
            result_terms.append(word)
            if word in self.synonyms:
                for syn in self.synonyms[word]:
                    if syn not in result_terms:
                        result_terms.append(syn)
                        expanded_terms.append(syn)

        return ' '.join(result_terms), expanded_terms

    def correct_spelling(self, query: str) -> str:
        """
        Simple spelling correction placeholder.
        In future can be implemented with a dictionary or edit distance.
        """
        # TODO: implement spelling correction
        return query

    def detect_entities(self, query: str) -> List[str]:
        """
        Detect potential entity names in query.
        Currently just extracts capitalized words as candidates.
        In future can be improved with NER model.
        """
        # Simple heuristic: extract sequences of capitalized words
        entities = []
        words = query.split()
        current_entity = []
        for word in words:
            if word and word[0].isupper():
                current_entity.append(word)
            else:
                if current_entity:
                    entities.append(' '.join(current_entity))
                    current_entity = []
        if current_entity:
            entities.append(' '.join(current_entity))
        return entities

    def process(self, query: str) -> ProcessedQuery:
        """Full query processing pipeline"""
        original = query.strip()
        cleaned = self.clean(original)
        corrected = self.correct_spelling(cleaned)
        # 标准产品目录归一化: 非标准叫法 -> 标准产品名
        normalized, matched_catalog = self.catalog_normalizer.normalize(corrected)
        rewritten, expanded = self.expand_synonyms(normalized)
        entities = self.detect_entities(normalized)

        # Calculate confidence
        confidence = 1.0
        issues = []

        if len(cleaned) < 2:
            confidence *= 0.5
            issues.append("Query too short")

        if len(re.findall(r'[a-zA-Z]', cleaned)) == 0:
            confidence *= 0.7
            issues.append("Query contains no letters")

        return ProcessedQuery(
            original_query=original,
            rewritten_query=rewritten,
            expanded_terms=expanded,
            cleaned_query=cleaned,
            detected_entities=entities,
            normalized_query=normalized,
            matched_catalog_names=matched_catalog,
            confidence=confidence,
            issues=issues
        )
