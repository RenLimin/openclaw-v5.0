"""
CrossEncoder reranking for retrieval results
Re-ranks top-K candidates based on query-document relevance
"""
from typing import List, Dict, Any, Optional
import numpy as np

from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch


class CrossEncoderReranker:
    """
    CrossEncoder-based re-ranker for retrieval results.
    Uses a pre-trained cross-encoder model to score query-document relevance.
    Falls back to original ranking if model not available.
    """

    DEFAULT_MODEL = "BAAI/bge-reranker-base"

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: Optional[str] = None,
        use_gpu: bool = True,
        batch_size: int = 32
    ):
        """
        Initialize cross-encoder reranker.
        Args:
            model_name: HuggingFace model name
            device: device to use ("cpu"/"cuda"/"mps")
            use_gpu: whether to use GPU if available
            batch_size: inference batch size
        """
        self.model_name = model_name
        self.batch_size = batch_size
        self._device = device
        self._use_gpu = use_gpu
        self._tokenizer = None
        self._model = None

    @property
    def tokenizer(self):
        if self._tokenizer is None:
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        return self._tokenizer

    @property
    def model(self):
        if self._model is None:
            self._model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
            device = self._device
            if device is None:
                if self._use_gpu and torch.cuda.is_available():
                    device = "cuda"
                elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                    device = "mps"
                else:
                    device = "cpu"
            self._model.to(device)
        return self._model

    def rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Re-rank retrieval results by query-document relevance.
        Args:
            query: original user query
            results: retrieval results from hybrid search, each has "snippet"/"similarity" etc
            top_k: number of results to return after reranking (None = all)
        Returns:
            re-ranked results with updated "rerank_score"
        """
        if len(results) == 0:
            return results

        try:
            # Prepare pairs for cross-encoder
            pairs = [
                (query, result.get("snippet", result.get("text", "")))
                for result in results
            ]

            scores = self._score_pairs(pairs)

            # Attach scores and sort
            for i, score in enumerate(scores):
                results[i]["rerank_score"] = score

            # Sort descending by rerank score
            results.sort(key=lambda r: r.get("rerank_score", 0), reverse=True)

            if top_k is not None and len(results) > top_k:
                results = results[:top_k]

            return results

        except Exception:
            # If anything fails, return original order
            return results

    def _score_pairs(self, pairs: List[Tuple[str, str]]) -> List[float]:
        """Score all pairs in batches"""
        scores = []
        n_pairs = len(pairs)

        with torch.no_grad():
            for i in range(0, n_pairs, self.batch_size):
                batch = pairs[i:i+self.batch_size]
                inputs = self.tokenizer(
                    batch,
                    truncation=True,
                    padding=True,
                    return_tensors="pt",
                    max_length=512
                )
                inputs = {k: v.to(self.model.device) for k, v in inputs.items()}
                outputs = self.model(**inputs)
                batch_scores = outputs.logits.squeeze().cpu().numpy()
                if len(batch_scores.shape) == 0:
                    # Single pair
                    batch_scores = np.array([batch_scores])
                scores.extend(batch_scores.tolist())

        return scores
