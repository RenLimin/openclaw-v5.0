"""
Indexing module: document chunking, embedding generation
"""
import os
import re
import math
import numpy as np
from typing import List, Dict, Optional, Tuple
from .db import ProductKBDB
from .io import TextExtractor


class DocumentChunker:
    def __init__(self, min_chunk_size: int = 300, max_chunk_size: int = 1000):
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size

    def chunk_text(self, text: str, doc_title: str = None) -> List[Tuple[Optional[str], str]]:
        """Split text into chunks by heading, keep chunk size within range"""
        # Split by heading patterns
        # Heading: starts with #, or 数字.  or 一、二、 etc.
        heading_pattern = re.compile(r'^(?:#+\s+|[\d\.]+\s+|[\u4e00-\u9fa5]{1,2}、)', re.MULTILINE)
        splits = heading_pattern.split(text)
        chunks = []

        current_chunk = []
        current_size = 0
        current_title = doc_title

        for part in splits:
            if not part.strip():
                continue
            lines = part.split('\n')
            for line in lines:
                line = line.rstrip()
                if not line.strip():
                    continue
                line_len = len(line)
                if current_size + line_len > self.max_chunk_size and current_size >= self.min_chunk_size:
                    # Flush current chunk
                    chunks.append((current_title, '\n'.join(current_chunk)))
                    current_chunk = [line]
                    current_size = line_len
                else:
                    current_chunk.append(line)
                    current_size += line_len
            # Check if this is a new heading
            if heading_pattern.match(part):
                # New heading, flush current
                if current_chunk:
                    chunks.append((current_title, '\n'.join(current_chunk)))
                current_title = part.strip()
                current_chunk = []
                current_size = 0

        # Flush remaining
        if current_chunk:
            chunks.append((current_title, '\n'.join(current_chunk)))

        # Merge small chunks
        merged = []
        merged_current = []
        merged_size = 0
        merged_title = None
        for title, chunk in chunks:
            chunk_len = len(chunk)
            if merged_size + chunk_len < self.min_chunk_size and merged_current:
                merged_current.append(chunk)
                merged_size += chunk_len
                if not merged_title:
                    merged_title = title
            else:
                if merged_current:
                    merged.append((merged_title or title, '\n'.join(merged_current)))
                merged_current = [chunk]
                merged_size = chunk_len
                merged_title = title
        if merged_current:
            merged.append((merged_title, '\n'.join(merged_current)))

        return merged

    def process_document(self, db: ProductKBDB, doc_id: int, text: str, doc_title: str = None):
        """Chunk document and store chunks with embeddings"""
        # Delete old chunks
        db.delete_doc_chunks(doc_id)

        chunks = self.chunk_text(text, doc_title)
        for i, (title, chunk_text) in enumerate(chunks):
            embedding = None
            try:
                embed_vec = get_embedding(chunk_text)
                embedding = np.array(embed_vec).tobytes()
            except Exception as e:
                print(f"Failed to get embedding for chunk {i} doc {doc_id}: {e}")

            db.create_doc_chunk(doc_id, i, title, chunk_text, embedding)
