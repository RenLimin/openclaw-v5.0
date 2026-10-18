"""
Semantic chunker: split document into chunks based on semantic similarity
Use embedding similarity to detect natural paragraph boundaries
"""
from typing import List, Tuple
import re

from ai_kb.embedding import EmbeddingProvider


class SemanticChunker:
    """
    Semantic chunker that splits text into chunks based on embedding similarity.
    Detects natural topic boundaries by comparing similarity between adjacent sentences.
    If embedding provider is not available, falls back to simple sentence splitting.
    """

    def __init__(
        self,
        embedding_provider: EmbeddingProvider = None,
        similarity_threshold: float = 0.7,
        min_chunk_size: int = 100,
        max_chunk_size: int = 1000,
        buffer_size: int = 3
    ):
        """
        Initialize semantic chunker.
        Args:
            embedding_provider: embedding provider for similarity calculation
            similarity_threshold: threshold for boundary detection (lower = more splits)
            min_chunk_size: minimum chars per chunk
            max_chunk_size: maximum chars per chunk
            buffer_size: number of sentences to keep as overlap buffer
        """
        self.embedding = embedding_provider
        self.threshold = similarity_threshold
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.buffer_size = buffer_size

    def split(self, text: str) -> List[str]:
        """Split text into semantic chunks"""
        if self.embedding is None or len(text) < self.min_chunk_size:
            # Fallback: simple paragraph splitting
            return self._fallback_split(text)

        sentences = self._split_sentences(text)
        if len(sentences) <= 1:
            return [text]

        # Calculate similarity between adjacent sentences
        chunks = []
        current_chunk = [sentences[0]]
        current_len = len(sentences[0])

        for i in range(1, len(sentences)):
            prev_sent = sentences[i-1]
            curr_sent = sentences[i]

            # Get embeddings
            try:
                emb_prev = self.embedding(prev_sent)
                emb_curr = self.embedding(curr_sent)
                similarity = self._cosine_sim(emb_prev, emb_curr)
            except Exception:
                # If embedding fails, use fixed threshold of 0.5 (average)
                similarity = 0.5

            # Check if boundary: similarity < threshold OR current chunk too big
            if similarity < self.threshold or current_len + len(curr_sent) > self.max_chunk_size:
                # Start new chunk, keep overlap from previous
                chunk_text = " ".join(current_chunk)
                chunks.append(chunk_text)
                # Keep last N sentences as overlap
                overlap_start = max(0, len(current_chunk) - self.buffer_size)
                current_chunk = current_chunk[overlap_start:]
                current_chunk = current_chunk + [curr_sent]
            else:
                current_chunk.append(curr_sent)

            current_len = sum(len(s) for s in current_chunk)

        # Add the last chunk
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            chunks.append(chunk_text)

        # If all splits resulted in tiny chunks, merge to meet min size
        chunks = self._merge_small_chunks(chunks)
        return chunks

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences"""
        # Split on common sentence endings
        sentences = re.split(r'(?<=[。！？!?\n])', text.strip())
        sentences = [s.strip() for s in sentences if s.strip()]
        return sentences

    def _fallback_split(self, text: str) -> List[str]:
        """Fallback when embedding is not available: paragraph splitting"""
        paragraphs = re.split(r'\n\s*\n', text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        # Merge small paragraphs
        merged = []
        current = []
        current_len = 0
        for p in paragraphs:
            if current_len + len(p) > self.max_chunk_size and current_len >= self.min_chunk_size:
                merged.append("\n\n".join(current))
                current = [p]
                current_len = len(p)
            else:
                current.append(p)
                current_len += len(p)
        if current:
            merged.append("\n\n".join(current))
        return merged

    def _merge_small_chunks(self, chunks: List[str]) -> List[str]:
        """Merge chunks smaller than min_chunk_size"""
        merged = []
        current = []
        current_len = 0
        for chunk in chunks:
            chunk_len = len(chunk)
            if current_len + chunk_len > self.max_chunk_size and current_len >= self.min_chunk_size:
                merged.append("".join(current))
                current = [chunk]
                current_len = chunk_len
            else:
                current.append(chunk)
                current_len += chunk_len
        if current:
            merged.append("".join(current))
        return merged

    @staticmethod
    def _cosine_sim(a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        dot = sum(x*y for x,y in zip(a,b))
        mag_a = sum(x*x for x in a)**0.5
        mag_b = sum(x*x for x in b)**0.5
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)
