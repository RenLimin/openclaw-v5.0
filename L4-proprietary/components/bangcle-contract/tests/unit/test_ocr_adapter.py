"""P2：OCR 适配器防御分支（真实临时模块/文件，非业务 mock）。

在临时目录写一个真实的 ocr_engine 包来驱动适配逻辑，
覆盖：入口解析、v5 旧入口、缺失入口、文本/置信度抽取、不支持类型。
"""

import os
import sys
import textwrap

import pytest

from contract_review.digitize import OCRAdapter, DigitizedText, digitize, DigitizeError


@pytest.fixture(autouse=True)
def _isolate_ocr_engine():
    """每个用例前后清掉缓存的伪 ocr_engine 模块与脚本路径，避免串扰。"""
    saved_modules = {
        k: v for k, v in sys.modules.items()
        if k == "ocr_engine" or k.startswith("ocr_engine.")
    }
    saved_path = list(sys.path)
    for k in list(saved_modules):
        sys.modules.pop(k, None)
    yield
    for k in list(sys.modules):
        if k == "ocr_engine" or k.startswith("ocr_engine."):
            sys.modules.pop(k, None)
    for k, v in saved_modules.items():
        sys.modules[k] = v
    sys.path[:] = saved_path


def _write_fake_engine(scripts_dir: str, body: str, pkg: str = "ocr_engine") -> str:
    pkg_dir = os.path.join(scripts_dir, pkg)
    os.makedirs(pkg_dir, exist_ok=True)
    with open(os.path.join(pkg_dir, "__init__.py"), "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(body))
    return scripts_dir


class _FakeResult:
    def __init__(self, text="fake ocr text", confidence=0.77):
        self._text = text
        self.confidence = confidence

    def to_text(self):
        return self._text


def test_adapter_loads_real_entry_and_extracts(tmp_path):
    scripts = _write_fake_engine(
        str(tmp_path / "scripts"),
        """
        def digitalize_document(path, backend="auto"):
            class R:
                confidence = 0.77
                def to_text(self_inner):
                    return "fake ocr text"
            return R()
        """,
    )
    adapter = OCRAdapter(l2_scripts_dir=scripts)
    out = adapter.recognize("/tmp/whatever.png")
    assert out.method == "ocr"
    assert out.full_text == "fake ocr text"
    assert out.ocr_confidence == pytest.approx(0.77)


def test_adapter_confidence_percent_scaled(tmp_path):
    scripts = _write_fake_engine(
        str(tmp_path / "scripts"),
        """
        def digitalize_document(path):
            class R:
                confidence = 83.0
                def to_text(self_inner):
                    return "t"
            return R()
        """,
    )
    adapter = OCRAdapter(l2_scripts_dir=scripts)
    out = adapter.recognize("x.png")
    assert out.ocr_confidence == pytest.approx(0.83)


def test_adapter_legacy_v5_entry(tmp_path):
    # __init__ 不暴露 digitalize_document；document.py 提供 v5
    scripts = _write_fake_engine(
        str(tmp_path / "scripts"),
        "# no digitalize_document here\n",
    )
    with open(os.path.join(scripts, "ocr_engine", "document.py"), "w") as f:
        f.write(
            "def digitalize_document_v5(path):\n"
            "    class R:\n"
            "        confidence = 0.9\n"
            "        text = 'legacy v5 text'\n"
            "    return R()\n"
        )
    adapter = OCRAdapter(l2_scripts_dir=scripts)
    out = adapter.recognize("x.png")
    assert "legacy v5 text" in out.full_text


def test_adapter_missing_entry_raises(tmp_path):
    scripts = _write_fake_engine(
        str(tmp_path / "scripts"),
        "X = 1\n",
    )
    with open(os.path.join(scripts, "ocr_engine", "document.py"), "w") as f:
        f.write("# nothing\n")
    adapter = OCRAdapter(l2_scripts_dir=scripts)
    with pytest.raises(DigitizeError):
        adapter._load_entry()


def test_adapter_import_error_raises(tmp_path):
    scripts = _write_fake_engine(
        str(tmp_path / "scripts"),
        "raise RuntimeError('boom on import')\n",
    )
    adapter = OCRAdapter(l2_scripts_dir=scripts)
    with pytest.raises(DigitizeError):
        adapter._load_entry()


def test_extract_text_fallback_attrs():
    class AttrResult:
        text = "attr text"
        confidence = None

    assert OCRAdapter._extract_text(AttrResult()) == "attr text"

    class StrResult:
        confidence = None

        def __str__(self):
            return "str result"

    assert OCRAdapter._extract_text(StrResult()) == "str result"


def test_extract_confidence_invalid():
    class R:
        confidence = "nope"

    assert OCRAdapter._extract_confidence(R()) is None

    class R2:
        pass

    assert OCRAdapter._extract_confidence(R2()) is None


def test_digitize_unsupported_type(tmp_path):
    f = tmp_path / "f.bin"
    f.write_bytes(b"x")
    with pytest.raises(DigitizeError):
        digitize(str(f), file_type="spreadsheet")
