"""P2：ingest 文件校验与本地暂存（真实文件/临时目录）。"""

import pytest

from contract_review.ingest import (
    IngestedFile,
    ingest_file,
    detect_file_type,
    IngestError,
)


def test_detect_file_type():
    assert detect_file_type("a.pdf") == "pdf"
    assert detect_file_type("a.DOCX") == "docx"
    assert detect_file_type("a.png") == "image"
    assert detect_file_type("a.jpeg") == "image"
    with pytest.raises(IngestError):
        detect_file_type("a.txt")
    with pytest.raises(IngestError):
        detect_file_type("a.exe")


def test_ingest_pdf_copies_to_staging(tmp_path):
    src = tmp_path / "contract.pdf"
    src.write_bytes(b"%PDF-1.4 fake pdf content")
    staging = tmp_path / "staging"

    ing = ingest_file(str(src), source="upload", staging_dir=str(staging))

    assert isinstance(ing, IngestedFile)
    assert ing.source == "upload"
    assert ing.original_name == "contract.pdf"
    assert ing.file_type == "pdf"
    assert ing.local_path.startswith(str(staging))
    # 副本字节一致
    assert open(ing.local_path, "rb").read() == b"%PDF-1.4 fake pdf content"


def test_ingest_docx_and_image(tmp_path):
    d = tmp_path / "c.docx"
    d.write_bytes(b"docx-bytes")
    assert ingest_file(str(d)).file_type == "docx"

    p = tmp_path / "scan.PNG"
    p.write_bytes(b"png-bytes")
    assert ingest_file(str(p), source="wecom").source == "wecom"
    assert ingest_file(str(p)).file_type == "image"


def test_ingest_idempotent_same_content(tmp_path):
    """同内容不同文件名 → 同一暂存副本（内容哈希去重）。"""
    staging = tmp_path / "staging"
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    a.write_bytes(b"same-bytes")
    b.write_bytes(b"same-bytes")

    ing1 = ingest_file(str(a), staging_dir=str(staging))
    ing2 = ingest_file(str(b), staging_dir=str(staging))
    assert ing1.local_path == ing2.local_path


def test_ingest_with_oa_ref(tmp_path):
    f = tmp_path / "c.pdf"
    f.write_bytes(b"x")
    ing = ingest_file(str(f), source="oa_cube", oa_ref="billid-99")
    assert ing.oa_ref == "billid-99"


def test_ingest_errors(tmp_path):
    with pytest.raises(IngestError):
        ingest_file(str(tmp_path / "missing.pdf"))

    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    with pytest.raises(IngestError):
        ingest_file(str(empty))

    good = tmp_path / "c.pdf"
    good.write_bytes(b"x")
    with pytest.raises(IngestError):
        ingest_file(str(good), source="bogus")
