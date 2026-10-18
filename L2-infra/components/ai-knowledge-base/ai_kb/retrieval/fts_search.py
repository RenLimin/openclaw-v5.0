"""
FTS (Full Text Search) keyword search
"""
from typing import List, Tuple

from ..db import AIKB


class FtsSearcher:
    """Full text search on chunks using SQLite FTS5"""

    def __init__(self, db: AIKB, domain_id: int, include_expired: bool = False):
        self.db = db
        self.domain_id = domain_id
        self.include_expired = include_expired

    def search(self, query: str, top_k: int = 20) -> List[Tuple[int, float]]:
        """
        Search for chunks by keyword.
        Returns list of (chunk_id, bm25_score_normalized)
        """
        fts_ids = self.db.fts_search_chunks(query, top_k)
        results: List[Tuple[int, float]] = []

        # TODO: Get actual BM25 score from FTS
        # For now, we just return the order as score based on position
        for i, chunk_id in enumerate(fts_ids):
            # Score decreasing with rank
            score = 1.0 / (i + 1)
            results.append((chunk_id, score))

        return results
