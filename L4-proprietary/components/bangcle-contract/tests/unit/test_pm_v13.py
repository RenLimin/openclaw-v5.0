"""v1.3 口径单测（Rex 2026-11-24，仅 wf_916）：C8 聚合 / C9 匹配层级 / C10 未结项优先 / C11 组织架构指派。

纯函数 + mock ONES；不触网、不需要 Chrome。真实回放结论见
docs/VERIFICATION-oa-project-management-asset-v1.3.md。
"""
from __future__ import annotations

import sys
from pathlib import Path

COMPONENT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(COMPONENT_ROOT / "services" / "oa" / "enhance"))

from pm.order import ProjectOrder, OrderItem  # noqa: E402
from pm import ones_refs  # noqa: E402
from pm.ones_refs import (  # noqa: E402
    RefProject, _lcs_len, _fuzzy_hit, _classify, find_reference_projects_v13,
    _MATCH_PRODUCT, _MATCH_CUSTOMER_ONLY, _collect_candidates,
)
from pm.render import _pm_lead, render_remark  # noqa: E402
from pm.risk import assess  # noqa: E402


def _order(**kw) -> ProjectOrder:
    o = ProjectOrder(request_id="T1", workflow_id=kw.pop("workflow_id", "wf_916"),
                     final_user=kw.pop("final_user", "武汉丰泰科技有限责任公司"))
    for k, v in kw.items():
        setattr(o, k, v)
    return o


# ---------------- C9：产品相似匹配 ----------------
def test_lcs_basic():
    assert _lcs_len("应用加固", "Android应用加固软件V7.0") == 4
    assert _lcs_len("ABC", "XYZ") == 0
    assert _lcs_len("", "x") == 0


def test_fuzzy_hit_threshold():
    keys = ["Android应用加固软件V7.0"]
    assert _fuzzy_hit(keys, ["【云端】黄河财产保险股份有限公司-应用加固-配置加固策略"])
    # 含子串即命中（类别词短，如「加固」→ 有意保留）；负例用**非子串且 LCS<3** 的变体
    assert _fuzzy_hit(["加固"], ["iOS应用加固"])
    assert not _fuzzy_hit(["加固软"], ["Android应用加固"])   # LCS=2 < 3
    assert not _fuzzy_hit(["V7.0"], ["Android应用加固软件V8.0"])  # 版本不同


def _ref(code, name="", ob_names=(), **kw):
    return RefProject(code=code, name=name or code, project_status="已完成",
                      status_label="已交付已验收", status_basis="t",
                      obligation_names=list(ob_names), **kw)


def test_classify_product_vs_customer_only():
    a = _ref("A", "某POC", ["Android应用加固软件V7.0"])
    b = _ref("B", "某签约", ["license授权"])
    _classify([a, b], ["Android应用加固软件V7.0"])
    assert a.match_level == _MATCH_PRODUCT and a.matched_products
    assert b.match_level == _MATCH_CUSTOMER_ONLY and not b.matched_products


# ---------------- C8：两路候选聚合 ----------------
def test_collect_candidates_two_paths(monkeypatch):
    """路径 A（义务名含客户名）+ 路径 B（项目名含客户名）须合并去重。"""
    obs = [
        {"issueType": {"name": "项目履约义务"}, "name": "【子交付】合同号+黄河财产保险",
         "project": {"uuid": "u1", "name": "【SSXM-2026-1102-2963】中科信控POC"}},
        {"issueType": {"name": "工单"}, "name": "黄河财产保险-其他",
         "project": {"uuid": "uX", "name": "【SSXM-1111-0000-0000】噪声"}},
    ]
    monkeypatch.setattr(ones_refs.ones_client, "search_obligations", lambda k: obs)
    monkeypatch.setattr(ones_refs.ones_client, "search_projects",
                        lambda k: [{"uuid": "u2", "name": "【SSXM-2026-1111-3074】黄河财产保险POC"}])
    cands = _collect_candidates(probes=["黄河财产保险"], final_user="黄河财产保险")
    assert set(cands) == {"SSXM-2026-1102-2963", "SSXM-2026-1111-3074"}
    assert "SSXM-1111-0000-0000" not in cands          # 非履约义务 → 丢弃


def test_collect_candidates_drops_wide_match(monkeypatch):
    """name_match 宽泛但不含检索词 → 不得入池（防张冠李戴）。"""
    obs = [{"issueType": {"name": "项目履约义务"}, "name": "无关任务",
            "project": {"uuid": "u", "name": "【SSXM-2026-0101-0001】别的公司"}}]
    monkeypatch.setattr(ones_refs.ones_client, "search_obligations", lambda k: obs)
    monkeypatch.setattr(ones_refs.ones_client, "search_projects", lambda k: [])
    assert _collect_candidates(probes=["黄河财产保险"], final_user="黄河财产保险") == {}


# ---------------- C10：未结项优先 + 排序 ----------------
def test_v13_open_priority_over_closed(monkeypatch):
    """v1.5：已结项（_Gvi8gt9w=已归档）**不再被剔除**，仅排后（未结项靠前）。

    校准依据：Rex 2026-11-24 实批 887722 同时引用已结项的 2504(POC)+2521(签约)，
    而未引任何未结项候选 → 硬剔除会丢掉 Rex 真实使用的参考项。
    """
    monkeypatch.setattr(ones_refs.ones_client, "search_obligations", lambda k: [])
    monkeypatch.setattr(ones_refs.ones_client, "search_projects", lambda k: [])

    def fake_build(code, uuid, name, fu, codes, source, names=(), cats=(), pm_source="obligation"):
        closed = code.endswith("0002")
        return RefProject(
            code=code, name=name, project_status="已完成", status_label="已结项" if closed else "已交付已验收",
            status_basis="x", obligation_project_states=["已归档"] if closed else [],
            pm="张燕兰")

    monkeypatch.setattr(ones_refs, "_build", fake_build)
    monkeypatch.setattr(ones_refs, "_collect_candidates",
                        lambda **kw: {"SSXM-2026-0101-0002": {"uuid": "b", "name": "【SSXM-2026-0101-0002】旧项目"},
                                      "SSXM-2026-0202-0001": {"uuid": "a", "name": "【SSXM-2026-0202-0001】新项目"}})
    refs, notes = find_reference_projects_v13(final_user="测试客户", customer="测试客户")
    # v1.5：两项均保留；未结项在前，已结项附后（不截断）
    assert [r.code for r in refs] == ["SSXM-2026-0202-0001", "SSXM-2026-0101-0002"]
    assert any("未结项优先" in n and "已结项附后" in n for n in notes)


def test_v13_keeps_closed_when_only_closed(monkeypatch):
    """v1.5：仅有已结项候选时全部保留并按新鲜度排序（不得输出空）。"""
    monkeypatch.setattr(ones_refs, "_collect_candidates",
                        lambda **kw: {"SSXM-2026-0101-0002": {"uuid": "b", "name": "【SSXM-2026-0101-0002】旧项目"}})

    def fake_build(code, uuid, name, fu, codes, source, names=(), cats=(), pm_source="obligation"):
        return RefProject(code=code, name=name, project_status="已完成", status_label="已结项",
                          status_basis="x", obligation_project_states=["已归档"], pm="")
    monkeypatch.setattr(ones_refs, "_build", fake_build)
    refs, notes = find_reference_projects_v13(final_user="测试客户", customer="测试客户")
    assert len(refs) == 1 and any("候选均为已结项" in n for n in notes)


# ---------------- C11：ONES 组织架构指派 ----------------
def test_c11_south_region_maps_to_feng_gang():
    """v1.4：PM 属 PM 团队 + 南区客户服务部 → 冯刚。"""
    o = _order()
    assert _pm_lead(o, pm="张燕兰", pm_depts=["南区客户服务部", "交付中心"],
                    pm_in_team=True) == "请冯刚安排项目经理"


def test_c11_other_region_maps_to_pm():
    """v1.4：PM 属 PM 团队但非南区 → PM 本人负责。"""
    o = _order()
    assert _pm_lead(o, pm="程涛", pm_depts=["大客户服务部", "交付中心"],
                    pm_in_team=True) == "请程涛负责"


def test_v14_non_pm_team_cannot_be_assignee():
    """Rex 2026-11-24 第1点：交付技术部等执行序列**不属于**项目经理团队。

    旧口径误取子任务执行人（2087 的 assign 计数最高者潘天功=交付技术部）
    → v1.4 必须回退冯刚，不得以其为指派依据。
    """
    o = _order()
    assert _pm_lead(o, pm="潘天功", pm_depts=["交付技术部", "交付中心"],
                    pm_in_team=False) == "请冯刚安排项目经理"


def test_v14_unknown_dept_not_assumed_pm():
    """部门未收录（ONES 无该人）→ 无法判定团队 → 回退冯刚（不伪造、不默认通过）。"""
    o = _order()
    assert _pm_lead(o, pm="孙康", pm_depts=[], pm_in_team=False) == "请冯刚安排项目经理"
    assert _pm_lead(o, pm="邓旭兵", pm_depts=[], pm_in_team=False) == "请冯刚安排项目经理"


def test_v14_pm_in_team_required_even_without_depts():
    """显式标记在团队内但无部门 → 仍可派（团队校验已过）；仍按非南区分流。"""
    o = _order()
    assert _pm_lead(o, pm="牛素芹", pm_depts=[], pm_in_team=True) == "请牛素芹负责"


def test_c11_916_ignores_assigner_and_c1():
    """916 分支优先于 C1/C5：assigner/区域负责人 都不改变结论。"""
    o = _order(region_owner="冯刚")
    assert _pm_lead(o, pm="程涛", assigner="任立民", pm_depts=["大客户服务部"],
                    pm_in_team=True) == "请程涛负责"


def test_c11_815_unchanged_by_pm_depts():
    """815/820 不受 C11 影响（pm_depts 忽略，仍走 C1）。"""
    o = _order(workflow_id="wf_815", region_owner="冯刚")
    assert _pm_lead(o, pm="张梨", pm_depts=["南区客户服务部"]) == "请冯刚安排项目经理"


def test_render_916_lead_uses_pm():
    o = _order()
    txt = render_remark(o, [], [], "张燕兰", pm_depts=["南区客户服务部"],
                       pm_in_team=True)
    assert txt.startswith("请冯刚安排项目经理")


# ---------------- 风险注：916 不出多项目隔离 / 待分配 ----------------
def test_916_no_multi_project_note():
    o = _order()
    refs = [_ref("A", "甲", matched_products=["x"]), _ref("B", "乙", matched_products=["x"])]
    risks = assess(o, refs, None)
    assert not [r for r in risks if r.code == "multi_project_same_product"]


def test_815_still_has_multi_project_note():
    o = _order(workflow_id="wf_815")
    refs = [_ref("A", "甲", matched_products=["x"]),
            _ref("B", "乙", matched_products=["x"])]
    risks = assess(o, refs, None)
    assert [r for r in risks if r.code == "multi_project_same_product"]


def test_916_no_pm_unassigned_note():
    o = _order(pm="", region_owner="")
    risks = assess(o, [], None)
    assert not [r for r in risks if r.code == "pm_unassigned"]


def test_916_keeps_archive_date_and_approval_notes():
    o = _order(archive_time="")
    risks = assess(o, [], None)
    assert [r for r in risks if r.code == "archive_date"]
