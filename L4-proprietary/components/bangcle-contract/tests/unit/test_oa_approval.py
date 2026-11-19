"""OA 销售合同审批触发链回归（真实数据，禁 mock）。

覆盖：
- 固定核查 L1（body.txt）：合同编号缺失=block；服务期已明确=pass
- 固定核查 L2 无原文：三项 manual（fail-closed，不伪造）
- 固定核查 L2 有原文：甲方邮箱=block、最终用户信息表=block、版本描述=warn
- 备注渲染：block→退回补充；无 block 有 manual→退回补充（待原文）；全 pass→同意
- 待办发现：真实 OA（会话失效则 skip 留证）
- 端到端：真实 886377 全链出标准备注

依赖缺失（无 raw / 会话失效）→ pytest.skip，不伪 pass。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from services.oa.enhance.checks import run_fixed_checks
from services.oa.enhance.oa_form import OrderForm, parse_order_form
from services.oa.enhance.remark import derive_verdict, render_remark
from services.oa.enhance.todo import discover_todos

COMPONENT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = COMPONENT_ROOT.parents[2]
RAW_DIR = REPO_ROOT / "tmp" / "oa-pif" / "raw"
BODY = RAW_DIR / "886377" / "body.txt"
CONTRACT_TXT = REPO_ROOT / "tmp" / "oa-757" / "886377" / "contract.txt"


@pytest.fixture
def form():
    if not (RAW_DIR / "886377" / "xhrs.json").exists():
        pytest.skip("缺 886377 raw（未捕获）")
    return parse_order_form(RAW_DIR, "886377")


@pytest.fixture
def body():
    if not BODY.exists():
        pytest.skip("缺 886377 body.txt")
    return BODY.read_text(encoding="utf-8", errors="replace")


def _lv(checks, cid):
    return next(c.level for c in checks if c.check_id == cid)


def test_l1_form_checks(form, body):
    """L1 表单层：合同编号缺失=block；服务期已明确=pass。"""
    checks = run_fixed_checks(form, body, None)
    assert _lv(checks, "contract_no_missing") == "block"
    assert _lv(checks, "service_period") == "pass"


def test_l2_without_contract_text_is_manual(form, body):
    """无原文 → L2 三项 manual（不伪造）。"""
    checks = run_fixed_checks(form, body, None)
    for cid in ("party_a_email", "end_user_table", "version_desc"):
        assert _lv(checks, cid) == "manual", cid


def test_l2_with_contract_text(form, body):
    """有原文 → 甲方邮箱 block、最终用户信息表 block、版本描述 warn。"""
    if not CONTRACT_TXT.exists():
        pytest.skip("缺 886377 合同原文")
    text = CONTRACT_TXT.read_text(encoding="utf-8")
    checks = run_fixed_checks(form, body, text)
    assert _lv(checks, "party_a_email") == "block"
    assert _lv(checks, "end_user_table") == "block"
    assert _lv(checks, "version_desc") == "warn"


def test_verdict_derivation(form, body):
    """结论推导：block→退回补充；仅 manual→待原文；全 pass→同意。"""
    checks = run_fixed_checks(form, body, None)
    assert derive_verdict(checks) == "退回补充"
    assert derive_verdict([c for c in checks if c.level != "block"]) == "退回补充（待原文）"
    assert derive_verdict(
        [type(checks[0])(check_id="x", level="pass", message="ok")]  # noqa: SLF001
    ) == "同意"


def test_remark_format_block(form, body):
    """备注含标准结构；block 存在时结论=退回补充。"""
    checks = run_fixed_checks(form, body, None)
    md = render_remark(form, checks, {"verdict": "提示", "queried_at": "2026-11-19 11:00:00"},
                       {"verdict": "超概算（提醒级）", "total_estimate": "60000.00",
                        "total_actual": "64000.00"}, degraded=[])
    assert md.startswith("【审批建议】退回补充")
    assert "合同：海通恒信加固产品销售合同（886377" in md
    assert "退回项（需关闭后重提）：" in md
    assert "R1 履约义务：提示" in md
    assert "R2 概算一致性：超概算（提醒级）" in md


def test_discover_todos_real_oa():
    """真实 OA 待办发现（会话失效 skip 留证；0 条也算有效结果）。"""
    try:
        todos = discover_todos("757")
    except Exception as exc:  # noqa: BLE001
        pytest.skip("OA 会话不可用：%s" % exc)
    assert isinstance(todos, list)
    assert all(t.workflow_id == "757" for t in todos)


def test_end_to_end_real_886377():
    """端到端：真实 886377 全链出标准备注（ONES/OA 不可用则 skip）。"""
    from services.oa.enhance.orchestrator import run_approval

    if not (RAW_DIR / "886377" / "xhrs.json").exists():
        pytest.skip("缺 886377 raw")
    out_dir = REPO_ROOT / "tmp" / "oa-approval-e2e"
    try:
        payload = run_approval(
            raw_dir=RAW_DIR,
            out_dir=out_dir,
            request_ids=["886377"],
            contract_file=CONTRACT_TXT if CONTRACT_TXT.exists() else None,
            discover=False,
        )
    except Exception as exc:  # noqa: BLE001
        pytest.skip("端到端依赖不可用（ONES/OA）：%s" % exc)
    r = payload["results"][0]
    assert r["error"] is None, r["error"]
    assert r["remark"].startswith("【审批建议】")
    assert "R1 履约义务：" in r["remark"]
    assert "R2 概算一致性：" in r["remark"]
    assert (out_dir / "remark-886377.md").exists()
