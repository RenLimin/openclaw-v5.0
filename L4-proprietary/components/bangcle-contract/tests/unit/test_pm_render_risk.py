"""P3 纯逻辑单测：状态推断 / 风险判定 / 三段式渲染。

不触网、不需要 Chrome；构造数据遵循真实字段结构（2026-11-19 实测口径）。
"""
from __future__ import annotations

import sys
from pathlib import Path

COMPONENT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(COMPONENT_ROOT / "services" / "oa" / "enhance"))

from pm.order import ProjectOrder, OrderItem  # noqa: E402
from pm.ones_refs import RefProject, _status_label, _matched  # noqa: E402
from pm.risk import assess, render_risks  # noqa: E402
from pm.render import render_remark, _short_end, _period_text  # noqa: E402


# ---------------- 状态推断规则表 ----------------
def test_status_delivered_accepted():
    assert _status_label("某项目", "验收完成", ["验收文件已归档"])[0] == "已交付已验收"


def test_status_poc_can_close():
    # 2727 实测：项目状态=未开始；义务=实施未开始 + 已完成（授权/配置类）→ 可结项
    assert _status_label("亳州药都农村商业银行股份有限公司POC2026", "未开始",
                         ["实施未开始", "已完成"])[0] == "可结项"


def test_status_advance_no_contract():
    assert _status_label("浙江农信提前实施2026", "进行中", ["交付邮件已归档"])[0] == "已交付未关联签约合同"


def test_status_delivered_not_accepted():
    assert _status_label("招商银行2026年大前端框架项目", "进行中", ["验收文件交接中"])[0] == "已交付未验收"


def test_status_in_progress():
    assert _status_label("某项目", "进行中", ["实施未开始"])[0] == "待实施"
    assert _status_label("某项目", "进行中", [])[0] == "进行中"


def test_status_basis_present():
    label, basis = _status_label("某项目", "验收完成", ["验收文件已归档"])
    assert "验收文件已归档" in basis and "验收完成" in basis


# ---------------- 匹配 ----------------
def test_matched_products():
    assert _matched(["Android应用加固软件V7.0", "iOS加固"], ["SP-AAP-7.0-SAPLV-PLUS"]) == []
    assert _matched(["SP-AAP-7.0-SAPLV-PLUS-交付"], ["SP-AAP-7.0-SAPLV-PLUS"]) == ["SP-AAP-7.0-SAPLV-PLUS"]


# ---------------- 短日期 ----------------
def test_short_end_one_year():
    assert _short_end("2026-08-11 ~ 2027-08-14") == "27.08"


def test_short_end_short_span():
    assert _short_end("2026-11-18 ~ 2026-11-30") == "26.11.30"
    assert _short_end("2026-10-14 ~ 2026-11-14") == "26.11.14"


# ---------------- 渲染：三段式同构 Rex 批注 ----------------
def _order(wf="wf_815", pm="", final="招商银行股份有限公司"):
    return ProjectOrder(
        request_id="886362", workflow_id=wf, title="", applicant="曾铭",
        final_user=final, customer=final, pm=pm,
        items=[OrderItem(line_category="Android应用加固", product_code="SP-AAP-7.0-SAPLV-PLUS")],
    )


def test_render_single_ref_matches_rex():
    """886362 同构：请程涛负责，参考提前实施项目 SSXM-...（已交付未验收，授权/维保至27.08）。"""
    o = _order(pm="程涛")
    refs = [RefProject(code="SSXM-2026-0810-2066", name="招商银行2026年大前端框架项目",
                       project_status="进行中", status_label="已交付未验收",
                       status_basis="x", license_period="2026-08-11 ~ 2027-08-14",
                       license_task="385446", source="direct")]
    txt = render_remark(o, refs, [], pm="程涛")
    assert txt.startswith("请程涛负责，参考签约项目：")
    assert "SSXM-2026-0810-2066（已交付未验收，授权/维保至27.08）。" in txt
    print("\n--- 886362 渲染 ---\n" + txt)


def test_render_list_refs_matches_rex_886404():
    """886404 同构：列表式 + 多项目隔离注。"""
    o = _order(wf="wf_815", pm="", final="浙江农村商业联合银行股份有限公司")
    refs = [
        RefProject(code="SSXM-2026-0624-1641", name="浙江农信提前实施", project_status="进行中",
                   status_label="已交付未关联签约合同", status_basis="x",
                   license_period="2026-11-18 ~ 2026-11-30", license_task="399765",
                   matched_products=["SP-AAP-7.0-SAPLV-PLUS"], source="direct"),
        RefProject(code="SSXM-2026-0924-2598", name="上半年结算-浙江农信", project_status="进行中",
                   status_label="已交付未验收", status_basis="x", source="direct",
                   matched_products=["SP-AAP-7.0-SAPLV-PLUS"]),
    ]
    risks = assess(o, refs, None)
    txt = render_remark(o, refs, risks, pm="")
    assert "请待分配负责" in txt
    assert "1. 提前实施项目 SSXM-2026-0624-1641（已交付未关联签约合同，产品授权至26.11.30）。" in txt
    assert "2. 签约项目 SSXM-2026-0924-2598（已交付未验收）。" in txt
    assert "不允许同最终用户同产品/服务存在多个未关联签约合同的提前实施项目" in txt
    print("\n--- 886404 渲染 ---\n" + txt)


def test_render_no_refs():
    o = _order(wf="wf_820", pm="张铭鑫", final="亳州药都农村商业银行股份有限公司")
    txt = render_remark(o, [], [], pm="张铭鑫")
    assert "请张铭鑫负责，参考POC项目：" in txt
    assert "请人工确认本期项目编号" in txt


# ---------------- 风险判定 ----------------
def test_risk_pm_unassigned():
    risks = assess(_order(pm=""), [], None)
    assert any(r.code == "pm_unassigned" and r.level == "必注" for r in risks)


def test_risk_archive_date_815():
    o = _order(pm="程涛")
    risks = assess(o, [], None)
    codes = [r.code for r in risks]
    assert "archive_date" in codes and "retroactive" in codes


def test_risk_916_has_approval_risk():
    o = _order(wf="wf_916", pm="")
    o.approval_flow = "销售合同审核流程-曾铭-2026-11-11"
    o.approval_flow_rid = "885637"

    class N:
        degraded = None
        risk_levels = ["重点复核", "需补充"]
        verdict_hint = "建议谨慎签署"

    risks = assess(o, [], N())
    assert any(r.code == "approval_risk" for r in risks)


def test_risk_no_permission_degraded():
    o = _order(wf="wf_916", pm="")
    o.approval_flow_rid = "885637"

    class N:
        degraded = "无权限，需人工查看"
        risk_levels = []
        verdict_hint = ""

    risks = assess(o, [], N())
    assert any(r.code == "approval_no_permission" for r in risks)
    assert not any(r.code == "approval_risk" for r in risks)


def test_render_risks_text():
    o = _order(pm="")
    txt = render_risks(assess(o, [], None))
    assert txt.startswith("必注：")
    print("\n--- 风险文本 ---\n" + txt)


# ---------------- 选取口径：OA 直给编号也不得绕过终态过滤 ----------------
from pm.ones_refs import _select  # noqa: E402


def _ref(code, name, label, matched=None):
    return RefProject(code=code, name=name, project_status="进行中",
                      status_label=label, status_basis="测试",
                      matched_products=matched or [])


def test_select_keeps_only_terminal():
    """885755 实测：OA 直给编号指向「待实施」项目 → 必须剔除，不回退硬引。"""
    refs = [_ref("SSXM-2026-1116-3099", "4700007283", "待实施")]
    notes = []
    out = _select(refs, "", notes)
    assert out == []
    assert any("终态" in n for n in notes)


def test_select_drops_same_period_new_project():
    """排除编号日期 ≥ 本单申请日的同期新建项目。"""
    refs = [
        _ref("SSXM-2026-1119-3139", "某签约项目A", "已交付未验收"),
        _ref("SSXM-2025-0403-0858", "某签约项目B", "已交付未验收"),
    ]
    notes = []
    out = _select(refs, "2026-11-18", notes)
    assert [r.code for r in out] == ["SSXM-2025-0403-0858"]
    assert any("同期" in n for n in notes)


def test_select_one_per_type():
    """同类型只取最相关 1 个（状态 rank → 命中产品数 → 编号）。"""
    refs = [
        _ref("SSXM-2026-0924-2598", "上半年结算-浙江农信", "已交付未验收", ["SP-A"]),
        _ref("SSXM-2026-0810-2066", "浙江农信签约项目", "已交付未验收", ["SP-A", "SP-B"]),
    ]
    out = _select(refs, "", [])
    assert len(out) == 1 and out[0].code == "SSXM-2026-0810-2066"


def test_select_keeps_both_when_types_differ():
    refs = [
        _ref("SSXM-2026-0624-1641", "浙江农信提前实施", "已交付未关联签约合同"),
        _ref("SSXM-2026-0924-2598", "上半年结算-浙江农信", "已交付未验收"),
    ]
    out = _select(refs, "", [])
    assert {r.code for r in out} == {"SSXM-2026-0624-1641", "SSXM-2026-0924-2598"}


def test_code_date_parses_mmdd_merged():
    """实测编号格式 SSXM-YYYY-MMDD-NNNN（MMDD 合并），旧正则按 YYYY-MM-DD- 永不匹配。"""
    from pm.ones_refs import _code_date
    assert _code_date("SSXM-2026-1119-3139") == "2026-11-19"
    assert _code_date("SSXM-2026-0810-2066") == "2026-08-10"
    assert _code_date("SSXM-2025-0403-0858") == "2025-04-03"
    assert _code_date("bad") == ""
