"""
Answer generation module with source attribution
Answers MUST include source references
"""
from typing import List, Dict, Optional


def _build_answer_preview(results: List[Dict], max_chars: int = 800) -> str:
    """
    Build an answer preview from retrieval results.
    When no external LLM answer_text is provided, concatenate the most relevant
    chunk snippets into a readable summary so the KB is self-contained.
    """
    parts = []
    seen_text = set()
    total = 0
    for r in results:
        chunk = r.get('chunk', {})
        text = (chunk.get('text') or '').strip()
        if not text or text in seen_text:
            continue
        seen_text.add(text)
        # Strip markdown heading markers for readability
        clean = '\n'.join(
            line.lstrip('#').strip() for line in text.splitlines()
            if line.strip()
        )
        if clean:
            parts.append(clean)
            total += len(clean)
            if total >= max_chars:
                break
    if not parts:
        return ""
    preview = '\n\n'.join(parts)
    if len(preview) > max_chars:
        preview = preview[:max_chars] + "…"
    return preview


def format_answer_with_sources(query: str, results: List[Dict], answer_text: str = "") -> Dict:
    """Format answer with mandatory source attribution.
    Every answer must be traceable back to original documents.
    """
    sources = []
    seen = set()
    for r in results:
        doc = r.get('doc', {})
        entity = r.get('entity', {})
        chunk = r.get('chunk', {})
        doc_key = doc.get('id', '')
        if doc_key in seen:
            continue
        seen.add(doc_key)
        sources.append({
            'doc_id': doc.get('id'),
            'file_name': doc.get('file_name'),
            'doc_type': doc.get('doc_type'),
            'version': doc.get('version'),
            'entity_name': entity.get('name'),
            'chunk_index': chunk.get('chunk_index'),
            'snippet': chunk.get('text', '')[:200],  # 原文片段
        })

    # If no external answer provided, auto-build a preview from sources
    if not answer_text:
        answer_text = _build_answer_preview(results)

    return {
        'query': query,
        'answer': answer_text,
        'sources': sources,
        'source_count': len(sources),
        'confidence': 'high' if len(sources) >= 3 else ('medium' if len(sources) >= 1 else 'low'),
    }


def render_markdown_answer(result: Dict) -> str:
    """Render answer as markdown with source references"""
    parts = []
    if result.get('answer'):
        parts.append(result['answer'])
    parts.append("\n---\n**来源引用**：\n")
    for i, s in enumerate(result['sources'], 1):
        entity = s.get('entity_name', '')
        fn = s.get('file_name', '')
        dtype = s.get('doc_type', '')
        ver = s.get('version', '')
        snippet = s.get('snippet', '').replace('\n', ' ')
        ver_str = f"（{ver}）" if ver else ""
        parts.append(f"{i}. **{entity}** — `{fn}`{ver_str} [{dtype}]")
        parts.append(f"   > 原文片段：{snippet[:150]}...")
    parts.append(f"\n共 {result['source_count']} 个来源，置信度：{result['confidence']}")
    return "\n".join(parts)
