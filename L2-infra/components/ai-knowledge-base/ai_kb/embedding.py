"""
Embedding utilities: text embedding, cosine similarity calculation
"""
import math
import numpy as np
from typing import List, Optional

# Local embedding model (using llama-cpp-python if available)
EMBEDDING_AVAILABLE = False
LLAMA_EMBEDDING = None

try:
    from llama_cpp import Llama
    # Check if model path is configured
    model_path = "~/.node-llama-cpp/models/hf_ggml-org_embeddinggemma-300m-qat-Q8_0.gguf"
    import os
    expanded_path = os.path.expanduser(model_path)
    if os.path.exists(expanded_path):
        LLAMA_EMBEDDING = Llama(
            model_path=expanded_path,
            n_ctx=512,
            embedding=True,
            verbose=False
        )
        EMBEDDING_AVAILABLE = True
except Exception as e:
    print(f"Local embedding not available: {e}")
    pass


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Calculate cosine similarity between two vectors"""
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)


def embed_text(text: str) -> Optional[List[float]]:
    """Embed text using local embedding model"""
    if not EMBEDDING_AVAILABLE or not LLAMA_EMBEDDING:
        return None
    embedding = LLAMA_EMBEDDING.embed(text)
    # Normalize embedding
    norm = np.linalg.norm(embedding)
    if norm > 0:
        embedding = embedding / norm
    return embedding.tolist()
