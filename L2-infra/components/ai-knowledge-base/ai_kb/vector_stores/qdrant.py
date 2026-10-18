"""
Qdrant vector store implementation
Supports local Qdrant instance and cloud Qdrant
"""
from typing import List, Dict, Any, Tuple, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models

from ai_kb.vector_stores.base import BaseVectorStore


class QdrantVectorStore(BaseVectorStore):
    """Qdrant vector store implementation"""

    def __init__(
        self,
        collection_name: str,
        url: str = "http://localhost:6333",
        api_key: Optional[str] = None,
        prefix: str = "aikb_"
    ):
        """
        Initialize Qdrant vector store.
        Args:
            collection_name: name of the collection
            url: Qdrant server URL
            api_key: optional API key for cloud Qdrant
            prefix: prefix for collection name in Qdrant
        """
        self.collection_name = f"{prefix}{collection_name}"
        self.client = QdrantClient(url=url, api_key=api_key)
        self._dimension: Optional[int] = None

    def init_collection(self, dimension: int):
        """Create collection if it doesn't exist"""
        self._dimension = dimension
        collections = self.client.get_collections()
        exists = any(c.name == self.collection_name for c in collections.collections)
        if not exists:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=dimension,
                    distance=models.Distance.COSINE
                )
            )

    def add_embedding(
        self,
        chunk_id: int,
        embedding: List[float],
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Add single embedding"""
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                models.PointStruct(
                    id=chunk_id,
                    vector=embedding,
                    payload=metadata or {}
                )
            ]
        )

    def add_embeddings(
        self,
        chunk_ids: List[int],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None
    ):
        """Add multiple embeddings in batch"""
        points = []
        for i, (cid, emb) in enumerate(zip(chunk_ids, embeddings)):
            payload = metadatas[i] if metadatas else {}
            points.append(models.PointStruct(
                id=cid,
                vector=emb,
                payload=payload
            ))
        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filter: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[int, float]]:
        """Search for similar embeddings"""
        qdrant_filter = None
        if filter:
            # Convert simple filter dict to Qdrant filter
            must = []
            for key, value in filter.items():
                must.append(models.FieldCondition(
                    key=key,
                    match=models.MatchValue(value=value)
                ))
            qdrant_filter = models.Filter(must=must)

        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding,
            limit=top_k,
            query_filter=qdrant_filter,
            with_payload=False
        )
        return [(result.id, result.score) for result in results]

    def delete_embedding(self, chunk_id: int):
        """Delete single embedding"""
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.PointIdsList(
                points=[chunk_id]
            )
        )

    def delete_collection(self):
        """Delete entire collection"""
        self.client.delete_collection(collection_name=self.collection_name)
