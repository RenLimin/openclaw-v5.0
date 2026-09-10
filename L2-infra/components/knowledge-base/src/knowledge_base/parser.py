"""文档解析器 — 从不同格式提取结构化内容。"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .document import Document


class DocumentParser(ABC):
    """文档解析器抽象基类。"""

    @abstractmethod
    def parse(self, content: str, source: str = "") -> Document:
        """解析文本内容为 Document 对象。"""
        ...

    def parse_file(self, path: str | Path) -> Document:
        """从文件解析。"""
        p = Path(path)
        content = p.read_text(encoding="utf-8")
        return self.parse(content, source=str(p))


class MarkdownParser(DocumentParser):
    """Markdown 解析器 — 提取 frontmatter + 正文。

    支持 YAML frontmatter（--- 包裹），解析为 metadata。
    """

    FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.DOTALL)
    INLINE_COMMENT_RE = re.compile(r"\s+#\s.*$")
    HEADING_RE = re.compile(r"^#+\s+(.+)$", re.MULTILINE)

    def parse(self, content: str, source: str = "") -> Document:
        metadata, body = self._extract_frontmatter(content)

        title = ""
        if metadata and "title" in metadata:
            title = str(metadata["title"]).strip()
        if not title:
            # 从第一个一级标题推导
            m = self.HEADING_RE.search(body)
            if m:
                title = m.group(1).strip()

        tags: list[str] = []
        if metadata and "tags" in metadata:
            raw = metadata["tags"]
            if isinstance(raw, list):
                tags = [str(t).strip() for t in raw]
            elif isinstance(raw, str):
                tags = [t.strip() for t in raw.split(",") if t.strip()]

        category = ""
        if metadata and "category" in metadata:
            category = str(metadata["category"]).strip()

        doc_id = ""
        if metadata and "id" in metadata:
            doc_id = str(metadata["id"]).strip()

        return Document(
            doc_id=doc_id,
            title=title,
            content=body.strip(),
            source=source,
            doc_type="markdown",
            category=category,
            tags=tags,
            metadata=metadata or {},
        )

    def _extract_frontmatter(self, content: str) -> tuple[dict[str, Any], str]:
        m = self.FRONTMATTER_RE.match(content)
        if not m:
            return {}, content

        raw_fm = m.group(1)
        body = content[m.end():]

        # 尝试用 YAML 解析，失败则退化为简单 key-value
        try:
            import yaml
            cleaned = "\n".join(
                self.INLINE_COMMENT_RE.sub("", line)
                for line in raw_fm.splitlines()
                if not line.lstrip().startswith("#")
            )
            meta = yaml.safe_load(cleaned) or {}
            if not isinstance(meta, dict):
                meta = {}
            return meta, body
        except ImportError:
            return self._simple_kv_parse(raw_fm), body
        except Exception:
            return self._simple_kv_parse(raw_fm), body

    @staticmethod
    def _simple_kv_parse(raw: str) -> dict[str, Any]:
        """简易 key-value 解析（YAML 不可用时的退化方案）。"""
        result: dict[str, Any] = {}
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            k, v = line.split(":", 1)
            k = k.strip()
            v = v.strip()
            # 列表检测：以 [ 开头或以逗号分隔
            if v.startswith("[") and v.endswith("]"):
                items = [i.strip().strip("'\"") for i in v[1:-1].split(",") if i.strip()]
                result[k] = items
            elif v.startswith("- "):
                # 多行列表（简化处理：只取首项）
                result[k] = [v[2:].strip()]
            else:
                result[k] = v.strip("'\"")
        return result


class PlainTextParser(DocumentParser):
    """纯文本解析器。"""

    def parse(self, content: str, source: str = "") -> Document:
        title = ""
        lines = content.strip().splitlines()
        if lines:
            title = lines[0].strip()[:120]

        return Document(
            title=title,
            content=content.strip(),
            source=source,
            doc_type="plaintext",
        )


class CodeParser(DocumentParser):
    """代码文件解析器。

    提取注释作为内容的一部分，保留完整代码。
    """

    # 常见语言的注释样式
    COMMENT_STYLES = {
        ".py": "#",
        ".js": "//",
        ".ts": "//",
        ".go": "//",
        ".java": "//",
        ".c": "//",
        ".cpp": "//",
        ".h": "//",
        ".sh": "#",
        ".bash": "#",
        ".zsh": "#",
        ".rb": "#",
        ".yaml": "#",
        ".yml": "#",
        ".toml": "#",
        ".json": "",  # JSON 无注释
        ".html": "<!--",
        ".css": "/*",
    }

    def parse(self, content: str, source: str = "") -> Document:
        title = Path(source).name if source else "code"
        ext = Path(source).suffix.lower() if source else ""

        # 提取前几行注释作为摘要信息
        comment_prefix = self.COMMENT_STYLES.get(ext, "#")
        description_lines: list[str] = []
        for line in content.strip().splitlines()[:20]:
            stripped = line.strip()
            if comment_prefix and stripped.startswith(comment_prefix):
                description_lines.append(stripped.lstrip(comment_prefix).strip())
            elif not stripped:
                continue
            else:
                break

        description = "\n".join(description_lines) if description_lines else title

        return Document(
            title=title,
            content=content.strip(),
            source=source,
            doc_type="code",
            category=ext.lstrip("."),
            metadata={
                "description": description,
                "extension": ext,
                "line_count": len(content.splitlines()),
            },
        )


def get_parser_for_file(path: str | Path) -> DocumentParser:
    """根据文件扩展名选择合适的解析器。"""
    ext = Path(path).suffix.lower()
    if ext == ".md" or ext == ".markdown":
        return MarkdownParser()
    if ext in CodeParser.COMMENT_STYLES:
        return CodeParser()
    return PlainTextParser()


def get_parser_for_type(doc_type: str) -> DocumentParser:
    """根据文档类型选择解析器。"""
    if doc_type == "markdown":
        return MarkdownParser()
    if doc_type == "code":
        return CodeParser()
    return PlainTextParser()
