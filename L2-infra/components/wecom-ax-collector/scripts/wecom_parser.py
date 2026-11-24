#!/usr/bin/env python3
"""企业微信消息区结构化解析（Phase 1）

依据本机实测的 AX 结构规律（VERIFICATION-wecom-ax-collection-poc-v1.0.md 与
engine 诊断输出），从引擎返回的原始 items 中还原「发送者 / 内容 / 时间 / @提及」。

结构规律（实测锚点，非通用假设）：
  - 时间戳: 文本全匹配时间正则（HH:MM / 昨天 HH:MM / 星期四 HH:MM /
            N月N日 HH:MM / YYYY/M/D HH:MM）。典型位于 x≈786~812，但实测
            部分会话渲染在内容列（x≈348），故判定不锁死 x，只看是否落在
            消息区（x >= 340）且全串匹配
  - 内容块: role == AXTextArea 且 340 <= x <= 360（主列，实测恒为 348）
  - 发送者: x < 360 且 h <= 8 且以 ':' / '：' 结尾（实测为 2x2 微型标签）
  - 媒体:   U+FFFC（对象替换字符）占位符 → media="unknown"，不伪造正文
  - 其余（x > 400 的卡片/群看板/成员面板）一律视为噪声丢弃

归属规则（实测自洽）：
  - 发送者标签只在其渲染处取值；**默认不继承**（宁缺毋错标）
  - 时间戳唯一归属：每个 ts 最多配给一条消息（|Δy| 贪心），避免一对多虚报
"""
from __future__ import annotations

import re
from typing import Any

TIME_RE = re.compile(
    r"^("
    r"\d{1,2}:\d{2}"                                       # 10:03
    r"|(昨天|前天|今天)\s*\d{1,2}:\d{2}"                    # 昨天 17:38
    r"|(刚刚|\d{1,3}分钟前|\d{1,3}小时前)"
    r"|(星期|周)[一二三四五六日天]\s*\d{1,2}:\d{2}"          # 星期四 20:40（实测 x≈792）
    r"|\d{1,2}月\d{1,2}日\s*\d{1,2}:\d{2}"                  # 11月4日 16:28
    r"|\d{4}/\d{1,2}/\d{1,2}\s*\d{1,2}:\d{2}"               # 2026/11/21 13:30
    r")$"
)
DATE_SEP_RE = re.compile(
    r"^((星期|周)[一二三四五六日天]|\d{1,2}月\d{1,2}日|\d{4}年\d{1,2}月)"
)
SYSTEM_KEYS = (
    "加入群聊", "退出了群聊", "撤回了一条消息", "被移出群聊",
    "已成为新群主", "邀请", "设置了群", "开启了", "关闭了",
)
MENTION_RE = re.compile(r"@([^\s@]{1,24})")

MEDIA_CHAR = "\ufffc"                                 # 图片/表情/贴纸占位符

CONTENT_X_MIN, CONTENT_X_MAX = 340.0, 360.0          # 主内容列（实测恒为 348）
CARD_X_MIN, CARD_X_MAX = 360.0, 400.0                # 次级列（372~388，多为卡片噪声）
CARD_MIN_W, CARD_MIN_H = 80.0, 20.0                  # 仅当宽高足够大才算真消息
# 消息区左界（左侧会话列表在 x<350）；时间正则全匹配，可安全放宽到整个消息区
RIGHT_X_MIN = 340.0
TIMESTAMP_X_TYPICAL = 750.0                            # 典型时间戳列（实测 786~812），仅记录用
SENDER_MAX_H = 8.0
SENDER_X_MAX = 360.0
TS_NEAREST_TOL = 100.0                               # 时间戳最近邻容差


def _num(it: dict, key: str) -> float:
    v = it.get(key)
    return float(v) if isinstance(v, (int, float)) else 0.0


def _is_content(role: str, x: float, h: float, w: Any) -> bool:
    """内容块判定。

    实测：真消息列恒为 x≈348（AXTextArea）；x≈372~388 多为日历/群看板卡片的
    小文本，仅当宽高足够大时才当作消息，避免卡片字段混入正文。
    """
    if role != "AXTextArea":
        return False
    wv = float(w) if isinstance(w, (int, float)) else 0.0
    if CONTENT_X_MIN <= x <= CONTENT_X_MAX:
        return True
    if CARD_X_MIN < x <= CARD_X_MAX:
        return wv >= CARD_MIN_W and h >= CARD_MIN_H
    return False


def classify(items: list[dict]) -> dict[str, list[dict]]:
    """把原始 items 分成 timestamps / senders / contents / systems / media / noise。"""
    out: dict[str, list[dict]] = {
        "timestamps": [], "senders": [], "contents": [],
        "systems": [], "media": [], "noise": [],
    }
    for it in items:
        v = str(it.get("value", "")).strip()
        if not v:
            continue
        x, y, h = _num(it, "x"), _num(it, "y"), _num(it, "h")
        role = str(it.get("role", ""))

        if x >= RIGHT_X_MIN and TIME_RE.match(v):
            out["timestamps"].append({"y": y, "text": v, "item": it})
            continue
        if DATE_SEP_RE.match(v) or (any(k in v for k in SYSTEM_KEYS) and len(v) < 80):
            out["systems"].append({"y": y, "text": v, "item": it})
            continue
        if x < SENDER_X_MAX and h <= SENDER_MAX_H and v.endswith((":", "：")):
            out["senders"].append({"y": y, "name": v.rstrip(":："), "item": it})
            continue
        if MEDIA_CHAR in v and not v.replace(MEDIA_CHAR, "").strip():
            out["media"].append({"y": y, "kind": "unknown", "item": it})
            continue
        if _is_content(role, x, h, it.get("w")):
            out["contents"].append({"y": y, "text": v, "item": it})
            continue
        out["noise"].append({"y": y, "text": v, "role": role, "x": x})

    for key in ("timestamps", "senders", "contents", "systems", "media"):
        out[key].sort(key=lambda e: e["y"])
    return out


def _nearest_sender(senders: list[dict], y: float, tol: float = 15.0) -> str:
    best, best_d = "", None
    for s in senders:
        d = abs(s["y"] - y)
        if d <= tol and (best_d is None or d < best_d):
            best, best_d = s["name"], d
    return best


def _cluster(items: list[dict], gap: float = 30.0) -> list[list[dict]]:
    """按 y 聚类：同气泡多行 Δy≈0~5，跨消息 Δy≥50，gap=30 安全。"""
    if not items:
        return []
    ordered = sorted(items, key=lambda e: e["y"])
    clusters: list[list[dict]] = [[ordered[0]]]
    for it in ordered[1:]:
        if abs(it["y"] - clusters[-1][-1]["y"]) <= gap:
            clusters[-1].append(it)
        else:
            clusters.append([it])
    return clusters


def _assign_timestamps(timestamps: list[dict], ys: list[float],
                       tol: float = TS_NEAREST_TOL) -> dict[float, str]:
    """时间戳唯一归属：每个 ts 最多配一条消息，按 |Δy| 贪心匹配。

    动机：实测连续多条消息可能共用同一可见时间戳，允许重复归属会把同一时间
    错标给多条。唯一归属保证不虚报。
    """
    pairs: list[tuple[float, float, str]] = []
    for cy in ys:
        for t in timestamps:
            d = abs(t["y"] - cy)
            if d <= tol:
                pairs.append((d, cy, t["text"]))
    pairs.sort(key=lambda p: p[0])
    used_ts: set[str] = set()
    result: dict[float, str] = {}
    for d, cy, text in pairs:
        if cy in result or text in used_ts:
            continue
        result[cy] = text
        used_ts.add(text)
    return result


def parse_messages(items: list[dict], inherit_sender: bool = False) -> list[dict]:
    """还原消息列表。

    企微实测行为：同一气泡组只在开头渲染一次发送者名字（微型标签 x≈346 h=2），
    其余消息在 AX 树里没有发送者信息（title/description/header 均为 nil）。
    因此默认 **不继承**：无标签 → sender=""，宁缺毋错标。
    """
    cls = classify(items)
    messages: list[dict] = []

    clusters = _cluster(cls["contents"])
    head_ys = [min(c["y"] for c in cl) for cl in clusters]
    ts_map = _assign_timestamps(cls["timestamps"], head_ys)

    for s in cls["systems"]:
        messages.append({
            "sender": "", "content": s["text"], "ts": "",
            "is_self": False, "is_system": True,
            "mentions": [], "items": [s["item"]],
            "_y": s["y"], "sender_visible": False, "media": None,
        })

    for md in cls["media"]:
        messages.append({
            "sender": "", "content": "", "ts": "",
            "is_self": False, "is_system": False,
            "mentions": [], "items": [md["item"]],
            "_y": md["y"], "sender_visible": False, "media": md["kind"],
        })

    last_sender = ""
    for cluster in clusters:
        head_y = min(c["y"] for c in cluster)
        body = "\n".join(c["text"] for c in cluster)
        mentions: list[str] = []
        for c in cluster:
            mentions.extend(MENTION_RE.findall(c["text"]))

        local = _nearest_sender(cls["senders"], head_y, tol=20.0)
        visible = bool(local)
        if visible:
            last_sender = local
        sender = local or (last_sender if inherit_sender else "")

        messages.append({
            "sender": sender,
            "content": body,
            "ts": ts_map.get(head_y, ""),
            "is_self": False,
            "is_system": False,
            "mentions": list(dict.fromkeys(mentions)),
            "items": [c["item"] for c in cluster],
            "_y": head_y,
            "sender_visible": visible,
            "media": None,
        })

    messages.sort(key=lambda m: m["_y"])
    return messages


def summarize(messages: list[dict]) -> dict:
    senders: dict[str, int] = {}
    for m in messages:
        s = m["sender"]
        senders[s] = senders.get(s, 0) + 1
    return {
        "total": len(messages),
        "with_sender": sum(1 for m in messages if m["sender"]),
        "with_ts": sum(1 for m in messages if m["ts"]),
        "system": sum(1 for m in messages if m["is_system"]),
        "media": sum(1 for m in messages if m.get("media")),
        "sender_visible": sum(1 for m in messages if m.get("sender_visible")),
        "senders": senders,
    }
