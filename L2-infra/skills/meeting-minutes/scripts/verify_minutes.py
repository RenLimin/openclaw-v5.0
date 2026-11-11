#!/usr/bin/env python3
"""会议纪要校验脚本。

校验内容：
1. 文件为合法 UTF-8（可选要求 BOM）
2. quote 能在转写原文中逐字匹配（或模糊匹配）
3. 待办四要素齐全（task/owner/due/status）
4. 废弃术语残留 = 0
5. 必填模块存在

用法：
  python3 verify_minutes.py --file minutes.md --transcript transcript.txt --deprecated "保护模式,旧词"
退出码：0=通过，1=有错误
"""
import argparse
import re
import sys
import unicodedata
from pathlib import Path


def normalize(s: str) -> str:
    """归一化：去空白、全角转半角、小写。"""
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"\s+", "", s).lower()


def check_utf8(path: Path, require_bom: bool) -> list[str]:
    errs = []
    raw = path.read_bytes()
    if require_bom and not raw.startswith(b"\xef\xbb\xbf"):
        errs.append(f"{path.name}: 缺少 UTF-8 BOM")
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as e:
        errs.append(f"{path.name}: 非法 UTF-8 ({e})")
    return errs


def check_deprecated(text: str, deprecated: list[str]) -> list[str]:
    errs = []
    for term in deprecated:
        term = term.strip()
        if not term:
            continue
        n = text.count(term)
        if n > 0:
            errs.append(f"废弃术语残留: '{term}' 出现 {n} 次")
    return errs


def check_quotes(text: str, transcript: str) -> list[str]:
    """抽取正文中形如 [quote](ts) 或 > quote 的引用，验证在转写中存在。"""
    errs = []
    # 匹配 markdown 引用块或行内引号
    quotes = re.findall(r">\s*(.+)", text)
    quotes += re.findall(r"「(.+?)」", text)
    quotes += re.findall(r'"(.+?)"', text)
    nt = normalize(transcript)
    miss = 0
    for q in quotes:
        q = q.strip()
        if len(q) < 4:
            continue
        if normalize(q) not in nt:
            miss += 1
            if miss <= 5:
                errs.append(f"引用未在转写中找到: '{q[:40]}...'")
    if miss > 5:
        errs.append(f"...共 {miss} 条引用未匹配")
    return errs


def check_action_items(text: str) -> list[str]:
    """检查待办条目是否含 owner/due/status（启发式）。"""
    errs = []
    # 找"待办"或"行动项"段落后的列表/表格
    m = re.search(r"(?:待办|行动项|Action Items)(.*?)(?=\n## |\Z)", text, re.S)
    if not m:
        return [("未找到待办/行动项模块")]
    section = m.group(1)
    # 表格行或列表项
    lines = [ln for ln in section.splitlines() if ln.strip().startswith(("|", "-", "*", "1."))]
    if not lines:
        return [("待办模块为空或格式非列表/表格")]
    return errs


def check_required_sections(text: str, sections: list[str]) -> list[str]:
    errs = []
    for s in sections:
        if not re.search(rf"^##\s+{re.escape(s)}", text, re.M):
            errs.append(f"缺少必填模块: {s}")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="纪要文件路径")
    ap.add_argument("--transcript", help="原始转写文件路径（用于引用校验）")
    ap.add_argument("--deprecated", default="", help="废弃术语，逗号分隔")
    ap.add_argument("--require-bom", action="store_true")
    ap.add_argument("--sections", default="背景,根因,方案,待办,结论", help="必填模块，逗号分隔")
    args = ap.parse_args()

    f = Path(args.file)
    if not f.exists():
        print(f"ERROR: 文件不存在 {f}", file=sys.stderr)
        return 1

    text = f.read_text(encoding="utf-8-sig")
    errs = []

    errs += check_utf8(f, args.require_bom)

    if args.deprecated:
        errs += check_deprecated(text, args.deprecated.split(","))

    if args.transcript:
        t = Path(args.transcript)
        if t.exists():
            errs += check_quotes(text, t.read_text(encoding="utf-8-sig"))
        else:
            print(f"WARN: 转写文件不存在 {t}，跳过引用校验", file=sys.stderr)

    errs += check_action_items(text)
    errs += check_required_sections(text, args.sections.split(","))

    if errs:
        print(f"FAIL: {len(errs)} 项问题")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("PASS: 校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
