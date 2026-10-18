"""
Entity exact / fuzzy match search
"""
from typing import List, Tuple, Dict, Any, Optional
import sqlite3

from ..db import AIKB


class EntitySearchResult:
    """Result from entity search"""
    def __init__(self, entity_id: int, score: float, match_type: str):
        self.entity_id = entity_id
        self.score = score
        self.match_type = match_type


# Common Chinese question suffixes to strip when building query candidates
QUESTION_SUFFIXES = [
    '有什么功能', '有哪些功能', '是什么', '有哪些', '有那些', '有哪些内容',
    '怎么使用', '如何使用', '怎么做', '怎么', '如何', '为什么', '哪个',
    '多少', '多少钱', '价格', '版本', '是什么东西', '干嘛的', '做什么的',
]


class EntitySearcher:
    """Search for entities by name/aliases"""

    def __init__(self, db: AIKB, domain_id: int, include_expired: bool = False):
        self.db = db
        self.domain_id = domain_id
        self.include_expired = include_expired

    def _query_candidates(self, query: str) -> List[str]:
        """
        Generate candidate query fragments for entity matching.
        Full query first, then stripped of common question suffixes.
        """
        candidates = [query]
        cleaned = query
        for suffix in QUESTION_SUFFIXES:
            if cleaned.endswith(suffix) and len(cleaned) > len(suffix):
                stripped = cleaned[:-len(suffix)].strip()
                if stripped and stripped not in candidates:
                    candidates.append(stripped)
        # Also add progressively shorter prefixes (min length 2)
        prefix = cleaned
        while len(prefix) > 2:
            prefix = prefix[:-1]
            if prefix not in candidates:
                candidates.append(prefix)
            if len(candidates) >= 6:
                break
        return candidates

    def search(self, query: str, top_k: int = 10) -> List[EntitySearchResult]:
        """
        Search entities with priority:
        1. Exact match
        2. Alias exact match
        3. Prefix match
        4. Fuzzy match (contains)
        5. FTS search
        Uses multi-level query candidates (full query → stripped fragments)
        """
        results: List[EntitySearchResult] = []
        seen_ids = set()
        candidates = self._query_candidates(query)

        for candidate in candidates:
            if len(results) >= top_k:
                break

            # 1. Exact match
            exact = self.db.find_entities_by_name(
                self.domain_id, candidate, limit=top_k, include_expired=self.include_expired
            )
            for ent in exact:
                if ent['id'] in seen_ids:
                    continue
                if ent['name'] == candidate:
                    seen_ids.add(ent['id'])
                    results.append(EntitySearchResult(ent['id'], 1.0, "exact_match"))
                elif ent['aliases'] and candidate in ent['aliases'].split(','):
                    seen_ids.add(ent['id'])
                    results.append(EntitySearchResult(ent['id'], 0.9, "alias_exact"))

            if len(results) >= top_k:
                break

            # 2. Prefix match
            prefix_results = self.db.execute("""
            SELECT id, name FROM entity
            WHERE domain_id = ? AND (name LIKE ? OR aliases LIKE ?)
            AND (status IS NULL OR status != 'expired' OR ?)
            LIMIT ?
            """, (self.domain_id, candidate + '%', candidate + '%', self.include_expired, top_k - len(results)))
            for (id, name) in prefix_results.fetchall():
                if id not in seen_ids:
                    seen_ids.add(id)
                    results.append(EntitySearchResult(id, 0.75, "prefix_match"))

            if len(results) >= top_k:
                break

            # 3. Fuzzy contains match
            fuzzy_results = self.db.execute("""
            SELECT id, name FROM entity
            WHERE domain_id = ? AND (name LIKE ? OR aliases LIKE ?)
            AND (status IS NULL OR status != 'expired' OR ?)
            LIMIT ?
            """, (self.domain_id, '%' + candidate + '%', '%' + candidate + '%', self.include_expired, top_k - len(results)))
            for (id, name) in fuzzy_results.fetchall():
                if id not in seen_ids:
                    seen_ids.add(id)
                    results.append(EntitySearchResult(id, 0.6, "fuzzy_contains"))

            if len(results) >= top_k:
                break

        # 4. FTS search (on original query)
        if len(results) < top_k:
            fts_ids = self.db.fts_search_entities(
                self.domain_id, query, top_k - len(results), self.include_expired
            )
            for entity_id in fts_ids:
                if entity_id not in seen_ids:
                    seen_ids.add(entity_id)
                    results.append(EntitySearchResult(entity_id, 0.5, "fts_match"))

        return results[:top_k]
