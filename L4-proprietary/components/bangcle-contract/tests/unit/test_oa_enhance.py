"""OA 审查增强（R1 履约义务）单元/集成测试。

原则：真实数据，禁止 mock；外部依赖不可用 → pytest.skip 显式留证（不伪 pass）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

COMPONENT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = COMPONENT_ROOT.parents[2]  # workspace 根
RAW_DIR = REPO_ROOT / "tmp" / "oa-pif" / "raw"
sys.path.insert(0, str(COMPONENT_ROOT))

from services.oa.enhance.oa_form import parse_order_form, OrderFormError  # noqa: E402
from services.oa.enhance import ones_obigation  # noqa: E402



def _need(path: Path, why: str):
    if not path.exists():
        pytest.skip("环境不满足：%s（%s）" % (why, path))


# ---------------------------------------------------------------
# oa_form：真实 886377 原始 XHR
# ---------------------------------------------------------------
def test_oa_form_parse_real_886377():
    _need(RAW_DIR / "886377" / "xhrs.json", "886377 原始捕获")
    form = parse_order_form(RAW_DIR, "886377")
    assert form.end_user == "海通恒信国际融资租赁股份有限公司"
    assert form.estimate_billid == "9955"
    assert form.estimate_flow_requestid == "885969"
    assert len(form.items) == 3
    codes = [i.product_code for i in form.items]
    assert codes == [
        "SP-AAP-7.0-SAPLV-PLUS",
        "SP-IAP-4.0-SAPLV",
        "SP-SDKP-7.0-SAPLV",
    ]
    amounts = [i.amount for i in form.items]
    assert [str(a) for a in amounts] == ["20000.00", "20000.00", "24000.00"]
    assert all(i.estimate_billid == "9955" for i in form.items)


def test_oa_form_missing_file():
    with pytest.raises(OrderFormError):
        parse_order_form(RAW_DIR, "999999999")


# ---------------------------------------------------------------
# R1：BDMS 项目编码定位（只读）
# ---------------------------------------------------------------
def test_r1_locate_project_codes_real():
    db = ones_obigation._bdms_path()
    _need(db, "BDMS 库")
    codes = ones_obigation.locate_project_codes("海通恒信国际融资租赁股份有限公司", "")
    assert "SSXM-2025-1111-3440" in codes


# ---------------------------------------------------------------
# R1：ONES 实时（依赖 Chrome ONES 登录态；不可用则 skip）
# ---------------------------------------------------------------
# ---------------------------------------------------------------
# R1 降级门禁（fail-closed：verdict=未知 必须标 degraded）
# ---------------------------------------------------------------
def test_r1_unknown_is_degraded():
    """2026-11-19 实测缺陷回归：ONES 查询层失效时 R1 静默变「未知」且无降级标记。"""
    from services.oa.enhance.ones_obigation import R1Result
    from services.oa.enhance.runner import _r1_degraded

    assert _r1_degraded(R1Result(verdict="未知")) is True
    assert _r1_degraded(R1Result(verdict="正常")) is False
    assert _r1_degraded(R1Result(verdict="提示")) is False
    assert _r1_degraded(R1Result(verdict="异常")) is False


def _ones_available() -> bool:
    """ONES 数据源可用性探测（复用权威源脚本的 CDP 探测）。

    红线（USER.md 2026-11-19）：禁止 osascript 驱动用户当前 Chrome。
    现统一走专用实例 CDP 9333 + localStorage 登录态；不可用即 skip
    （「数据源不可用」不得当作正常测试结果，AGENTS.md 降级红线）。
    """
    import importlib.util, sys
    from pathlib import Path as _P

    script = (
        _P(__file__).resolve().parents[2]          # bangcle-contract/
        / ".."
        / ".."
        / "skills"
        / "ones-browser-export"
        / "scripts"
        / "oa_workflow_ones.py"
    ).resolve()
    if not script.exists():
        return False
    spec = importlib.util.spec_from_file_location("_ones_reuse_probe", script)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_ones_reuse_probe"] = mod
    spec.loader.exec_module(mod)
    return bool(mod.ones_available())


@pytest.mark.skipif(not _ones_available(), reason="ONES 实时依赖 Chrome 登录态，不可用则 skip")
def test_r1_real_886377_verdict():
    r = ones_obigation.check_obligations(
        end_user="海通恒信国际融资租赁股份有限公司",
        project_codes=["SSXM-2025-1111-3440", "SSXM-2025-1015-3068"],
        product_codes=["SP-AAP-7.0-SAPLV-PLUS"],
    )
    assert r.missing == []
    by_code = {p.project_code: p for p in r.projects}
    # 断言稳定契约（verdict），不断言具体状态串——ONES 实时状态会推进漂移
    # （2026-11-19 实测：3440 验收态由「客户确认版验收单」→「验收文件交接中」，verdict 仍=正常）
    assert by_code["SSXM-2025-1111-3440"].verdict == "正常"
    assert by_code["SSXM-2025-1015-3068"].verdict == "提示"
    sts3440 = set(by_code["SSXM-2025-1111-3440"].statuses)
    sts3068 = set(by_code["SSXM-2025-1015-3068"].statuses)
    assert sts3440 & set(ones_obigation._NORMAL), "正常判定须锚定至少一个正常状态"
    assert sts3068 & set(ones_obigation._HINT), "提示判定须锚定至少一个提示状态"
    assert r.verdict == "提示"


@pytest.mark.skipif(not _ones_available(), reason="ONES 实时依赖 Chrome 登录态，不可用则 skip")
def test_r1_unknown_end_user_missing():
    r = ones_obigation.check_obligations(
        end_user="不存在的客户XYZ", project_codes=["SSXM-9999-9999-9999"],
    )
    assert r.projects == []
    assert r.missing  # 显式留证
    assert r.verdict == "未知"


# ---------------------------------------------------------------
# R2：概算一致性（真实卡片 9955）
# ---------------------------------------------------------------
EST_RAW = REPO_ROOT / "tmp" / "oa-757" / "9955" / "xhrs.json"


def _oa_session_available() -> bool:
    state = Path.home() / ".openclaw" / "data" / "clm-oa-recon" / "state.json"
    return state.exists()


def test_r2_offline_parse_real_9955():
    """离线：用真实 9955 原始 XHR 验证解析 + 逐项比对（不依赖会话）。"""
    _need(EST_RAW, "9955 原始捕获")
    import json
    from services.oa.cube import CubeClient
    from services.oa.enhance import estimate as est

    d = json.loads(EST_RAW.read_text(encoding="utf-8"))
    raw = None
    for it in d:
        if "getDetailFields" in (it.get("url") or "") and len(it.get("body") or "") > 1000:
            raw = CubeClient._lenient_json_loads(it["body"])
            break
    assert raw is not None, "未找到 9955 明细 XHR"
    rows = est._parse_estimate_row  # 语法自检
    parsed = [est._parse_estimate_row(r) for r in raw.get("datas") or []]
    assert [p["code"] for p in parsed] == [
        "SP-AAP-7.0-SAPLV-PLUS", "SP-IAP-4.0-SAPLV", "SP-SDKP-7.0-SAPLV",
    ]
    assert [str(p["amount"]) for p in parsed] == ["20000.00", "20000.00", "20000.00"]


@pytest.mark.skipif(not _oa_session_available(), reason="R2 在线依赖 OA 会话，不可用则 skip")
def test_r2_real_9955_verdict():
    from services.oa.enhance.estimate import check_estimate
    form = parse_order_form(RAW_DIR, "886377")
    r = check_estimate(billid=form.estimate_billid, items=form.items)
    if r.skipped:
        pytest.skip("OA 会话/权限不可用: %s" % r.skipped)
    assert r.verdict == "超概算（提醒级）"
    assert str(r.total_estimate) == "60000.00"
    assert str(r.total_actual) == "64000.00"
    over = [x for x in r.rows if x.verdict == "over_budget_warn"]
    assert len(over) == 1 and over[0].product_code == "SP-SDKP-7.0-SAPLV"
    assert str(over[0].diff) == "4000.00"


@pytest.mark.skipif(not _oa_session_available(), reason="R2 在线依赖 OA 会话，不可用则 skip")
def test_r2_no_permission_degrades():
    """无权限/读不到的 billid → 显式 skipped，不伪造。"""
    from services.oa.enhance.estimate import check_estimate
    form = parse_order_form(RAW_DIR, "886377")
    r = check_estimate(billid="999999999", items=form.items)
    assert r.skipped is not None or r.verdict == "未知"
