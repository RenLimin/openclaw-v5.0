"""
Recall fusion and ranking
"""
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class RecallResult:
    """Result from a single recall channel"""
    chunk_id: int
    entity_id: int
    doc_id: int
    channel: str
    raw_score: float
    weight: float


@dataclass
class RankedResult:
    """Final ranked result"""
    chunk_id: int
    entity_id: int
    doc_id: int
    score: float
    channels: List[str]


class FusionRanker:
    """Fuse results from multiple recall channels and rank them"""

    METHOD_WEIGHTED_SUM = "weighted_sum"
    METHOD_RRF = "rrf"

    def __init__(self, method: str = METHOD_WEIGHTED_SUM, rrf_k: int = 60):
        self.method = method
        self.rrf_k = rrf_k

    def fuse(self,
             entity_results: List[RecallResult],
             fts_results: List[RecallResult],
             vector_results: List[RecallResult],
             graph_results: Optional[List[RecallResult]] = None) -> List[RankedResult]:
        """Fuse results from multiple channels into a single ranked list"""
        all_results: Dict[int, RecallResult] = {}
        scores: Dict[int, float] = {}
        channels: Dict[int, List[str]] = {}

        # Collect all results
        for results in [entity_results, fts_results, vector_results, graph_results or []]:
            for result in results:
                key = result.chunk_id
                if key not in all_results:
                    all_results[key] = result
                    scores[key] = 0.0
                    channels[key] = []
                channels[key].append(result.channel)

        if self.method == self.METHOD_WEIGHTED_SUM:
            for result in all_results.values():
                scores[result.chunk_id] += result.raw_score * result.weight
        elif self.method == self.METHOD_RRF:
            # Reciprocal Rank Fusion
            # For each result compute 1 / (k + rank)
            rank_map: Dict[int, int] = {}
            results_list = [entity_results, fts_results, vector_results, graph_results or []]
            for results in results_list:
                if not results:
                    continue
                sorted_results = sorted(results, key=lambda x: x.raw_score, reverse=True)
                for rank, result in enumerate(sorted_results):
                    key = result.chunk_id
                    rank_map[key] = rank_map.get(key, 0) + 1.0 / (self.rrf_k + rank + 1)
            for key in rank_map:
                scores[key] = rank_map[key]

        # Sort by final score
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        final_results: List[RankedResult] = []
        for chunk_id, score in ranked:
            result = all_results[chunk_id]
            final_results.append(RankedResult(
                chunk_id=chunk_id,
                entity_id=result.entity_id,
                doc_id=result.doc_id,
                score=score,
                channels=channels[chunk_id]
            ))

        return final_results
