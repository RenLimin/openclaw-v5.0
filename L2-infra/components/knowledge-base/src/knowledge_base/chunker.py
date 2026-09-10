"""文本分块器 — 将文档切分为适合向量化的小块。"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any

from .document import Chunk, Document


class Chunker(ABC):
    """分块器抽象基类。"""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    @abstractmethod
    def chunk(self, doc: Document) -> list[Chunk]:
        """将文档切分为块列表。"""
        ...

    def _make_chunk(self, doc: Document, content: str, index: int,
                    metadata: dict[str, Any] | None = None) -> Chunk:
        return Chunk(
            content=content.strip(),
            doc_id=doc.doc_id,
            index=index,
            metadata=metadata or {},
        )


class CharacterChunker(Chunker):
    """按字符数分块（最简单可靠）。

    在 chunk_size 附近寻找自然断点（句号/换行/段落）。
    """

    # 优先寻找的断点（从强到弱）
    BREAK_PATTERNS = [
        re.compile(r"\n\s*\n"),      # 段落
        re.compile(r"[。！？.!?]\s"),  # 句子结束
        re.compile(r"[，,；;]\s"),    # 分句
        re.compile(r"\s"),             # 空格
    ]

    def chunk(self, doc: Document) -> list[Chunk]:
        text = doc.content
        if not text.strip():
            return []

        chunks: list[Chunk] = []
        start = 0
        idx = 0
        text_len = len(text)

        while start < text_len:
            # 计算理想结束位置
            end = min(start + self.chunk_size, text_len)

            # 如果不是最后一块，尝试找自然断点
            if end < text_len:
                # 在 overlap 区域内找断点
                search_start = max(start + self.chunk_size - self.chunk_overlap, start + 1)
                search_end = min(start + self.chunk_size + self.chunk_overlap, text_len)

                found = False
                for pattern in self.BREAK_PATTERNS:
                    # 从后往前找，尽量接近 chunk_size
                    match_pos = -1
                    pos = search_end
                    while pos >= search_start:
                        m = pattern.search(text, search_start, pos)
                        if m:
                            match_pos = m.end()
                            break
                        pos -= 1
                    # 直接用 finditer 更高效
                    matches = list(pattern.finditer(text, search_start, search_end))
                    if matches:
                        # 选最接近 chunk_size 的
                        target = start + self.chunk_size
                        best = min(matches, key=lambda m: abs(m.end() - target))
                        end = best.end()
                        found = True
                        break

                if not found:
                    # 找不到断点，硬切
                    end = start + self.chunk_size

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(self._make_chunk(doc, chunk_text, idx))
                idx += 1

            if end >= text_len:
                break

            # 下一块的起点，考虑 overlap
            next_start = end - self.chunk_overlap
            if next_start <= start:
                next_start = end  # 防止死循环
            start = next_start

        return chunks


class TokenChunker(Chunker):
    """按 token 数分块。

    使用简单的 token 估算（中文按字、英文按词），不依赖外部 tokenizer。
    适合没有 tokenizer 时的近似分块。
    """

    def __init__(self, chunk_size: int = 200, chunk_overlap: int = 20):
        super().__init__(chunk_size, chunk_overlap)

    @staticmethod
    def _count_tokens(text: str) -> int:
        """粗略估算 token 数：
        - 中文字符：1 token / 字
        - 英文单词：1 token / 词
        - 标点/数字：简单计入
        """
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_words = len(re.findall(r'[a-zA-Z]+', text))
        numbers = len(re.findall(r'\d+', text))
        return chinese_chars + english_words + numbers

    def chunk(self, doc: Document) -> list[Chunk]:
        text = doc.content
        if not text.strip():
            return []

        # 策略：按段落切分，然后按 token 数合并
        paragraphs = re.split(r'\n\s*\n', text)
        chunks: list[Chunk] = []
        current_text = ""
        current_tokens = 0
        idx = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            para_tokens = self._count_tokens(para)

            if current_tokens + para_tokens <= self.chunk_size:
                current_text += ("\n\n" if current_text else "") + para
                current_tokens += para_tokens
            else:
                # 当前块已满，存下
                if current_text:
                    chunks.append(self._make_chunk(doc, current_text, idx))
                    idx += 1

                # 单个段落超过 chunk_size：按句子拆分
                if para_tokens > self.chunk_size:
                    sub_chunks = self._split_long_paragraph(doc, para, idx)
                    for sc in sub_chunks:
                        chunks.append(sc)
                        idx += 1
                    current_text = ""
                    current_tokens = 0
                else:
                    # 保留 overlap：取最后一段的末尾作为下一块的开头
                    current_text = para
                    current_tokens = para_tokens

        if current_text:
            chunks.append(self._make_chunk(doc, current_text, idx))

        return chunks

    def _split_long_paragraph(self, doc: Document, para: str, start_idx: int) -> list[Chunk]:
        """按句子拆分超长段落。"""
        sentences = re.split(r'(?<=[。！？.!?])\s*', para)
        chunks: list[Chunk] = []
        current = ""
        current_tokens = 0
        idx = start_idx

        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            st = self._count_tokens(sent)
            if current_tokens + st <= self.chunk_size:
                current += sent
                current_tokens += st
            else:
                if current:
                    chunks.append(self._make_chunk(doc, current, idx))
                    idx += 1
                current = sent
                current_tokens = st

        if current:
            chunks.append(self._make_chunk(doc, current, idx))

        return chunks


class SemanticChunker(Chunker):
    """语义分块 — 基于标题层级/段落结构的分块。

    对 Markdown 文档，优先在标题处分块，保持语义完整性。
    对纯文本，退化为段落分块。
    """

    HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)

    def chunk(self, doc: Document) -> list[Chunk]:
        if doc.doc_type == "markdown":
            return self._chunk_markdown(doc)
        return self._chunk_plain(doc)

    def _chunk_markdown(self, doc: Document) -> list[Chunk]:
        """按 Markdown 标题层级分块。"""
        text = doc.content
        headings = list(self.HEADING_RE.finditer(text))

        if not headings:
            # 没有标题，退化为字符分块
            return CharacterChunker(
                chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap
            ).chunk(doc)

        chunks: list[Chunk] = []
        idx = 0

        # 文档开头（第一个标题前的内容）
        first_h = headings[0]
        preamble = text[:first_h.start()].strip()
        if preamble and len(preamble) > 20:
            chunks.append(self._make_chunk(doc, preamble, idx, {"section": "preamble"}))
            idx += 1

        # 每个标题段
        for i, h in enumerate(headings):
            level = len(h.group(1))
            title = h.group(2).strip()
            start = h.start()
            end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
            section_text = text[start:end].strip()

            section_len = len(section_text)
            if section_len <= self.chunk_size:
                chunks.append(self._make_chunk(doc, section_text, idx, {
                    "section": title, "heading_level": level
                }))
                idx += 1
            else:
                # 大节再按子标题或字符粒度细分
                sub_doc = Document(
                    content=section_text,
                    doc_id=f"{doc.doc_id}_s{i}",
                    title=title,
                    doc_type="markdown",
                )
                sub_chunks = CharacterChunker(
                    chunk_size=self.chunk_size,
                    chunk_overlap=self.chunk_overlap,
                ).chunk(sub_doc)
                for sc in sub_chunks:
                    sc.doc_id = doc.doc_id
                    sc.index = idx
                    sc.chunk_id = f"{doc.doc_id}_chunk{idx}"
                    sc.metadata["section"] = title
                    sc.metadata["heading_level"] = level
                    chunks.append(sc)
                    idx += 1

        return chunks

    def _chunk_plain(self, doc: Document) -> list[Chunk]:
        """纯文本：按段落分块，合并小段。"""
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', doc.content) if p.strip()]
        chunks: list[Chunk] = []
        current = ""
        idx = 0

        for para in paragraphs:
            if len(current) + len(para) <= self.chunk_size:
                current += ("\n\n" if current else "") + para
            else:
                if current:
                    chunks.append(self._make_chunk(doc, current, idx))
                    idx += 1
                # 单段过长
                if len(para) > self.chunk_size:
                    sub = CharacterChunker(
                        chunk_size=self.chunk_size,
                        chunk_overlap=self.chunk_overlap,
                    ).chunk(Document(content=para, doc_id=f"{doc.doc_id}_p"))
                    for s in sub:
                        s.doc_id = doc.doc_id
                        s.index = idx
                        s.chunk_id = f"{doc.doc_id}_chunk{idx}"
                        chunks.append(s)
                        idx += 1
                    current = ""
                else:
                    current = para

        if current:
            chunks.append(self._make_chunk(doc, current, idx))

        return chunks
