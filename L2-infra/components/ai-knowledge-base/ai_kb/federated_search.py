"""
Federated search across multiple knowledge base instances
Supports cross-instance retrieval, result fusion, deduplication
"""
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass

from ai_kb.api import AIKBService
from ai_kb.embedding import EmbeddingProvider
from ai_kb.embedding import cosine_sim


@dataclass
class FederatedResult:
    instance_code: str
    result: Dict[str, Any]
    global_score: float


class FederatedSearch:
    """
    Federated search across multiple KB instances.
    Runs query on all instances, collects top results, fuses scores, deduplicates.
    """

    def __init__(
        self,
        instances: List[AIKBService],
        embedding_provider: EmbeddingProvider = None,
        top_k_global: int = 10
    ):
        """
        Initialize federated search.
        Args:
            instances: list of AIKBService instances for different KB instances
            embedding_provider: optional embedding provider for cross-instance score fusion
            top_k_global: maximum number of results to return globally
        """
        self.instances = {inst.domain_code: inst for inst in instances}
        self.embedding = embedding_provider
        self.top_k_global = top_k_global

    def search(
        self,
        query: str,
        top_k_per_instance: int = 5,
        include_expired: bool = False
    ) -> List[FederatedResult]:
        """
        Run federated search across all instances.
        Args:
            query: search query
            top_k_per_instance: max results to collect from each instance
            include_expired: whether to include expired entities
        Returns:
            sorted list of federated results
        """
        all_results: List[FederatedResult] = []

        # Run query on each instance
        for code, service in self.instances.items():
            try:
                # Get raw results from instance
                results = service.search(query, top_k=top_k_per_instance, include_expired=include_expired)
                # Wrap each result
                for r in results:
                    # If we have embedding provider, calculate global similarity
                    global_score = r.get("similarity", 0)
                    if self.embedding is not None:
                        # Get embedding of query and result text
                        q_emb = self.embedding(query)
                        text = r.get("text", r.get("snippet", ""))
                        if text:
                            r_emb = self.embedding(text)
                            global_score = cosine_sim(q_emb, r_emb)
                    all_results.append(FederatedResult(
                        instance_code=code,
                        result=r,
                        global_score=global_score
                    ))
            except Exception:
                continue

        # Sort by global score descending
        all_results.sort(key=lambda r: r.global_score, reverse=True)

        # Deduplicate: keep the highest scoring result for identical entities
        deduped = self._deduplicate(all_results)

        # Truncate to top_k_global
        if len(deduped) > self.top_k_global:
            deduped = deduped[:self.top_k_global]

        return deduped

    def query_with_answer(
        self,
        query: str,
        top_k_global: int = 10,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Run federated search and format for answer with sources.
        Returns format compatible with single instance answer.
        """
        results = self.search(query, top_k_global=top_k_global, **kwargs)
        sources = [fr.result for fr in results]
        # Build answer structure same as AIKBService.query
        # Final answer generation is up to the caller, we just provide sources
        return {
            "query": query,
            "sources": sources,
            "source_count": len(sources),
            "instances": list(self.instances.keys()),
            "total_results": sum(len(fr.result) for fr in results)
        }

    def _deduplicate(self, results: List[FederatedResult]) -> List[FederatedResult]:
        """Deduplicate results: keep highest scoring for each entity id"""
        seen: Dict[int, FederatedResult] = {}
        for fr in results:
            entity_id = fr.result.get("entity", {}).get("id")
            if not entity_id:
                seen[hash(fr.result.get("snippet", ""))] = fr
                continue
            if entity_id not in seen or fr.global_score > seen[entity_id].global_score:
                seen[entity_id] = fr
        # Convert back to sorted list
        deduped = list(seen.values())
        deduped.sort(key=lambda r: r.global_score, reverse=True)
        return deduped

    def add_instance(self, service: AIKBService):
        """Add a new KB instance to federated search"""
        self.instances[service.domain_code] = service

    def remove_instance(self, domain_code: str):
        """Remove a KB instance from federated search"""
        if domain_code in self.instances:
            del self.instances[domain_code]
