"""
Document chunking module
Supports multiple chunking strategies: section, fixed, semantic
"""
import re
from typing import List, Tuple
from dataclasses import dataclass


@dataclass
class Chunk:
    """Represents a document chunk"""
    index: int
    title: str
    text: str
    start_line: int
    end_line: int


class BaseChunker:
    """Base class for chunkers"""
    def __init__(self, max_tokens: int = 512, min_tokens: int = 50, overlap_tokens: int = 64):
        self.max_tokens = max_tokens
        self.min_tokens = min_tokens
        self.overlap_tokens = overlap_tokens

    def estimate_tokens(self, text: str) -> int:
        """Very rough token estimation: 1 token ≈ 4 characters for Chinese, 0.75 words for English"""
        # Count Chinese characters
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        # Count English words
        english_words = len(re.findall(r'[a-zA-Z]+', text))
        return chinese_chars + int(english_words * 1.33)

    def chunk(self, title: str, content: str) -> List[Chunk]:
        """Chunk the document content"""
        raise NotImplementedError


class SectionChunker(BaseChunker):
    """
    Section-based chunker: chunks by markdown headings / sections.
    Good for structured documents like docs, articles.
    """
    def __init__(self, max_tokens: int = 512, min_tokens: int = 50, overlap_tokens: int = 64,
                 preserve_tables: bool = True, preserve_code: bool = True):
        super().__init__(max_tokens, min_tokens, overlap_tokens)
        self.preserve_tables = preserve_tables
        self.preserve_code = preserve_code

    def _split_sections(self, lines: List[str]) -> List[Tuple[str, List[str]]]:
        """Split content into sections based on headings"""
        sections = []
        current_section_title = ""
        current_section_lines = []

        heading_pattern = re.compile(r'^(#+)\s+(.*)$')

        for line in lines:
            match = heading_pattern.match(line)
            if match:
                # New section
                if current_section_lines:
                    sections.append((current_section_title, current_section_lines))
                level = len(match.group(1))
                title = match.group(2).strip()
                current_section_title = title
                current_section_lines = [line]
            else:
                current_section_lines.append(line)

        if current_section_lines:
            sections.append((current_section_title, current_section_lines))

        # If no headings found, treat whole document as one section
        if len(sections) == 0 and lines:
            sections.append(("", lines))

        return sections

    def _merge_small_chunks(self, chunks: List[Chunk]) -> List[Chunk]:
        """Merge consecutive small chunks to meet min_tokens requirement"""
        if not chunks:
            return []

        result = []
        current = None

        for chunk in chunks:
            tokens = self.estimate_tokens(chunk.text)
            if tokens < self.min_tokens:
                if current is None:
                    current = chunk
                else:
                    # Merge with current
                    current.text += "\n\n" + chunk.text
                    current.end_line = chunk.end_line
                    if not current.title:
                        current.title = chunk.title
            else:
                if current is not None:
                    result.append(current)
                    current = chunk
                else:
                    result.append(chunk)
                    current = None

        if current is not None:
            if result and self.estimate_tokens(result[-1].text) + self.estimate_tokens(current.text) <= self.max_tokens:
                # Merge with last
                last = result[-1]
                last.text += "\n\n" + current.text
                last.end_line = current.end_line
            else:
                result.append(current)

        return result

    def chunk(self, doc_title: str, content: str) -> List[Chunk]:
        lines = content.splitlines()
        sections = self._split_sections(lines)
        chunks = []
        chunk_index = 0
        current_start_line = 0

        for (section_title, section_lines) in sections:
            current_text = []
            current_start = current_start_line
            token_count = 0

            for i, line in enumerate(section_lines):
                line_tokens = self.estimate_tokens(line)
                if token_count + line_tokens > self.max_tokens and current_text:
                    # Flush current chunk
                    full_title = doc_title
                    if section_title:
                        full_title = f"{doc_title} - {section_title}"
                    chunks.append(Chunk(
                        index=chunk_index,
                        title=full_title,
                        text='\n'.join(current_text),
                        start_line=current_start + 1,
                        end_line=current_start + i
                    ))
                    chunk_index += 1
                    # Apply overlap: keep last N tokens for next chunk
                    if self.overlap_tokens > 0:
                        overlap_lines = []
                        overlap_tokens = 0
                        for reversed_line in reversed(current_text):
                            lt = self.estimate_tokens(reversed_line)
                            if overlap_tokens + lt > self.overlap_tokens:
                                break
                            overlap_lines.insert(0, reversed_line)
                            overlap_tokens += lt
                        current_text = overlap_lines
                        token_count = overlap_tokens
                        current_start = current_start + i - len(overlap_lines)
                    else:
                        current_text = []
                        token_count = 0
                        current_start = current_start + i + 1

                current_text.append(line)
                token_count += line_tokens

            # Flush remaining
            if current_text:
                full_title = doc_title
                if section_title:
                    full_title = f"{doc_title} - {section_title}"
                chunks.append(Chunk(
                    index=chunk_index,
                    title=full_title,
                    text='\n'.join(current_text),
                    start_line=current_start + 1,
                    end_line=current_start + len(section_lines)
                ))
                chunk_index += 1

            current_start_line += len(section_lines)

        return self._merge_small_chunks(chunks)


class FixedSizeChunker(BaseChunker):
    """
    Fixed size chunker: splits content into chunks of approx max_tokens size.
    Good for unstructured content.
    """
    def chunk(self, doc_title: str, content: str) -> List[Chunk]:
        lines = content.splitlines()
        chunks = []
        chunk_index = 0
        current_start_line = 0
        current_text = []
        current_tokens = 0

        for i, line in enumerate(lines):
            line_tokens = self.estimate_tokens(line)

            # If adding this line exceeds max_tokens, flush
            if current_tokens + line_tokens > self.max_tokens and current_text:
                chunks.append(Chunk(
                    index=chunk_index,
                    title=f"{doc_title} - chunk {chunk_index + 1}",
                    text='\n'.join(current_text),
                    start_line=current_start_line + 1,
                    end_line=current_start_line + i
                ))
                chunk_index += 1

                # Overlap
                if self.overlap_tokens > 0:
                    overlap_lines = []
                    overlap_tokens = 0
                    for reversed_line in reversed(current_text):
                        lt = self.estimate_tokens(reversed_line)
                        if overlap_tokens + lt > self.overlap_tokens:
                            break
                        overlap_lines.insert(0, reversed_line)
                        overlap_tokens += lt
                    current_text = overlap_lines
                    current_tokens = overlap_tokens
                    current_start_line = current_start_line + i - len(overlap_lines)
                else:
                    current_text = []
                    current_tokens = 0
                    current_start_line = current_start_line + i + 1

            current_text.append(line)
            current_tokens += line_tokens

        if current_text:
            chunks.append(Chunk(
                index=chunk_index,
                title=f"{doc_title} - chunk {chunk_index + 1}",
                text='\n'.join(current_text),
                start_line=current_start_line + 1,
                end_line=current_start_line + len(lines)
            ))

        return chunks
