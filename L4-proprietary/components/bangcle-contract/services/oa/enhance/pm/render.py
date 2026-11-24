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

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from .order import ProjectOrder
from .ones_refs import RefProject, project_type
from .ones_refs import _MATCH_PRODUCT, _MATCH_CUSTOMER_ONLY
from .risk import Risk


def _short_end(period: str) -> str:
    """授权区间结束日 → Rex 批注口径的短日期。

    实测口径（PRD §0.1，4 样本校准）：
      2026-08-11 ~ 2027-08-14（368 天，满一年）→ `27.08`
      2025-12-12 ~ 2026-12-11（364 天，差 1 天）→ `26.12.11`
      2026-10-14 ~ 2026-11-14（31 天）          → `26.11.14`
      2026-11-18 ~ 2026-11-30（12 天）          → `26.11.30`
    规则：区间跨度 ≥ 365 天 → YY.MM；否则 YY.MM.DD（不足一年保留日）。
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
            if (d1 - d0).days >= 365:
                return f"{yy}.{m}"
        except (ValueError, TypeError):
            pass
    return f"{yy}.{m}.{d}"


def _pm_text(ref: RefProject) -> str:
    """参考项目对应项目经理（Rex 2026-11-20 第2点：反馈信息须比手工备注多此项）。

    取 ONES 履约义务/项目记录任务负责人；缺失写「项目经理【缺失】」（不伪造）。
    """
    pm = (ref.pm or "").strip()
    if not pm:
        return "，项目经理【缺失】"
    return "，项目经理：%s" % pm


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


_FENG_GANG = "冯刚"
_FRAMEWORK_CATEGORIES = {"框架合同", "框架合同订单/结算单"}


def _pm_lead(order: ProjectOrder, pm: str = "", assigner: str = "",
              pm_depts: Sequence[str] = (),
              pm_in_team: Optional[bool] = None) -> str:
    """首段指派措辞。

    v1.2 C5（Rex 2026-11-20）：**按参考项目 PM 所属部门**区分指派人——
    - 交付中心（项目管理部）序列 → 「请任立民安排项目经理」
    - 区域/其他序列 → 「请冯刚安排项目经理」
    指派人由调用方经企微通讯录判定后注入（渲染层保持纯函数，不触网）。

    降级：assigner 为空（企微通讯录不可用 / PM 无部门）→ 回退 v1.1 C1：
    ① 区域负责人（OA 字段 qyfzr）= 冯刚 → 「请冯刚安排项目经理」
    ② 否则 PM 字段非空 → 「请<PM>负责」
    ③ 否则 → 「请冯刚安排项目经理」

    C1 实证 8/8：885576/885673/885755（区域负责人=冯刚）→ 冯刚；
    886404（PM 空）→ 冯刚；886314/886362/886368/886448（PM 非空且区域负责人≠冯刚）→ PM 本人。
    """
    # ── v1.5（Rex 2026-11-24 实批反推）：三条流程统一指派口径 ─────────
    #   数据源：ONES 配置中心-组织架构 + 项目「项目负责人」(project.assign)。
    #     属 PM 团队 + 含「南区客户服务部」 → 请冯刚安排项目经理
    #     属 PM 团队 + 其他客户服务序列       → 请<PM>负责
    #     非 PM 团队 / 部门未收录             → 不以其为依据，回退请冯刚安排项目经理
    #   实证：916 全部「请冯刚安排」(南区)；820 张辉/程涛/王文博、815 牛素芹均
    #         「请<PM>负责」，与其引用项目的 project.assign 逐一吻合。
    name = (pm or "").strip()
    depts = [d for d in pm_depts if d]
    # pm_in_team 三态：
    #   False → **已校验且未通过**（非 PM 团队 / 部门未收录）：绝不以该 PM 为指派依据
    #   True  → 已校验且在 PM 团队内：南区分流冯刚，其余「请<PM>负责」
    #   None  → **未做团队校验**（历史 C1/C5 调用方）：保留原兜底链
    if pm_in_team is False:
        return "请冯刚安排项目经理"
    if pm_in_team and "南区客户服务部" in depts:
        return "请冯刚安排项目经理"
    if pm_in_team and name:
        return "请%s负责" % name

    if (assigner or "").strip():
        return "请%s安排项目经理" % assigner.strip()
    if (order.region_owner or "").strip() == _FENG_GANG:
        return "请冯刚安排项目经理"
    name = (pm or order.pm or "").strip()
    if name:
        return "请%s负责" % name
    return "请冯刚安排项目经理"


def _framework_no(order: ProjectOrder) -> str:
    """框架合同主号（去掉尾部 -N 订单号）；非框架合同返回 ""（v1.1 C3）。

    `XSZS2512020984-6` → `XSZS2512020984`；合同分类 ∈ {框架合同(4), 框架合同订单/结算单(6)}。
    """
    if (order.contract_category or "").strip() not in _FRAMEWORK_CATEGORIES:
        return ""
    no = (order.contract_no or "").strip()
    return re.sub(r"-\d+$", "", no)


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
    assigner: str = "",
    pm_depts: Sequence[str] = (),
    pm_in_team: Optional[bool] = None,
) -> str:
    """渲染可粘贴的三段式批注。

    Args:
        date_text: 注入日期（纯函数可测；空则不使用）。
        assigner: v1.2 C5 指派人（任立民/冯刚），由调用方经企微通讯录判定后注入；
                  空则回退 C1 口径（区域负责人/PM 字段）。
        pm_depts: v1.3 C11 PM 所属部门（ONES 组织架构）；仅 916 使用。
    """
    lead = _pm_lead(order, pm, assigner, pm_depts, pm_in_team)
    lines: List[str] = []

    # 首段：指派（范围词来自被参考项目类型；混合类型留空 → 只写「参考：」）
    fw_no = _framework_no(order)
    if fw_no:
        # v1.1 C3：框架合同通常多订单 → 按框架合同编号描述，不逐一列 SSXM 订单项目
        lines.append("%s，参考框架合同%s订单对应签约项目。" % (lead, fw_no))
    else:
        scope = _scope_word(order, refs)
        if scope:
            lines.append("%s，参考%s：" % (lead, scope))
        else:
            lines.append("%s，参考：" % lead)

    # 参考项目：单行式 / 列表式（混合类型时各项自带类型词，与 Rex 886404 一致）
    if fw_no:
        pass
    elif not refs:
        lines.append("ONES 未匹配到最终客户「%s」相关项目，请人工确认本期项目编号。"
                     % (order.final_user or "—"))
    else:
        mixed = len({project_type(r.name) for r in refs}) > 1
        if len(refs) == 1 and not mixed:
            r = refs[0]
            lines.append("%s（%s，%s%s）。" % (
                r.code, r.status_label, _period_text(r, order), _pm_text(r)))
        else:
            for i, r in enumerate(refs, 1):
                tw = ("%s " % project_type(r.name)) if mixed else ""
                period = _period_text(r, order) if (i == 1 or r.license_period) else ""
                tail = "，%s" % period if period else ""
                lines.append("%d. %s%s（%s%s%s）。" % (
                    i, tw, r.code, r.status_label, tail, _pm_text(r)))

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
    assigner: str = "",
    pm_depts: Sequence[str] = (),
    pm_in_team: Optional[bool] = None,
    match_levels: Optional[Dict[str, str]] = None,
) -> str:
    """完整 Markdown 建议稿（正文 + 依据表 + 降级项）。"""
    out: List[str] = ["## 批注建议", "", "```",
                      render_remark(order, refs, risks, pm, assigner=assigner,
                                    pm_depts=pm_depts, pm_in_team=pm_in_team), "```", ""]
    out.append("## 参考项目依据")
    out.append("")
    if refs:
        # v1.3：加「匹配层级」列（产品命中 / 同客户项目），供人工取舍
        show_lv = any(getattr(r, "match_level", "") for r in refs)
        # v1.5：ONES「客户信息」原文——用于区分「签约主体/代理商」与「最终用户」。
        #   实证 887728：2087/2173/2227/2462 的 ONES 客户信息=武汉丰泰，但实际服务
        #   对象为湖北运之盟/灵犀云创等；Rex 定性其为代理商项目，只引了 3074。
        show_ci = any((getattr(r, "customer_info", "") or "").strip() for r in refs)
        cols = ["编号", "项目", "状态"]
        if show_lv:
            cols.append("匹配层级")
        cols += ["推断依据", "授权/维保"]
        if show_ci:
            cols.append("ONES客户信息")
        cols += ["证据", "参考项目PM", "来源"]
        out.append("| " + " | ".join(cols) + " |")
        out.append("|" + "|".join(["---"] * len(cols)) + "|")
        for r in refs:
            src = "OA 项目编号" if r.source == "direct" else "名称候选（需人工确认）"
            cells = [r.code, r.name, r.status_label]
            if show_lv:
                lv = ("产品命中" if getattr(r, "match_level", "") == "product"
                      else "同客户项目" if getattr(r, "match_level", "") == _MATCH_CUSTOMER_ONLY
                      else "—")
                cells.append(lv)
            cells.append(r.status_basis)
            cells.append(r.license_period or "【缺失】")
            if show_ci:
                cells.append((getattr(r, "customer_info", "") or "—").replace("\n", " ").replace("|", "／"))
            cells += ["#%s" % (r.license_task or "—"), r.pm or "【缺失】", src]
            out.append("| " + " | ".join(cells) + " |")
        # v1.4：PM 团队校验留证（仅 916；pm_in_team 由 v13 链路写入）
        team_notes = [(r.code, r.pm or "【缺失】", getattr(r, "pm_team_note", "") or "")
                      for r in refs if getattr(r, "pm_team_note", "")]
        if team_notes:
            out.append("")
            out.append("> **PM 团队校验**（ONES 配置中心-组织架构）：")
            for code, nm, note in team_notes:
                mark = "✅" if ("PM 团队" in note and "非项目经理团队" not in note) else "⚠️"
                out.append("> - %s %s（%s）：%s" % (mark, code, nm, note))
        pm_missing = [r.code for r in refs if not (r.pm or "").strip()]
        if pm_missing:
            out.append("")
            out.append("> 参考项目 PM 未取到：%s（ONES 无项目负责人/记录负责人，需人工确认）"
                       % "、".join(pm_missing))
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
