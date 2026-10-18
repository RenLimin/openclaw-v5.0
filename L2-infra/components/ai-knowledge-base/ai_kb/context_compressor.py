"""
Context compressor: compress long retrieved contexts to reduce LLM input token
Uses embedding-based relevance scoring to keep only relevant sentences
"""
from typing import List, Dict, Any
import re

from ai_kb.embedding import EmbeddingProvider
from ai_kb.search import HybridSearch


class ContextCompressor:
    """
    Compress retrieval context by keeping only the most relevant sentences.
    Uses embeddings to score each sentence against the original query.
    """

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        max_tokens: int = 1000,
        min_relevance_score: float = 0.2
    ):
        """
        Initialize context compressor.
        Args:
            embedding_provider: embedding provider for relevance scoring
            max_tokens: maximum output tokens (approximate by character count / 4)
            min_relevance_score: minimum score to keep sentence
        """
        self.embedding = embedding_provider
        self.max_tokens = max_tokens
        self.min_score = min_relevance_score

    def compress(
        self,
        query: str,
        results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Compress retrieval results by keeping only relevant sentences.
        Args:
            query: original user query
            results: retrieval results from hybrid search
        Returns:
            compressed results with only relevant sentences
        """
        if self.embedding is None or len(results) == 0:
            return results

        query_emb = self.embedding(query)
        total_chars = 0
        max_chars = self.max_tokens * 4  # approx 4 chars per token
        compressed_results = []

        for result in results:
            snippet = result.get("text", result.get("snippet", ""))
            if not snippet:
                compressed_results.append(result)
                continue

            # Split into sentences
            sentences = re.split(r'(?<=[。！？!?\n])', snippet)
            sentences = [s.strip() for s in sentences if s.strip()]

            if len(sentences) <= 1:
                # Already short enough
                compressed_results.append(result)
                total_chars += len(snippet)
                continue

            # Score each sentence
            scored_sentences = []
            for sentence in sentences:
                try:
                    sent_emb = self.embedding(sentence)
                    similarity = self._cosine_sim(query_emb, sent_emb)
                    if similarity >= self.min_score:
                        scored_sentences.append((similarity, sentence))
                except Exception:
                    # If embedding fails, keep sentence
                    scored_sentences.append((0.5, sentence))

            # Sort by relevance descending
            scored_sentences.sort(reverse=True, key=lambda x: x[0])

            # Keep until we hit max chars
            kept_sentences = []
            current_chars = 0
            for _, sentence in scored_sentences:
                if current_chars + len(sentence) > max_chars and current_chars > 0:
                    break
                kept_sentences.append(sentence)
                current_chars += len(sentence)

            # Reconstruct text from kept sentences (keep original order)
            kept_set = set(kept_sentences)
            compressed_text = " ".join([s for _, s in scored_sentences if s in kept_set])

            # Replace original text with compressed
            compressed_result = result.copy()
            if "text" in compressed_result:
                compressed_result["text"] = compressed_text
            if "snippet" in compressed_result:
                compressed_result["snippet"] = compressed_text
            compressed_results.append(compressed_result)
            total_chars += len(compressed_text)

            if total_chars >= max_chars:
                break

        return compressed_results

    @staticmethod
    def _cosine_sim(a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        dot = sum(x*y for x,y in zip(a,b))
        mag_a = sum(x*x for x in a)**0.5
        mag_b = sum(x*x for x in b)**0.5
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)
