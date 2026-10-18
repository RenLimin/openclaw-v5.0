"""
Hybrid Search: deterministic entity lookup + FTS + vector hybrid search
Backward compatible with existing usage
"""
import numpy as np
from typing import List, Dict, Optional, Tuple
from .db import AIKB
from .retrieval import RetrievalEngine


class HybridSearch:
    """
    Hybrid search combining deterministic entity lookup, FTS keyword search and vector similarity search.
    Backward compatible with existing API.
    """
    def __init__(self, kb: AIKB, domain_id: int, include_expired: bool = False):
        self.kb = kb
        self.domain_id = domain_id
        self.include_expired = include_expired
        self.retrieval_engine = RetrievalEngine(kb, domain_id, include_expired=include_expired)

    def search(self, query: str, top_k: int = 5, min_score: float = 0.3) -> List[Dict]:
        """
        Public search API, returns the same format as before for backward compatibility.
        """
        result = self.retrieval_engine.search(query, top_k, min_score)
        hits = result.hits
        output = []
        for hit in hits:
            output.append({
                "entity": hit.entity,
                "doc": hit.doc,
                "chunk": hit.chunk,
                "similarity": hit.score,
            })
        return output
