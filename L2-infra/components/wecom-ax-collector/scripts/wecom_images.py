#!/usr/bin/env python3
"""企业微信消息区图片：分类 + 关联（Phase 2，严格只读）

数据来源：engine `images` 子命令（AXImage.AXImageData → PNG 字节 → sha256/尺寸）。
本模块**只处理引擎已提取的元数据**，不产生任何对客户端的写入或网络外发。

实测依据（本机企微 5.0.13，见 VERIFICATION-v1.0.md §6.2）：
  1. 图片按区域分两类：
       - 右侧成员面板/信息栏：x >= 1300（实测 1324~1494），几乎全是 UI 图标
       - 消息气泡区：340 <= x < 1300
  2. UI 资产的 AXDescription 常含 icon/member/gender/file/online/leave 等词
     （如 `icon member online male`、`new icon gender male`、`file pdf emphasized`）
  3. 极小尺寸 + 极小字节（如 32x32 / 925B）也强烈指向 UI 图标
  4. **跨会话复现**是最强证据：同一 sha256 出现在多个会话 → 必为固定 UI 元素
     （实测 240x240/23093B 的大表情在 14 个会话中重复出现）

分类类别（互斥，按优先级）：
  side_panel_ui  右侧成员面板 UI      → 丢弃（非聊天内容）
  ui_icon        图标类（desc/尺寸签名）→ 丢弃
  ui_reused      跨会话复现的固定元素    → 丢弃
  content        疑似真实聊天图片       → 保留（待 OCR/VLM 定性）
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# ---- 经验常量（实测锚点，可被回归测试守护）----
SIDE_PANEL_X_MIN = 1300.0     # 右侧成员面板左界（实测 1324）
MESSAGE_X_MIN = 340.0         # 消息区左界
UI_DESC_KEYS = (
    "icon", "member", "gender", "file", "online", "leave",
    "emoji", "sticker", "avatar", "logo", "new ",
)
TINY_MAX_DIM = 96.0           # 像素边长 ≤ 此值且字节很小 → 图标
TINY_MAX_BYTES = 6000
DIMS_RE = re.compile(r"^(\d+)x(\d+)$")


def _num(v) -> float:
    return float(v) if isinstance(v, (int, float)) else 0.0


def parse_dims(dims: str) -> tuple[float, float]:
    m = DIMS_RE.match(str(dims or ""))
    if not m:
        return (0.0, 0.0)
    return (float(m.group(1)), float(m.group(2)))


def classify_image(im: dict, session_hits: int = 0) -> dict:
    """返回 {category, reason}。

    session_hits: 该 sha256 历史出现的会话数（>=2 视为跨会话复现）。
    """
    x = _num(im.get("x"))
    desc = str(im.get("desc", "")).strip().lower()
    embed = str(im.get("embed", "")).strip().lower()
    w, h = parse_dims(im.get("dims"))
    size = max(w, h)
    nbytes = int(_num(im.get("bytes")))

    if x >= SIDE_PANEL_X_MIN:
        return {"category": "side_panel_ui", "reason": f"x={x:.0f}>=侧栏{SIDE_PANEL_X_MIN:.0f}"}

    if session_hits >= 2:
        return {"category": "ui_reused", "reason": f"sha 复现于 {session_hits} 个会话"}

    if any(k in desc or k in embed for k in UI_DESC_KEYS):
        return {"category": "ui_icon", "reason": "AXDescription/AXEmbeddedImageDescription 命中 UI 关键词"}

    if size <= TINY_MAX_DIM and nbytes <= TINY_MAX_BYTES:
        return {"category": "ui_icon", "reason": f"极小尺寸 {size:.0f}px/{nbytes}B"}

    return {"category": "content", "reason": "无 UI 签名，疑似真实内容图"}


class ImageCatalog:
    """跨会话 sha256 复现记录（JSON 持久化，天然去重）。

    用途：把「同一张图在多个会话出现」这一最强 UI 证据固化下来，
    避免仅凭单帧尺寸/描述误判真实聊天图片。
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.sessions: dict[str, set[str]] = {}
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self.sessions = {k: set(v) for k, v in (raw.get("sessions") or {}).items()}
            except (json.JSONDecodeError, OSError, TypeError):
                self.sessions = {}

    def hits(self, sha: str) -> int:
        return len(self.sessions.get(sha, ()))

    def add(self, sha: str, session: str):
        self.sessions.setdefault(sha, set()).add(session)

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(
            {"sessions": {k: sorted(v) for k, v in sorted(self.sessions.items())}},
            ensure_ascii=False,
        ), encoding="utf-8")
        tmp.replace(self.path)


def associate(images: list[dict], messages: list[dict], tol: float = 120.0) -> dict[int, int]:
    """把消息区图片按最近 y 唯一关联到消息（贪心，容差 tol）。

    返回 {image_index: message_index}。侧栏/被过滤的图片不参与。
    与时间戳归属同一原则：一张图最多配一条消息，避免一对多虚报。
    """
    pairs: list[tuple[float, int, int]] = []
    msg_ys = [m.get("_y") for m in messages]
    for i, im in enumerate(images):
        if classify_image(im).get("category") != "content":
            continue
        iy = _num(im.get("y"))
        for mi, my in enumerate(msg_ys):
            if not isinstance(my, (int, float)):
                continue
            d = abs(iy - my)
            if d <= tol:
                pairs.append((d, i, mi))
    pairs.sort(key=lambda p: p[0])
    used_img: set[int] = set()
    used_msg: set[int] = set()
    out: dict[int, int] = {}
    for d, i, mi in pairs:
        if i in used_img or mi in used_msg:
            continue
        out[i] = mi
        used_img.add(i)
        used_msg.add(mi)
    return out


def summarize(images: list[dict]) -> dict:
    cats: dict[str, int] = {}
    for im in images:
        c = classify_image(im).get("category", "?")
        cats[c] = cats.get(c, 0) + 1
    return {"total": len(images), "categories": cats,
            "content": cats.get("content", 0)}
