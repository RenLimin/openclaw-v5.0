"""
Vector similarity search
"""
import struct
import math
from typing import List, Tuple, Optional

from ..db import AIKB
from ..embedding import embed_text, cosine_similarity


class VectorSearcher:
    """Vector similarity search using cosine similarity"""

    def __init__(self, db: AIKB, domain_id: int, include_expired: bool = False):
        self.db = db
        self.domain_id = domain_id
        self.include_expired = include_expired

    def search(self, query_text: str, top_k: int = 20) -> List[Tuple[int, float]]:
        """
        Search for similar chunks by vector similarity.
        Returns list of (chunk_id, similarity_score) sorted descending.
        """
        # Embed query
        query_vec = embed_text(query_text)
        if not query_vec:
            return []

        # Get all chunks with embeddings
        # TODO: For large datasets this should use approximate nearest neighbor (FAISS/Annoy)
        # For now, brute force for small to medium datasets (< 100k chunks)
        cursor = self.db.execute("""
        SELECT dc.id, dc.embedding FROM doc_chunk dc
        JOIN doc_asset da ON dc.doc_id = da.id
        JOIN entity e ON da.entity_id = e.id
        WHERE e.domain_id = ? AND (e.status IS NULL OR e.status != 'expired' OR ?)
        AND dc.embedding IS NOT NULL
        """, (self.domain_id, self.include_expired))

        similarities: List[Tuple[int, float]] = []
        for (chunk_id, embedding_bytes) in cursor.fetchall():
            if embedding_bytes is None:
                continue
            # Unpack embedding from bytes
            n_floats = len(embedding_bytes) // struct.calcsize('f')
            chunk_vec = struct.unpack(f'{n_floats}f', embedding_bytes)
            sim = cosine_similarity(query_vec, chunk_vec)
            similarities.append((chunk_id, sim))

        # Sort descending by similarity
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]
