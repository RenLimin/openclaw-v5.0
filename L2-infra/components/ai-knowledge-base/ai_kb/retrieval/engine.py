"""
Main Retrieval Engine
"""
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from ..db import AIKB
from ..permissions import PermissionChecker
from .query_processor import QueryProcessor, ProcessedQuery
from .entity_search import EntitySearcher, EntitySearchResult
from .fts_search import FtsSearcher
from .vector_search import VectorSearcher
from .fusion import FusionRanker, RecallResult, RankedResult


@dataclass
class RetrievalHit:
    """A single retrieval hit"""
    chunk_id: int
    entity_id: int
    doc_id: int
    entity: Dict[str, Any]
    doc: Dict[str, Any]
    chunk: Dict[str, Any]
    score: float
    channels: List[str]


@dataclass
class RetrievalResult:
    """Final retrieval result"""
    original_query: str
    rewritten_query: str
    hits: List[RetrievalHit]
    total_found: int
    confidence: float


class RetrievalEngine:
    """
    Main retrieval engine that orchestrates:
    1. Query processing
    2. Multiple recall channels (entity, FTS, vector, graph)
    3. Fusion ranking
    4. Permission filtering
    5. Return final ranked results
    """

    def __init__(self,
                 db: AIKB,
                 domain_id: int,
                 query_processor: Optional[QueryProcessor] = None,
                 include_expired: bool = False,
                 channel_config: Optional[Dict[str, Dict[str, Any]]] = None,
                 fusion_method: str = FusionRanker.METHOD_WEIGHTED_SUM,
                 permission_checker: Optional[PermissionChecker] = None):
        self.db = db
        self.domain_id = domain_id
        self.include_expired = include_expired
        self.query_processor = query_processor or QueryProcessor()
        self.permission_checker = permission_checker

        # Default channel config
        default_config = {
            "entity": {"enabled": True, "weight": 1.2, "top_k": 10},
            "fts": {"enabled": True, "weight": 1.0, "top_k": 20},
            "vector": {"enabled": True, "weight": 0.9, "top_k": 20},
            "graph": {"enabled": False, "weight": 0.8, "top_k": 10},
        }

        self.channel_config = default_config
        if channel_config:
            # Merge user config with default
            for channel, config in channel_config.items():
                if channel in self.channel_config:
                    self.channel_config[channel].update(config)

        # Initialize searchers
        self.entity_searcher = EntitySearcher(db, domain_id, include_expired)
        self.fts_searcher = FtsSearcher(db, domain_id, include_expired)
        self.vector_searcher = VectorSearcher(db, domain_id, include_expired)

        self.fusion_ranker = FusionRanker(method=fusion_method)

    def search(self, query_text: str, top_k: int = 5, min_score: float = 0.1) -> RetrievalResult:
        """Full search pipeline"""

        # 1. Process query
        processed = self.query_processor.process(query_text)

        # 2. Collect recall from each enabled channel
        entity_recall: List[RecallResult] = []
        if self.channel_config['entity']['enabled']:
            entity_results = self.entity_searcher.search(
                processed.cleaned_query,
                self.channel_config['entity']['top_k']
            )
            for ent_result in entity_results:
                ent = self.db.get_entity(ent_result.entity_id)
                if not ent:
                    continue
                docs = self.db.get_docs_by_entity(ent['id'])
                for doc in docs[:3]:  # Take first 3 docs per entity
                    chunks = self.db.get_chunks_by_doc(doc['id'], 3)
                    for chunk in chunks:
                        entity_recall.append(RecallResult(
                            chunk_id=chunk['id'],
                            entity_id=ent['id'],
                            doc_id=doc['id'],
                            channel="entity",
                            raw_score=ent_result.score,
                            weight=self.channel_config['entity']['weight']
                        ))

        fts_recall: List[RecallResult] = []
        if self.channel_config['fts']['enabled']:
            fts_results = self.fts_searcher.search(
                processed.rewritten_query,
                self.channel_config['fts']['top_k']
            )
            for (chunk_id, score) in fts_results:
                chunk = self.db.get_chunk(chunk_id)
                if not chunk:
                    continue
                doc = self.db.get_doc(chunk['doc_id'])
                if not doc:
                    continue
                entity = self.db.get_entity(doc['entity_id'])
                if not entity:
                    continue
                # Skip expired if not include_expired
                if not self.include_expired and entity['status'] == 'expired':
                    continue
                # Permission check
                if self.permission_checker and not self.permission_checker.can_access(chunk):
                    continue
                fts_recall.append(RecallResult(
                    chunk_id=chunk_id,
                    entity_id=entity['id'],
                    doc_id=doc['id'],
                    channel="fts",
                    raw_score=score,
                    weight=self.channel_config['fts']['weight']
                ))

        vector_recall: List[RecallResult] = []
        if self.channel_config['vector']['enabled']:
            vector_results = self.vector_searcher.search(
                processed.rewritten_query,
                self.channel_config['vector']['top_k']
            )
            for (chunk_id, score) in vector_results:
                chunk = self.db.get_chunk(chunk_id)
                if not chunk:
                    continue
                doc = self.db.get_doc(chunk['doc_id'])
                if not doc:
                    continue
                entity = self.db.get_entity(doc['entity_id'])
                if not entity:
                    continue
                # Skip expired if not include_expired
                if not self.include_expired and entity['status'] == 'expired':
                    continue
                # Permission check
                if self.permission_checker and not self.permission_checker.can_access(chunk):
                    continue
                vector_recall.append(RecallResult(
                    chunk_id=chunk_id,
                    entity_id=entity['id'],
                    doc_id=doc['id'],
                    channel="vector",
                    raw_score=score,
                    weight=self.channel_config['vector']['weight']
                ))

        # 3. Fuse and rank
        ranked = self.fusion_ranker.fuse(entity_recall, fts_recall, vector_recall)

        # 4. Filter by min score and take top_k
        filtered = [r for r in ranked if r.score >= min_score][:top_k]

        # 5. Build final result with full info
        final_hits: List[RetrievalHit] = []
        for r in filtered:
            entity_dict = dict(self.db.get_entity(r.entity_id))
            doc_dict = dict(self.db.get_doc(r.doc_id))
            chunk_dict = dict(self.db.get_chunk(r.chunk_id))
            final_hits.append(RetrievalHit(
                chunk_id=r.chunk_id,
                entity_id=r.entity_id,
                doc_id=r.doc_id,
                entity=entity_dict,
                doc=doc_dict,
                chunk=chunk_dict,
                score=r.score,
                channels=r.channels
            ))

        return RetrievalResult(
            original_query=query_text,
            rewritten_query=processed.rewritten_query,
            hits=final_hits,
            total_found=len(ranked),
            confidence=processed.confidence
        )
