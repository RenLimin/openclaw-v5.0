"""
Document ingestion pipeline: discovery → parse → quality check → chunk → embed → index → database
"""
import os
import re
import hashlib
import uuid
from typing import List, Dict, Any, Optional, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .db import AIKB
from .parsers import get_parser_for_format, ParsedDocument, get_supported_formats
from .chunker import BaseChunker, SectionChunker, FixedSizeChunker, Chunk
from .quality import check_quality, PIIDetector, QualityCheckResult
from .embedding import embed_text


class IngestionStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class IngestionTask:
    """Represents an ingestion task for a document"""
    task_id: str
    file_path: str
    domain_id: int
    entity_id: Optional[int]
    status: IngestionStatus
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


@dataclass
class IngestionResult:
    """Result of ingesting a single document"""
    success: bool
    doc_id: Optional[int] = None
    chunks_created: int = 0
    quality_score: float = 1.0
    issues: List[str] = field(default_factory=list)
    pii_masked: List[Tuple[str, str]] = field(default_factory=list)
    error: Optional[str] = None


class IngestionPipeline:
    """
    Main ingestion pipeline for documents.
    Steps:
    1. Discover files (scan directory or single file)
    2. Parse each file according to format
    3. Quality check (content length, garbled text, etc.)
    4. PII detection and masking
    5. Chunk document into smaller pieces
    6. Generate embeddings for each chunk
    7. Insert into database and indexes
    """

    def __init__(self,
                 db: AIKB,
                 chunker: Optional[BaseChunker] = None,
                 min_quality_score: float = 0.5,
                 pii_mask_action: str = 'mask',
                 embedding_provider: Optional[Callable[[str], List[float]]] = None):
        self.db = db
        self.chunker = chunker or SectionChunker()
        self.min_quality_score = min_quality_score
        self.pii_mask_action = pii_mask_action
        self.embedding_provider = embedding_provider or embed_text

    def get_file_format(self, file_path: str) -> str:
        """Get file format from extension"""
        ext = Path(file_path).suffix.lower().lstrip('.')
        return ext

    def compute_md5(self, file_path: str) -> str:
        """Compute MD5 hash of file content"""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def ingest_single_file(self,
                           domain_id: int,
                           file_path: str,
                           entity_id: Optional[int] = None,
                           collection_id: Optional[int] = None,
                           entity_type: str = "document",
                           overwrite_existing: bool = True) -> IngestionResult:
        """Ingest a single file through the full pipeline"""

        # 1. Check if file exists
        if not os.path.exists(file_path):
            return IngestionResult(
                success=False,
                error=f"File not found: {file_path}"
            )

        # 2. Check for existing file by MD5 to avoid duplicates
        file_md5 = self.compute_md5(file_path)
        existing_doc = self.db.get_doc_by_md5(file_md5)
        if existing_doc and not overwrite_existing:
            return IngestionResult(
                success=True,
                doc_id=existing_doc['id'],
                chunks_created=0,
                quality_score=1.0,
                issues=["Duplicate file skipped (same MD5)"]
            )

        # If overwriting an existing doc, reuse its entity to avoid duplicate entities
        if existing_doc and entity_id is None:
            entity_id = existing_doc['entity_id']

        # 3. Get parser and parse
        fmt = self.get_file_format(file_path)
        parser = get_parser_for_format(fmt)
        if not parser:
            supported = get_supported_formats()
            return IngestionResult(
                success=False,
                error=f"Unsupported format: {fmt}. Supported formats: {', '.join(supported)}"
            )

        parsed = parser.parse(file_path)

        # 4. Quality check
        quality_result = check_quality(
            parsed.content,
            min_word_count=50,
            min_quality_score=self.min_quality_score
        )

        # 5. PII masking
        pii_detector = PIIDetector()
        masked_content, pii_found = pii_detector.mask(parsed.content, self.pii_mask_action)

        # 6. Chunking
        chunks = self.chunker.chunk(parsed.title, masked_content)

        # 7. Create entity if not exists
        if not entity_id:
            # Create new entity for this document
            entity_name = parsed.title or os.path.basename(file_path)
            entity_code = re.sub(r'[^a-zA-Z0-9-_.]', '_', entity_name.lower())
            # Ensure code uniqueness: append short suffix
            import hashlib as _hashlib
            suffix = _hashlib.md5(file_path.encode()).hexdigest()[:8]
            entity_code = f"{entity_code[:40]}_{suffix}"
            entity_id = self.db.create_entity(
                domain_id=domain_id,
                collection_id=collection_id,
                entity_type=entity_type,
                family=None,
                name=entity_name,
                aliases=None,
                code=entity_code,
                version_latest=None,
                status='active',
                summary=parsed.content[:200]  # First 200 chars as summary
            )

        # 8. Create doc asset
        original_path = os.path.abspath(file_path)
        file_name = os.path.basename(file_path)
        doc_id = self.db.create_doc_asset(
            entity_id=entity_id,
            doc_type="document",
            original_path=original_path,
            relative_path=None,
            file_name=file_name,
            version=None,
            format_=fmt,
            md5=file_md5,
            permissions=None
        )

        # 9. Embed and insert chunks
        chunks_created = 0
        for chunk in chunks:
            # Generate embedding
            embedding = None
            if self.embedding_provider:
                embedding_bytes = None
                try:
                    vec = self.embedding_provider(chunk.text)
                    if vec is None:
                        # Embedding unavailable (e.g. no local model) — index without vector
                        embedding_bytes = None
                    else:
                        # Convert to bytes for SQLite storage
                        import struct
                        embedding_bytes = struct.pack(f'{len(vec)}f', *vec)
                except Exception as e:
                    parsed.parse_errors.append(f"Embedding failed: {str(e)}")
            else:
                embedding_bytes = None

            self.db.create_doc_chunk(
                doc_id=doc_id,
                chunk_index=chunk.index,
                title=chunk.title,
                text=chunk.text,
                embedding=embedding_bytes,
                permissions=None
            )
            chunks_created += 1

        # Collect all issues
        all_issues = quality_result.issues + parsed.parse_errors
        total_quality = quality_result.quality_score * parsed.quality_score
        if not quality_result.is_acceptable:
            all_issues.insert(0, "Quality check failed")

        return IngestionResult(
            success=True,
            doc_id=doc_id,
            chunks_created=chunks_created,
            quality_score=total_quality,
            issues=all_issues,
            pii_masked=pii_found
        )

    def scan_directory(self,
                       domain_id: int,
                       dir_path: str,
                       recursive: bool = True,
                       collection_id: Optional[int] = None,
                       on_result: Optional[Callable[[str, IngestionResult], None]] = None) -> Dict[str, Any]:
        """Scan a directory and ingest all supported files"""
        if not os.path.isdir(dir_path):
            return {
                "success": False,
                "error": f"Not a directory: {dir_path}"
            }

        supported_formats = set(get_supported_formats())
        results: Dict[str, IngestionResult] = {}
        total_files = 0
        success_count = 0
        total_chunks = 0

        # Walk directory
        if recursive:
            for root, _, files in os.walk(dir_path):
                for file_name in files:
                    ext = Path(file_name).suffix.lower().lstrip('.')
                    if ext in supported_formats:
                        file_path = os.path.join(root, file_name)
                        result = self.ingest_single_file(
                            domain_id, file_path, None, collection_id
                        )
                        results[file_path] = result
                        total_files += 1
                        if result.success:
                            success_count += 1
                            total_chunks += result.chunks_created
                        if on_result:
                            on_result(file_path, result)
        else:
            for entry in os.listdir(dir_path):
                file_path = os.path.join(dir_path, entry)
                if not os.path.isfile(file_path):
                    continue
                ext = Path(entry).suffix.lower().lstrip('.')
                if ext in supported_formats:
                    result = self.ingest_single_file(
                        domain_id, file_path, None, collection_id
                    )
                    results[file_path] = result
                    total_files += 1
                    if result.success:
                        success_count += 1
                        total_chunks += result.chunks_created
                    if on_result:
                        on_result(file_path, result)

        return {
            "success": True,
            "total_files": total_files,
            "success_count": success_count,
            "failed_count": total_files - success_count,
            "total_chunks_created": total_chunks,
            "results": results
        }
