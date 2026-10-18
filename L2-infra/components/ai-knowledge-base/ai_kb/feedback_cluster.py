"""
Feedback clustering: automatically cluster similar user feedback
Uses embedding-based clustering to group similar feedback queries
Helps identify knowledge gaps and low-quality content
"""
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass

from ai_kb.db import AIKB
from ai_kb.embedding import EmbeddingProvider


@dataclass
class FeedbackCluster:
    """Cluster of similar feedback"""
    cluster_id: int
    center_query: str
    feedback_ids: List[int]
    size: int
    average_score: float
    queries: List[str]


class FeedbackClustering:
    """
    Cluster user feedback based on query similarity.
    Uses k-means clustering on embeddings.
    """

    def __init__(
        self,
        db: AIKB,
        embedding_provider: EmbeddingProvider,
        min_cluster_size: int = 3,
        similarity_threshold: float = 0.7
    ):
        """
        Initialize feedback clustering.
        Args:
            db: AIKB database instance
            embedding_provider: embedding provider for query similarity
            min_cluster_size: minimum size for a valid cluster
            similarity_threshold: threshold for agglomerative clustering
        """
        self.db = db
        self.embedding = embedding_provider
        self.min_cluster_size = min_cluster_size
        self.threshold = similarity_threshold

    def get_all_feedback(self, domain_id: int) -> List[Dict[str, Any]]:
        """Get all feedback for domain with basic info"""
        rows = self.db.execute("""
        SELECT id, query_text, feedback_type FROM kb_feedback
        WHERE domain_id = ?
        ORDER BY created_at DESC
        """, (domain_id,)).fetchall()
        return [dict(r) for r in rows]

    def cluster_feedback(
        self,
        domain_id: int,
        n_clusters: Optional[int] = None
    ) -> List[FeedbackCluster]:
        """
        Cluster all feedback for a domain.
        Uses k-means if n_clusters provided, else agglomerative clustering.
        """
        feedback = self.get_all_feedback(domain_id)
        if len(feedback) < self.min_cluster_size:
            return []

        # Get embeddings for all queries
        queries = [f["query_text"] for f in feedback if f["query_text"]]
        ids = [f["id"] for f in feedback if f["query_text"]]
        if len(queries) < 2:
            return []

        embeddings = []
        valid_queries = []
        valid_ids = []
        for q, fid in zip(queries, ids):
            try:
                emb = self.embedding(q)
                embeddings.append(emb)
                valid_queries.append(q)
                valid_ids.append(fid)
            except Exception:
                continue

        if len(valid_queries) < self.min_cluster_size:
            return []

        emb_np = np.array(embeddings)

        if n_clusters is None:
            clusters = self._agglomerative_clustering(emb_np)
        else:
            clusters = self._kmeans_clustering(emb_np, n_clusters)

        # Build result
        result = []
        for cluster_id, cluster_indices in enumerate(clusters):
            if len(cluster_indices) < self.min_cluster_size:
                continue
            cluster_queries = [valid_queries[i] for i in cluster_indices]
            cluster_ids = [valid_ids[i] for i in cluster_indices]
            # Find center (closest to mean)
            center_idx = self._find_center(emb_np[cluster_indices])
            center_query = cluster_queries[center_idx]
            result.append(FeedbackCluster(
                cluster_id=cluster_id,
                center_query=center_query,
                feedback_ids=cluster_ids,
                size=len(cluster_indices),
                average_score=0.0,  # TODO: average score calculation
                queries=cluster_queries
            ))

        return result

    def _kmeans_clustering(
        self,
        embeddings: np.ndarray,
        n_clusters: int
    ) -> List[List[int]]:
        """K-means clustering"""
        from sklearn.cluster import KMeans
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init='auto')
        labels = kmeans.fit_predict(embeddings)
        clusters = [[] for _ in range(n_clusters)]
        for i, label in enumerate(labels):
            clusters[label].append(i)
        return clusters

    def _agglomerative_clustering(
        self,
        embeddings: np.ndarray
    ) -> List[List[int]]:
        """Agglomerative clustering based on similarity threshold"""
        from sklearn.cluster import AgglomerativeClustering
        clustering = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=1 - self.threshold,
            linkage='complete'
        )
        labels = clustering.fit_predict(embeddings)
        n_clusters = clustering.n_clusters_
        clusters = [[] for _ in range(n_clusters)]
        for i, label in enumerate(labels):
            clusters[label].append(i)
        return clusters

    def _find_center(self, embeddings: np.ndarray) -> int:
        """Find index of embedding closest to mean of cluster"""
        mean = np.mean(embeddings, axis=0)
        distances = np.linalg.norm(embeddings - mean, axis=1)
        return np.argmin(distances)

    def get_knowledge_gaps(self, domain_id: int, min_size: int = 3) -> List[FeedbackCluster]:
        """Get clusters that likely represent knowledge gaps (multiple not useful feedback)"""
        clusters = self.cluster_feedback(domain_id)
        gaps = []
        # Filter clusters by size and negative feedback
        # TODO: check feedback types and average score
        for cluster in clusters:
            if cluster.size >= min_size:
                gaps.append(cluster)
        return gaps
