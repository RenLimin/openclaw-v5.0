"""阶段4：从合同标的/服务内容条款抽枚举行项目（L4 编排）。

补 L3 parser 对"1. … 2. …"枚举清单提取不全的弱项。纯正则启发式：
抽不到返回 []，由报告标 no_line_items_extracted，不阻塞（纯服务合同可能无清单）。
"""
import re

from .models import LineItem

# 标的区定位关键词
_SECTION_KEYWORDS = [
    "服务内容", "采购内容", "产品清单", "授权产品", "合同标的",
    "项目内容", "产品和服务", "标的物", "供货范围", "报价明细",
]
# 行内产品词（命中非枚举行时才收）
_PRODUCT_WORDS = re.compile(
    r"(加固|监测|情报|防护|SDK|平台|软件|系统|检测|扫描|认证|证书|盾|盒|网关|授权|License|V\d)"
)
# 枚举序号：1. / 1) / (1) / （1） / 1、
_ENUM = re.compile(r"^\s*[(（]?\s*\d+\s*(?:[)）.、]|\s+|(?=[\u4e00-\u9fff]))\s*(.+)")
# 型号：V5.0 / Version 2.1 / 型号：xxx
_MODEL_V = re.compile(r"[Vv](?:ersion)?\s*(\d+(?:\.\d+)+)")
_MODEL_KV = re.compile(r"型号[:：]\s*([A-Za-z0-9\-_.]+)")
# 单价：单价100000元 / 单价：5万元 / 单价 10万
_PRICE = re.compile(r"单价[:：]?\s*([0-9][0-9,]*(?:\.\d+)?)\s*(万)?\s*元?")
# 数量词/前导清洗
_LEAD_NOISE = re.compile(r"^\s*[(（]?\d+\s*(?:[)）.、]|\s+|(?=[\u4e00-\u9fff]))\s*")
_QTY_WORDS = re.compile(r"[，,。；;].*$")
_TRAIL_QTY = re.compile(r"(?:[，,。；;]|\s{2,}).*$")

# 条款 category（L3）里属于标的区的
_TARGET_CATS = {"合同标的", "数量与质量"}


def _locate_section_text(parsed) -> str:
    chunks = []
    for c in getattr(parsed, "clauses", []):
        if getattr(c, "category", "") in _TARGET_CATS and getattr(c, "original_text", ""):
            chunks.append(c.original_text)
    if chunks:
        return "\n".join(chunks)
    # 回退：关键词窗口（raw_text）
    raw = getattr(parsed, "raw_text", "") or ""
    return raw


def _keyword_window(raw: str) -> str:
    """从 raw_text 取关键词命中后约 40 行窗口。"""
    lines = raw.splitlines()
    for i, ln in enumerate(lines):
        if any(k in ln for k in _SECTION_KEYWORDS):
            return "\n".join(lines[i:i + 40])
    return raw


def _parse_price(text: str):
    m = _PRICE.search(text)
    if not m:
        return None
    num = float(m.group(1).replace(",", ""))
    if m.group(2) == "万":
        num *= 10000
    return num


def _parse_model(text: str):
    m = _MODEL_V.search(text)
    if m:
        return m.group(1)
    m = _MODEL_KV.search(text)
    if m:
        return m.group(1)
    return None


def _clean_name(line: str) -> str:
    name = _LEAD_NOISE.sub("", line).strip()
    # 截到第一个单价/金额短句之前
    name = re.split(r"(?:单价|金额|小计|合计)[:：]?", name)[0]
    # 去尾部数量/标点从句
    name = _TRAIL_QTY.split(name)[0]
    name = name.strip(" ：:，,。；;、")
    return name[:60].strip()


def extract_line_items(text: str, parsed) -> list:
    section = _locate_section_text(parsed)
    if not section:
        section = _keyword_window(text)
    else:
        # 标的条款可能很短，补关键词窗口提升召回
        win = _keyword_window(getattr(parsed, "raw_text", "") or text)
        if win and len(win) > len(section):
            section = section + "\n" + win

    items = []
    seen = set()
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m = _ENUM.match(line)
        is_enum = bool(m)
        body = m.group(1) if is_enum else line
        if not is_enum and not _PRODUCT_WORDS.search(line):
            continue
        name = _clean_name(line)
        if not name or len(name) < 2:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(
            LineItem(
                raw_name=name,
                model=_parse_model(body),
                price=_parse_price(body),
                source_line=line,
            )
        )
    return items
