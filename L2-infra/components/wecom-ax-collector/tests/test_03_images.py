"""测试：消息区图片分类 / 关联 / 跨会话复现（严格只读）。

分类规则源自本机企微 5.0.13 实测（正式落地见 VERIFICATION-v1.0.md §7）：
  1) 右侧成员面板(x>=1300) → side_panel_ui
  2) 同一 sha 跨会话复现      → ui_reused（最强 UI 证据）
  3) AXDescription 命中 icon/member/gender/file/online/leave… → ui_icon
  4) 极小尺寸 + 极小字节        → ui_icon
  5) 其余                     → content（疑似真实聊天图片）

这些断言是**回归锚点**：分类若放宽到把 UI 资产当内容图，会污染下游 OCR/VLM。
"""
import json
from pathlib import Path

import pytest

import wecom_images as I

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "images_snapshot.json"


def img(**kw) -> dict:
    base = {"i": 0, "x": 600.0, "y": 100.0, "w": 120.0, "h": 120.0,
            "bytes": 20000, "desc": "", "embed": "", "dims": "240x240",
            "sha256": "a" * 64}
    base.update(kw)
    return base


# ---- 分类 ----
def test_side_panel_is_ui():
    v = I.classify_image(img(x=1324.0))
    assert v["category"] == "side_panel_ui"


def test_message_area_big_untagged_is_content():
    v = I.classify_image(img(x=868.0))
    assert v["category"] == "content", v


def test_desc_signature_marks_ui():
    v = I.classify_image(img(desc="icon member online male"))
    assert v["category"] == "ui_icon"
    assert v["reason"].startswith("AXDescription")


def test_embed_signature_marks_ui():
    v = I.classify_image(img(embed="file pdf emphasized"))
    assert v["category"] == "ui_icon"


def test_tiny_is_ui():
    v = I.classify_image(img(dims="32x32", bytes=925, x=700.0))
    assert v["category"] == "ui_icon"


def test_cross_session_reuse_is_ui():
    """同一 sha 出现在 >=2 个会话 → 必为固定 UI 元素。"""
    v = I.classify_image(img(), session_hits=2)
    assert v["category"] == "ui_reused"


def test_single_session_not_auto_reused():
    v = I.classify_image(img(), session_hits=1)
    assert v["category"] != "ui_reused"


def test_priority_side_panel_over_reuse():
    v = I.classify_image(img(x=1400.0), session_hits=5)
    assert v["category"] == "side_panel_ui"


# ---- 关联 ----
def _msg(y):
    return {"_y": y, "sender": "", "content": f"m{y}", "items": [{"y": y}]}


def test_associate_nearest_y_unique():
    images = [img(i=0, y=95.0, x=868.0), img(i=1, y=400.0, x=868.0)]
    msgs = [_msg(100.0), _msg(390.0)]
    assoc = I.associate(images, msgs, tol=120.0)
    assert assoc == {0: 0, 1: 1}, assoc


def test_associate_one_image_one_message():
    """两张图贴近同一条消息时，只能有一张归属（避免一对多虚报）。"""
    images = [img(i=0, y=100.0, x=868.0), img(i=1, y=102.0, x=868.0)]
    msgs = [_msg(101.0)]
    assoc = I.associate(images, msgs, tol=120.0)
    assert len(assoc) == 1


def test_associate_skips_non_content():
    images = [img(i=0, y=100.0, x=1400.0), img(i=1, y=100.0, x=868.0)]
    msgs = [_msg(100.0)]
    assoc = I.associate(images, msgs, tol=120.0)
    assert assoc == {1: 0}, assoc


def test_associate_tolerance_boundary():
    images = [img(i=0, y=0.0, x=868.0)]
    assert I.associate(images, [_msg(119.0)], tol=120.0) == {0: 0}
    assert I.associate(images, [_msg(121.0)], tol=120.0) == {}


# ---- 复现目录 ----
def test_catalog_persists_and_counts(tmp_path):
    cat = I.ImageCatalog(tmp_path / ".image_catalog.json")
    cat.add("s1", "群A")
    cat.add("s1", "群B")
    cat.add("s2", "群A")
    cat.save()
    again = I.ImageCatalog(tmp_path / ".image_catalog.json")
    assert again.hits("s1") == 2
    assert again.hits("s2") == 1
    assert again.hits("missing") == 0


def test_catalog_tolerates_corrupt_file(tmp_path):
    p = tmp_path / ".image_catalog.json"
    p.write_text("{not json", encoding="utf-8")
    cat = I.ImageCatalog(p)
    assert cat.hits("x") == 0


# ---- summarize ----
def test_summarize_counts():
    s = I.summarize([
        img(x=868.0), img(x=1400.0),
        img(desc="icon member online male"), img(dims="32x32", bytes=900),
    ])
    assert s["total"] == 4
    assert s["content"] == 1
    assert s["categories"]["side_panel_ui"] == 1
    assert s["categories"]["ui_icon"] == 2


# ---- 真实 fixture 锚点 ----
def test_real_fixture_shape():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert data.get("read_only") is True, "引擎输出必须标记 read_only"
    assert isinstance(data.get("images"), list)
    for im in data["images"]:
        assert "sha256" in im and "dims" in im and "bytes" in im
        assert im["bytes"] > 0
        # dims 形如 240x240
        assert I.parse_dims(im["dims"]) != (0.0, 0.0)


def test_real_fixture_no_base64_without_flag():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert all("data_b64" not in im for im in data["images"]), \
        "默认不得在 JSON 中内联图片字节（体积/敏感）"


def test_real_fixture_images_classifiable():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for im in data["images"]:
        assert I.classify_image(im)["category"] in {
            "content", "ui_icon", "side_panel_ui", "ui_reused"}
