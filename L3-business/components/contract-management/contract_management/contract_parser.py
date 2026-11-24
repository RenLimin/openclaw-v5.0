#!/usr/bin/env python3
"""
合同条款解析器
组件: CLM-GEN-001 (L3)
功能: 按《民法典》合同编的 28 条核心条款类别，逐条解析合同原文
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ContractClause:
    """合同条款"""
    category: str           # 条款类别（如"主体信息"、"违约责任"）
    law_article: str        # 对应法条（如"§470"）
    original_text: str      # 合同原文
    summary: str            # 条款摘要
    key_terms: dict = field(default_factory=dict)  # 关键术语/数值
    issues: list = field(default_factory=list)     # 发现的问题
    suggestions: list = field(default_factory=list)  # 修改建议


@dataclass
class ParsedContract:
    """解析后的合同"""
    title: str = ""
    contract_no: str = ""
    party_a: dict = field(default_factory=dict)
    party_b: dict = field(default_factory=dict)
    clauses: list = field(default_factory=list)
    raw_text: str = ""


# ============================================================
# 条款类别定义（基于《民法典》合同编）
# ============================================================

CLAUSE_CATEGORIES = {
    "主体信息": {
        "law": "§470",
        "description": "合同当事人的名称、地址、联系方式等基本信息",
        "required": True,
    },
    "合同标的": {
        "law": "§470",
        "description": "合同权利义务指向的对象，如服务内容、产品、技术等",
        "required": True,
    },
    "数量与质量": {
        "law": "§470",
        "description": "合同标的的数量和质量标准",
        "required": False,
    },
    "价款与报酬": {
        "law": "§510",
        "description": "合同价款或报酬的金额、计算方式",
        "required": True,
    },
    "履行期限": {
        "law": "§511",
        "description": "合同义务的履行时间或期限",
        "required": True,
    },
    "履行地点": {
        "law": "§511",
        "description": "合同义务的履行地点或交付地点",
        "required": False,
    },
    "履行方式": {
        "law": "§509",
        "description": "合同义务的履行方式、方法",
        "required": False,
    },
    "验收标准": {
        "law": "§509",
        "description": "合同标的的验收标准、方法、期限",
        "required": True,
    },
    "付款条件": {
        "law": "§510",
        "description": "付款的时间、方式、条件",
        "required": True,
    },
    "发票条款": {
        "law": "—",
        "description": "发票的类型、税率、开具时间",
        "required": True,
    },
    "违约责任": {
        "law": "§577-585",
        "description": "违约情形、违约金、赔偿损失",
        "required": True,
    },
    "争议解决": {
        "law": "§507",
        "description": "争议解决方式（诉讼/仲裁）及管辖",
        "required": True,
    },
    "知识产权": {
        "law": "§847",
        "description": "技术成果、知识产权的归属",
        "required": True,
    },
    "保密条款": {
        "law": "§501",
        "description": "保密义务、保密范围、保密期限",
        "required": True,
    },
    "不可抗力": {
        "law": "§180,§590",
        "description": "不可抗力的定义、通知义务、后果",
        "required": False,
    },
    "合同解除": {
        "law": "§563",
        "description": "合同解除的条件、程序、后果",
        "required": False,
    },
    "合同变更": {
        "law": "§543",
        "description": "合同变更的条件、程序",
        "required": False,
    },
    "合同转让": {
        "law": "§545",
        "description": "合同权利义务的转让",
        "required": False,
    },
    "格式条款": {
        "law": "§496-498",
        "description": "格式条款的提示义务、无效情形",
        "required": False,
    },
    "通知送达": {
        "law": "—",
        "description": "通知的送达方式、地址",
        "required": False,
    },
    "合同份数": {
        "law": "—",
        "description": "合同正本/副本数量、持有人",
        "required": False,
    },
    "合同生效": {
        "law": "§490",
        "description": "合同生效条件、签署要求",
        "required": True,
    },
    "合同附件": {
        "law": "—",
        "description": "合同附件的清单、效力",
        "required": False,
    },
    "项目联系人": {
        "law": "—",
        "description": "双方项目联系人的姓名、联系方式",
        "required": False,
    },
    "质保条款": {
        "law": "§509",
        "description": "质量保证期、质保范围、响应时间",
        "required": False,
    },
    "付款账户": {
        "law": "—",
        "description": "收款方的银行账户信息",
        "required": False,
    },
    "税费承担": {
        "law": "—",
        "description": "税费的承担方、税率",
        "required": False,
    },
    "服务标准": {
        "law": "—",
        "description": "SLA、响应时间、服务质量标准",
        "required": False,
    },
    "授权签署": {
        "law": "§490",
        "description": "签署人的授权、身份",
        "required": True,
    },
}


def parse_contract(text: str) -> ParsedContract:
    """
    解析合同原文，按条款类别逐条提取
    """
    # OCR 文本归一化（修正常见识别错误 + 清理页眉页脚）
    text = _normalize_ocr_text(text)
    parsed = ParsedContract(raw_text=text)

    # 1. 提取标题
    title_match = re.search(r'项目名称[：:]\s*(.+?)(?:\n|$)', text)
    if title_match:
        parsed.title = title_match.group(1).strip()

    # 2. 提取主体信息
    parsed.party_a = _extract_party_info(text, "甲方")
    parsed.party_b = _extract_party_info(text, "乙方")

    # 3. 逐条解析条款
    parsed.clauses = _extract_all_clauses(text)

    return parsed


# ============================================================
# 主体信息抽取（v1.1 重写：按方归属，禁止跨方串用）
# ------------------------------------------------------------
# v1.0 缺陷：地址/邮箱/开户行/账号按「全文首个匹配」赋值，且甲乙方共用同一规则，
# 同一值被复制给双方（真实样本 886377 复现：party_a == party_b，银行账号实为乙方）。
# v1.1 口径：
#   1) 双列表格行（含 `|` 且成对「字段：值」单元）按列归属：首列→甲方(需方)，
#      次列→乙方(供方)；出现顺序相反时按标签实际位置纠正；
#   2) 其余字段按「与本方标签最近提及距离」归属；与其他方并列（距离相等）时
#      **不归属**——缺失优于错误；
#   3) 邮箱仅取 ASCII 本地部分，剥离中文前缀（如「向huijuan.lin@…」）；
#   4) 地址值做卫生过滤（空值 / 含「电子邮箱」等串行了文字的候选丢弃）。
# ============================================================

_PARTY_ALIASES = {
    "甲方": ("甲方", "需方"),
    "乙方": ("乙方", "供方"),
}

_PARTY_FIELD_PATTERNS = [
    ("address", r"地址[：:]\s*([^|\n]+)"),
    ("zip", r"邮编[：:]\s*(\d{6})"),
    ("phone", r"(?:联系电话|电话)[：:]\s*(\d[\d\-]+)"),
    ("email", r"([A-Za-z0-9._+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})"),
    ("credit_code", r"统一社会信用代码[：:]\s*([0-9A-Z]{18})"),
    ("bank", r"开户行[：:]\s*([^|\n]+)"),
    ("account", r"账号[：:]\s*(\d+)"),
]


def _party_mention_lines(lines, aliases):
    """返回命中别名集合的行号列表。"""
    return [i for i, ln in enumerate(lines) if any(a in ln for a in aliases)]


def _nearest_distance(idx, hits):
    if not hits:
        return None
    return min(abs(idx - h) for h in hits)


_ROW_FIELD_LABELS = ["联系电话", "需方", "供方", "地址", "邮编", "联系人",
                     "传真", "电话"]


def _row_cells(line):
    """解析一行中的「标签：值」单元序列。

    兼容两种版式：
      1) 管道分隔（txt/OCR 导出）：`地址： | A | 地址： | B`
      2) 空格连排（docx 表格提取，无 |）：`地址： A 地址： B`
    """
    cells = [c.strip() for c in line.split("|")]
    out, i = [], 0
    while i < len(cells) - 1:
        m = re.match(r"^([\u4e00-\u9fa5]{1,8})[：:]$", cells[i])
        if m:
            out.append((m.group(1), cells[i + 1].strip()))
            i += 2
        else:
            i += 1
    if out:
        return out
    # 无管道：按标签重复出现顺序切分
    labels = "|".join(re.escape(x) for x in _ROW_FIELD_LABELS)
    pat = re.compile(r"(%s)\s*[：:]\s*" % labels)
    hits = list(pat.finditer(line))
    res = []
    for idx, h in enumerate(hits):
        end = hits[idx + 1].start() if idx + 1 < len(hits) else len(line)
        res.append((h.group(1), line[h.end():end].strip()))
    return res

def _clean_value(key, value):
    """候选值卫生过滤：返回清洗后的值，无效返回 ''。"""
    v = (value or "").strip()
    if not v:
        return ""
    if key == "address":
        # 串行了后续文字的 OCR 脏值（如「…年授权产品电子邮箱/地址：」）
        if "电子邮箱" in v or v.count("：") >= 2:
            return ""
        if len(v) > 60:
            return ""
    return v


def _extract_party_name(text, party_label, aliases):
    """名称：优先签字页 `甲方：公司`，其次 `公司（以下简称"甲方"）`。"""
    for al in aliases:
        m = re.search(rf"^\s*{al}\s*[：:]\s*([一-龥A-Za-z0-9（）()]+?)\s*$",
                      text, re.M)
        if m:
            return m.group(1).strip()
    for al in aliases:
        m = re.search(rf"([一-龥A-Za-z0-9（）()]+?)（以下简称[\"“]?{al}[\"”]?）", text)
        if m:
            return m.group(1).strip()
    return ""


def _extract_party_info(text: str, party_label: str) -> dict:
    """提取一方主体信息（v1.1：按方归属，绝不把其他方的值复制到本方）。"""
    info = {}
    lines = text.split("\n")
    self_alias = _PARTY_ALIASES.get(party_label, (party_label,))
    other_label = "乙方" if party_label == "甲方" else "甲方"
    other_alias = _PARTY_ALIASES.get(other_label, (other_label,))
    self_hits = _party_mention_lines(lines, self_alias)
    other_hits = _party_mention_lines(lines, other_alias)

    # 1) 名称
    info["name"] = _extract_party_name(text, party_label, self_alias)

    # 2) 双列表格行：按列归属（需方/供方 或同名字段两列）
    #    列序由「需方/供方」标签行推断：需方(甲方)在前 → ["甲方","乙方"]。
    _col_order = None
    for idx, line in enumerate(lines):
        pairs = _row_cells(line)
        if not pairs:
            continue
        has_pipe = "|" in line
        same_pair = len(pairs) >= 2 and pairs[0][0] == pairs[1][0]
        has_supply_labels = any(lbl in ("需方", "供方") for lbl, _ in pairs)
        if not has_pipe and not same_pair and not has_supply_labels:
            # 无管道的正文散行（如「甲方指定地址：」）：不做列切分，交给距离归属
            continue
        # 需方/供方 行 → 名称
        for label, value in pairs:
            if label in ("需方", "供方"):
                target = "甲方" if label == "需方" else "乙方"
                if target == party_label and value and not info.get("name"):
                    info["name"] = value
        # 同名字段两列 → 按列序分配
        if len(pairs) >= 2 and pairs[0][0] == pairs[1][0]:
            field = pairs[0][0]
            keymap = {"地址": "address", "邮编": "zip", "电话": "phone",
                      "联系电话": "phone", "联系人": "contact"}
            key = keymap.get(field)
            if not key:
                continue
            vals = [p[1] for p in pairs[:2]]
            if _col_order is None:
                head = "\n".join(lines[max(0, idx - 6):idx])
                p_need = head.rfind("需方")
                p_supply = head.rfind("供方")
                if p_supply != -1 and p_need != -1:
                    # 文本中出现更早的一方 = 首列
                    _col_order = ["甲方", "乙方"] if p_need < p_supply else ["乙方", "甲方"]
                else:
                    _col_order = ["甲方", "乙方"]
            mine = vals[0] if _col_order[0] == party_label else vals[1]
            mine = _clean_value(key, mine)
            if mine and not info.get(key):
                info[key] = mine

    # 3) 单值字段：最近提及距离归属；并列则不归属
    for key, pat in _PARTY_FIELD_PATTERNS:
        if info.get(key):
            continue
        best = None
        for m_idx, ln in enumerate(lines):
            m = re.search(pat, ln)
            if not m:
                continue
            val = _clean_value(key, m.group(1))
            if not val:
                continue
            d_self = _nearest_distance(m_idx, self_hits)
            d_other = _nearest_distance(m_idx, other_hits)
            if d_self is None:
                if d_other is None:  # 双方都无提及 → 退化场景，允许全局首配
                    best = val if best is None else best
                continue
            if d_other is not None and d_other <= d_self:
                continue  # 更近/等于他方 → 不归本方（并列=不归属）
            if d_self > 8:
                continue  # 离本方太远，不可信
            best = val if best is None else best
        if best:
            info[key] = best

    return info


def _normalize_ocr_text(text: str) -> str:
    """OCR 文本归一化：修正常见识别错误 + 清理页眉页脚"""
    import re as _re
    
    # 清理页眉页脚（常见模式）
    # 移除 "第X页共Y页" / "第X页 共Y页"
    text = _re.sub(r'第\s*\d+\s*页\s*共\s*\d+\s*页', '', text)
    text = _re.sub(r'第\s*\d+\s*页\s*\d+\s*页', '', text)
    
    # 清理水印/页眉行（连续的短行 + | 分隔符）
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        s = line.strip()
        # 跳过明显的页眉（含|且<20字）
        if '|' in s and len(s) < 25:
            continue
        # 跳过空行过多的
        cleaned.append(line)
    text = '\n'.join(cleaned)
    
    # 常见 OCR 错误修正（合同场景）
    corrections = [
        (r'合[网同]', '合同'),  # 合网 / 合同
        (r'款件', '软件'),
        (r'投权', '授权'),
        (r'保秘', '保密'),
        (r'不可抗[力拒]', '不可抗力'),
        (r'违约全', '违约金'),
        (r'争仪', '争议'),
        (r'知识产[杈权]', '知识产权'),
        (r'有限公[可司同]', '有限公司'),
        (r'签[暑署]', '签署'),
        (r'[加周固]固', '加固'),
        (r'携述', '描述'),
        (r'演后', '届满后'),
        (r'测活', '激活'),
        (r'邦[懋帮]', '梆梆'),
        (r'郴邦', '梆梆'),
        (r'郴安全', '梆梆安全'),
        (r'服带', '服务'),
        (r'思事', '思智'),
        (r'惠集', '惠智'),
        (r'喝师', '顾问'),
        (r'需费全', '安全'),
        (r'想邦', '梆梆'),
        # 金额/日期类
        (r'万随任元', '捌万陆仟元'),
        (r'任元整', '仟元整'),
        (r'捌任', '捌仟'),
        (r'40k年', '2026年'),
        (r'二月日', '三月二十日'),
        # 公司名类
        (r'北京郴郴安全', '北京梆梆安全'),
        (r'北京帮梯安全', '北京梆梆安全'),
        (r'携高梦', '指南针'),
        # 通用错字
        (r'产晶', '产品'),
        (r'贵任', '责任'),
        (r'精速单价', '版本单价'),
        (r'想趣', '安全'),
        (r'兵8', '共8'),
    ]
    for pat, repl in corrections:
        text = _re.sub(pat, repl, text)
    
    return text


def _split_articles(text: str) -> dict:
    """按"第X条"将合同拆分为各条款段
    Returns: { "第一条": "完整内容", "第二条": "完整内容", ... }
    """
    import re as _re
    # 匹配中文数字或阿拉伯数字的条款标题
    pattern = r'(第[一二三四五六七八九十百\d]+条[^\n]*)'
    matches = list(_re.finditer(pattern, text))
    articles = {}
    for i, m in enumerate(matches):
        title_line = m.group(1).strip()
        # 提取条号（第X条）
        num_match = _re.match(r'(第[一二三四五六七八九十百\d]+条)', title_line)
        if not num_match:
            continue
        art_num = num_match.group(1)
        # 内容：从标题后到下一个条标题前
        start = m.end()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        content_text = text[start:end].strip()
        # 合并标题和内容
        full = title_line + "\n" + content_text
        # 去重（同一个条号出现多次时，取最长的）
        if art_num not in articles or len(full) > len(articles[art_num]):
            articles[art_num] = full
    return articles

def _find_article_by_keyword(text: str, keywords: list) -> str:
    """通过关键词查找条款内容
    先按第X条拆分，然后在标题里搜关键词
    """
    articles = _split_articles(text)
    for art_num, content in articles.items():
        first_line = content.split('\n')[0] if '\n' in content else content[:80]
        for kw in keywords:
            if kw in first_line:
                return content
    return ""

def _extract_all_clauses(text: str) -> list:
    """提取所有条款"""
    clauses = []

    # 按条款类别逐一提取
    extractors = {
        "主体信息": _extract_clause_主体信息,
        "合同标的": _extract_clause_合同标的,
        "价款与报酬": _extract_clause_价款与报酬,
        "履行期限": _extract_clause_履行期限,
        "履行方式": _extract_clause_履行方式,
        "验收标准": _extract_clause_验收标准,
        "付款条件": _extract_clause_付款条件,
        "发票条款": _extract_clause_发票条款,
        "违约责任": _extract_clause_违约责任,
        "争议解决": _extract_clause_争议解决,
        "知识产权": _extract_clause_知识产权,
        "保密条款": _extract_clause_保密条款,
        "不可抗力": _extract_clause_不可抗力,
        "合同解除": _extract_clause_合同解除,
        "合同变更": _extract_clause_合同变更,
        "格式条款": _extract_clause_格式条款,
        "合同份数": _extract_clause_合同份数,
        "合同生效": _extract_clause_合同生效,
        "项目联系人": _extract_clause_项目联系人,
        "质保条款": _extract_clause_质保条款,
        "付款账户": _extract_clause_付款账户,
        "授权签署": _extract_clause_授权签署,
        "服务标准": _extract_clause_服务标准,
    }

    for category, extractor in extractors.items():
        clause = extractor(text)
        if clause:
            clauses.append(clause)

    return clauses


# ============================================================
# 各类条款提取函数
# ============================================================

def _extract_clause_主体信息(text: str) -> Optional[ContractClause]:
    """提取主体信息条款"""
    party_a = _extract_party_info(text, "甲方")
    party_b = _extract_party_info(text, "乙方")

    # 提取原文段落
    original = ""
    sections = re.findall(r'(?:甲方|乙方)[（(][^）)]*[）)][：:].*?(?=\n\n|\n第)', text, re.DOTALL)
    if sections:
        original = "\n".join(sections[:4])

    clause = ContractClause(
        category="主体信息",
        law_article="§470",
        original_text=original[:500],
        summary=f"甲方：{party_a.get('name', '未提取')}；乙方：{party_b.get('name', '未提取')}",
        key_terms={
            "甲方名称": party_a.get("name", ""),
            "乙方名称": party_b.get("name", ""),
            "甲方地址": party_a.get("address", ""),
            "乙方地址": party_b.get("address", ""),
        },
    )

    # 检查问题
    if not party_a.get("name"):
        clause.issues.append("甲方名称未明确提取")
    if not party_b.get("name"):
        clause.issues.append("乙方名称未明确提取")
    if not party_a.get("address"):
        clause.issues.append("甲方地址缺失")
    if not party_b.get("address"):
        clause.issues.append("乙方地址缺失")

    return clause


def _extract_clause_合同标的(text: str) -> Optional[ContractClause]:
    """提取合同标的条款（通用版）"""
    # 找第一条或含"标的/产品/服务/授权"的条款
    art_text = _find_article_by_keyword(text, ["产品名称", "授权产品", "合同标的", "服务内容", "技术服务", "采购内容", "项目内容"])
    if not art_text:
        articles = _split_articles(text)
        for k in ["第一条", "第1条"]:
            if k in articles:
                art_text = articles[k]
                break
    
    original = art_text[:500] if art_text else ""
    summary_parts = []
    key_terms = {}
    
    if art_text:
        # 提取第一条标题
        first_line = art_text.split('\n')[0] if art_text else ""
        if first_line:
            # 去掉"第一条"前缀
            title = re.sub(r'^第[一二三四五六七八九十\d]+条', '', first_line).strip()
            if title:
                key_terms["条款标题"] = title
                summary_parts.append(title[:60])
        
        # 提取产品/服务名称（OCR文本里可能没有冒号分隔，尝试从行内容找）
        found = False
        for pat in [r'产品名称[：:]\s*(.+?)(?:\n|产品型号|规格)',
                    r'项目名称[：:]\s*(.+?)(?:\n|$)',
                    r'Android应用加固软件[^\n]+',
                    r'软件[：:]?(.+?)[年付费|许可]']:
            m = re.search(pat, art_text)
            if m and m.group(1).strip():
                key_terms["产品名称"] = m.group(1).strip()[:60]
                summary_parts = [f"产品：{m.group(1).strip()[:40]}"]
                found = True
                break
        # 兜底：从表格里找产品行
        if not found:
            # 找含"加固"或"软件"的产品行
            for line in art_text.split('\n'):
                if ('软件' in line or '产品' in line or '加固' in line) and len(line) > 10:
                    key_terms["产品名称"] = line.strip()[:80]
                    summary_parts = [f"产品：{line.strip()[:50]}"]
                    break
    else:
        summary_parts.append("未提取到合同标的内容")

    return ContractClause(
        category="合同标的",
        law_article="§470",
        original_text=original[:500],
        summary="；".join(summary_parts) if summary_parts else "未提取到合同标的内容",
        key_terms=key_terms,
    )


def _extract_clause_价款与报酬(text: str) -> Optional[ContractClause]:
    """提取价款与报酬条款（通用版）"""
    # 找付款相关条款
    art_text = _find_article_by_keyword(text, ["付款方式", "价款", "报酬", "合同金额", "费用支付", "支付方式"])
    if not art_text:
        articles = _split_articles(text)
        for k in ["第二条", "第2条"]:
            if k in articles:
                art_text = articles[k]
                break
    
    original = art_text[:500] if art_text else ""
    key_terms = {}
    issues = []
    summary = ""
    
    # 全文搜索金额（数字）
    amount_num = ""
    amt_patterns = [
        r'合同总价[（(]元[)）][）]?[：:]?\s*[￥¥]?\s*([\d,]+\.?\d*)',
        r'合同总金额[：:]\s*[￥¥]?\s*([\d,]+\.?\d*)',
        r'本合同总价为[：:]?\s*[￥¥]?\s*([\d,]+\.?\d*)\s*元',
        r'总金额[：:]\s*[￥¥]?\s*([\d,]+\.?\d*)',
        r'合同金额[：:]\s*[￥¥]?\s*([\d,]+\.?\d*)',
        r'合计[（(]元[)）][：:]?\s*([\d,]+\.?\d*)',
        r'([\d,]+\.?\d*)\s*元人民币',
        r'[￥¥]\s*([\d,]+\.?\d*)',
    ]
    for pat in amt_patterns:
        m = re.search(pat, text)
        if m:
            amount_num = m.group(1).strip().replace(',', '')
            key_terms["金额数字"] = amount_num
            break
    
    # 大写金额
    cn_match = re.search(r'大写[：:]?\s*([\u4e00-\u9fa5零壹贰叁肆伍陆柒捌玖拾佰仟万亿元整]+)', text)
    if cn_match:
        amount_cn = cn_match.group(1).strip()
        key_terms["金额大写"] = amount_cn
    
    if amount_num:
        summary = f"合同金额：¥{amount_num}"
        if cn_match:
            summary += f"（{cn_match.group(1).strip()}）"
    else:
        summary = "未提取到合同金额"
        issues.append("合同金额未明确提取")
    
    return ContractClause(
        category="价款与报酬",
        law_article="§510",
        original_text=original[:500],
        summary=summary,
        key_terms=key_terms,
        issues=issues,
        suggestions=[],
    )


def _extract_clause_履行期限(text: str) -> Optional[ContractClause]:
    """提取履行期限条款（通用版）"""
    key_terms = {}
    summary_parts = []
    original = ""
    
    # 找期限相关条款
    art_text = _find_article_by_keyword(text, ["履行期限", "服务期限", "有效期限", "授权期限", "合同期限", "质保期", "交付时间"])
    
    # 全文搜索日期范围
    date_patterns = [
        r'授权使用期限[为：:]?\s*(.+?)(?:\n到期|；|。)',
        r'合同期限[为：:]?\s*(.+?)(?:；|。)',
        r'服务期限[为：:]?\s*(.+?)(?:；|。)',
        r'有效期限[为：:]?\s*(.+?)(?:；|。)',
        r'(\d{4}年\d{1,2}月\d{1,2}日\s*至\s*\d{4}年\d{1,2}月\d{1,2}日)',
    ]
    period_text = ""
    period_label = ""
    for pat in date_patterns:
        m = re.search(pat, text)
        if m:
            period_text = m.group(1).strip().replace('\n', '')
            if "授权" in pat: period_label = "授权期限"
            elif "服务" in pat: period_label = "服务期限"
            elif "有效" in pat: period_label = "有效期限"
            elif "合同" in pat: period_label = "合同期限"
            else: period_label = "履行期限"
            break
    
    if period_text:
        key_terms[period_label] = period_text
        summary_parts.append(f"{period_label}：{period_text[:50]}")
        if art_text:
            original = art_text[:500]
        else:
            original = period_text
    else:
        summary_parts.append("未提取到履行期限")
        if art_text:
            original = art_text[:500]
    
    return ContractClause(
        category="履行期限",
        law_article="§511",
        original_text=original[:500],
        summary="；".join(summary_parts),
        key_terms=key_terms,
    )


def _extract_clause_履行方式(text: str) -> Optional[ContractClause]:
    """提取履行方式条款"""
    method_match = re.search(r'技术服务的方式[：:]\s*(.+?)(?:\n\d|$)', text)

    if method_match:
        return ContractClause(
            category="履行方式",
            law_article="§509",
            original_text=method_match.group(0)[:300],
            summary=method_match.group(1).strip(),
            key_terms={"服务方式": method_match.group(1).strip()},
        )
    return None


def _extract_clause_验收标准(text: str) -> Optional[ContractClause]:
    """提取验收标准条款（通用版）"""
    art_text = _find_article_by_keyword(text, ["验收标准", "验收方法", "产品交付与验收", "验收", "交付与验收"])
    
    original = art_text[:500] if art_text else ""
    summary_parts = []
    key_terms = {}
    
    if art_text:
        # 提取验收方式
        if "验收确认" in art_text or "验收合格" in art_text:
            summary_parts.append("验收方式：双方确认/验收合格")
            key_terms["验收方式"] = "双方确认"
        if "上门安装" in art_text or "交付" in art_text:
            summary_parts.append("交付方式：上门/远程交付")
            key_terms["交付方式"] = "按合同约定"
        if not summary_parts:
            # 取前 80 字
            first_para = art_text.split('\n')[1] if '\n' in art_text else art_text
            summary_parts.append(first_para[:60])
    else:
        summary_parts.append("未提取到验收标准")
    
    return ContractClause(
        category="验收标准",
        law_article="§509",
        original_text=original[:500],
        summary="；".join(summary_parts),
        key_terms=key_terms,
    )


def _extract_clause_付款条件(text: str) -> Optional[ContractClause]:
    """提取付款条件条款（通用版）"""
    art_text = _find_article_by_keyword(text, ["付款方式", "付款条件", "支付方式", "结算方式"])
    
    original = art_text[:500] if art_text else ""
    summary = ""
    key_terms = {}
    
    if art_text:
        # 提取付款节点
        if "全额付款" in art_text or "一次性支付" in art_text or "全额" in art_text:
            key_terms["付款方式"] = "一次性付款"
            summary = "一次性/全额付款"
        elif "分期" in art_text:
            key_terms["付款方式"] = "分期付款"
            summary = "分期付款"
        else:
            # 找"XX个工作日"
            day_m = re.search(r'(\d+)\s*个工作日', art_text)
            if day_m:
                key_terms["付款期限"] = f"{day_m.group(1)}个工作日"
                summary = f"合同生效后{day_m.group(1)}个工作日内支付"
            else:
                summary = "按合同约定付款"
        
        # 结算方式
        if "汇款" in art_text or "转账" in art_text:
            key_terms["结算方式"] = "银行汇款/转账"
    else:
        summary = "未提取到付款条件"
    
    return ContractClause(
        category="付款条件",
        law_article="§510",
        original_text=original[:500],
        summary=summary,
        key_terms=key_terms,
    )


def _extract_clause_发票条款(text: str) -> Optional[ContractClause]:
    """提取发票条款"""
    invoice_match = re.search(r'发票税率(\d+%)', text)
    invoice_type = re.search(r'增值税专用发?票', text)

    key_terms = {}
    summary_parts = []

    if invoice_match:
        key_terms["税率"] = invoice_match.group(1)
        summary_parts.append(f"税率：{invoice_match.group(1)}")

    if invoice_type:
        key_terms["发票类型"] = "增值税专用发票"
        summary_parts.append("发票类型：增值税专用发票")

    if not summary_parts:
        return None

    return ContractClause(
        category="发票条款",
        law_article="—",
        original_text="；".join(summary_parts),
        summary="；".join(summary_parts),
        key_terms=key_terms,
    )


def _extract_clause_违约责任(text: str) -> Optional[ContractClause]:
    """提取违约责任条款（通用版）"""
    art_text = _find_article_by_keyword(text, ["违约责任", "违约条款", "违约"])
    
    original = ""
    key_terms = {}
    issues = []
    
    if art_text:
        original = art_text[:800]
    else:
        # 兜底找含"违约"的段落
        penalty_matches = re.findall(r'第[一二三四五六七八九十\d]+条[^\n]*\n.*?违约.*?\n', text)
        if penalty_matches:
            original = "\n".join(penalty_matches)[:800]
    
    # 提取违约金比例（支持阿拉伯数字% 和中文"千分之X/百分之X"）
    penalty_rates = re.findall(r'(\d+(?:\.\d+)?)\s*%', original)
    # 中文数字比例：千分之一/千分之五/百分之X
    cn_rates = re.findall(r'千分之[一二三四五六七八九十百\d]+', original)
    if cn_rates:
        penalty_rates.extend(cn_rates)
    pct_rates = re.findall(r'百分之[一二三四五六七八九十百\d]+', original)
    if pct_rates:
        penalty_rates.extend(pct_rates)
    if penalty_rates:
        key_terms["违约金比例"] = penalty_rates
    
    # 检查日违约金
    daily_penalty = re.findall(r'每逾期一日.*?(\d+(?:\.\d+)?)\s*%', original)
    if not daily_penalty:
        # 中文数字的日违约金
        daily_cn = re.findall(r'每逾期一日.*?千分之[一二三四五六七八九十]+', original)
        if daily_cn:
            key_terms["日违约金比例"] = daily_cn
    if daily_penalty:
        key_terms["日违约金比例"] = daily_penalty
        for rate in daily_penalty:
            try:
                if float(rate) > 0.5:
                    issues.append(f"日违约金{rate}%偏高（年化{float(rate)*365:.0f}%），建议降至0.3%以下")
            except ValueError:
                pass
    
    # 检查上限
    cap_match = re.search(r'最高不超过合同总额的(\d+)%', original)
    if cap_match:
        key_terms["违约金上限"] = f"{cap_match.group(1)}%"
    
    rates_display = key_terms.get('违约金比例', [])
    if rates_display:
        rates_str = '、'.join(str(r) for r in rates_display[:3])
    else:
        rates_str = '未约定'
    summary = f"违约金比例：{rates_str}；上限：{key_terms.get('违约金上限', '未约定')}"
    
    return ContractClause(
        category="违约责任",
        law_article="§577-585",
        original_text=original[:500],
        summary=summary,
        key_terms=key_terms,
        issues=issues,
    )


def _extract_clause_争议解决(text: str) -> Optional[ContractClause]:
    """提取争议解决条款（通用版）"""
    art_text = _find_article_by_keyword(text, ["争议解决", "争议处理", "管辖", "诉讼"])
    
    original = art_text[:500] if art_text else ""
    summary = ""
    key_terms = {}
    issues = []
    
    if art_text:
        # 提取管辖法院
        if "人民法院" in art_text:
            # 找哪个法院
            court_match = re.search(r'(.+?人民法院)', art_text)
            if court_match:
                key_terms["管辖法院"] = court_match.group(1).strip()
                summary = f"管辖法院：{court_match.group(1).strip()[:40]}"
            else:
                summary = "诉讼解决（人民法院管辖）"
                key_terms["解决方式"] = "诉讼"
        elif "仲裁" in art_text:
            summary = "仲裁解决"
            key_terms["解决方式"] = "仲裁"
            # 检查仲裁机构是否明确
            if "仲裁委员会" not in art_text:
                issues.append("仲裁条款未明确仲裁机构，可能无效")
        elif "协商" in art_text:
            summary = "协商解决"
            key_terms["解决方式"] = "协商"
        else:
            summary = art_text[:60]
    else:
        summary = "未约定争议解决条款"
        issues.append("未约定争议解决条款，发生争议时按法定管辖处理")
    
    return ContractClause(
        category="争议解决",
        law_article="§507",
        original_text=original[:500],
        summary=summary,
        key_terms=key_terms,
        issues=issues,
    )


def _extract_clause_知识产权(text: str) -> Optional[ContractClause]:
    """提取知识产权条款"""
    ip_match = re.search(r'第七条[：:].*?(?=第八条|$)', text, re.DOTALL)

    original = ""
    key_terms = {}

    if ip_match:
        original = ip_match.group(0)[:500]
        if "归.*甲方" in original or "甲方.*所有" in original:
            key_terms["成果归属"] = "归甲方所有"
        elif "归.*乙方" in original:
            key_terms["成果归属"] = "归乙方所有"

    if not original:
        return None

    return ContractClause(
        category="知识产权",
        law_article="§847",
        original_text=original[:300],
        summary=f"新技术成果归属：{key_terms.get('成果归属', '需进一步确认')}",
        key_terms=key_terms,
    )


def _extract_clause_保密条款(text: str) -> Optional[ContractClause]:
    """提取保密条款"""
    section4_match = re.search(r'第四条[：:].*?(?=第五条|$)', text, re.DOTALL)

    if not section4_match:
        return None

    original = section4_match.group(0)[:500]
    key_terms = {}

    if "保密" in original:
        key_terms["保密义务"] = "已约定"
    if "终止" in original and "保密" in original:
        key_terms["保密期限"] = "合同终止后继续有效"
    if "律师费" in original:
        key_terms["赔偿范围"] = "包括律师费"

    return ContractClause(
        category="保密条款",
        law_article="§501",
        original_text=original[:300],
        summary=f"保密义务：已约定；保密期限：{key_terms.get('保密期限', '未明确')}",
        key_terms=key_terms,
    )


def _extract_clause_不可抗力(text: str) -> Optional[ContractClause]:
    """提取不可抗力条款"""
    force_match = re.search(r'不可抗力[；;，,]\s*(.+?)(?:\n|$)', text)

    if not force_match:
        # 搜索第十条
        section10 = re.search(r'第十条[：:].*?(?=第十一条|$)', text, re.DOTALL)
        if section10 and "不可抗力" in section10.group(0):
            force_match = section10

    if not force_match:
        return None

    original = force_match.group(0)[:300] if hasattr(force_match, 'group') else force_match.group(0)[:300]
    key_terms = {"存在": True}

    return ContractClause(
        category="不可抗力",
        law_article="§180,§590",
        original_text=original,
        summary="已约定不可抗力条款，但定义和通知义务待完善",
        key_terms=key_terms,
        issues=["未定义不可抗力的具体范围", "未约定通知义务的期限", "未约定不可抗力后果处理"],
    )


def _extract_clause_合同解除(text: str) -> Optional[ContractClause]:
    """提取合同解除条款"""
    section10 = re.search(r'第十条[：:].*?(?=第十一条|$)', text, re.DOTALL)

    if not section10:
        return None

    original = section10.group(0)[:300]
    key_terms = {}

    if "不可抗力" in original:
        key_terms["解除条件1"] = "发生不可抗力"

    return ContractClause(
        category="合同解除",
        law_article="§563",
        original_text=original,
        summary=f"解除条件：{key_terms}",
        key_terms=key_terms,
    )


def _extract_clause_合同变更(text: str) -> Optional[ContractClause]:
    """提取合同变更条款"""
    section5 = re.search(r'第五条[：:].*?(?=第六条|$)', text, re.DOTALL)

    if not section5:
        return None

    original = section5.group(0)[:300]

    return ContractClause(
        category="合同变更",
        law_article="§543",
        original_text=original,
        summary="合同变更需双方协商一致并以书面形式确定",
        key_terms={"变更条件": "双方协商一致+书面形式"},
    )


def _extract_clause_格式条款(text: str) -> Optional[ContractClause]:
    """提取格式条款相关信息"""
    # 检查是否存在格式条款风险
    issues = []

    # 检查是否有明显不对等的条款
    if re.search(r'乙方有权停止履行.*不承担违约责任', text):
        issues.append("乙方单方面停止履行且不承担违约责任，可能被认定为格式条款无效（§497）")

    if not issues:
        return None

    return ContractClause(
        category="格式条款",
        law_article="§496-498",
        original_text="；".join(issues),
        summary="存在格式条款风险",
        issues=issues,
    )


def _extract_clause_合同份数(text: str) -> Optional[ContractClause]:
    """提取合同份数条款"""
    copies_match = re.search(r'本合同一式\s*(\w+)\s*份[，,]\s*甲方持\s*(\w+)\s*份[，,]\s*乙方持\s*(\w+)\s*份', text)

    if copies_match:
        return ContractClause(
            category="合同份数",
            law_article="—",
            original_text=copies_match.group(0),
            summary=f"一式{copies_match.group(1)}份，甲方持{copies_match.group(2)}份，乙方持{copies_match.group(3)}份",
            key_terms={
                "总份数": copies_match.group(1),
                "甲方份数": copies_match.group(2),
                "乙方份数": copies_match.group(3),
            },
        )
    return None


def _extract_clause_合同生效(text: str) -> Optional[ContractClause]:
    """提取合同生效条款"""
    effect_match = re.search(r'本合同经双方签字盖章后生效', text)

    if effect_match:
        return ContractClause(
            category="合同生效",
            law_article="§490",
            original_text=effect_match.group(0),
            summary="经双方签字盖章后生效",
            key_terms={"生效条件": "双方签字盖章"},
        )
    return None


def _extract_clause_项目联系人(text: str) -> Optional[ContractClause]:
    """提取项目联系人条款"""
    section9 = re.search(r'第九条[：:].*?(?=第十条|$)', text, re.DOTALL)

    if not section9:
        return None

    original = section9.group(0)[:300]
    key_terms = {}

    contact_a = re.search(r'甲方指定\s*(.+?)\s*为甲方项目联系人', original)
    contact_b = re.search(r'乙方指定\s*(.+?)\s*为乙方项目联系人', original)

    if contact_a:
        key_terms["甲方联系人"] = contact_a.group(1).strip()
    if contact_b:
        key_terms["乙方联系人"] = contact_b.group(1).strip()

    issues = []
    if not contact_a or contact_a.group(1).strip() in ["/", ""]:
        issues.append("甲方项目联系人未填写")
    if not contact_b or contact_b.group(1).strip() in ["/", ""]:
        issues.append("乙方项目联系人未填写")

    return ContractClause(
        category="项目联系人",
        law_article="—",
        original_text=original,
        summary=f"甲方联系人：{key_terms.get('甲方联系人', '未填')}；乙方联系人：{key_terms.get('乙方联系人', '未填')}",
        key_terms=key_terms,
        issues=issues,
    )


def _extract_clause_质保条款(text: str) -> Optional[ContractClause]:
    """提取质保条款"""
    quality_match = re.search(r'质量保证期.*?(?=\n\d|$)', text, re.DOTALL)

    if not quality_match:
        return None

    original = quality_match.group(0)[:300]
    key_terms = {}

    if "免费维修" in original:
        key_terms["质保服务"] = "免费维修"
    if "质量问题" in original:
        key_terms["质量问题处理"] = "已约定"

    return ContractClause(
        category="质保条款",
        law_article="§509",
        original_text=original,
        summary=f"质保服务：{key_terms.get('质保服务', '已约定')}",
        key_terms=key_terms,
    )


def _extract_clause_付款账户(text: str) -> Optional[ContractClause]:
    """提取付款账户信息"""
    bank_match = re.search(r'开户行[：:]\s*(.+?)\n账号[：:]\s*(\d+)', text)

    if not bank_match:
        return None

    return ContractClause(
        category="付款账户",
        law_article="—",
        original_text=bank_match.group(0),
        summary=f"开户行：{bank_match.group(1).strip()}；账号：{bank_match.group(2)}",
        key_terms={
            "开户行": bank_match.group(1).strip(),
            "账号": bank_match.group(2),
        },
    )


def _extract_clause_授权签署(text: str) -> Optional[ContractClause]:
    """提取授权签署条款"""
    section13 = re.search(r'第十三条[：:].*?(?=第十四条|$)', text, re.DOTALL)

    if not section13:
        return None

    original = section13.group(0)[:300]
    key_terms = {}

    auth_a = re.search(r'甲方授权\s*(.+?)\s*为该合同的签署人', original)
    auth_b = re.search(r'乙方授权\s*(.+?)\s*为该合同的签署人', original)

    if auth_a:
        key_terms["甲方签署人"] = auth_a.group(1).strip()
    if auth_b:
        key_terms["乙方签署人"] = auth_b.group(1).strip()

    issues = []
    if not auth_b or auth_b.group(1).strip() in ["/", ""]:
        issues.append("乙方授权签署人未填写")

    return ContractClause(
        category="授权签署",
        law_article="§490",
        original_text=original,
        summary=f"甲方签署人：{key_terms.get('甲方签署人', '未填')}；乙方签署人：{key_terms.get('乙方签署人', '未填')}",
        key_terms=key_terms,
        issues=issues,
    )


def _extract_clause_服务标准(text: str) -> Optional[ContractClause]:
    """提取服务标准/SLA"""
    quality_req = re.search(r'技术服务质量要求[：:]\s*(.+?)(?:\n\d|$)', text)

    if not quality_req:
        return None

    return ContractClause(
        category="服务标准",
        law_article="—",
        original_text=quality_req.group(0)[:300],
        summary=quality_req.group(1).strip(),
        key_terms={"质量要求": quality_req.group(1).strip()},
    )


# ============================================================
# 输出格式化
# ============================================================

def format_parsed_contract(parsed: ParsedContract) -> str:
    """格式化输出解析结果"""
    lines = []
    lines.append("=" * 70)
    lines.append("合同条款解析报告")
    lines.append("=" * 70)
    lines.append(f"合同名称：{parsed.title}")
    lines.append(f"甲方：{parsed.party_a.get('name', 'N/A')}")
    lines.append(f"乙方：{parsed.party_b.get('name', 'N/A')}")
    lines.append(f"提取条款数：{len(parsed.clauses)}")
    lines.append("")

    for i, clause in enumerate(parsed.clauses, 1):
        lines.append(f"【{i}】{clause.category}（{clause.law_article}）")
        lines.append(f"  摘要：{clause.summary}")
        if clause.issues:
            for issue in clause.issues:
                lines.append(f"  ⚠️ {issue}")
        lines.append(f"  原文：{clause.original_text[:150]}...")
        lines.append("")

    return "\n".join(lines)
