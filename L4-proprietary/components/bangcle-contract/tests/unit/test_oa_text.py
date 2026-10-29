"""oa_text 回归：OA 附件全文提取 + 临时目录即用即焚。"""
import os
import sys
import types
from pathlib import Path

import fitz
import pytest

COMPONENT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if COMPONENT_ROOT not in sys.path:
    sys.path.insert(0, COMPONENT_ROOT)

from contract_review.oa_text import digitize_oa_data  # noqa: E402


def _make_pdf(path, text):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=12)
    doc.save(str(path))
    doc.close()


def test_extracts_pdf_fulltext(tmp_path):
    pdf = tmp_path / "contract.pdf"
    _make_pdf(pdf, "OA CONTRACT FULLTEXT BODY")
    data = {"attachments_local": [{"name": "contract.pdf", "local_path": str(pdf)}]}
    dt = digitize_oa_data(data)
    assert dt is not None
    assert dt.method == "oa_attachment"
    assert "OA CONTRACT FULLTEXT BODY" in dt.full_text


def test_skips_card_txt_non_contract(tmp_path):
    # 浏览器兜底落的 card.txt 不是合同原文，必须跳过
    txt = tmp_path / "billid_1_card.txt"
    txt.write_text("不应被当作合同正文", encoding="utf-8")
    data = {"attachments": [{"name": txt.name, "local_path": str(txt)}]}
    assert digitize_oa_data(data) is None


def test_error_attachment_skipped(tmp_path):
    pdf = tmp_path / "a.pdf"
    _make_pdf(pdf, "REAL")
    data = {"attachments_local": [
        {"name": "b.docx", "error": "下载失败"},
        {"name": "a.pdf", "local_path": str(pdf)},
    ]}
    dt = digitize_oa_data(data)
    assert dt is not None and "REAL" in dt.full_text


def test_no_attachments_returns_none():
    assert digitize_oa_data({"main_fields": {"a": "b"}}) is None


def test_cli_oa_tmpdir_is_burned(tmp_path, monkeypatch):
    """集成：CLI review --oa-billid 完成后，临时附件目录必须被删除。"""
    from argparse import Namespace
    from cli.contractctl import cmd_review

    captured = {}

    def fake_fetch(billid, out_dir):
        out = Path(out_dir)
        pdf = out / "contract.pdf"
        _make_pdf(pdf, "BURNNED-CONTRACT-BODY")
        captured["tmp"] = out
        return {
            "billid": str(billid),
            "main_fields": {},
            "attachments_local": [{"name": "contract.pdf", "local_path": str(pdf)}],
            "card_text_snippet": "",
        }

    import services.oa.entry as entry
    monkeypatch.setattr(entry, "get_contract_with_fallback", fake_fetch)

    args = Namespace(
        oa_billid="99999", file=None, source="oa",
        format="md", out_dir=str(tmp_path / "reports"),
        db=str(tmp_path / "test.db"),
    )
    rc = cmd_review(args)
    assert rc == 0
    tmp = captured["tmp"]
    assert not tmp.exists(), "临时附件目录未被焚毁: %s" % tmp
