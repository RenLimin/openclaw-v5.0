"""ONES 参考项目核查（只读，复用 ones_client / 权威源脚本，不重写自动化）。

输入：最终客户 / 客户名称 / 本单产品编码 / 已知项目编号
输出：RefProject 列表（编号 / 状态推断 / 授权期限 / 依据）

状态推断规则表见 DESIGN-DETAIL §5.1。**禁止**用 OA 导航树反推分类（KB EXP-20261112-001）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

try:                       # 正常包结构：services.oa.enhance.pm
    from .. import ones_client
except ImportError:        # 直接以 pm 为顶层包加载（单测/脚本）：补 sys.path
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
    import ones_client

# 履约义务 issueType（与 ones_obigation 同口径）
OBLIGATION_ISSUE_TYPE = "项目履约义务"

# 状态关键词（任务名前缀）
_ADVANCE_HINT = "提前实施"

# 项目类型词（由项目名判定；口径来自 Rex 批注反推）
# 结算项目在批注中写作「签约项目」（886404：2598 结算 → 「签约项目」）
def project_type(name: str) -> str:
    if _ADVANCE_HINT in (name or ""):
        return "提前实施项目"
    if "POC" in (name or "").upper():
        return "POC项目"
    return "签约项目"


# 流程 → 参考项目类型口径（Rex 实测：815 引「签约 + 提前实施」，820 引 POC，916 引签约）
_TYPE_SCOPE = {
    "wf_820": ("POC项目",),
    "wf_815": ("签约项目", "提前实施项目"),
    "wf_916": ("签约项目",),
}


def _core_name(name: str) -> str:
    """客户名归一：去公司后缀，便于匹配项目名中的简称。"""
    import re as _re
    return _re.sub(r"(股份有限公司|有限责任公司|有限公司|农村商业银行|村镇银行)", "", name or "")


def _search_tokens(final_user: str, customer: str) -> List[str]:
    """检索词：全名 / 去后缀 / 前三字（覆盖「浙江农商」vs「浙江农信」类简称差异）。"""
    toks: List[str] = []
    for nm in (final_user, customer, _core_name(final_user), _core_name(customer)):
        if nm and nm not in toks:
            toks.append(nm)
    for nm in (final_user, customer):
        if nm and len(nm) >= 3 and nm[:3] not in toks:
            toks.append(nm[:3])
    return toks


@dataclass
class RefProject:
    code: str
    name: str
    project_status: str
    status_label: str
    status_basis: str
    license_period: str = ""      # 授权/维保区间（无则【缺失】由渲染层处理）
    license_task: str = ""
    obligation_states: List[str] = field(default_factory=list)
    obligation_names: List[str] = field(default_factory=list)
    matched_products: List[str] = field(default_factory=list)
    source: str = ""              # direct（OA 项目编号）/ candidate（名称候选）
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


class RefsError(RuntimeError):
    """ONES 查询不可用（显式留证，不伪造）。"""


def _status_label(project_name: str, project_status: str,
                  ob_states: Sequence[str]) -> tuple[str, str]:
    """状态推断规则表（DESIGN-DETAIL §5.1）。返回 (label, basis)。"""
    states = [s for s in ob_states if s]
    has_archive = "验收文件已归档" in states
    has_delivery = "交付邮件已归档" in states
    has_handover = "验收文件交接中" in states
    is_advance = _ADVANCE_HINT in project_name
    is_poc = "POC" in (project_name or "").upper()

    # 口径校准自 Rex 5 个参考项目实测（PRD §0.1）：
    #   2066 验收文件交接中 → 已交付未验收；0858 交付邮件已归档 → 已交付未验收；
    #   2598 交接中+交付邮件 → 已交付未验收（优先于「可结项」）；
    #   1641 提前实施+已完成交付义务 → 已交付未关联签约合同；
    #   2727 POC+已完成义务 → 可结项
    if project_status == "验收完成" or has_archive:
        return "已交付已验收", f"项目状态={project_status or '—'}；履约义务含「验收文件已归档」"
    if is_advance and has_delivery:
        return "已交付未关联签约合同", "项目名含「提前实施」；履约义务含「交付邮件已归档」"
    if is_advance and "已完成" in states and not has_archive and project_status != "已完成":
        return "已交付未关联签约合同", (
            f"项目名含「提前实施」；存在已完成交付义务且无验收归档（项目状态={project_status}）")
    if has_handover or has_delivery:
        return "已交付未验收", "履约义务含「验收文件交接中/交付邮件已归档」"
    if is_poc and "已完成" in states:
        return "可结项", "POC 项目且存在已完成履约义务（无验收/交付待办）"
    if project_status == "已完成" and has_delivery:
        return "可结项", "项目状态=已完成；履约义务含「交付邮件已归档」"
    if "实施未开始" in states:
        return "待实施", "履约义务含「实施未开始」"
    return "进行中", f"项目状态={project_status or '—'}（未命中交付/验收特征）"


def _matched(items: Sequence[str], codes: Sequence[str]) -> List[str]:
    """本单产品编码与项目任务的命中（编码或名称包含）。"""
    hits = []
    for c in codes:
        if not c:
            continue
        for it in items:
            if c and c in (it or ""):
                hits.append(c)
                break
    return sorted(set(hits))


def _build(code: str, uuid: str, name: str, final_user: str,
           product_codes: Sequence[str], source: str,
           product_names: Sequence[str] = (),
           product_categories: Sequence[str] = ()) -> Optional[RefProject]:
    try:
        status = ones_client.project_status(uuid)
        tasks = ones_client.project_tasks(uuid)
    except Exception as exc:  # noqa: BLE001 - 单项目失败显式留证
        raise RefsError("ONES 查询失败 %s: %s" % (code, exc)) from exc

    ob_states: List[str] = []
    ob_items: List[str] = []
    for t in tasks:
        if (t.get("issueType") or {}).get("name") != OBLIGATION_ISSUE_TYPE:
            continue
        ob_states.append(str((t.get("status") or {}).get("name") or ""))
        ob_items.append(str(t.get("name") or ""))

    period, evid = ones_client.license_period(tasks)
    label, basis = _status_label(name, status, ob_states)
    # 匹配键 = 产品编码 + 产品名 + 产品服务类别
    # （ONES 义务名按「类别-形态-产品名」书写，如「渠道监测-服务-APP渠道监测服务」；
    #   仅按产品名匹配会漏掉结算/综合服务类项目，如 886404 的 SSXM-2026-0924-2598）
    keys = [k for k in list(product_codes) + list(product_names)
            + list(product_categories) if k]
    return RefProject(
        code=code, name=name, project_status=status,
        status_label=label, status_basis=basis,
        license_period=period, license_task=evid,
        obligation_states=ob_states,
        obligation_names=ob_items,
        matched_products=_matched(ob_items, keys),
        source=source,
    )


def find_reference_projects(
    *,
    final_user: str,
    customer: str = "",
    product_codes: Sequence[str] = (),
    product_names: Sequence[str] = (),
    product_categories: Sequence[str] = (),
    project_code: str = "",
    workflow_id: str = "",
    apply_date: str = "",
) -> tuple[List[RefProject], List[str]]:
    """定位参考项目。

    Returns:
        (refs, notes)；notes 记录缺失/降级原因（不伪造）。
    """
    notes: List[str] = []
    refs: List[RefProject] = []

    # 1) OA 已给项目编号 → 直查
    if project_code and str(project_code).startswith("SSXM-"):
        p = ones_client.project_by_code(project_code)
        if p:
            r = _build(project_code, p["uuid"], p.get("name") or "", final_user,
                       product_codes, "direct", product_names, product_categories)
            if r:
                refs.append(r)
            return refs, notes
        notes.append("OA 项目编号 %s 在 ONES 未找到" % project_code)

    # 2) 名称候选：**遍历全部检索词并合并**（项目名常省略「股份有限公司」等后缀，
    #    只在第一个词命中就 break 会漏掉关键项目，如 886362 的 SSXM-2026-0810-2066）
    allowed_types = _TYPE_SCOPE.get(workflow_id, ())
    seen_codes: set = set()
    probes = [x for x in (final_user, customer, _core_name(final_user),
                          _core_name(customer)) if x]
    short = final_user[:3] if final_user else ""
    for key in _search_tokens(final_user, customer):
        try:
            cands = ones_client.search_projects(key)
        except Exception as exc:  # noqa: BLE001
            notes.append("ONES 项目搜索失败(%s): %s" % (key, exc))
            continue
        for c in cands:
            nm = c.get("name") or ""
            uuid = c.get("uuid") or ""
            if not uuid:
                continue
            code = _code_of(nm)
            if not code or code in seen_codes:
                continue
            # 客户名须出现在项目名（全名/去后缀/前三字任一命中）
            if not any(p in nm for p in probes) and not (short and short in nm):
                continue
            # 类型过滤（同类型才作参考）
            if allowed_types and project_type(nm) not in allowed_types:
                continue
            try:
                r = _build(code, uuid, nm, final_user, product_codes, "candidate",
                           product_names, product_categories)
            except RefsError as exc:
                notes.append(str(exc))
                continue
            if r:
                seen_codes.add(code)
                if all(x.code != code for x in refs):
                    refs.append(r)

    # 产品过滤：本单给了产品时，只保留义务命中本单产品的项目
    # （Rex 批注实测：886362 只引 1 个参考项目，而非该客户全部 47 个项目）
    if (product_codes or product_names or product_categories) and refs:
        filtered = [r for r in refs if r.matched_products]
        if filtered:
            if len(filtered) < len(refs):
                notes.append(
                    "按本单产品/服务过滤：%d 个候选中 %d 个义务命中本单产品"
                    % (len(refs), len(filtered)))
            refs = filtered

    # 口径校准自 Rex 4 条批注（PRD §0.1）：
    #   a) 只引**终态**项目（已交付未验收/已交付未关联签约合同/可结项/已交付已验收）；
    #      「进行中/待实施」不引（886362 未引进行中的 0449，886368 未引待实施的 3139）
    #   b) 排除**同期新建**项目（编号日期 ≥ 本单申请日，如 SSXM-2026-1119-*）
    #   c) 同类型只取 1 个（按 状态rank → 命中产品数 → 编号 排序）
    if refs:
        _TERMINAL = {"已交付未验收", "已交付未关联签约合同", "可结项", "已交付已验收"}
        keep = [r for r in refs if r.status_label in _TERMINAL]
        if len(keep) < len(refs):
            notes.append("仅保留终态项目：%d 个候选 → %d 个（剔除进行中/待实施）"
                         % (len(refs), len(keep)))
            refs = keep

    if refs and apply_date:
        keep = [r for r in refs if not (_code_date(r.code) >= apply_date)]
        if len(keep) < len(refs):
            notes.append("排除同期新建项目 %d 个（编号日期 ≥ 申请日 %s）"
                         % (len(refs) - len(keep), apply_date))
            refs = keep

    if refs:
        _rank = {
            "已交付未验收": 0, "已交付未关联签约合同": 0,
            "可结项": 1, "已交付已验收": 2,
        }
        refs.sort(key=lambda r: (_rank.get(r.status_label, 9),
                                 -len(r.matched_products), r.code))
        picked: List[RefProject] = []
        seen_types: set = set()
        for r in refs:
            t = project_type(r.name)
            if t in seen_types:
                continue
            seen_types.add(t)
            picked.append(r)
        if len(picked) < len(refs):
            notes.append("同类型仅取最相关 1 个：%d 个候选 → %d 个（类型：%s）"
                         % (len(refs), len(picked), "、".join(sorted(seen_types))))
        refs = picked

    if not refs:
        notes.append("ONES 未匹配到最终客户「%s」相关项目（需人工确认本期项目编号）"
                     % (final_user or "—"))
    return refs, notes


def _code_date(code: str) -> str:
    """从 SSXM-YYYY-MM-DD-NNNN 提取日期（用于排除本单同期新建项目）。"""
    import re as _re
    m = _re.search(r"SSXM-(\d{4})-(\d{2})-(\d{2})-", code or "")
    return "%s-%s-%s" % m.groups() if m else ""


def _code_of(name: str) -> str:
    """从项目名提取 SSXM 编号（与权威源脚本 code_of 同口径）。"""
    import re
    m = re.search(r"【(SSXM-[0-9\-]+)】", name or "")
    return m.group(1) if m else ""
