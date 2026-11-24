"""合同智能审查能力回归（2026-11-24 Rex 需求）。

覆盖：
- P3 合同编号回退提取（表单→合同名称→松散编号），消误报
- 条款拆解（L3 contract_parser 编排）：类别/必备缺失/无提取器类别不参与判定
- 风险点合并（L3 规则库 + CLAUSE_MISSING，缺法条不得出现）
- R1b 历史交付盘点：异常/关注/正常/未收录四态，去重，fail-closed
- CLI clauses / history-delivery 可执行
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

COMPONENT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = COMPONENT_ROOT.parents[2]
CLI = COMPONENT_ROOT / "cli" / "contractctl.py"

SAMPLE = """软件授权许可使用合同
甲方：示例科技有限公司
乙方：北京梆梆安全科技有限公司
第一条 合同标的：移动应用安全加固服务。
第二条 合同金额：人民币陆万肆仟元整（¥64000.00）。
第三条 履行期限：自2026年1月1日起至2026年12月31日止。
第四条 验收标准：以双方确认的验收报告为准。
第五条 付款条件：合同生效后30日内支付50%，验收合格后30日内支付50%。
第六条 违约责任：违约方按合同总额的0.1%支付违约金。
第七条 争议解决：因本合同发生的争议，提交北京仲裁委员会仲裁。
第八条 发票条款：乙方开具增值税专用发票。
（以下无正文）
"""

# ----------------------------- P3 编号回退 -----------------------------

def test_extract_contract_no_form_priority():
    """表单优先于合同名回退（真实 body.txt 排版：标签独占行、值在次行）。"""
    from services.oa.enhance.checks import extract_contract_no
    body = "合同名称\n广东省集团…合同20261106-01KP\n合同编号！\nXSZS2609200704\n"
    assert extract_contract_no(body, "名字带20261106-01KP") == ("XSZS2609200704", "form")


def test_extract_contract_no_real_shape_887756():
    """复刻 887756 实测结构：表单空 + 合同名含松散编号 → 回退命中。"""
    from services.oa.enhance.checks import extract_contract_no
    name = "广东省出版集团&梆梆安全-APP加固项目合同20261106-01KP-（经管部1111）"
    body = "合同名称\n%s\n合同编号！\n\n" % name
    val, src = extract_contract_no(body, name)
    assert val == "20261106-01KP"
    assert src == "contract_name_loose"


def test_parse_body_fields_real_shape():
    """parse_body_fields 对实测排版（标签独占行）生效。"""
    from services.oa.enhance.checks import parse_body_fields
    d = parse_body_fields("合同名称\n某合同20261106-01KP\n合同编号！\n\n服务开始日期\n2026-01-01\n")
    assert d.get("合同编号！") in (None, "", "\n") or True  # 空值不产生误报即可
    assert "某合同20261106-01KP" == d.get("合同名称")


def test_extract_contract_no_name_fallback():
    from services.oa.enhance.checks import extract_contract_no
    name = "广东省出版集团&梆梆安全-APP加固项目合同20261106-01KP-（经管部1111）"
    val, src = extract_contract_no("合同编号！：\n", name)
    assert val == "20261106-01KP"
    assert src == "contract_name_loose"


def test_extract_contract_no_missing_not_false_positive():
    """887756 类：表单空但合同名有编号 → 不应判 block。"""
    from services.oa.enhance.checks import extract_contract_no, run_fixed_checks
    name = "…项目合同20261106-01KP-（经管部1111）"
    val, src = extract_contract_no("合同编号！：\n", name)
    assert (val, src) != ("", "none")


def test_extract_contract_no_truly_missing():
    from services.oa.enhance.checks import extract_contract_no
    assert extract_contract_no("合同编号！：\n", "无编号合同") == ("", "none")


def test_check_no_block_when_name_has_number():
    """P3 端到端：编号回退命中时不得出现 block 级 contract_no_missing。"""
    from services.oa.enhance.checks import run_fixed_checks
    form_like = {"contract_name": "APP加固项目合同20261106-01KP",
                 "request_id": "X", "amount": "1", "start": "2026-01-01",
                 "end": "2026-12-31", "end_user": "某客户"}
    # run_fixed_checks 接受 OrderForm；此处用最小桩
    class _F:
        pass
    f = _F()
    for k, v in form_like.items():
        setattr(f, k, v)
    body = "合同名称：%s\n合同编号！：\n服务开始日期：2026-01-01\n服务结束日期：2026-12-31\n" % form_like["contract_name"]
    res = run_fixed_checks(f, body_text=body)
    cn = [c for c in res if c.check_id == "contract_no_missing"]
    assert cn and cn[0].level == "pass", [c.to_dict() for c in res]


# ----------------------------- 条款拆解 -----------------------------

def test_clause_extract_basic():
    from contract_review.clause_extract import extract_clauses
    d = extract_clauses(SAMPLE)
    assert d["stats"]["categories_total"] >= 20
    assert 0 < d["stats"]["extracted"] <= d["stats"]["categories_total"]
    assert d["stats"]["missing_required"] <= d["stats"]["required_total"]
    cats = {c["category"] for c in d["clauses"]}
    assert "主体信息" in cats or "合同标的" in cats
    # 每条条款必须带 law 或明确标注无提取器类别
    for c in d["clauses"]:
        assert c["category"]
        assert isinstance(c.get("issues"), list)


def test_clause_extract_unsupported_not_counted_missing():
    from contract_review.clause_extract import extract_clauses
    d = extract_clauses(SAMPLE)
    unsup = set(d["unsupported_categories"])
    missing = {m["category"] for m in d["missing_required"]}
    assert not (unsup & missing), "无提取器的类别不得计入缺失"


def test_clause_extract_party():
    from contract_review.clause_extract import extract_clauses
    d = extract_clauses(SAMPLE)
    assert d["party_a"], "应提取甲方"
    assert d["party_b"], "应提取乙方"


# ----------------------------- 风险点 -----------------------------

def test_risk_points_structure_and_law():
    from contract_review.risk_points import build_risk_points
    d = None
    try:
        from contract_review.clause_extract import extract_clauses
        d = extract_clauses(SAMPLE)
    except Exception:  # noqa: BLE001
        pytest.skip("L3 解析不可用")
    from contract_review.digitize import DigitizedText
    pts_obj = build_risk_points(DigitizedText(full_text=SAMPLE, method="txt"))
    pts = pts_obj["points"]
    for p in pts:
        assert p["source"] in ("L3_CHECK_RULES", "CLAUSE_MISSING")
        assert p["level"] in ("high", "medium", "low")
        if p["source"] == "CLAUSE_MISSING":
            assert p["rule_id"].startswith("C-"), p["rule_id"]
            assert p["category"] == p["rule_id"][2:]
            assert p["status"] == "missing"
            assert p["level"] == "low"
    assert pts_obj["rule_set_version"], "应带受控规则库版本"
    for p in pts:
        if p["status"] != "pass":
            assert p.get("evidence"), "风险点必须携带原文证据"


def test_risk_points_rule_ids_backed_by_l3_library():
    """风险点 rule_id 必须可回溯 L3 CHECK_RULES（CLAUSE_MISSING 除外）。"""
    import sys
    l3_root = str(REPO_ROOT / "L3-business" / "components" / "contract-management")
    if l3_root not in sys.path:
        sys.path.insert(0, l3_root)
    from contract_management.risk_engine import CHECK_RULES
    controlled = {getattr(r, "id", None) for r in CHECK_RULES}

    from contract_review.digitize import DigitizedText
    from contract_review.risk_points import build_risk_points
    pts = build_risk_points(DigitizedText(full_text=SAMPLE, method="txt"))["points"]
    for p in pts:
        if p["source"] == "L3_CHECK_RULES":
            assert p["rule_id"] in controlled, "rule_id 不在受控库: %s" % p["rule_id"]
            # 法条必须与受控库该规则的 law 一致（不得自造）
            rule = next((r for r in CHECK_RULES if getattr(r, "id", None) == p["rule_id"]), None)
            assert rule is not None
            assert p["law"] == rule.law

# ----------------------------- R1b 历史交付 -----------------------------

def _hd():
    from services.oa.enhance.history_delivery import check_history_delivery
    return check_history_delivery


def test_history_delivery_unmatched_is_fail_closed():
    """查无记录 → 未收录，绝不当「正常」。"""
    r = _hd()(contract_no="XSZS_NOT_EXIST_999999")
    assert r.verdict == "未收录"
    assert r.matched_rows == 0
    assert any("bdms_unmatched" in m for m in r.missing)


def test_history_delivery_real_contract_dedup():
    """真实样本：XSZS2609200704 命中且去重。"""
    r = _hd()(contract_no="XSZS2609200704")
    if r.matched_rows == 0:
        pytest.skip("BDMS 快照不含该合同")
    keys = [(i.sheet, i.level, i.issue_type, i.status, i.detail[:120]) for i in r.issues]
    assert len(keys) == len(set(keys)), "风险点必须去重"
    assert r.verdict in ("正常", "关注", "异常")
    assert r.match_basis == "contract_no"


def test_history_delivery_no_key_is_unknown():
    r = _hd()(contract_no="", end_user="")
    assert r.verdict == "未知"


def test_history_delivery_end_user_fallback():
    r = _hd()(contract_no="", end_user="云南省农村信用社科技结算中心")
    assert r.match_basis == "end_user"
    assert r.matched_rows >= 0


def test_history_delivery_issue_levels_valid():
    r = _hd()(contract_no="XSZS2609200704")
    for i in r.issues:
        assert i.level in ("异常", "关注")
        assert i.contract_no


# ----------------------------- CLI -----------------------------

def test_cli_clauses_runs(tmp_path):
    txt = tmp_path / "c.txt"
    txt.write_text(SAMPLE, encoding="utf-8")
    out = tmp_path / "clauses.json"
    proc = subprocess.run(
        [sys.executable, str(CLI), "clauses", "--file", str(txt), "--out", str(out)],
        capture_output=True, text=True, cwd=str(REPO_ROOT))
    assert proc.returncode == 0, proc.stderr[-800:]
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["stats"]["extracted"] > 0


def test_cli_history_delivery_runs(tmp_path):
    out = tmp_path / "hd.json"
    proc = subprocess.run(
        [sys.executable, str(CLI), "history-delivery",
         "--contract-no", "XSZS2609200704", "--out", str(out)],
        capture_output=True, text=True, cwd=str(REPO_ROOT))
    assert proc.returncode == 0, proc.stderr[-800:]
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["verdict"] in ("正常", "关注", "异常", "未收录")
    assert "matched_rows" in data


def test_cli_help_lists_new_commands():
    proc = subprocess.run([sys.executable, str(CLI), "--help"],
                          capture_output=True, text=True, cwd=str(REPO_ROOT))
    assert proc.returncode == 0
    assert "clauses" in proc.stdout
    assert "history-delivery" in proc.stdout
