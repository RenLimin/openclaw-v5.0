"""三流程 OA 单据解析单测（P2）。

数据源：``tests/fixtures/pm_886453.json`` / ``pm_886362.json`` / ``pm_886314.json``
——2026-11-19 从真实 OA 捕获（sandbox ``tmp/oa-pif/raw/<rid>/xhrs.json``）精简而来，
仅保留解析所需字段节点，**非臆造**。走完整 ``parse()`` 路径（含「取最大 body」逻辑）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

COMPONENT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(COMPONENT_ROOT / "services" / "oa" / "enhance"))

from pm.order import parse, PmAssetError  # noqa: E402
from pm.fields import resolve, infer_from_title, FieldMapError  # noqa: E402

FIX = Path(__file__).resolve().parents[1] / "fixtures"

CASES = [
    ("886453", "wf_916", "销售合同下单流程-深圳分公司-金融-曾铭-2026-11-11"),
    ("886362", "wf_815", "提前实施需求申请流程-深圳分公司-金融-曾铭-2026-11-18"),
    ("886314", "wf_820", "PoC需求申请流程-北区营销部-陈龙-2026-11-18"),
]


def _stage(fixture: Path, tmp_path: Path) -> Path:
    """把精简夹具还原成 xhrs.json 结构（parse 的真实输入形态）。"""
    f = json.loads(fixture.read_text(encoding="utf-8"))
    raw = tmp_path / f["request_id"]
    raw.mkdir(parents=True, exist_ok=True)
    xhrs = [
        {"url": "https://oa.bangcle.com/api/workflow/reqform/loadForm",
         "body": json.dumps({"maindata": f["maindata"]}, ensure_ascii=False)},
    ]
    if f.get("detail_rows"):
        xhrs.append({
            "url": "https://oa.bangcle.com/api/workflow/detailData",
            "body": json.dumps({"detail_1": {"rowDatas": f["detail_rows"]}}, ensure_ascii=False),
        })
    (raw / "xhrs.json").write_text(json.dumps(xhrs, ensure_ascii=False), encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("rid,wf,title", CASES)
def test_parse_fields(rid, wf, title, tmp_path):
    o = parse(_stage(FIX / f"pm_{rid}.json", tmp_path), rid, wf, title)
    assert o.request_id == rid
    assert o.workflow_id == wf
    assert o.applicant, "申请人不得为空"
    assert o.final_user, "最终客户不得为空"
    assert o.customer, "客户名称不得为空"
    assert infer_from_title(title) == wf
    assert o.field_semantics["approval_flow_field"]


def test_916_full( tmp_path):
    o = parse(_stage(FIX / "pm_886453.json", tmp_path), "886453", "wf_916", CASES[0][2])
    assert o.final_user == "招商永隆银行有限公司"
    assert o.customer == "深圳市艾锐迪科技有限公司"
    assert o.contract_no == "XSZS2611120892"
    assert o.contract_name == "永隆香港总行2026-2027年加固项目"
    assert o.estimate_name == "永隆银行-香港总行加固项目-2026"
    assert o.service_start == "2027-01-01" and o.service_end == "2027-12-31"
    assert o.amount == "100000.00"
    assert o.pm == ""                      # 卡出口8 待派 PM 的根因
    assert o.approval_flow == "销售合同审核流程-曾铭-2026-11-11"
    assert o.approval_flow_rid == "885637"
    assert len(o.items) == 3
    assert o.product_codes == ["SP-AAP-7.0-SAPLV-PLUS", "SP-AAP-7.0-EA-AEA021", "SP-IAP-4.0-SAPLV"]
    assert [i.product_name for i in o.items] == [
        "Android应用加固软件V7.0", "Android应用加固软件V7.0", "iOS应用加固软件V4.0"]
    assert [i.line_category for i in o.items] == ["Android应用加固", "Android应用加固", "iOS应用加固"]
    assert [i.line_type for i in o.items] == ["私有化软件", "扩展授权", "私有化软件"]


def test_815_full(tmp_path):
    o = parse(_stage(FIX / "pm_886362.json", tmp_path), "886362", "wf_815", CASES[1][2])
    assert o.final_user == "招商银行股份有限公司"
    assert o.pm == "程涛"
    assert o.region_manager == "任立民"
    assert o.estimate_name == "招商银行-手机银行加固-2026"
    assert o.approval_flow_rid == ""       # 815 无此字段
    assert len(o.items) == 1
    assert o.items[0].product_code == "SP-AAP-7.0-SAPLV-PLUS"
    assert o.items[0].product_name == "Android应用加固软件V7.0"


def test_820_full(tmp_path):
    o = parse(_stage(FIX / "pm_886314.json", tmp_path), "886314", "wf_820", CASES[2][2])
    assert o.final_user == "亳州药都农村商业银行股份有限公司"
    assert o.pm == "张铭鑫"
    assert o.amount == "12000.0"           # 千分位归一
    assert o.approval_flow_rid == ""
    assert o.items[0].product_code == "SP-MPP-3.3-PC"
    assert o.items[0].line_type == "公有云软件"


# ---------- 故障：fail-closed ----------
def test_missing_raw(tmp_path):
    with pytest.raises(PmAssetError):
        parse(tmp_path, "999999", "wf_916", "")


def test_unknown_workflow(tmp_path):
    with pytest.raises(FieldMapError):
        resolve("wf_999")


def test_no_loadform(tmp_path):
    raw = tmp_path / "886453"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "xhrs.json").write_text(json.dumps([{"url": "x", "body": "{}"}]), encoding="utf-8")
    with pytest.raises(PmAssetError):
        parse(tmp_path, "886453", "wf_916", "")


# ---------- 「取最大 body」逻辑 ----------
def test_picks_largest_loadform(tmp_path):
    """同一单多个 loadForm：必须取 body 最大者（实测 886453：402542 vs 12 字节）。"""
    raw = tmp_path / "886453"
    raw.mkdir(parents=True, exist_ok=True)
    big = json.dumps({"maindata": {"field29612": {"value": "招商永隆银行有限公司"}}}, ensure_ascii=False)
    xhrs = [
        {"url": "https://oa.bangcle.com/api/workflow/injectDev/loadFormDevFileList",
         "body": json.dumps({"maindata": {}}, ensure_ascii=False)},
        {"url": "https://oa.bangcle.com/api/workflow/reqform/loadForm", "body": big},
    ]
    (raw / "xhrs.json").write_text(json.dumps(xhrs, ensure_ascii=False), encoding="utf-8")
    o = parse(tmp_path, "886453", "wf_916", "")
    assert o.final_user == "招商永隆银行有限公司"
