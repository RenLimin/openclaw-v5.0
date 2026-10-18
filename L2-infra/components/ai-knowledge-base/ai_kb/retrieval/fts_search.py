"""
FTS (Full Text Search) keyword search
"""
import re
from typing import List, Tuple

from ..db import AIKB

# Stopwords that don't add retrieval value
_STOPWORDS = {
    "的", "了", "是", "在", "有", "和", "与", "及", "或", "为", "对",
    "哪些", "什么", "怎么", "如何", "请问", "支持", "可以", "吗", "呢",
    "a", "an", "the", "is", "are", "do", "does", "what", "which", "how",
    "的", "此", "该", "中", "上", "下", "我", "你", "他",
}


def _extract_terms(query: str, max_terms: int = 8) -> List[str]:
    """Extract meaningful search terms from a mixed CN/EN query.

    - Keeps ASCII words (split on whitespace) and CJK runs
    - For CJK: extract 2-gram shingles for better FTS matching
    - Drops stopwords
    - Returns up to max_terms terms, most specific first
    """
    # Normalize
    q = query.lower().strip()
    # ASCII tokens
    ascii_tokens = re.findall(r"[a-z0-9][a-z0-9.\-_]*", q)
    # Remove CJK and punctuation, keep contiguous CJK runs
    cjk_runs = re.findall(r"[\u4e00-\u9fff]+", q)

    terms = []
    # ASCII tokens first (they're highly specific)
    for tok in ascii_tokens:
        if len(tok) >= 2 and tok not in _STOPWORDS:
            terms.append(tok)

    # CJK shingles (bigrams)
    for run in cjk_runs:
        if len(run) == 1:
            continue
        if len(run) <= 4:
            # Short run: keep whole run as a phrase-ish term
            if run not in _STOPWORDS:
                terms.append(run)
        else:
            # Long run: extract bigrams
            for i in range(len(run) - 1):
                bg = run[i:i + 2]
                if bg not in _STOPWORDS and bg not in terms:
                    terms.append(bg)

    # De-dup preserving order
    seen = set()
    out = []
    for t in terms:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out[:max_terms]


class FtsSearcher:
    """Full text search on chunks using SQLite FTS5"""

    def __init__(self, db: AIKB, domain_id: int, include_expired: bool = False):
        self.db = db
        self.domain_id = domain_id
        self.include_expired = include_expired

    def search(self, query: str, top_k: int = 20) -> List[Tuple[int, float]]:
        """
        Search for chunks by keyword.
        Returns list of (chunk_id, normalized_score).
        Uses OR semantics over extracted terms so long natural-language
        queries still surface relevant chunks; ranked by BM25.
        """
        terms = _extract_terms(query)
        if not terms:
            return []

        match_clause = " OR ".join(f'"{t}"' for t in terms)

        sql = f'''
        SELECT
            dc.id AS chunk_id,
            bm25(chunk_fts) AS score
        FROM chunk_fts
        INNER JOIN doc_chunk dc ON chunk_fts.rowid = dc.id
        INNER JOIN doc_asset da ON dc.doc_id = da.id
        INNER JOIN entity e ON da.entity_id = e.id
        WHERE chunk_fts MATCH ? AND e.domain_id = ?
        ORDER BY score ASC
        LIMIT ?
        '''
        cursor = self.db.execute(sql, (match_clause, self.domain_id, top_k))
        rows = list(cursor.fetchall())
        if not rows:
            return []

        # Normalize: lower BM25 = better match. Invert to 0..1 so higher = better.
        max_abs = max(abs(r[1]) for r in rows)
        if max_abs == 0:
            return [(r[0], 1.0) for r in rows]
        return [(r[0], 1.0 - (abs(r[1]) / max_abs)) for r in rows]
