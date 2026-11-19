"""串联回归：review 报告引用 oa-enhance 结论（向后兼容）。

覆盖：
- build_markdown 不带 enhance_section → 结构与旧版一致（向后兼容）
- 带 enhance_section → 章节存在且位于免责声明之前
- write_markdown 透传
- 端到端：真实 886377 的 enhance 结论并入报告（ONES/OA 不可用则 skip）
"""
from __future__ import annotations

from pathlib import Path

import pytest

from contract_review.kb_match import KbReview, KbMatchResult
from contract_review.report import build_markdown, write_markdown

COMPONENT_ROOT = Path(__file__).resolve().parents[2]          # bangcle-contract/
REPO_ROOT = COMPONENT_ROOT.parents[2]                          # workspace 根
RAW_DIR = REPO_ROOT / "tmp" / "oa-pif" / "raw"
ENHANCE_MD = REPO_ROOT / "tmp" / "oa-enh-test" / "oa-enhance-886377.md"


@pytest.fixture
def risk_dict():
    return {
        "overall_risk": "medium",
        "findings": [{"id": "1.5", "category": "主体信息", "item": "签字盖章",
                      "status": "pass", "risk": "high", "law": "§490"}],
    }


@pytest.fixture
def kb_review():
    return KbReview(satisfaction="partial", referenced=True,
                    items=[KbMatchResult(input_name="应用加固", matched=True, score=0.9,
                                         product="应用加固", sku="SKU-1", alert="")])


def test_backward_compatible_without_enhance(risk_dict, kb_review):
    """不带 enhance_section 时，报告不含增强核查章节（旧行为不变）。"""
    md = build_markdown(contract_ref="C1", source="upload", risk=risk_dict, kb=kb_review)
    assert "增强核查" not in md
    assert "合同智能审查报告" in md
    assert "免责声明" in md


def test_enhance_section_inserted_before_disclaimer(risk_dict, kb_review):
    section = "## 增强核查（履约义务 / 概算一致性）\n\n**R1：提示**\n"
    md = build_markdown(contract_ref="C1", source="oa", risk=risk_dict, kb=kb_review,
                        enhance_section=section)
    assert "增强核查" in md
    assert "R1：提示" in md
    # 位置：在免责声明之前
    assert md.index("增强核查") < md.index("免责声明")
    assert md.index("产品/服务参照") < md.index("增强核查")


def test_write_markdown_transparently_passes_enhance(tmp_path, risk_dict, kb_review):
    section = "## 增强核查\n\n内容"
    out = tmp_path / "r.md"
    write_markdown(contract_ref="C1", source="upload", risk=risk_dict, kb=kb_review,
                   out_path=str(out), enhance_section=section)
    content = out.read_text(encoding="utf-8")
    assert "增强核查" in content


def _enhance_available() -> bool:
    return RAW_DIR.exists() and ENHANCE_MD.exists()


@pytest.mark.skipif(not _enhance_available(),
                    reason="真实 enhance 产物/捕获不存在，skip 留证")
def test_end_to_end_real_886377_report_with_enhance(risk_dict, kb_review, tmp_path):
    """真实 886377：enhance 结论并入 review 报告。"""
    section = ENHANCE_MD.read_text(encoding="utf-8")
    out = tmp_path / "report-886377.md"
    write_markdown(contract_ref="requestid:886377", source="oa",
                   risk=risk_dict, kb=kb_review, out_path=str(out),
                   enhance_section=section)
    content = out.read_text(encoding="utf-8")
    assert "增强核查" in content
    assert "R1 履约义务" in content
    assert "R2 概算一致性" in content
    assert "海通恒信" in content
    assert "已验证" in content  # 应答契约时间戳
    assert content.index("产品/服务参照") < content.index("增强核查") < content.index("免责声明")
