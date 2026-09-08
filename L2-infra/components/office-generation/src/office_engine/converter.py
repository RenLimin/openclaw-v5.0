"""
格式转换模块 — 优先 LibreOffice，不可用时降级报错。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

from .exceptions import OfficeUnsupportedError


def _find_soffice() -> str | None:
    """查找 soffice 可执行文件路径。"""
    # 1. PATH 中的 soffice
    if shutil.which("soffice"):
        return "soffice"
    # 2. macOS LibreOffice.app
    mac_path = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    if os.path.exists(mac_path):
        return mac_path
    # 3. 常见 Linux 路径
    for p in ["/usr/bin/soffice", "/usr/local/bin/soffice"]:
        if os.path.exists(p):
            return p
    return None


class OfficeConverter:
    """格式转换模块。优先 LibreOffice，不可用时抛异常。"""

    _soffice_path: str | None = None

    @classmethod
    def is_available(cls) -> bool:
        """检测 LibreOffice 是否可用。"""
        if cls._soffice_path is None:
            cls._soffice_path = _find_soffice()
        return cls._soffice_path is not None

    @classmethod
    def to_pdf(cls, input_path: str, output_path: str | None = None) -> str:
        """
        将 Office 文档转换为 PDF。

        Args:
            input_path: 输入文件路径（docx/xlsx/pptx）
            output_path: 输出 PDF 路径；None 则同目录同名 .pdf

        Returns:
            输出 PDF 文件路径

        Raises:
            OfficeUnsupportedError: LibreOffice 不可用
            FileNotFoundError: 输入文件不存在
            RuntimeError: 转换失败
        """
        if not cls.is_available():
            raise OfficeUnsupportedError(
                "LibreOffice is not available. "
                "Install it via: brew install --cask libreoffice (macOS) "
                "or apt install libreoffice (Linux)"
            )

        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")

        # 确定输出路径
        if output_path is None:
            base = os.path.splitext(input_path)[0]
            output_path = base + ".pdf"

        output_dir = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(output_dir, exist_ok=True)

        # 用临时输出目录避免 soffice 的路径问题
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd = [
                cls._soffice_path,
                "--headless",
                "--convert-to", "pdf",
                "--outdir", tmpdir,
                os.path.abspath(input_path),
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"PDF conversion failed (code {result.returncode}):\n"
                    f"stdout: {result.stdout}\nstderr: {result.stderr}"
                )

            # soffice 输出的文件名是 <basename>.pdf
            base_name = os.path.splitext(os.path.basename(input_path))[0]
            generated = os.path.join(tmpdir, base_name + ".pdf")
            if not os.path.exists(generated):
                raise RuntimeError(f"PDF not generated: {generated}")

            shutil.move(generated, output_path)

        return output_path

    @staticmethod
    def detect_format(path: str) -> str:
        """
        检测文件格式。
        按扩展名识别，返回 'docx' / 'xlsx' / 'pptx' / 未知返回空字符串。
        """
        if not os.path.exists(path):
            return ""
        ext = os.path.splitext(path)[1].lower()
        if ext in (".docx", ".xlsx", ".pptx"):
            return ext.lstrip(".")
        # 进一步可做 magic byte 检测，这里先用扩展名
        return ""
