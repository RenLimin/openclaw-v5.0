"""资产审计 — 取证定性 + 处置建议（v1.1，DETAIL §3.2）。

输入 full_audit §12 探针输出（dict），输出 AuditItem[]。
纯函数，不执行任何变更。

分类/建议/tier 规则表（DETAIL §3.2）：
  P1 计数漂移   → 口径漂移 → 重新登记生成器        → L1
  P2 路径断链   → 断链     → 修正文档引用           → L2
  P3 空壳组件   → 空壳     → 降级设计态 / 补实现     → L2
  P4 未跟踪未提交 → 口径漂移 → 人工确认范围后提交     → L2
  P5 硬编码根路径 → 残留    → 改代码 + 迁移 + 重启    → L2
  P6 重复资产   → 重复     → 归位到规范目录（git mv） → L1
"""
from __future__ import annotations

import re
from dataclasses import replace

from .models import AuditItem

SECTION_CONSISTENCY = "12. 资产一致性检测"

# 探针名前缀（"P1 计数漂移" → "P1"）
_PROBE_ID = re.compile(r"^(P[1-6])")

# P2 detail: "N 条断链: path（doc）; path2（doc2）"
_P2_ITEM = re.compile(r"(L[1-4][-_a-zA-Z0-9/]*(?:/[-_a-zA-Z0-9.]+)*/?)(?:（([^）]*)）)?")
# P6 detail: "pathA ↔ pathB; pathC ↔ pathD"
_P6_PAIR_SPLIT = re.compile(r"\s*;\s*")
_P6_PAIR = re.compile(r"\s*↔\s*")
# P3 detail: "name（file: 0 py）"
_P3_ITEM = re.compile(r"([-_a-zA-Z0-9.]+)（([^）]*)）")
# P5 detail: "file:line"
_P5_ITEM = re.compile(r"([-_a-zA-Z0-9./]+):(\d+)")

# ── 规则表：probe_id → (category, suggestion, tier) ──
_RULES: dict[str, tuple[str, str, str]] = {
    "P1": ("口径漂移", "运行 gen_asset_inventory.py 重新登记（文档生成器，可回滚）", "L1"),
    "P2": ("断链", "修正文档引用（改文档或补齐路径），需人工核对", "L2"),
    "P3": ("空壳", "降级为「📐 设计态」或补实现，需人工拍板", "L2"),
    "P4": ("口径漂移", "人工确认范围后 git add + commit", "L2"),
    "P5": ("残留", "改代码路径 + 迁移文件 + 重启 daemon，需人工确认", "L2"),
    "P6": ("重复", "确认非继承/vendor/备份后，git mv 归位到规范目录", "L1"),
}


def _slug(text: str, n: int = 40) -> str:
    """evidence → 稳定 slug（保留中英文与数字，其余转 -）。"""
    s = re.sub(r"[^一-鿿\w]+", "-", text).strip("-")
    return s[:n] or "x"


def _stable_id(probe_id: str, item_key: str) -> str:
    return f"{probe_id}-{_slug(item_key)}"


def _item_key(pid: str, pd: dict) -> str:
    """提取单项的稳定业务标识（不同项必须不同，同项跨轮必须不变）。"""
    if pid == "P2":
        return pd.get("path", "")
    if pid == "P3":
        return pd.get("component", "")
    if pid == "P5":
        return f"{pd.get('file', '')}:{pd.get('line', '')}"
    if pid == "P6":
        return "~".join(pd.get("paths", []))
    # P1 / P4：单块项，用 reason
    return pd.get("reason", "")[:60]


def _split_probe(name: str) -> str | None:
    m = _PROBE_ID.match(name.strip())
    return m.group(1) if m else None


# ── 各探针 detail 解析 → AuditItem.detail ──

def _parse_p1(detail: str) -> list[dict]:
    return [{"action_type": "regen", "reason": detail}]


def _parse_p2(detail: str) -> list[dict]:
    body = detail.split("条断链:", 1)[-1]
    out = []
    for m in _P2_ITEM.finditer(body):
        out.append({"action_type": "docfix", "path": m.group(1), "source": m.group(2) or ""})
    return out


def _parse_p3(detail: str) -> list[dict]:
    body = re.sub(r"^\d+ 个:\s*", "", detail)
    out = []
    for m in _P3_ITEM.finditer(body):
        out.append({"action_type": "downgrade", "component": m.group(1), "evidence_file": m.group(2)})
    return out


def _parse_p4(detail: str) -> list[dict]:
    return [{"action_type": "commit", "reason": detail}]


def _parse_p5(detail: str) -> list[dict]:
    body = re.sub(r"^\d+ 处:\s*", "", detail)
    out = []
    for m in _P5_ITEM.finditer(body):
        out.append({"action_type": "codefix", "file": m.group(1), "line": int(m.group(2))})
    return out


def _parse_p6(detail: str) -> list[dict]:
    body = re.sub(r"^[^:]*:\s*", "", detail, count=1)
    body = re.sub(r"^同内容重复 \d+ 组:\s*", "", body)
    out = []
    for group in _P6_PAIR_SPLIT.split(body):
        if not group.strip():
            continue
        paths = [p.strip() for p in _P6_PAIR.split(group) if p.strip()]
        if len(paths) >= 2:
            out.append({"action_type": "move", "paths": paths})
    return out


_PARSERS = {
    "P1": _parse_p1,
    "P2": _parse_p2,
    "P3": _parse_p3,
    "P4": _parse_p4,
    "P5": _parse_p5,
    "P6": _parse_p6,
}


def classify(audit: dict, only: set[str] | None = None) -> list[AuditItem]:
    """full_audit dict（--json）→ AuditItem[]。仅消费 §12 的 ⚠️ 项。

    only: 限定探针（{"P1","P3"}）；None=全部。
    """
    items: list[AuditItem] = []
    sections = audit.get("sections") or {}
    for probe in sections.get(SECTION_CONSISTENCY) or []:
        if probe.get("status") != "⚠️":
            continue
        name = probe.get("name", "")
        detail = probe.get("detail", "")
        pid = _split_probe(name)
        if not pid or pid not in _RULES:
            continue
        if only and pid not in only:
            continue
        category, suggestion, tier = _RULES[pid]
        parsed = _PARSERS[pid](detail)
        if not parsed:
            parsed = [{"action_type": "manual", "reason": detail}]
        for pd in parsed:
            items.append(AuditItem(
                id=_stable_id(pid, _item_key(pid, pd)),
                category=category,
                evidence=detail[:200],
                suggestion=suggestion,
                tier=tier,
                status="pending",
                detail={"probe": pid, **pd},
            ))
    return items


def initial_status(item: AuditItem) -> AuditItem:
    """拍板环节：L2 → needs-human；L1 → pending（进 dry-run 清单）。"""
    if item.tier == "L2":
        return replace(item, status="needs-human")
    return replace(item, status="pending")
