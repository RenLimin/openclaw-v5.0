"""
Base vector store interface
Supports: SQLite blob storage (default) / Qdrant / FAISS
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple, Optional


class BaseVectorStore(ABC):
    """Base vector store interface"""

    @abstractmethod
    def init_collection(self, dimension: int):
        """Initialize collection if not exists"""
        pass

    @abstractmethod
    def add_embedding(
        self,
        chunk_id: int,
        embedding: List[float],
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Add single embedding"""
        pass

    @abstractmethod
    def add_embeddings(
        self,
        chunk_ids: List[int],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None
    ):
        """Add multiple embeddings in batch"""
        pass

    @abstractmethod
    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filter: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[int, float]]:
        """Search for similar embeddings, returns (chunk_id, similarity)"""
        pass

    @abstractmethod
    def delete_embedding(self, chunk_id: int):
        """Delete single embedding"""
        pass

    @abstractmethod
    def delete_collection(self):
        """Delete entire collection"""
        pass
