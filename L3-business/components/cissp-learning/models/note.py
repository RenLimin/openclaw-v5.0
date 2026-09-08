"""笔记领域模型。

Markdown 内容 + 字数统计 + 关联知识点。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional

from pydantic import Field, computed_field

from base.base_model import TenantModel


class Note(TenantModel):
    """笔记聚合根。"""

    # ── 基本信息 ────────────────────────────────────────────────
    title: str
    content: str = ""            # Markdown 原文
    summary: str = ""            # 摘要/大纲（自动生成或手动填写）

    # ── 关联 ────────────────────────────────────────────────────
    knowledge_point_id: Optional[str] = None  # 关联知识点
    plan_id: Optional[str] = None             # 关联学习计划
    owner_id: str = ""

    # ── 状态 ────────────────────────────────────────────────────
    is_draft: bool = True
    is_public: bool = False

    # ── 格式 ────────────────────────────────────────────────────
    format: str = "markdown"     # markdown / plain / html

    # ── 标签 ────────────────────────────────────────────────────
    tags: List[str] = Field(default_factory=list)

    # ── 字数统计（计算属性） ─────────────────────────────────────

    @computed_field
    @property
    def word_count(self) -> int:
        """总字数（中文按字计，英文按单词计）。"""
        if not self.content:
            return 0
        # 中文字符数
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", self.content))
        # 英文单词数
        english_words = len(re.findall(r"[a-zA-Z]+", self.content))
        # 数字串
        number_tokens = len(re.findall(r"\d+", self.content))
        return chinese_chars + english_words + number_tokens

    @computed_field
    @property
    def char_count(self) -> int:
        """字符数（不含空白）。"""
        return len(re.sub(r"\s+", "", self.content))

    @computed_field
    @property
    def line_count(self) -> int:
        """行数。"""
        if not self.content:
            return 0
        return self.content.count("\n") + 1

    @computed_field
    @property
    def reading_minutes(self) -> int:
        """预估阅读时间（分钟）。

        按中文 300 字/分钟、英文 200 词/分钟估算，取较大值。
        """
        if not self.content:
            return 0
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", self.content))
        english_words = len(re.findall(r"[a-zA-Z]+", self.content))
        minutes_cn = chinese_chars / 300 if chinese_chars else 0
        minutes_en = english_words / 200 if english_words else 0
        total = max(minutes_cn, minutes_en, (minutes_cn + minutes_en) / 2)
        return max(1, round(total))

    # ── 方法 ────────────────────────────────────────────────────

    def update_content(self, new_content: str) -> None:
        """更新内容，自动更新 updated_at。"""
        self.content = new_content
        self.updated_at = datetime.utcnow()

    def publish(self) -> None:
        """发布笔记（草稿 → 正式）。"""
        if not self.title.strip():
            raise ValueError("Note title cannot be empty")
        self.is_draft = False
        self.updated_at = datetime.utcnow()

    def unpublish(self) -> None:
        """撤回为草稿。"""
        self.is_draft = True
        self.updated_at = datetime.utcnow()

    def append_content(self, text: str) -> None:
        """追加内容。"""
        if self.content:
            self.content += "\n\n" + text
        else:
            self.content = text
        self.updated_at = datetime.utcnow()
