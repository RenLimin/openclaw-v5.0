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

    if project_status == "验收完成" or has_archive:
        return "已交付已验收", f"项目状态={project_status or '—'}；履约义务含「验收文件已归档」"
    if is_advance and has_delivery:
        return "已交付未关联签约合同", f"项目名含「提前实施」；履约义务含「交付邮件已归档」"
    if project_status == "已完成" and has_delivery:
        return "可结项", f"项目状态=已完成；履约义务含「交付邮件已归档」"
    if has_handover or has_delivery:
        return "已交付未验收", f"履约义务含「验收文件交接中/交付邮件已归档」"
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
           product_codes: Sequence[str], source: str) -> Optional[RefProject]:
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
    return RefProject(
        code=code, name=name, project_status=status,
        status_label=label, status_basis=basis,
        license_period=period, license_task=evid,
        obligation_states=ob_states,
        matched_products=_matched(ob_items, product_codes),
        source=source,
    )


def find_reference_projects(
    *,
    final_user: str,
    customer: str = "",
    product_codes: Sequence[str] = (),
    project_code: str = "",
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
                       product_codes, "direct")
            if r:
                refs.append(r)
            return refs, notes
        notes.append("OA 项目编号 %s 在 ONES 未找到" % project_code)

    # 2) 名称候选：最终客户 → 客户名称（须精确包含）
    for key, tag in ((final_user, "final_user"), (customer, "customer")):
        if not key:
            continue
        try:
            cands = ones_client.search_projects(key)
        except Exception as exc:  # noqa: BLE001
            notes.append("ONES 项目搜索失败(%s=%s): %s" % (tag, key, exc))
            continue
        for c in cands:
            nm = c.get("name") or ""
            uuid = c.get("uuid") or ""
            if not uuid or key not in nm:
                continue
            code = _code_of(nm)
            if not code:
                continue
            try:
                r = _build(code, uuid, nm, final_user, product_codes, "candidate")
            except RefsError as exc:
                notes.append(str(exc))
                continue
            if r and all(x.code != code for x in refs):
                refs.append(r)
        if refs:
            break

    if not refs:
        notes.append("ONES 未匹配到最终客户「%s」相关项目（需人工确认本期项目编号）"
                     % (final_user or "—"))
    return refs, notes


def _code_of(name: str) -> str:
    """从项目名提取 SSXM 编号（与权威源脚本 code_of 同口径）。"""
    import re
    m = re.search(r"【(SSXM-[0-9\-]+)】", name or "")
    return m.group(1) if m else ""
