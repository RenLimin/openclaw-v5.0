"""ONES 参考项目核查（只读，复用 ones_client / 权威源脚本，不重写自动化）。

输入：最终客户 / 客户名称 / 本单产品编码 / 已知项目编号
输出：RefProject 列表（编号 / 状态推断 / 授权期限 / 依据）

状态推断规则表见 DESIGN-DETAIL §5.1。**禁止**用 OA 导航树反推分类（KB EXP-20261112-001）。
"""
from __future__ import annotations

import re
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
    return _re.sub(r"(%s)" % "|".join(_COMPANY_SUFFIX), "", name or "")


_ADMIN_PREFIX_RE = re.compile(
    r"^(?:[^省市县区]{0,6}?(?:自治区|自治州|省|市|区|县|旗|地区))+"
)


def _strip_admin_prefix(name: str) -> str:
    """去行政区划前缀（如「广州市」「深圳市」）。

    仅当前缀剥离后剩余 ≥ 4 字才剥离（避免把短客户名掏空）。
    实证：887401「广州市宏视信息技术有限公司」→「宏视信息技术有限公司」。
    """
    t = name or ""
    m = _ADMIN_PREFIX_RE.match(t)
    if not m:
        return t
    rest = t[m.end():]
    return rest if len(rest) >= 4 else t


_ADMIN_SUFFIX = ("省", "市", "区", "县", "自治区", "自治州", "旗", "地区")

# 公司后缀全集（_core_name 归一用；缺「集团」会破坏全称匹配：
# 「中国人寿保险（集团）公司」去掉「公司」剩「中国人寿保险（集团）」，
# 项目名「中国人寿保险（集团）公司…」反而不被自身命中 —— 2026-11-20 实测）
_COMPANY_SUFFIX = (
    "股份有限公司", "有限责任公司", "有限公司", "农村商业银行", "村镇银行",
    "集团", "公司",
)


def _is_admin_prefix(tok: str) -> bool:
    """是否为纯行政区划前缀（如「广州市」「深圳市」「北京市」）。

    实证（2026-11-20，887401）：客户「广州市宏视信息技术有限公司」的
    前三字「广州市」是纯行政区划，用它匹配会把「广州市潜宇信息科技…」
    误当候选（张冠李戴）。故纯行政区划短词**不得**作匹配词。
    反例保留：「浙江农」不是纯行政区划（「浙江」才是），仍需保留以覆盖
    「浙江农信」类简称（886404 实证）。
    """
    t = (tok or "").strip()
    if len(t) < 2 or len(t) > 5:
        return False
    return any(t.endswith(x) for x in _ADMIN_SUFFIX)


def _search_tokens(final_user: str, customer: str) -> List[str]:
    """检索词（长词优先，短词仅作辅助）：

    ① 全名（final_user / customer）—— 项目名常含全称，最强
    ② 去后缀名（_core_name）—— 项目名常省略「股份有限公司」等
    ③ 非行政区划前三字 —— 覆盖「浙江农商」vs「浙江农信」类简称差异，
       但**排除纯行政区划**（「广州市」），否则会把同城别家客户误配
       （887401 实证：宏视 ← 误配 潜宇）

    ⚠️ 顺序即优先级：长词必须先于短词，否则「广州市宏视信息技术」
    （短词截断）会先命中，反而盖过去后缀的「宏视信息技术有限公司」。
    """
    toks: List[str] = []
    for nm in (final_user, customer):
        if not nm:
            continue
        variants = [
            nm,                                   # ① 全名
            _core_name(nm),                       # ② 去公司后缀
            _strip_admin_prefix(nm),              # ③ 去行政区划前缀
            _core_name(_strip_admin_prefix(nm)),  # ④ 去前缀 + 去后缀
        ]
        pre = nm[:3]
        if len(pre) >= 3 and not _is_admin_prefix(pre):
            variants.append(pre)                 # ⑤ 前三字（非纯行政区划）
        for v in variants:
            if v and v not in toks:
                toks.append(v)
    return toks


def _search_tokens_long(final_user: str, customer: str = "") -> List[str]:
    """长词检索集（≥4 字）：排除 3 字短词，避免歧义放大。

    v1.3/v1.5（916 链路）专用：全量义务查询口径下，短词会把无关项目灌入候选
    （实证 887594 类误配），故只用长词。815/820 走 ``_search_tokens``（含短词，
    但短词命中须经 ONES「客户信息」佐证后才准入，见 find_reference_projects）。
    """
    return [x for x in _search_tokens(final_user, customer) if len(x) >= 4]


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
    obligation_project_states: List[str] = field(default_factory=list)  # 义务「项目状态」(v1.1 C2)
    obligation_names: List[str] = field(default_factory=list)
    matched_products: List[str] = field(default_factory=list)
    pm: str = ""                  # 参考项目对应项目经理
    pm_basis: str = ""            # 取数依据（口径可追溯，禁止无来源）
    pm_in_team: bool = False      # v1.4：PM 是否属项目经理团队（ONES 组织架构）
    pm_depts: List[str] = field(default_factory=list)   # v1.4：PM 所属部门（原始，供渲染判定）
    pm_team_note: str = ""        # 团队校验说明（非 PM / 未收录部门时留证）
    source: str = ""              # direct（OA 项目编号）/ candidate（名称候选）
    note: str = ""
    # v1.3 C9：product（同客户+同产品）/ customer_only（同客户项目）。
    # 默认空串 = **v1.2 链路**（815/820）不设此字段，渲染层据此决定是否显示该列，
    # 保证 v1.2 报告逐字不变（AC-5 回归）。
    match_level: str = ""
    closed: bool = False          # v1.3 C10：已结项（_Gvi8gt9w=已归档），未结项优先
    customer_info: str = ""      # v1.5：ONES「客户信息」任务原文（区分签约主体 vs 最终用户）
    product_info: List[str] = field(default_factory=list)  # v1.5：ONES「产品信息」任务名（匹配源）
    customer_mismatch: bool = False  # v1.5：客户信息与最终用户/客户均不符（降权，不剔除）

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


class RefsError(RuntimeError):
    """ONES 查询不可用（显式留证，不伪造）。"""


def _status_label(project_name: str, project_status: str,
                  ob_states: Sequence[str],
                  ob_project_states: Sequence[str] = ()) -> tuple[str, str]:
    """状态推断规则表（DESIGN-DETAIL §5.1 + v1.1 C2）。返回 (label, basis)。

    v1.1 C2（Rex 2026-11-19）：**「已结项」来自履约义务的「项目状态」字段**
    （ONES 任务自定义字段 ``_Gvi8gt9w``，值 ``已归档``），优先于其他判定；
    其余状态词来自履约义务的「状态」（status.name）。
    """
    states = [s for s in ob_states if s]
    # 口径（Rex 2026-11-20）：**履约义务优先**，无结论时才回退项目状态字段。
    # ① 义务「项目状态」=已归档 → 已结项（v1.1 C2）
    if "已归档" in [x for x in ob_project_states if x]:
        return "已结项", "履约义务「项目状态」=已归档（ONES 字段 _Gvi8gt9w）"
    has_archive = "验收文件已归档" in states
    has_delivery = "交付邮件已归档" in states
    has_handover = "验收文件交接中" in states
    is_advance = _ADVANCE_HINT in project_name
    is_poc = "POC" in (project_name or "").upper()

    # ② 履约义务结论（优先）
    # 口径校准自 Rex 5 个参考项目实测（PRD §0.1）：
    #   2066 验收文件交接中 → 已交付未验收；0858 交付邮件已归档 → 已交付未验收；
    #   2598 交接中+交付邮件 → 已交付未验收（优先于「可结项」）；
    #   1641 提前实施+已完成交付义务 → 已交付未关联签约合同；
    #   2727 POC+已完成义务 → 可结项
    if has_archive:
        return "已交付已验收", "履约义务含「验收文件已归档」"
    if is_advance and has_delivery:
        return "已交付未关联签约合同", "项目名含「提前实施」；履约义务含「交付邮件已归档」"
    if is_advance and "已完成" in states and project_status != "已完成":
        return "已交付未关联签约合同", (
            f"项目名含「提前实施」；存在已完成交付义务且无验收归档（项目状态={project_status}）")
    if has_handover or has_delivery:
        return "已交付未验收", "履约义务含「验收文件交接中/交付邮件已归档」"
    if is_poc and "已完成" in states:
        return "可结项", "POC 项目且存在已完成履约义务（无验收/交付待办）"
    if "实施未开始" in states:
        return "待实施", "履约义务含「实施未开始」"
    # ③ 义务无结论 → 回退项目状态字段
    if project_status == "验收完成":
        return "已交付已验收", "项目状态=验收完成（履约义务无验收特征，回退项目状态）"
    if project_status == "已完成":
        # v1.5（Rex 2026-11-24 对照反推）：项目状态「已完成」本身即为终态。
        #   实证 887594：SSXM-2021-0922-2638 项目状态=已完成、无履约义务记录，
        #   Rex 实批引用之（原判定因「无交付归档」落「进行中」被终态过滤剔除）。
        return "可结项", ("项目状态=已完成；履约义务含「交付邮件已归档」" if has_delivery
                          else "项目状态=已完成（履约义务无验收特征，回退项目状态）")
    return "进行中", f"项目状态={project_status or '—'}（履约义务无结论，回退项目状态）"


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
           product_categories: Sequence[str] = (),
           pm_source: str = "project") -> Optional[RefProject]:
    try:
        status = ones_client.project_status(uuid)
        tasks = ones_client.project_tasks(uuid)
    except Exception as exc:  # noqa: BLE001 - 单项目失败显式留证
        raise RefsError("ONES 查询失败 %s: %s" % (code, exc)) from exc

    ob_states: List[str] = []
    ob_project_states: List[str] = []
    ob_items: List[str] = []
    for t in tasks:
        if (t.get("issueType") or {}).get("name") != OBLIGATION_ISSUE_TYPE:
            continue
        ob_states.append(str((t.get("status") or {}).get("name") or ""))
        ps = t.get("_Gvi8gt9w")
        if isinstance(ps, dict) and ps.get("value"):
            ob_project_states.append(str(ps["value"]).strip())
        ob_items.append(str(t.get("name") or ""))

    # v1.5：ONES「客户信息」任务原文（用于区分「签约主体/代理商」与「最终用户」）
    cust_info = ""
    for tk in tasks:
        if (tk.get("issueType") or {}).get("name") == "客户信息":
            cust_info = str(tk.get("name") or "").strip()
            break
    if not cust_info:
        for tk in tasks:
            v = str(tk.get("_RnWqUALs") or "").strip()
            if v:
                cust_info = v
                break

    # v1.5：ONES「产品信息」任务名（部分项目无履约义务，产品信息是唯一匹配源；
    #   实证 887594 的 SSXM-2021-0922-2638 仅 3 个任务：项目信息/产品信息/客户信息）
    prod_items = [str(tk.get("name") or "").strip() for tk in tasks
                  if (tk.get("issueType") or {}).get("name") == "产品信息"]

    period, evid = ones_client.license_period(tasks)
    label, basis = _status_label(name, status, ob_states, ob_project_states)
    # 参考项目对应项目经理
    #   v1.5（Rex 2026-11-24 批注反推，**全流系统一**）：项目「项目负责人」project.assign。
    #   实证：Rex 实批 820 的指派对象（张辉/程涛/牛素芹/王文博）= 其引用项目的 project.assign。
    #   旧「履约义务 owner/assign 计数」会误取子任务执行人（潘天功/张志超等），已废弃。
    try:
        if pm_source == "project":
            pm, pm_basis = ones_client.project_pm_owner(uuid)
        else:
            pm, pm_basis = ones_client.project_pm(uuid)
    except Exception:  # noqa: BLE001 - PM 缺失不阻塞主流程
        pm, pm_basis = "", "（查询失败，未取到）"
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
        obligation_project_states=ob_project_states,
        obligation_names=ob_items,
        # v1.5：匹配源 = 履约义务名 + 产品信息名（后者补「无义务」项目的缺口）
        matched_products=_matched(list(ob_items) + list(prod_items), keys),
        pm=pm, pm_basis=pm_basis,
        source=source,
        customer_info=cust_info,
        product_info=[x for x in prod_items if x],
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

    # 1) OA 项目编号 → 作为**候选**直查（不当作参考结论）
    #    实证（Rex 手工批注 2026-11-19）：885576/885673 的 OA「项目编号」填的是
    #    **本期新建项目**（SSXM-2026-1112-3082/3083，与申请日同期），Rex 批注
    #    引用的却是更早的终态项目（2476/4149）。故该字段仅作候选，
    #    与名称候选同池，由统一选取口径（终态/同期排除/每类型取1）裁决。
    if project_code and str(project_code).startswith("SSXM-"):
        p = ones_client.project_by_code(project_code)
        if p:
            r = _build(project_code, p["uuid"], p.get("name") or "", final_user,
                       product_codes, "direct", product_names, product_categories)
            if r:
                refs.append(r)
        else:
            notes.append("OA 项目编号 %s 在 ONES 未找到" % project_code)

    # 2) v1.5：检索口径统一为**双路（义务名 + 项目名）长词**（与 v1.3/v13 同款）。
    #    · 义务名跨项目检索：项目名常不含客户名（实证 887726 的 2963、
    #      887581 Rex 引用的 1766/3952 义务名含「上汽通用五菱」而项目名只有「五菱」）；
    #    · 仅用长词（≥4）：3 字短词已证实张冠李戴（887594「北京东」→北京东大正保、
    #      887597「上海新」→上海新晨、887581「上汽通」→上汽通用汽车金融），故弃用。
    # v1.5：类型**不再作硬过滤**（实证 887594 Rex 引用 2638，其项目名无「POC」字样却被
    #   写作「历史提前实施项目」；887597/887581 亦跨类型引用）。类型仅作排序偏好。
    type_pref = _TYPE_SCOPE.get(workflow_id, ())
    seen_codes: set = {r.code for r in refs}
    probes = _search_tokens_long(final_user, customer)
    try:
        cands = _collect_candidates(probes=probes, final_user=final_user,
                                    customer=customer, project_code="")
    except Exception as exc:  # noqa: BLE001 - 单路失败降级，不伪造
        notes.append("ONES 候选检索失败: %s" % exc)
        cands = {}
    if not probes:
        notes.append("检索词为空（最终用户/客户名缺失），无法检索 ONES")
    for code, meta in sorted(cands.items()):
        nm = meta.get("name") or ""
        uuid = meta.get("uuid") or ""
        if not code or code in seen_codes:
            continue
        try:
            r = _build(code, uuid, nm, final_user, product_codes, "candidate",
                       product_names, product_categories)
        except RefsError as exc:
            notes.append(str(exc))
            continue
        if r:
            seen_codes.add(code)
            refs.append(r)

    # v1.5：客户归属一致性校验（防张冠李戴）。实证 887569：检索召回
    #   SSXM-2023-0727-1560（义务名含「伊利」但 ONES 客户信息=「内蒙古奥创科技」），
    #   若直接采用即把别家客户项目当参考。不符者剔除并留证（全不符则保留供人工判断）。
    # v1.5：仅标注「客户归属不符」供人工参考，不剔除（理由见 _customer_consistent）
    _mark_customer_mismatch(refs, final_user, customer, probes, notes)

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

    # 过滤后候选（兜底「已结项」只用同产品候选，v1.1 C2）
    all_refs = list(refs)

    # 统一选取口径（OA 直给编号与名称候选**同一条路径**，不得绕过）
    refs = _select(refs, apply_date, notes, refs_all=all_refs, type_pref=type_pref)

    # v1.5（Rex 2026-11-24 批注反推）：**全流系统一**做 PM 团队校验。
    #   PM 已由 _build(pm_source="project") 取「项目负责人」project.assign；
    #   此处按 ONES 组织架构判定其是否属项目经理团队，供渲染/指派层使用。
    if refs:
        try:
            check_pm_team(refs, notes)
        except Exception as exc:  # noqa: BLE001 - 校验失败不阻断主流程
            notes.append("PM 团队校验不可用（%s），指派归属待人工确认" % exc)

    if not refs:
        notes.append("ONES 未匹配到最终客户「%s」相关项目（需人工确认本期项目编号）"
                     % (final_user or "—"))
    return refs, notes


# 「已结项」**不作常规终态**，仅作**兜底**——实证校准（v1.1 C2，8 单全拟合）：
#   - 885576：v1.0 终态候选空（3082 可结项被同期排除）→ Rex 引已结项 2476；
#   - 885673：v1.0 终态候选空（3083 被同期排除）→ Rex 引已结项 4149；
#   - 886362：有 2066（已交付未验收）→ Rex **只引 2066**，未引已结项的 0449；
#   - 886448：有 3925（已交付已验收）→ Rex **只引 3925**，未引已结项的 3835。
#   ⇒ 语义：已结项项目已关闭、参考意义最低；仅当**无任何其他终态候选**时才兜底引用。
# ═══════════════════════════════════════════════════════════════
# v1.3（Rex 2026-11-24，**仅 wf_916 销售合同下单**）
#   C8  实时全量履约义务查询 → 项目维度聚合（项目名常不含客户名）
#   C9  匹配优先级：同客户+同产品（含相似） > 仅同客户（标「同客户项目」）
#   C10 未结项优先（项目履约义务「项目状态」≠已归档），无则回退已结项
#   815/820 仍走 find_reference_projects()（v1.2），互不影响
# ═══════════════════════════════════════════════════════════════

_MATCH_PRODUCT = "product"              # 同客户 + 产品命中/相似
_MATCH_CUSTOMER_ONLY = "customer_only"  # 仅同客户（反馈中标注「同客户项目」）
_FUZZY_MIN = 3                          # 中文最长公共子串阈值（产品相似判定）
_TYPE_ORDER_V13 = {"签约项目": 0, "提前实施项目": 1, "POC项目": 2}


def _lcs_len(a: str, b: str) -> int:
    """最长公共子串长度（产品「相似」判定用；纯函数，无外部依赖）。"""
    if not a or not b:
        return 0
    if len(a) > len(b):
        a, b = b, a
    best = 0
    # 经典 DP，滚动数组（避免长文本 O(n*m) 内存爆掉）
    prev = [0] * (len(a) + 1)
    for cb in b:
        cur = [0]
        for i, ca in enumerate(a, 1):
            if ca == cb:
                v = prev[i - 1] + 1
                if v > best:
                    best = v
                cur.append(v)
            else:
                cur.append(0)
        prev = cur
    return best


def _fuzzy_hit(keys: Sequence[str], texts: Sequence[str]) -> List[str]:
    """相似命中：检索词与文本的最长公共子串 ≥ 阈值（覆盖「应用加固」vs「Android应用加固」类差异）。"""
    hits = []
    for k in keys:
        if not k:
            continue
        for tx in texts:
            if not tx:
                continue
            if k in tx or _lcs_len(k, tx) >= _FUZZY_MIN:
                hits.append(k)
                break
    return sorted(set(hits))


def _collect_candidates(
    *,
    probes: Sequence[str],
    final_user: str,
    customer: str = "",
    project_code: str = "",
) -> Dict[str, Dict[str, Any]]:
    """C8：两路取候选项目，合并去重（code → {uuid,name}）。

    路径 A（义务名）：遍历检索词实时查全部相关任务 → 过滤履约义务 → 按所属项目聚合。
      实证 887726：项目名不含「黄河财产保险」，仅义务名含 → 只有此路能命中 2963。
    路径 B（项目名）：`projects(name_match)` → 覆盖「项目名即客户名」的项目
      （实证 887728 的 SSXM-2026-1111-3074，其义务名不含客户名）。
    命中校验：项目名或义务名任一含检索词即可（防止 name_match 宽泛误配）。
    """
    cands: Dict[str, Dict[str, Any]] = {}
    probes = [x for x in probes if x]

    def _add(code: str, uuid: str, name: str, blob: str) -> None:
        if not code or not uuid or not name:
            return
        if not any(k in blob for k in probes):
            return
        if code not in cands:
            cands[code] = {"uuid": uuid, "name": name}

    for key in probes:
        try:
            obs = ones_client.search_obligations(key)
        except Exception:  # noqa: BLE001 - 单词失败降级（调用方汇总留证）
            obs = []
        for ob in obs:
            if (ob.get("issueType") or {}).get("name") != OBLIGATION_ISSUE_TYPE:
                continue
            proj = ob.get("project") or {}
            nm = str(proj.get("name") or "")
            _add(_code_of(nm), str(proj.get("uuid") or ""), nm,
                 nm + " " + str(ob.get("name") or ""))
        try:
            for pr in ones_client.search_projects(key):
                nm = str(pr.get("name") or "")
                _add(_code_of(nm), str(pr.get("uuid") or ""), nm, nm)
        except Exception:  # noqa: BLE001
            pass

    # OA 项目编号：作为候选直入（不当结论，见 v1.2 说明）
    if project_code and str(project_code).startswith("SSXM-"):
        if project_code not in cands:
            try:
                pj = ones_client.project_by_code(project_code)
            except Exception:  # noqa: BLE001
                pj = None
            if pj and pj.get("uuid"):
                cands[project_code] = {"uuid": pj["uuid"], "name": pj.get("name") or ""}
    return cands


def _customer_consistent(r: "RefProject", final_user: str, customer: str,
                         probes: Sequence[str]) -> bool:
    """v1.5：候选客户归属是否与「最终用户/客户」一致（防张冠李戴，不剔除只降权）。

    判定（任一成立即一致）：
      · ONES「客户信息」== 最终用户或客户；
      · 去公司后缀后的核心名有 ≥4 字公共子串（集团简称情形，如「五菱」）；
        **必须去后缀**，否则「有限公司」等通用字样会让任意两家公司判为一致
        （实证 887569：奥创 vs 伊利 因共有「有限公司」被误判一致）；
      · 项目名含任一长检索词。
    实证：887569 候选 SSXM-2023-0727-1560 客户信息=「内蒙古奥创科技有限公司」，
      核心名「内蒙古奥创科技」与「内蒙古伊利实业集团」公共子串仅「内蒙古」(3<4)
      且项目名不含长词 → 判不一致（仅标注留证）。

    ⚠️ v1.5 复核：**不作剔除、不作排序惩罚**。Rex 实批 887581 亲自引用了
      「客户信息」为华为云计算/怀来软通动力的项目（1766/3952/1934）——这些是
      最终用户经第三方交付的项目，Rex 的取舍看项目名而非该字段。故该字段
      只作提示，不参与裁决（避免把 Rex 会引的项目误删）。
    """
    ci = (r.customer_info or "").strip()
    fu = (final_user or "").strip()
    cu = (customer or "").strip()
    if ci and (ci == fu or ci == cu):
        return True
    if ci:
        cci, cfu = _core_name(ci), _core_name(fu)
        ccu = _core_name(cu) if cu else ""
        if _lcs_len(cci, cfu) >= 4 or (ccu and _lcs_len(cci, ccu) >= 4):
            return True
    return any(p and p in (r.name or "") for p in probes)


def _mark_customer_mismatch(refs: List["RefProject"], final_user: str,
                            customer: str, probes: Sequence[str],
                            notes: List[str]) -> None:
    bad = [r for r in refs if not _customer_consistent(r, final_user, customer, probes)]
    for r in bad:
        r.customer_mismatch = True
    if bad:
        notes.append("客户归属不符（降权，未剔除）：%s（客户信息=%s）"
                     % ("、".join(r.code for r in bad),
                        "；".join((r.customer_info or "—")[:14] for r in bad)))


def _classify(refs: List[RefProject], product_keys: Sequence[str]) -> None:
    """C9：标记匹配层级（就地写 match_level / matched_products）。

    产品命中 = 检索词（编码/名称/类别）包含于义务名 **或** 与义务名相似（LCS≥3）。
    """
    keys = [k for k in product_keys if k]
    for r in refs:
        exact = _matched(r.obligation_names, keys)
        fuzzy = _fuzzy_hit(keys, r.obligation_names) if keys else []
        hits = sorted(set(exact + fuzzy))
        r.matched_products = sorted(set(list(r.matched_products) + hits))
        r.match_level = _MATCH_PRODUCT if hits else _MATCH_CUSTOMER_ONLY


PM_TEAM_DEPARTMENTS = (
    "大客户服务部", "南区客户服务部", "北区客户服务部", "项目管理部",
)


def check_pm_team(refs: List[RefProject], notes: Optional[List[str]] = None) -> None:
    """v1.4（Rex 2026-11-24 第1点）：校验参考项目 PM 是否属**项目经理团队**。

    判定源：ONES 配置中心-组织架构（``users(filter:{name_match}) { departments{name} }``）。
      · 命中 PM_TEAM_DEPARTMENTS → pm_in_team=True
      · 有部门但不在 PM 团队 → pm_in_team=False，标注「非项目经理团队」（如交付技术部）
      · ONES 未收录该人（无部门）→ 无法判定，标注待人工确认（不伪造、不默认通过）

    就地写 pm_in_team / pm_team_note；notes 仅记录全局性说明。
    """
    for r in refs:
        who = (r.pm or "").strip()
        if not who:
            continue
        try:
            deps = ones_client.user_departments(who)
        except Exception as exc:  # noqa: BLE001 - 组织架构不可用显式留证
            r.pm_team_note = "组织架构查询失败（%s），PM 团队归属待人工确认" % exc
            continue
        r.pm_depts = list(deps)
        if not deps:
            r.pm_team_note = ("ONES 组织架构未收录「%s」，无法判定 PM 团队归属，待人工确认"
                              % who)
            continue
        r.pm_in_team = bool(set(deps) & set(PM_TEAM_DEPARTMENTS))
        if r.pm_in_team:
            hit = sorted(set(deps) & set(PM_TEAM_DEPARTMENTS))
            r.pm_team_note = "PM 团队（%s）" % "、".join(hit)
        else:
            r.pm_team_note = ("非项目经理团队（%s）——不得作为指派依据，需人工确认实际 PM"
                              % "、".join(deps))


def find_reference_projects_v13(
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
    """v1.3 参考项目定位（C8/C9/C10）。**仅 wf_916 调用**。

    Returns: (refs, notes)。notes 记录缺失/降级原因（不伪造）。
    """
    notes: List[str] = []
    # v1.5：仅用长词（≥4）检索，避免 3 字短词把同名集团别家公司灌入候选
    probes = _search_tokens_long(final_user, customer)
    cands = _collect_candidates(probes=probes, final_user=final_user,
                                customer=customer, project_code=project_code)

    refs: List[RefProject] = []
    failed = 0
    for code, meta in sorted(cands.items()):
        try:
            # v1.4（Rex 2026-11-24）：916 取项目「项目负责人」project.assign
            r = _build(code, meta["uuid"], meta["name"], final_user, product_codes,
                       "candidate", product_names, product_categories,
                       pm_source="project")
        except RefsError:
            failed += 1
            continue
        if r:
            r.closed = "已归档" in [x for x in r.obligation_project_states if x]
            refs.append(r)
    if failed:
        notes.append("v13 候选项目 ONES 查询失败 %d 个（已跳过，其余照常）" % failed)

    # v1.5：客户归属一致性校验（同 v1.2，防张冠李戴）
    # v1.5：仅标注「客户归属不符」供人工参考，不剔除（理由见 _customer_consistent）
    _mark_customer_mismatch(refs, final_user, customer, probes, notes)

    # v1.5：排除「同期新建」项目（编号日期 ≥ 本单申请日，**严格**）。
    #   实证 887722 的 3182、887719 的 3186、887717 的 3185、887594 的 3188、
    #   887610 的 3184、887597 的 3180、887636 的 3178（均为本单同期新建，Rex 实批未引用）。
    if apply_date and refs:
        keep = [r for r in refs if not (_code_date(r.code) >= apply_date)]
        if len(keep) < len(refs):
            notes.append("排除同期新建项目 %d 个（编号日期 ≥ 申请日 %s）"
                         % (len(refs) - len(keep), apply_date))
        refs = keep

    keys = [k for k in list(product_codes) + list(product_names)
            + list(product_categories) if k]
    _classify(refs, keys)

    # C10（v1.5 校准）：「未结项优先」由硬剔除降为**排序键**。
    #   Rex 2026-11-24 实批 887722 同时引用**已结项**的 2504(POC) + 2521(签约)，
    #   而未引任何未结项候选 → 证明已结项项不可静默丢弃。现全部保留、未结项靠前，
    #   由人取舍（不截断）。
    n_closed = sum(1 for r in refs if r.closed)
    if n_closed and len(refs) > n_closed:
        notes.append("未结项优先：%d 个未结项排前，%d 个已结项附后（均列出，供取舍）"
                     % (len(refs) - n_closed, n_closed))
    elif n_closed:
        notes.append("候选均为已结项项目（%d 个，按新鲜度排序）" % n_closed)

    # v1.4：PM 团队校验（仅 916 链路）
    check_pm_team(refs, notes)

    # 排序（**不截断**，人工取舍）：
    #   匹配层级 → **新鲜度(新→旧)** → 类型 → 状态rank → 命中数 → 编号
    # v1.5（Rex 2026-11-24 实批反推）：同级同客户下**新鲜度优先于状态/类型**。
    #   实证 887722 Rex 引 2504(POC,2026-09) + 2521(签约,2025-08)，未引大量 2020-2023
    #   的「进行中」旧项目；887719 只引 3611(2025) 不引 2854(2021)。
    refs.sort(key=lambda r: (
        0 if r.match_level == _MATCH_PRODUCT else 1,
        0 if not r.closed else 1,          # 未结项优先（v1.5：排序键，不剔除）
        -_code_epoch(r.code),
        _TYPE_ORDER_V13.get(project_type(r.name), 9),
        _RANK.get(r.status_label, 9),
        -len(r.matched_products),
        r.code,
    ))
    if refs:
        n_co = sum(1 for r in refs if r.match_level == _MATCH_CUSTOMER_ONLY)
        if n_co:
            notes.append("匹配层级：%d 个产品命中，%d 个仅同客户（已标注「同客户项目」）"
                         % (len(refs) - n_co, n_co))

    if not refs:
        notes.append("ONES 未匹配到最终客户「%s」相关履约义务（需人工确认本期项目编号）"
                     % (final_user or "—"))
    return refs, notes


def pm_departments(pm: str) -> tuple[List[str], bool]:
    # ⚠️ 已弃用（v1.4）：PM 口径改由「项目负责人 + PM 团队校验」承担
    #   （check_pm_team / project_pm_owner）。保留仅为向后兼容，CLI 已不再调用。
    """v1.3 C11：参考项目 PM 所属团队（ONES 配置中心-组织架构）。

    Returns: (部门名列表, 是否可用)。ONES 不可用 / 未收录 → ([], False)，
    调用方按非南区处理并标注待人工确认（不伪造部门）。
    """
    name = (pm or "").strip()
    if not name:
        return [], False
    try:
        deps = ones_client.user_departments(name)
    except Exception:  # noqa: BLE001 - 组织架构不可用显式降级
        return [], False
    return list(deps), True

_TERMINAL = {"已交付未验收", "已交付未关联签约合同", "可结项", "已交付已验收"}
_FALLBACK = {"已结项"}
_RANK = {
    "已交付未验收": 0, "已交付未关联签约合同": 0,
    "可结项": 1, "已交付已验收": 2,
}


def _select(
    refs: List[RefProject], apply_date: str, notes: List[str],
    refs_all: Optional[List[RefProject]] = None,
    type_pref: Sequence[str] = (),
    max_per_type: int = 2,
) -> List[RefProject]:
    """选取口径（校准自 Rex 4 条批注，PRD §0.1）。

    Args:
        refs_all: 产品过滤后的候选全集（兜底「已结项」用；缺省取 refs）。

    a) 只引**常规终态**项目（已交付未验收/已交付未关联签约合同/可结项/已交付已验收）；
       「已结项」仅作兜底（见 _TERMINAL 上方说明，v1.1 C2 校准）；
       「进行中/待实施」不引（886362 未引进行中的 0449，886368 未引待实施的 3139）。
       注意：**不能回退**——候选全是非终态时结果为空，由渲染层提示人工确认，
       而不是硬引一个「待实施」项目（实测 885755 曾直引 SSXM-2026-1116-3099）。
    b) 排除**同期新建**项目（编号日期 ≥ 本单申请日，严格）。
    c) 同类型最多取 max_per_type 个（默认 2；v1.5 校准自 Rex 实批 887714/887610）。
    """
    if not refs:
        return refs

    orig = list(refs)                      # 过滤前候选（兜底数据源）
    if refs_all is None:
        refs_all = orig

    keep = [r for r in refs if r.status_label in _TERMINAL]
    if len(keep) < len(refs):
        notes.append("仅保留终态项目：%d 个候选 → %d 个（剔除进行中/待实施）"
                     % (len(refs), len(keep)))
        refs = keep

    if refs and apply_date:
        # v1.5 复核：**严格**按编号日期排除（≥ 申请日即视为本单同期新建）。
        #   曾试「有交付结论则保留」，实证反而把本单同期项放回（887636 的 3178、
        #   887597 的 3180、887610 的 3184、887594 的 3188——Rex 实批均不引用），故回退。
        #   代价：887717 的 SSXM-2026-1029-2905（日期晚于申请日 7 天但被 Rex 引用）不再出现，
        #   属可接受偏差（该单仍给出 Rex 实引的 2714/3115）。
        keep = [r for r in refs if not (_code_date(r.code) >= apply_date)]
        if len(keep) < len(refs):
            notes.append("排除同期新建项目 %d 个（编号日期 ≥ 申请日 %s）"
                         % (len(refs) - len(keep), apply_date))
            refs = keep

    # 兜底（v1.1 C2）：**常规终态候选被过滤/同期排除干净后**，才回退引「已结项」
    # （兜底同样遵守同期排除，避免引到本单同期新建项目）
    if not refs:
        fb = [r for r in refs_all if r.status_label in _FALLBACK
              and not (apply_date and _code_date(r.code) >= apply_date)]
        if fb:
            notes.append("无常规终态候选，回退引已结项项目（%d 个）" % len(fb))
            refs = fb

    if not refs:
        return refs

    # v1.5（Rex 批注反推）：同级同类型下优先**最近**项目。
    #   实证：887618 Rex 取 2787(2026-10) 而非 1862(2024-07)；887610 取 3425/3426(2025-11)
    #   而非 1242(2024-05)；887719 只要 3611(2025) 不引 2854(2021)。
    #   新鲜度按编号日期倒序（_code_date 越大越前）。
    # 两次稳定排序：先按新鲜度倒序（新→旧），再按主键覆盖；
    # 稳定排序保证主键相同的组内保持「新→旧」。
    # v1.5：类型偏好为首位（符合流程口径的项目类型优先，但不剔除其他类型）；
    #   **类型内部新鲜度优先于状态 rank**——Rex 实批反推：
    #   · 887610 引 3425/3426（2025-11，已交付已验收）而非 1902/1851（2021-22，可结项）；
    #   · 887588 引 3519（2025-11，已交付已验收）而非更早的可结项旧项；
    #   · 887719 只引 3611（2025）不引 2854（2021）。
    refs.sort(key=lambda r: (
        0 if project_type(r.name) in type_pref else 1,
        -_code_epoch(r.code),
        _RANK.get(r.status_label, 9),
        -len(r.matched_products),
        r.code,
    ))
    # v1.5：每类型最多取 max_per_type 个（校准自 Rex 实批：887714 引 0918+0831 两个
    #   签约项目、887610 引 3425+3426 两个签约项目 → 旧「每类型 1 个」过严）。
    picked: List[RefProject] = []
    seen_types: Dict[str, int] = {}
    for r in refs:
        ty = project_type(r.name)
        if seen_types.get(ty, 0) >= max_per_type:
            continue
        seen_types[ty] = seen_types.get(ty, 0) + 1
        picked.append(r)
    if len(picked) < len(refs):
        notes.append("同类型最多取最相关 %d 个：%d 个候选 → %d 个（类型：%s）"
                     % (max_per_type, len(refs), len(picked),
                        "、".join(sorted(seen_types))))
    return picked


def _code_date(code: str) -> str:
    """从 SSXM-YYYY-MMDD-NNNN 提取日期（用于排除本单同期新建项目）。

    实测编号格式：SSXM-2026-1119-3139 → 2026-11-19（**MMDD 合并**，
    不是 YYYY-MM-DD）。旧正则按 YYYY-MM-DD- 匹配，永远落空返回 ""，
    使「同期新建排除」成为死代码（2026-11-19 实测发现）。
    解析不出时返回 ""（视为不晚于申请日，保守保留）。
    """
    import re as _re
    m = _re.search(r"SSXM-(\d{4})-(\d{2})(\d{2})-", code or "")
    if not m:
        return ""
    y, mm, dd = m.groups()
    return "%s-%s-%s" % (y, mm, dd)


def _code_epoch(code: str) -> int:
    """编号日期转整数（YYYYMMDD），用于「新→旧」主序键。解析不出返回 0（最旧）。"""
    m = re.search(r"SSXM-(\d{4})-(\d{2})(\d{2})-", code or "")
    return int("%s%s%s" % m.groups()) if m else 0


def _code_of(name: str) -> str:
    """从项目名提取 SSXM 编号（与权威源脚本 code_of 同口径）。"""
    import re
    m = re.search(r"【(SSXM-[0-9\-]+)】", name or "")
    return m.group(1) if m else ""
