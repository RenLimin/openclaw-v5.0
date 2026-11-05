"""L4 OCR 适配器：直接调 tesseract CLI（chi_sim+eng）。

为什么不走 L2 ImageOcrParser：
1) 运行环境缺 Python 绑定 pytesseract -> L2 ImageOcrParser.is_available()=False，不注册；
2) 即便装上，L2 parser 的 image_to_string(image) 未指定 lang，默认 eng，中文合同识别失败；
   L4 红线禁止改 L2 源码。
故对扫描图片，L4 用已就位的 tesseract CLI（5.5.3，含 chi_sim）做 OCR——
同一 OCR 引擎、非降级伪造，只是用 CLI 调用并正确指定语言。
"""
import re
import shutil
import subprocess

from .models import DigitizedText

IMAGE_FORMATS = {"png", "jpg", "jpeg", "tif", "tiff", "bmp", "gif"}
DEFAULT_LANG = "chi_sim+eng"


class TesseractUnavailable(Exception):
    pass


def is_image_format(fmt: str) -> bool:
    return fmt.lower() in IMAGE_FORMATS


def ocr_image(path: str, lang: str = DEFAULT_LANG) -> DigitizedText:
    if shutil.which("tesseract") is None:
        raise TesseractUnavailable(
            "未找到 tesseract CLI；扫描件 OCR 需要 tesseract（含 chi_sim 语言包）。"
        )
    proc = subprocess.run(
        ["tesseract", path, "stdout", "-l", lang],
        capture_output=True,
        text=True,
        timeout=120,
    )
    errors = []
    if proc.returncode != 0:
        errors.append(f"tesseract exit={proc.returncode}: {proc.stderr.strip()[:200]}")
    content = proc.stdout or ""
    content = _normalize_cjk_spacing(content)
    return DigitizedText(
        text=content,
        parser_used="TesseractCLI(chi_sim+eng)",
        parse_errors=errors,
        quality=_ocr_quality(content),
    )


def _ocr_quality(content: str) -> float:
    if not content or len(content.strip()) < 20:
        return 0.3
    cjk = sum(1 for c in content if "\u4e00" <= c <= "\u9fff")
    if cjk == 0:
        return 0.3
    return 0.85

def _normalize_cjk_spacing(content: str) -> str:
    """归一化 tesseract 中文 OCR 噪声空格。

    实测 chi_sim 会在每个汉字之间、汉字与 ASCII 之间插入空格
    （"全 渠 道 软 件 V6.0 单价 100000 元"）。逐行处理：
    含 CJK 的行内，删除汉字相邻的空格（保留换行结构）；
    纯英文/数字行不动。
    """
    cjk = r"\u4e00-\u9fff"
    out_lines = []
    for line in content.splitlines():
        if re.search(f"[{cjk}]", line):
            # 汉字间空格
            line = re.sub(f"(?<=[{cjk}])[ \t]+(?=[{cjk}])", "", line)
            # 汉字 <-> ASCII 间空格
            line = re.sub(f"(?<=[{cjk}])[ \t]+(?=[A-Za-z0-9])", "", line)
            line = re.sub(f"(?<=[A-Za-z0-9])[ \t]+(?=[{cjk}])", "", line)
            # 数字与汉字间残余空格（"100000 元"）
            line = re.sub(r"(?<=[0-9])[ \t]+(?=[元万亿])", "", line)
        out_lines.append(line.rstrip())
    return "\n".join(out_lines)
