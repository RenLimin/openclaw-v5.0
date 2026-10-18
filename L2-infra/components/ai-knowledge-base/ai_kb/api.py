"""
Standardized API interface for L2 AI KB
Supports MCP (Model Context Protocol) and REST-style access
Usable by any AI Agent through standard tool calls
"""
import json
import os
from typing import List, Dict, Optional, Tuple
from .db import AIKB
from .search import HybridSearch
from .graphrag import GraphRAG
from .permissions import PermissionChecker
from .answer import format_answer_with_sources, render_markdown_answer
from .retrieval import RetrievalEngine


class AIKBService:
    """
    Standardized AI Knowledge Base service interface.
    
    Designed for multi-Agent sharing: every Agent can instantiate
    this service against its own domain, with proper permissions.
    
    API methods return structured dicts that are easy to serialize
    for MCP tools, REST endpoints, or CLI.
    """

    def __init__(self, db_path: str, domain_code: str, embedding_func=None, user_attrs=None, include_expired=False):
        self.db_path = db_path
        self.domain_code = domain_code
        self.kb = AIKB(db_path)
        self.kb.connect()
        self.domain_id = self._get_domain_id()
        self.search = HybridSearch(self.kb, self.domain_id, include_expired=include_expired)
        self.graph = GraphRAG(self.kb)
        self.perms = PermissionChecker(self.kb)
        self.user_attrs = user_attrs or {'role': 'viewer', 'clearance': 'internal'}
        self.retrieval_engine = RetrievalEngine(
            self.kb,
            self.domain_id,
            include_expired=include_expired,
            permission_checker=self.perms
        )

    def _get_domain_id(self) -> int:
        row = self.kb.execute("SELECT id FROM domain WHERE code = ?", (self.domain_code,)).fetchone()
        if not row:
            raise ValueError(f"Domain not found: {self.domain_code}")
        return row['id']

    def close(self):
        self.kb.close()

    # === Core Query API ===

    def query(self, question: str, top_k: int = 5, use_graph: bool = False,
              start_entity: Optional[str] = None, format: str = 'json', include_expired: bool = False) -> Dict:
        """
        Query the knowledge base and return answers WITH source references.
        Source attribution is MANDATORY — no answer without traceable sources.
        
        Args:
            question: The question to answer
            top_k: Number of top results to return
            use_graph: Whether to use GraphRAG enhanced search
            start_entity: Starting entity name for graph expansion
            format: 'json' (structured) or 'markdown' (human-readable)
            include_expired: Whether to include expired entities in results
        
        Returns:
            Dict with answer + sources + confidence
        """
        if use_graph and start_entity:
            results = self.graph.graph_enhanced_search(
                self.domain_id, question, start_entity, top_k=top_k, include_expired=include_expired
            )
        else:
            if include_expired != self.search.include_expired:
                # Rebuild search with requested expired setting
                self.search = HybridSearch(self.kb, self.domain_id, include_expired=include_expired)
            results = self.search.search(question, top_k=top_k)

        # Enforce permissions
        results = self.perms.filter_results_by_permissions(results, self.user_attrs)

        # Format with mandatory source attribution
        answer = format_answer_with_sources(question, results)

        if format == 'markdown':
            answer['markdown'] = render_markdown_answer(answer)

        return answer

    # === Feedback API ===

    def add_feedback(self, query_text: str, feedback_type: str, answer_text: str = None,
                     feedback_comment: str = None, entity_id: int = None, doc_id: int = None,
                     chunk_id: int = None, user_id: str = None) -> Dict:
        """
        Add user feedback for a query/answer.
        
        feedback_type: 'useful' / 'not_useful' / 'incorrect'
        """
        feedback_id = self.kb.add_feedback(
            query_text, feedback_type, answer_text, feedback_comment,
            entity_id, doc_id, chunk_id, user_id
        )
        return {
            'feedback_id': feedback_id,
            'status': 'success'
        }

    def get_entity_feedback_stats(self, entity_id: int) -> Dict:
        """Get feedback statistics for a specific entity"""
        stats = self.kb.get_feedback_stats_for_entity(entity_id)
        total = sum(stats.values())
        return {
            'entity_id': entity_id,
            'stats': stats,
            'total': total
        }

    def get_doc_feedback_stats(self, doc_id: int) -> Dict:
        """Get feedback statistics for a specific document"""
        stats = self.kb.get_feedback_stats_for_doc(doc_id)
        total = sum(stats.values())
        return {
            'doc_id': doc_id,
            'stats': stats,
            'total': total
        }

    def list_low_score_knowledge(self, threshold: int = 1) -> List[Dict]:
        """
        List entities in current domain that have more than threshold negative feedback.
        Negative feedback: 'not_useful' or 'incorrect'
        """
        rows = self.kb.list_low_score_knowledge(self.domain_id, threshold)
        return [dict(row) for row in rows]

    # === Management API ===

    def list_entities(self, collection_id: Optional[int] = None,
                      status: Optional[str] = None) -> List[Dict]:
        """List entities in the domain"""
        if collection_id:
            rows = self.kb.list_entities_by_collection(collection_id, status)
        else:
            if status:
                rows = self.kb.execute(
                    "SELECT * FROM entity WHERE domain_id = ? AND status = ? ORDER BY name",
                    (self.domain_id, status)
                ).fetchall()
            else:
                rows = self.kb.execute(
                    "SELECT * FROM entity WHERE domain_id = ? AND (status IS NULL OR status != 'expired') ORDER BY name",
                    (self.domain_id,)
                ).fetchall()
        return [dict(r) for r in rows]

    def get_entity(self, entity_id: int) -> Optional[Dict]:
        """Get entity detail by ID"""
        row = self.kb.get_entity(entity_id)
        return dict(row) if row else None

    def get_entity_docs(self, entity_id: int) -> List[Dict]:
        """Get all documents for an entity"""
        rows = self.kb.get_docs_by_entity(entity_id)
        return [dict(r) for r in rows]

    def add_relation(self, subject_id: int, relation_type: str,
                     object_id: int, subject_type: str = 'entity',
                     object_type: str = 'entity', metadata: Optional[str] = None) -> int:
        """Add a knowledge graph relation"""
        return self.graph.add_relation(
            subject_type, subject_id, relation_type, object_type, object_id, metadata
        )

    def batch_update_entity_status(self, entity_ids: List[int], status: str) -> Dict:
        """
        Batch update entity status (mark as expired/active/archived).
        Returns count of updated entities.
        """
        updated = 0
        for entity_id in entity_ids:
            self.kb.update_entity(entity_id, status=status)
            updated += 1
        return {
            'updated_count': updated,
            'status': 'success'
        }

    def mark_entity_expired(self, entity_id: int) -> Dict:
        """Mark a single entity as expired (soft下架)"""
        self.kb.update_entity(entity_id, status='expired')
        return {
            'entity_id': entity_id,
            'status': 'expired',
            'result': 'success'
        }

    def stats(self, include_expired: bool = False) -> Dict:
        """Get knowledge base statistics"""
        return {
            'domain_code': self.domain_code,
            'domain_id': self.domain_id,
            'entities': self.kb.count_entities(self.domain_id, include_expired),
            'documents': self.kb.count_docs(self.domain_id),
            'chunks': self.kb.count_chunks(self.domain_id),
        }

    # === MCP Tool Descriptors (for MCP server integration) ===

    @staticmethod
    def mcp_tools() -> List[Dict]:
        """
        Return MCP tool descriptors for all available KB operations.
        Can be directly registered with an MCP server.
        """
        return [
            {
                "name": "kb_query",
                "description": "Query the AI knowledge base. Returns answer with source references (mandatory).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "Your question"},
                        "top_k": {"type": "integer", "description": "Number of results", "default": 5},
                        "use_graph": {"type": "boolean", "description": "Use GraphRAG enhanced search", "default": False},
                        "start_entity": {"type": "string", "description": "Start entity for graph expansion"},
                        "format": {"type": "string", "enum": ["json", "markdown"], "default": "markdown"},
                        "include_expired": {"type": "boolean", "description": "Include expired entities in results", "default": False}
                    },
                    "required": ["question"]
                }
            },
            {
                "name": "kb_add_feedback",
                "description": "Add user feedback for a query/answer to help improve knowledge base quality.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query_text": {"type": "string", "description": "Original query text"},
                        "feedback_type": {"type": "string", "enum": ["useful", "not_useful", "incorrect"], "description": "Feedback type"},
                        "answer_text": {"type": "string", "description": "The answer that was given to the user"},
                        "feedback_comment": {"type": "string", "description": "Optional user comment about why this feedback"},
                        "entity_id": {"type": "integer", "description": "Associated entity ID (if any)"},
                        "doc_id": {"type": "integer", "description": "Associated document ID (if any)"},
                        "chunk_id": {"type": "integer", "description": "Associated chunk ID (if any)"},
                        "user_id": {"type": "string", "description": "User ID of the person giving feedback"}
                    },
                    "required": ["query_text", "feedback_type"]
                }
            },
            {
                "name": "kb_get_entity_feedback_stats",
                "description": "Get feedback statistics for a specific entity",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "integer", "description": "Entity ID"}
                    },
                    "required": ["entity_id"]
                }
            },
            {
                "name": "kb_list_low_score_knowledge",
                "description": "List entities that have more than threshold negative feedback (not_useful/incorrect)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "threshold": {"type": "integer", "description": "Minimum negative feedback count", "default": 1}
                    }
                }
            },
            {
                "name": "kb_list_entities",
                "description": "List all entities in the knowledge base domain",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "collection_id": {"type": "integer", "description": "Filter by collection ID"},
                        "status": {"type": "string", "description": "Filter by entity status (e.g. 'active', 'expired')"}
                    }
                }
            },
            {
                "name": "kb_get_entity",
                "description": "Get detailed info about a specific entity",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "integer", "description": "Entity ID"}
                    },
                    "required": ["entity_id"]
                }
            },
            {
                "name": "kb_batch_update_entity_status",
                "description": "Batch update entity status (mark as expired/active/archived)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "List of entity IDs to update"
                        },
                        "status": {"type": "string", "description": "New status value (e.g. 'expired', 'active')"}
                    },
                    "required": ["entity_ids", "status"]
                }
            },
            {
                "name": "kb_mark_entity_expired",
                "description": "Mark a single entity as expired (soft下架)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "integer", "description": "Entity ID to mark as expired"}
                    },
                    "required": ["entity_id"]
                }
            },
            {
                "name": "kb_stats",
                "description": "Get knowledge base statistics (entity count, document count, etc.)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "include_expired": {"type": "boolean", "description": "Include expired entities in statistics", "default": False}
                    }
                }
            }
        ]
