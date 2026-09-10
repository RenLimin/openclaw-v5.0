"""向量化接口 — 抽象基类 + 多种实现。"""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from typing import Any


class Embedder(ABC):
    """向量化器抽象基类。"""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """向量维度。"""
        ...

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """将单条文本向量化。"""
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量向量化。默认逐次调用，子类可覆盖优化。"""
        return [self.embed(t) for t in texts]

    @staticmethod
    def normalize(vec: list[float]) -> list[float]:
        """L2 归一化。"""
        norm = math.sqrt(sum(x * x for x in vec))
        if norm == 0:
            return vec
        return [x / norm for x in vec]


class MockEmbedder(Embedder):
    """Mock 向量化器 — 用于测试，不依赖真实模型。

    使用基于文本哈希的伪随机向量，保证相同文本得到相同向量，
    且语义相似的文本（有较多相同词）向量相似度更高。
    """

    def __init__(self, dimension: int = 128):
        self._dimension = dimension
        # 词向量缓存
        self._word_cache: dict[str, list[float]] = {}

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, text: str) -> list[float]:
        """基于词袋 + 哈希的伪向量，相似文本相似度高。"""
        words = self._tokenize(text)
        if not words:
            return [0.0] * self._dimension

        vec = [0.0] * self._dimension
        total = 0
        for word in words:
            word_vec = self._get_word_vector(word)
            for i in range(self._dimension):
                vec[i] += word_vec[i]
            total += 1

        if total > 0:
            vec = [v / total for v in vec]

        return self.normalize(vec)

    def _tokenize(self, text: str) -> list[str]:
        """简单分词：中文按字，英文按词。"""
        tokens: list[str] = []
        # 英文单词
        for m in re.finditer(r'[a-zA-Z]+', text):
            tokens.append(m.group().lower())
        # 中文字符
        for ch in text:
            if '\u4e00' <= ch <= '\u9fff':
                tokens.append(ch)
        return tokens

    def _get_word_vector(self, word: str) -> list[float]:
        """基于哈希生成稳定的词向量。"""
        if word in self._word_cache:
            return self._word_cache[word]

        h = hashlib.sha256(word.encode("utf-8")).digest()
        vec = [0.0] * self._dimension
        # 用哈希字节填充向量
        for i in range(self._dimension):
            # 循环使用哈希字节
            byte_idx = i % len(h)
            bit_idx = (i // len(h)) % 8
            val = (h[byte_idx] >> bit_idx) & 1
            # 加入一些变化：每维用 8 位哈希值归一化
            pos = (i * 7) % len(h)
            raw = h[pos] / 255.0 * 2 - 1  # [-1, 1]
            vec[i] = raw

        self._word_cache[word] = self.normalize(vec)
        return self._word_cache[word]


class LocalEmbedder(Embedder):
    """本地 GGUF 嵌入模型 — 基于 llama-cpp-provider。

    与 memory_search 使用同一个本地 embedding 模型。
    模型不可用时自动降级为 MockEmbedder。
    """

    def __init__(self, model_path: str | None = None, dimension: int = 768):
        self._model_path = model_path
        self._dimension = dimension
        self._model = None
        self._fallback: MockEmbedder | None = None
        self._initialized = False

    @property
    def dimension(self) -> int:
        return self._dimension

    def _ensure_model(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        try:
            from llama_cpp import Llama
            # 默认模型路径（与 memory_search 一致）
            if not self._model_path:
                import os
                default = os.path.expanduser(
                    "~/.node-llama-cpp/models/hf_ggml-org_embeddinggemma-300m-qat-Q8_0.gguf"
                )
                self._model_path = default

            import os
            if not os.path.exists(self._model_path):
                raise FileNotFoundError(f"模型文件不存在: {self._model_path}")

            self._model = Llama(
                model_path=self._model_path,
                embedding=True,
                n_ctx=512,
                verbose=False,
            )
            # 从模型推断实际维度
            if hasattr(self._model, 'n_embd'):
                self._dimension = self._model.n_embd
        except Exception:
            # 不可用时降级到 mock
            self._fallback = MockEmbedder(dimension=self._dimension)
            self._model = None

    def embed(self, text: str) -> list[float]:
        self._ensure_model()

        if self._model is not None:
            try:
                result = self._model.embed(text)
                if isinstance(result, list) and len(result) > 0:
                    if isinstance(result[0], list):
                        vec = result[0]
                    else:
                        vec = result
                    return self.normalize(vec)
            except Exception:
                pass

        if self._fallback:
            return self._fallback.embed(text)

        raise RuntimeError("嵌入模型不可用，且 fallback 未启用")

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self._ensure_model()

        if self._model is not None:
            try:
                results: list[list[float]] = []
                for text in texts:
                    result = self._model.embed(text)
                    if isinstance(result, list) and len(result) > 0:
                        if isinstance(result[0], list):
                            vec = result[0]
                        else:
                            vec = result
                        results.append(self.normalize(vec))
                    else:
                        results.append([0.0] * self._dimension)
                return results
            except Exception:
                pass

        if self._fallback:
            return self._fallback.embed_batch(texts)

        raise RuntimeError("嵌入模型不可用，且 fallback 未启用")
