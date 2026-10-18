"""
Base dialect interface for database abstraction
All database dialects must implement this interface
Supports SQLite and PostgreSQL (and others can be added)
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Tuple, Any, Dict


class BaseDialect(ABC):
    """Base interface for database dialects"""

    @abstractmethod
    def connect(self, **kwargs):
        """Connect to database"""
        pass

    @abstractmethod
    def close(self):
        """Close connection"""
        pass

    @abstractmethod
    def execute(self, sql: str, params: Tuple = ()):
        """Execute SQL"""
        pass

    @abstractmethod
    def commit(self):
        """Commit transaction"""
        pass

    @abstractmethod
    def get_now(self) -> str:
        """Get current timestamp as ISO string"""
        pass

    @abstractmethod
    def init_tables(self):
        """Initialize all required tables"""
        pass

    # --- Domain operations ---
    @abstractmethod
    def get_or_create_domain(self, name: str, code: str, description: Optional[str] = None) -> int:
        pass

    @abstractmethod
    def list_domains(self) -> List[Dict[str, Any]]:
        pass

    # --- Collections ---
    @abstractmethod
    def get_or_create_collection(self, domain_id: int, name: str, parent_id: Optional[int] = None) -> int:
        pass

    @abstractmethod
    def list_collections(self, domain_id: int) -> List[Dict[str, Any]]:
        pass

    # --- Entity operations ---
    @abstractmethod
    def get_or_create_entity(
        self,
        domain_id: int,
        entity_type: str,
        name: str,
        code: Optional[str] = None,
        aliases: Optional[List[str]] = None,
        collection_id: Optional[int] = None
    ) -> int:
        pass

    @abstractmethod
    def get_entity_by_id(self, entity_id: int) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def find_entities_by_name(
        self,
        domain_id: int,
        name: str,
        limit: int = 10,
        include_expired: bool = False
    ) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def update_entity_status(self, entity_id: int, status: str) -> bool:
        pass

    @abstractmethod
    def list_entities(
        self,
        domain_id: int,
        collection_id: Optional[int] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def count_entities(self, domain_id: Optional[int], include_expired: bool = False) -> int:
        pass

    # --- Document operations ---
    @abstractmethod
    def create_doc_asset(
        self,
        entity_id: int,
        doc_type: str,
        original_path: str,
        relative_path: Optional[str],
        file_name: str,
        version: Optional[str],
        format_: str,
        md5: str,
        permissions: Optional[str] = None
    ) -> int:
        pass

    @abstractmethod
    def get_doc_by_id(self, doc_id: int) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def list_docs_for_entity(self, entity_id: int) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def count_docs(self, domain_id: Optional[int]) -> int:
        pass

    # --- Chunk operations ---
    @abstractmethod
    def create_doc_chunk(
        self,
        doc_id: int,
        chunk_index: int,
        title: Optional[str],
        text: str,
        embedding: Optional[bytes],
        permissions: Optional[str] = None
    ) -> int:
        pass

    @abstractmethod
    def get_chunks_for_doc(self, doc_id: int) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def count_chunks(self, domain_id: Optional[int]) -> int:
        pass

    # --- Relations ---
    @abstractmethod
    def add_relation(
        self,
        subject_type: str,
        subject_id: int,
        relation_type: str,
        object_type: str,
        object_id: int,
        confidence: float = 1.0,
        metadata: Optional[str] = None
    ) -> int:
        pass

    @abstractmethod
    def count_entity_relations(self, entity_id: int) -> int:
        pass

    # --- Feedback ---
    @abstractmethod
    def add_feedback(
        self,
        domain_id: int,
        query_text: str,
        feedback_type: str,
        answer_text: Optional[str],
        entity_id: Optional[int],
        doc_id: Optional[int],
        chunk_id: Optional[int],
        user_id: Optional[str],
        comment: Optional[str]
    ) -> int:
        pass

    @abstractmethod
    def get_feedback_stats_for_entity(self, entity_id: int) -> Dict[str, int]:
        pass

    @abstractmethod
    def get_feedback_stats_for_doc(self, doc_id: int) -> Dict[str, int]:
        pass

    # --- Template ---
    @abstractmethod
    def save_template(
        self,
        template_id: str,
        name: str,
        version: str,
        description: Optional[str],
        author: Optional[str],
        category: Optional[str],
        config_yaml: str
    ) -> int:
        pass

    @abstractmethod
    def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        pass

    # --- Audit ---
    @abstractmethod
    def add_audit_log(
        self,
        operation_type: str,
        user_id: Optional[str],
        object_type: Optional[str],
        object_id: Optional[int],
        request_id: Optional[str],
        risk_level: Optional[str],
        rule_triggered: Optional[str],
        action_taken: Optional[str],
        details: Optional[str]
    ) -> int:
        pass

    # --- Migration ---
    @abstractmethod
    def get_current_migration_version(self) -> int:
        pass

    @abstractmethod
    def apply_migration(self, version: int, name: str):
        pass
