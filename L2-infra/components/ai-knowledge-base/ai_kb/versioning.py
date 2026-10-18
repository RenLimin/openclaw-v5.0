"""
Document version management: full version control for documents
Supports: version history, version comparison, rollback, diff
"""
import difflib
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from ai_kb.db import AIKB
from ai_kb.ingestion import IngestionPipeline


@dataclass
class VersionInfo:
    version: str
    doc_id: int
    md5: str
    created_at: str
    comment: Optional[str]
    changelog: Optional[str]


@dataclass
class DiffResult:
    old_version: str
    new_version: str
    diff_text: str
    added_lines: int
    removed_lines: int


class VersionManager:
    """
    Manage document versions.
    Each document change creates a new version, keeps history.
    Supports rollback to any previous version and diff between versions.
    """

    def __init__(self, db: AIKB, pipeline: IngestionPipeline):
        self.db = db
        self.pipeline = pipeline
        self._ensure_version_table()

    def _ensure_version_table(self):
        """Create doc_version table if missing"""
        self.db.execute("""
        CREATE TABLE IF NOT EXISTS doc_version (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id INTEGER NOT NULL,
            version TEXT NOT NULL,
            md5 TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            created_at DATETIME NOT NULL,
            comment TEXT,
            changelog TEXT,
            FOREIGN KEY (doc_id) REFERENCES doc_asset (id)
        )
        """)
        self.db.commit()

    def create_new_version(
        self,
        entity_id: int,
        file_path: str,
        current_doc_id: Optional[int] = None,
        comment: Optional[str] = None
    ) -> VersionInfo:
        """
        Create a new version of a document.
        If current_doc_id is None, this is the first version.
        """
        # Calculate md5 of file content
        md5 = self._file_md5(file_path)
        content = open(file_path, 'rb').read()
        content_hash = hashlib.sha256(content).hexdigest()
        content_text = content.decode('utf-8', errors='replace')
        now = self.db.get_now()

        # Ingest new document
        # FIXME: we need to update the entity, but keep old doc as previous version
        # For now, create new doc_asset, keep the old one with versioned name
        filename = os.path.basename(file_path)
        version = self._next_version(current_doc_id)
        doc_id = self.pipeline.ingest_single_file(
            entity_id=entity_id,
            file_path=file_path
        )

        # Record version
        cursor = self.db.execute("""
        INSERT INTO doc_version (
            doc_id, version, md5, content_hash, created_at, comment, changelog
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            doc_id, version, md5, content_hash, now, comment, None
        ))
        self.db.commit()

        return VersionInfo(
            version=version,
            doc_id=doc_id,
            md5=md5,
            created_at=now,
            comment=comment,
            changelog=None
        )

    def list_versions(self, doc_id: int) -> List[VersionInfo]:
        """List all versions of a document ordered by version descending"""
        rows = self.db.execute("""
        SELECT * FROM doc_version WHERE doc_id = ? ORDER BY version DESC
        """, (doc_id,)).fetchall()
        versions = []
        for row in rows:
            versions.append(VersionInfo(
                version=row['version'],
                doc_id=row['doc_id'],
                md5=row['md5'],
                created_at=row['created_at'],
                comment=row['comment'],
                changelog=row['changelog']
            ))
        return versions

    def get_version(self, doc_id: int, version: str) -> Optional[VersionInfo]:
        """Get specific version info"""
        row = self.db.execute("""
        SELECT * FROM doc_version WHERE doc_id = ? AND version = ?
        """, (doc_id, version)).fetchone()
        if not row:
            return None
        return VersionInfo(
            version=row['version'],
            doc_id=row['doc_id'],
            md5=row['md5'],
            created_at=row['created_at'],
            comment=row['comment'],
            changelog=row['changelog']
        )

    def diff(
        self,
        doc_id: int,
        old_version: str,
        new_version: str
    ) -> Optional[DiffResult]:
        """Get diff between two versions"""
        v_old = self.get_version(doc_id, old_version)
        v_new = self.get_version(doc_id, new_version)
        if not v_old or not v_new:
            return None

        # Get content for both versions
        # FIXME: we need to get content from original file storage
        # For now, assume doc_id is the versioned doc (this needs improvement)
        # For now, get the text from chunks
        old_text = self._get_doc_text(v_old.doc_id)
        new_text = self._get_doc_text(v_new.doc_id)

        # Generate diff
        diff = difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile=old_version,
            tofile=new_version,
            lineterm=''
        )
        diff_lines = list(diff)
        diff_text = '\n'.join(diff_lines)

        # Count added/removed
        added = sum(1 for line in diff_lines if line.startswith('+'))
        removed = sum(1 for line in diff_lines if line.startswith('-'))

        return DiffResult(
            old_version=old_version,
            new_version=new_version,
            diff_text=diff_text,
            added_lines=added,
            removed_lines=removed
        )

    def rollback(
        self,
        doc_id: int,
        target_version: str
    ) -> Optional[bool]:
        """Rollback document to target version"""
        # TODO: implement full rollback
        # This needs restoring content and creating a new rollback version
        return None

    def _file_md5(self, path: str) -> str:
        """Calculate md5 hash of file"""
        hash_md5 = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def _next_version(self, current_doc_id: Optional[int]) -> str:
        """Generate next version number (semver: increment patch)"""
        if current_doc_id is None:
            return "1.0.0"
        versions = self.list_versions(current_doc_id)
        if not versions:
            return "1.0.0"
        latest = versions[0]
        # Parse semver and increment patch
        parts = latest.version.split('.')
        if len(parts) != 3:
            return f"{latest.version}.1"
        try:
            major = int(parts[0])
            minor = int(parts[1])
            patch = int(parts[2])
            return f"{major}.{minor}.{patch + 1}"
        except ValueError:
            return f"{latest.version}.1"

    def _get_doc_text(self, doc_id: int) -> str:
        """Get full text of a document from chunks"""
        chunks = self.db.get_chunks_by_doc(doc_id, limit=1000)
        texts = [c['text'] for c in chunks]
        return '\n\n'.join(texts)
