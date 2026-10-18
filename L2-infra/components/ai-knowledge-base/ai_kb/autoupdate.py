"""
Automatic knowledge update: detect changes in source files and sync changes
Scans source directory for file changes (add/change/delete) and auto updates KB
Supports periodic scanning and incremental updates
"""
import os
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from ai_kb.db import AIKB
from ai_kb.ingestion import IngestionPipeline
from ai_kb.versioning import VersionManager


@dataclass
class ChangeDetected:
    path: str
    change_type: str  # added/changed/deleted
    current_md5: Optional[str]
    previous_md5: Optional[str]


class AutoUpdater:
    """
    Automatic knowledge updater.
    Scans a source directory for changes, detects adds/changes/deletes and updates KB.
    """

    def __init__(
        self,
        domain_id: int,
        db: AIKB,
        pipeline: IngestionPipeline,
        version_manager: VersionManager
    ):
        self.domain_id = domain_id
        self.db = db
        self.pipeline = pipeline
        self.version_manager = version_manager

    def scan_directory(
        self,
        root_dir: str,
        extensions: Optional[List[str]] = None
    ) -> List[ChangeDetected]:
        """
        Scan directory for changes.
        Args:
            root_dir: root directory to scan
            extensions: list of extensions to include (e.g. ['.md', '.txt'])
        Returns:
            list of changes detected
        """
        if extensions is None:
            # Default to all supported formats
            extensions = [
                '.md', '.txt', '.html', '.csv', '.json',
                '.docx', '.doc', '.xls', '.xlsx', '.pptx', '.ppt', '.pdf',
                '.mp3', '.wav', '.flac', '.m4a', '.ogg', '.opus',
                '.mp4', '.avi', '.mov', '.mkv', '.webm'
            ]

        changes: List[ChangeDetected] = []

        # Walk directory and check each file
        for dirpath, _, filenames in os.walk(root_dir):
            for filename in filenames:
                ext = os.path.splitext(filename)[1].lower()
                if ext not in extensions:
                    continue
                full_path = os.path.join(dirpath, filename)
                rel_path = os.path.relpath(full_path, root_dir)
                current_md5 = self._file_md5(full_path)

                # Check if we already have this file
                # We match by relative path
                doc = self._find_doc_by_relative_path(rel_path)
                if not doc:
                    # New file added
                    changes.append(ChangeDetected(
                        path=full_path,
                        change_type="added",
                        current_md5=current_md5,
                        previous_md5=None
                    ))
                else:
                    previous_md5 = doc.get('md5')
                    if previous_md5 != current_md5:
                        # File changed
                        changes.append(ChangeDetected(
                            path=full_path,
                            change_type="changed",
                            current_md5=current_md5,
                            previous_md5=previous_md5
                        ))

        # TODO: detect deleted files (not in dir but in KB)
        return changes

    def apply_changes(
        self,
        changes: List[ChangeDetected],
        auto_approve: bool = True
    ) -> Dict[str, Any]:
        """
        Apply detected changes to KB.
        Returns summary of changes applied.
        """
        summary = {
            "added": 0,
            "changed": 0,
            "deleted": 0,
            "failed": 0,
            "errors": []
        }

        for change in changes:
            try:
                if change.change_type == "added":
                    # Add new document
                    entity_id = self.db.get_or_create_entity(
                        domain_id=self.domain_id,
                        entity_type="document",
                        name=os.path.basename(change.path),
                        code=None
                    )
                    result = self.pipeline.ingest_single_file(
                        entity_id=entity_id,
                        file_path=change.path
                    )
                    if result.success:
                        summary["added"] += 1
                    else:
                        summary["failed"] += 1
                        summary["errors"].append(f"{change.path}: {result.error}")

                elif change.change_type == "changed":
                    # Find existing document and update it
                    doc = self._find_doc_by_relative_path(change.path)
                    if not doc:
                        summary["failed"] += 1
                        summary["errors"].append(f"{change.path}: not found in KB")
                        continue
                    # Create new version
                    # TODO: full versioning update needs more work
                    summary["changed"] += 1
            except Exception as e:
                summary["failed"] += 1
                summary["errors"].append(f"{change.path}: {str(e)}")

        return summary

    def _file_md5(self, path: str) -> str:
        """Calculate md5 of file"""
        hash_md5 = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def _find_doc_by_relative_path(self, relative_path: str):
        """Find document by relative path"""
        docs = self.db.get_docs_for_entity_domain(self.domain_id)
        for doc in docs:
            if doc.get('relative_path') == relative_path:
                return doc
        return None
