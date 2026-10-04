"""笔记测试。"""

from models.note import Note
from repositories.note_repo import NoteRepository


class TestNoteModel:
    def test_create_note(self):
        note = Note(
            title="CISSP 第一章笔记",
            content="## 信息安全治理\n\n这是第一章的学习笔记。",
            knowledge_point_id="kp-001",
            owner_id="user-001",
        )
        assert note.title == "CISSP 第一章笔记"
        assert note.is_draft is True
        assert note.is_public is False
        assert note.format == "markdown"

    def test_word_count_chinese(self):
        note = Note(
            title="测试",
            content="这是一段中文测试内容，用来计算字数。",
        )
        # 中文 20 字左右
        assert note.word_count > 0
        assert note.char_count > 0
        assert note.line_count == 1

    def test_word_count_english(self):
        note = Note(
            title="Test",
            content="Hello world. This is a test note with multiple words.",
        )
        # 10 个英文单词左右
        assert note.word_count >= 8

    def test_word_count_mixed(self):
        note = Note(
            title="混合测试",
            content="Python 是一种编程语言，Java 也是。共 2 种语言。",
        )
        # 中文字 + 英文单词 + 数字
        assert note.word_count > 5

    def test_word_count_empty(self):
        note = Note(title="空", content="")
        assert note.word_count == 0
        assert note.char_count == 0
        assert note.line_count == 0

    def test_reading_minutes(self):
        long_content = "你好 " * 300  # 300 中文字
        note = Note(title="长文", content=long_content)
        assert note.reading_minutes >= 1

    def test_update_content(self):
        note = Note(title="测试", content="原始内容")
        original_updated = note.updated_at
        note.update_content("新内容")
        assert note.content == "新内容"
        assert note.updated_at >= original_updated

    def test_publish(self):
        note = Note(title="发布测试", content="内容")
        assert note.is_draft is True
        note.publish()
        assert note.is_draft is False

    def test_publish_empty_title_raises(self):
        import pytest
        note = Note(title="  ", content="内容")
        with pytest.raises(ValueError, match="title cannot be empty"):
            note.publish()

    def test_unpublish(self):
        note = Note(title="测试", content="内容", is_draft=False)
        note.unpublish()
        assert note.is_draft is True

    def test_append_content(self):
        note = Note(title="测试", content="第一段")
        note.append_content("第二段")
        assert "第一段" in note.content
        assert "第二段" in note.content
        assert "\n\n" in note.content

    def test_append_to_empty(self):
        note = Note(title="测试", content="")
        note.append_content("新内容")
        assert note.content == "新内容"


class TestNoteRepository:
    def test_create_and_get(self):
        note = NoteRepository.create(
            title="笔记1",
            content="内容",
            owner_id="u1",
            knowledge_point_id="kp1",
        )
        fetched = NoteRepository.get_by_id(note.id)
        assert fetched is not None
        assert fetched.title == "笔记1"
        assert fetched.owner_id == "u1"

    def test_list_by_owner(self):
        NoteRepository.create(title="笔记1", content="", owner_id="u1")
        NoteRepository.create(title="笔记2", content="", owner_id="u1")
        NoteRepository.create(title="笔记3", content="", owner_id="u2")
        assert len(NoteRepository.list_by_owner("u1")) == 2
        assert len(NoteRepository.list_by_owner("u2")) == 1

    def test_list_by_knowledge_point(self):
        NoteRepository.create(title="n1", content="", owner_id="u1", knowledge_point_id="kp1")
        NoteRepository.create(title="n2", content="", owner_id="u1", knowledge_point_id="kp1")
        NoteRepository.create(title="n3", content="", owner_id="u1", knowledge_point_id="kp2")
        assert len(NoteRepository.list_by_knowledge_point("kp1")) == 2

    def test_list_drafts(self):
        NoteRepository.create(title="草稿", content="", owner_id="u1", is_draft=True)
        NoteRepository.create(title="已发布", content="", owner_id="u1", is_draft=False)
        drafts = NoteRepository.list_drafts("u1")
        assert len(drafts) == 1
        assert drafts[0].title == "草稿"

    def test_search_by_content(self):
        NoteRepository.create(title="加密笔记", content="AES 是对称加密算法", owner_id="u1")
        NoteRepository.create(title="网络笔记", content="TCP/IP 协议栈", owner_id="u1")
        NoteRepository.create(title="加密进阶", content="RSA 是非对称加密", owner_id="u1")
        results = NoteRepository.search_by_content("加密")
        assert len(results) >= 2  # 标题 + 内容匹配

    def test_count_words_by_owner(self):
        NoteRepository.create(
            title="笔记1", content="一二三", owner_id="u1", is_draft=False
        )
        NoteRepository.create(
            title="笔记2", content="四五", owner_id="u1", is_draft=False
        )
        NoteRepository.create(
            title="草稿", content="不算", owner_id="u1", is_draft=True
        )
        total = NoteRepository.count_words_by_owner("u1")
        assert total == 5  # 3 + 2

    def test_publish_via_repo(self):
        note = NoteRepository.create(
            title="发布测试", content="内容", owner_id="u1"
        )
        assert note.is_draft is True
        published = NoteRepository.publish(note.id)
        assert published.is_draft is False

    def test_list_by_plan(self):
        NoteRepository.create(title="n1", content="", owner_id="u1", plan_id="plan1")
        NoteRepository.create(title="n2", content="", owner_id="u1", plan_id="plan1")
        assert len(NoteRepository.list_by_plan("plan1")) == 2
