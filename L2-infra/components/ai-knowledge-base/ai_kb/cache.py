"""
Query cache for repeated queries
Uses LRU cache to store recent query results
Improves performance for frequently asked questions
"""
from typing import Dict, Any, List, Optional
from collections import OrderedDict
import hashlib
import json

from ai_kb.search import HybridSearch


class LRUQueryCache:
    """
    LRU cache for search results.
    Caches the final retrieval results for repeated queries.
    """

    def __init__(self, max_size: int = 100):
        """
        Initialize LRU cache.
        Args:
            max_size: maximum number of cached entries
        """
        self.max_size = max_size
        self._cache = OrderedDict()
        self._hits = 0
        self._misses = 0

    @property
    def size(self):
        return len(self._cache)

    @property
    def hits(self):
        return self._hits

    @property
    def misses(self):
        return self._misses

    def _get_key(self, query: str, domain_code: str, top_k: int) -> str:
        """Generate cache key from query parameters"""
        key_str = f"{domain_code}:{top_k}:{query.lower().strip()}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def get(self, query: str, domain_code: str, top_k: int) -> Optional[List[Dict[str, Any]]]:
        """Get cached search results if available"""
        key = self._get_key(query, domain_code, top_k)
        if key not in self._cache:
            self._misses += 1
            return None
        # Move to end (most recently used)
        self._cache.move_to_end(key)
        self._hits += 1
        return self._cache[key]

    def put(self, query: str, domain_code: str, top_k: int, results: List[Dict[str, Any]]):
        """Cache search results"""
        key = self._get_key(query, domain_code, top_k)
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self.max_size:
                # Remove least recently used
                self._cache.popitem(last=False)
            self._cache[key] = results

    def clear(self):
        """Clear all cache entries"""
        self._cache.clear()

    def stats(self) -> Dict[str, int]:
        """Get cache statistics"""
        return {
            "size": self.size,
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_ratio": self.hits / (self.hits + self.misses) if (self.hits + self.misses) > 0 else 0
        }
