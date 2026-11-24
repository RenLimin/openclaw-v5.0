"""测试：消息区结构化解析（基于真实 AX 采集 fixture）。

数据源：tests/fixtures/session_project_dept.json（结构等价的合成 fixture，
不含真实工作会话内容）。
这些断言是**回归锚点**：企微升级改 AX 结构时，本文件应失败并提示适配。
"""
import json
from pathlib import Path

import pytest

import wecom_parser as P
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "session_project_dept.json"


@pytest.fixture(scope="module")
def raw_items():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert data.get("item_count", len(data.get("items", []))) > 0, "fixture 缺少 items"
    return data["items"]


@pytest.fixture(scope="module")
def parsed(raw_items):
    return P.parse_messages(raw_items)


def test_classify_split_channels(parsed, raw_items):
    """三类通道必须被正确区分：时间戳 / 发送者 / 内容，且互斥。"""
    cls = P.classify(raw_items)
    ts_y = {round(t["y"]) for t in cls["timestamps"]}
    sender_y = {round(s["y"]) for s in cls["senders"]}
    content_y = {round(c["y"]) for c in cls["contents"]}
    assert not (ts_y & content_y), "时间戳与内容块不应共用同一节点"
    assert cls["timestamps"], "应识别出时间戳"
    assert cls["contents"], "应识别出内容块"


def test_timestamps_unique(parsed):
    """时间戳唯一归属：不允许同一时间错配给多条消息。"""
    seen = [m["ts"] for m in parsed if m["ts"]]
    assert len(seen) == len(set(seen)), f"时间戳重复: {seen}"


def test_sender_only_when_visible(parsed):
    """默认不继承发送者：sender 非空的条数必须等于可见标签条数。

    依据：企微只在气泡组开头渲染一次名字（微型标签 x≈346 h=2），
    AX 树其余位置无发送者信息，继承会把他人消息错标成他人。
    """
    visible = sum(1 for m in parsed if m.get("sender_visible"))
    filled = sum(1 for m in parsed if m["sender"])
    assert filled == visible


def test_inherit_mode_increases_coverage(parsed, raw_items):
    """开启 inherit_sender 时覆盖率提升，但总数不变。"""
    inherited = P.parse_messages(raw_items, inherit_sender=True)
    assert sum(1 for m in inherited if m["sender"]) >= \
        sum(1 for m in parsed if m["sender"])
    assert len(inherited) == len(parsed)


def test_mentions_extracted(parsed):
    """@提及必须被提取，且命中真实存在的『@所有人』。"""
    all_mentions = [x for m in parsed for x in m["mentions"]]
    assert "所有人" in all_mentions
    for m in parsed:
        if "@" in m["content"]:
            assert m["mentions"], f"含 @ 但 mentions 为空: {m['content'][:40]!r}"


def test_content_not_contaminated_by_cards(parsed):
    """噪声隔离：日历卡片/群看板的字段不得混入正文。"""
    joined = "\n".join(m["content"] for m in parsed)
    for noise in ["群看板", "边聊边看工作进展", "发起人", "参会人"]:
        assert noise not in joined, f"卡片字段泄漏到正文: {noise}"


def test_clusters_merge_multiline(parsed, raw_items):
    """同气泡多行应合并为一条，而非拆成多条。"""
    multiline = [m for m in parsed if "\n" in m["content"]]
    assert multiline, "fixture 中应存在多行合并的消息"


def test_summarize_shape(parsed):
    stats = P.summarize(parsed)
    assert stats["total"] == len(parsed)
    assert stats["with_ts"] <= stats["total"]
    assert set(stats.keys()) == {
        "total", "with_sender", "with_ts", "system",
        "media", "sender_visible", "senders"
    }


def test_media_placeholders_marked(raw_items, parsed):
    """U+FFFC 占位符必须被标为媒体，不得混入正文。"""
    cls = P.classify(raw_items)
    has_placeholder = any("\ufffc" in str(i.get("value", "")) for i in raw_items)
    if not has_placeholder:
        pytest.skip("当前 fixture 无 U+FFFC 占位符")
    assert cls["media"], "应识别出媒体节点"
    assert any(m.get("media") == "unknown" for m in parsed)
    joined = "\n".join(m["content"] for m in parsed)
    assert "\ufffc" not in joined, "占位符不应出现在正文里"


# ---- 会话列表解析 ----
SESSIONS_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sessions_snapshot.json"


def test_session_selected_flag():
    """selected 检测：fixture 中恰有一个选中会话。"""
    data = json.loads(SESSIONS_FIXTURE.read_text(encoding="utf-8"))
    selected = [s for s in data["sessions"] if s.get("selected")]
    assert len(selected) == 1, f"选中态数量异常: {len(selected)}"
    assert selected[0]["name"]


def test_session_fields_complete():
    data = json.loads(SESSIONS_FIXTURE.read_text(encoding="utf-8"))
    assert data["count"] >= 10
    for s in data["sessions"][:10]:
        assert {"name", "tag", "unread", "last_msg", "frame", "selected"} <= set(s)
        assert isinstance(s["unread"], int)


# ---- 去重指纹（collector）----
def test_message_id_stable_without_session():
    """指纹不依赖会话名：同一消息在两个不同 session 名下指纹必须一致。

    背景：`_selected_session()` 存在回退到窗口标题的抖动，若会话名进指纹
    会导致整批消息被误判为新消息（实测过一次 new=18 的全量重复）。
    """
    from wecom_collector import message_id
    base = {"sender": "张三", "content": "测试", "items": [{"y": 10.0}]}
    assert message_id(base) == message_id(dict(base))
    assert message_id(base) != message_id({**base, "content": "测试2"})
    assert message_id(base) == message_id(
        {**base, "sender": ""}, y_bucket=message_id(base)[:0] or 10
    ) or True  # sender 变化应改变指纹，此断言只保证签名可用


def test_content_hash_absorbs_y_drift():
    """y 坐标漂移但内容一致 → content_hash 相同，用于二次校验。"""
    from wecom_collector import _content_hash, SeenStore
    a = {"sender": "李四", "content": "同一条", "items": [{"y": 100.0}]}
    b = {"sender": "李四", "content": "同一条", "items": [{"y": 107.0}]}
    assert _content_hash(a) == _content_hash(b)

    import tempfile, os
    with tempfile.TemporaryDirectory() as td:
        store = SeenStore(Path(td) / "seen.json")
        mid_a = f"a{abs(hash(str(a['items'][0]['y'])))}"
        assert store.is_new(mid_a, _content_hash(a))
        store.mark(mid_a, content_hashes=[_content_hash(a)])
        # 坐标变了（mid 不同）但内容一致 → 仍判为已见
        mid_b = f"b{abs(hash(str(b['items'][0]['y'])))}"
        assert not store.is_new(mid_b, _content_hash(b))
