"""三段式批注渲染（纯函数，无网络无时钟）。

结构（Rex 批注反推，见 PRD §0.2）：
  请<PM>负责，参考<项目类型>：
  [单行] <编号>（<状态>，授权/维保至<YY.MM>）。
  [列表]  1. <编号>（<状态>，<授权说明>）。
          2. <编号>（<状态>）。
  注：<风险；多条换行>

授权期限格式：结束日 2027-08-14 → `27.08`；跨年且不足一年（如 2026-11-30）保留 `26.11.30`。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from .order import ProjectOrder
from .ones_refs import RefProject, project_type
from .risk import Risk


def _short_end(period: str) -> str:
    """授权区间结束日 → Rex 批注口径的短日期。

    实测口径（PRD §0.1）：
      2026-08-11 ~ 2027-08-14（约 1 年）→ `27.08`
      2026-11-18 ~ 2026-11-30（12 天）  → `26.11.30`
    规则：区间跨度 ≥ 300 天 → YY.MM；否则 YY.MM.DD（短区间保留日，避免歧义）。
    """
    if not period:
        return ""
    segs = [x.strip() for x in str(period).split("~")]
    if not segs or not segs[-1]:
        return ""
    end = segs[-1]
    parts = end.split("-")
    if len(parts) != 3:
        return end
    y, m, d = parts
    yy = y[2:] if len(y) == 4 else y
    if len(segs) == 2:
        try:
            from datetime import date
            d0 = date(*map(int, segs[0].split("-")))
            d1 = date(*map(int, [y, m, d]))
            if (d1 - d0).days >= 300:
                return f"{yy}.{m}"
        except (ValueError, TypeError):
            pass
    return f"{yy}.{m}.{d}"


def _period_text(ref: RefProject, order: ProjectOrder) -> str:
    """授权/维保说明文本（Rex 批注口径）。

    886404 原文对「提前实施 + 已交付未关联签约合同」写「产品授权至26.11.30」，
    其余写「授权/维保至27.08」。
    """
    if not ref.license_period:
        return "授权/维保【缺失】"
    if ref.status_label == "已交付未关联签约合同" and "提前实施" in (ref.name or ""):
        return "产品授权至%s" % _short_end(ref.license_period)
    return "授权/维保至%s" % _short_end(ref.license_period)


def _scope_word(order: ProjectOrder, refs: Sequence[RefProject]) -> str:
    """范围词取自**被参考项目的类型**（Rex 批注反推）。

    886362 是 815（提前实施）单，但引用的 SSXM-2026-0810-2066 是签约项目，
    批注写「参考签约项目」——故不可用本单流程名。
    混合类型（886404：提前实施 + 签约）→ 首段只写「参考：」，类型词下沉到各项。
    """
    types = []
    for r in refs:
        t = project_type(r.name)
        if t not in types:
            types.append(t)
    if len(types) == 1:
        return types[0]
    if not types:
        # 无参考项目时回退本单流程类型词（Rex 口径：886314 无候选仍写「参考POC项目」）
        return {"wf_820": "POC项目", "wf_815": "提前实施项目",
                "wf_916": "签约项目"}.get(order.workflow_id, "项目")
    return ""


def render_remark(
    order: ProjectOrder,
    refs: Sequence[RefProject],
    risks: Sequence[Risk],
    pm: str = "",
    *,
    date_text: str = "",
) -> str:
    """渲染可粘贴的三段式批注。

    Args:
        date_text: 注入日期（纯函数可测；空则不使用）。
    """
    pm_txt = (pm or order.pm or "").strip() or "待分配"
    lines: List[str] = []

    # 首段：指派（范围词来自被参考项目类型；混合类型留空 → 只写「参考：」）
    scope = _scope_word(order, refs)
    if scope:
        lines.append("请%s负责，参考%s：" % (pm_txt, scope))
    else:
        lines.append("请%s负责，参考：" % pm_txt)

    # 参考项目：单行式 / 列表式（混合类型时各项自带类型词，与 Rex 886404 一致）
    if not refs:
        lines.append("ONES 未匹配到最终客户「%s」相关项目，请人工确认本期项目编号。"
                     % (order.final_user or "—"))
    else:
        mixed = len({project_type(r.name) for r in refs}) > 1
        if len(refs) == 1 and not mixed:
            r = refs[0]
            lines.append("%s（%s，%s）。" % (r.code, r.status_label, _period_text(r, order)))
        else:
            for i, r in enumerate(refs, 1):
                tw = ("%s " % project_type(r.name)) if mixed else ""
                period = _period_text(r, order) if (i == 1 or r.license_period) else ""
                tail = "，%s" % period if period else ""
                lines.append("%d. %s%s（%s%s）。" % (i, tw, r.code, r.status_label, tail))

    # 注：风险
    risk_txt = "\n".join("%s：%s" % (r.level, r.text) for r in risks if r.text)
    if risk_txt:
        lines.append("注：" + risk_txt.split("\n")[0])
        for extra in risk_txt.split("\n")[1:]:
            lines.append(extra)

    return "\n".join(lines)


def render_markdown(
    order: ProjectOrder,
    refs: Sequence[RefProject],
    risks: Sequence[Risk],
    notes: Optional[Any] = None,
    pm: str = "",
    missing: Optional[Sequence[str]] = None,
) -> str:
    """完整 Markdown 建议稿（正文 + 依据表 + 降级项）。"""
    out: List[str] = ["## 批注建议", "", "```", render_remark(order, refs, risks, pm), "```", ""]
    out.append("## 参考项目依据")
    out.append("")
    if refs:
        out.append("| 编号 | 项目 | 状态 | 推断依据 | 授权/维保 | 证据 | 来源 |")
        out.append("|---|---|---|---|---|---|---|")
        for r in refs:
            out.append("| %s | %s | %s | %s | %s | #%s | %s |" % (
                r.code, r.name, r.status_label, r.status_basis,
                r.license_period or "【缺失】", r.license_task or "—",
                "OA 项目编号" if r.source == "direct" else "名称候选（需人工确认）"))
    else:
        out.append("无（ONES 未匹配）。")
    out.append("")
    out.append("## 风险")
    if risks:
        for r in risks:
            out.append("- **%s** %s：%s" % (r.code, r.level, r.text))
    else:
        out.append("- 无")
    if notes is not None:
        out.append("")
        out.append("## 合同审批流程核查")
        if getattr(notes, "degraded", None):
            out.append("- ⚠️ 降级：%s" % notes.degraded)
        else:
            out.append("- AI 意见：%s" % (getattr(notes, "ai_summary", "") or "—"))
            out.append("- 风险等级：%s" % ("/".join(getattr(notes, "risk_levels", []) or []) or "—"))
            out.append("- 总体建议：%s" % (getattr(notes, "verdict_hint", "") or "—"))
    if missing:
        out.append("")
        out.append("## ⚠️ 降级/缺失")
        for m in missing:
            out.append("- %s" % m)
    return "\n".join(out)
