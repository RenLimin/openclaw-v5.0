import sys
sys.path.insert(0, '/Users/bangcle/.openclaw/sandboxes/workspace-90f666906d683a4d17e1cd69bac09dd8')

"""
Search module: hybrid keyword + vector search
"""
import numpy as np
from typing import List, Dict, Optional, Tuple
from .db import ProductKBDB

# get_embedding will be injected at runtime
get_embedding = None


class HybridSearch:
    def __init__(self, db: ProductKBDB, embedding_func=None):
        self.db = db
        global get_embedding
        if embedding_func:
            get_embedding = embedding_func

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        return dot_product / (norm_a * norm_b)

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """Hybrid search: FTS + vector search"""
        # Get FTS results
        fts_chunk_ids = self.db.fts_search_chunks(query, 20)

        if not get_embedding:
            raise RuntimeError('get_embedding function not injected')

        # Get vector embedding for query
        query_embed = np.array(get_embedding(query))

        # Collect all candidate chunks
        candidates = []
        seen = set()
        # Process vector candidates first, then FTS
        # For each candidate, get embedding and compute similarity
        for chunk_id in fts_chunk_ids:
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            chunk = self.db.get_chunk(chunk_id)
            if not chunk:
                continue
            if chunk["embedding"] is None:
                continue
            chunk_embed = np.frombuffer(chunk["embedding"], dtype=np.float64)
            similarity = self.cosine_similarity(query_embed, chunk_embed)
            candidates.append({
                "chunk_id": chunk_id,
                "similarity": similarity,
                "chunk": chunk
            })

        # Sort by similarity descending
        candidates.sort(key=lambda x: x["similarity"], reverse=True)

        # Get full info for top results
        results = []
        for cand in candidates[:top_k]:
            chunk = cand["chunk"]
            doc = self.db.get_doc(chunk["doc_id"])
            product = self.db.get_product(doc["product_id"])
            results.append({
                "product": dict(product),
                "doc": dict(doc),
                "chunk": dict(chunk),
                "similarity": cand["similarity"]
            })

        return results
