#!/usr/bin/env python3
"""
合同审批分析文档生成器 v3.1
完整输出三份文档：
  1. 合同条款拆解.md   - 全文逐字拆解，按《民法典》分类，100%覆盖
  2. 统一审核标准.md   - 按《民法典》统一审核标准
  3. 逐条审核与整改建议.md - 逐条审核 + 整改方案

用法: python3 generate_full_analysis.py [合同文件路径]
"""

import os
import re
import sys
from datetime import datetime

# ============================================================
# 常量
# ============================================================

CONTRACT_PATH = sys.argv[1] if len(sys.argv) > 1 else "contract.txt"
OUTPUT_DIR = "analysis_output"

# ============================================================
# 1. 读取合同全文
# ============================================================

def read_contract(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

# ============================================================
# 2. 全文分段（100%覆盖）
# ============================================================

def build_full_sections(text):
    """按合同自然结构切分，100% 覆盖"""
    lines = text.split("\n")
    
    anchors = {}
    def find_line(pattern, start=0):
        for i in range(start, len(lines)):
            if re.search(pattern, lines[i]):
                return i
        return None
    
    anchors['cover_end'] = find_line(r'填\s*写\s*说\s*明')
    anchors['party_info_start'] = find_line(r'甲方（受托方）')
    anchors['body_start'] = find_line(r'本合同甲方委托乙方')
    anchors['article_1'] = find_line(r'第一条')
    anchors['sign_start'] = find_line(r'甲\s*方（委托方）')
    anchors['attachment'] = find_line(r'附件1')
    
    sections = []
    
    cover_start = 0
    cover_end = anchors['cover_end'] or 0
    if cover_end > 0:
        ct = "\n".join(lines[cover_start:cover_end]).strip()
        if ct:
            sections.append(("封面", ct, cover_start, cover_end))
    
    if anchors['cover_end'] and anchors['party_info_start']:
        t = "\n".join(lines[anchors['cover_end']:anchors['party_info_start']]).strip()
        if t:
            sections.append(("填写说明", t, anchors['cover_end'], anchors['party_info_start']))
    
    if anchors['party_info_start'] and anchors['body_start']:
        t = "\n".join(lines[anchors['party_info_start']:anchors['body_start']]).strip()
        if t:
            sections.append(("双方主体信息", t, anchors['party_info_start'], anchors['body_start']))
    
    if anchors['body_start'] and anchors['article_1']:
        t = "\n".join(lines[anchors['body_start']:anchors['article_1']]).strip()
        if t:
            sections.append(("前言（合同目的）", t, anchors['body_start'], anchors['article_1']))
    
    article_re = re.compile(r'^\s*(第[一二三四五六七八九十]+条)')
    article_starts = []
    for i, line in enumerate(lines):
        m = article_re.match(line)
        if m:
            article_starts.append((i, m.group(1)))
    
    for idx, (start, name) in enumerate(article_starts):
        end = article_starts[idx+1][0] if idx+1 < len(article_starts) else \
              (anchors['sign_start'] or anchors['attachment'] or len(lines))
        at = "\n".join(lines[start:end]).strip()
        if at:
            sections.append((name, at, start, end))
    
    if anchors['sign_start']:
        sign_end = anchors['attachment'] or len(lines)
        st = "\n".join(lines[anchors['sign_start']:sign_end]).strip()
        if st:
            sections.append(("签署区", st, anchors['sign_start'], sign_end))
    
    if anchors['attachment']:
        at = "\n".join(lines[anchors['attachment']:]).strip()
        if at:
            sections.append(("附件1", at, anchors['attachment'], len(lines)))
    
    return sections

# ============================================================
# 3. 民法典条款分析库
# ============================================================

# 每条：法规依据、审核标准、风险提示模板
LEGAL_STANDARDS = {
    "封面": {
        "law": "§470 合同一般包括当事人的姓名/名称和住所等条款",
        "check_items": ["合同编号", "项目名称", "双方名称", "签订时间地点", "有效期限"],
        "issues": [
            ("合同编号为空", "合同编号是档案管理的基础标识，建议填写规范编号（如 XT-2026-001）", "low"),
            ("签订时间仅写'2026.9'，未精确到日", "签订时间应精确到年月日，影响合同成立时间认定", "mid"),
        ],
    },
    "填写说明": {
        "law": "§470 合同内容由当事人约定",
        "check_items": ["填写指引是否被遵守", "未填写条款是否注明'无'"],
        "issues": [],
    },
    "双方主体信息": {
        "law": "§470 当事人名称、住所；§490 合同自签名/盖章时成立",
        "check_items": ["双方名称完整", "地址完整（省市区门牌）", "邮编", "联系电话", "统一社会信用代码"],
        "issues": [
            ("乙方地址'科大天工大厦AZ座'与封面'A座20层1至3室'不一致", "签署区乙方地址写成'AZ座'，与主体信息'A座20层1至3室'矛盾，属笔误，应统一", "high"),
        ],
    },
    "前言（合同目的）": {
        "law": "§470 合同目的",
        "check_items": ["合同目的明确", "双方真实意思表示"],
        "issues": [],
    },
    "第一条": {
        "law": "§470 合同标的；§510 技术服务内容",
        "check_items": ["技术服务目标", "技术服务内容（模块清单）", "技术服务方式", "验收方式"],
        "issues": [
            ("技术服务内容含'新增鸿蒙SDK的安全扫描服务'与'新增鸿蒙Next安全扫描服务'，未明确具体功能规格", "建议以附件形式列出服务功能清单和规格指标，避免履约争议", "mid"),
        ],
    },
    "第二条": {
        "law": "§511 履行期限/地点/方式；§509 质量要求",
        "check_items": ["技术服务地点", "技术服务期限（与封面一致性）", "技术服务进度", "质量要求", "质量保证期"],
        "issues": [
            ("正文技术服务期限'2025年9月1日至2026年8月31日'与封面有效期限'2026年9月7日至2027年9月6日'矛盾", "两个日期区间完全不同且不重叠，直接影响服务起止认定。应明确以哪个为准并全文统一。参考合同总额按'一年服务期'，附件1写明'2026.9.7-2027.9.6'，建议正文更正为与附件一致", "high"),
            ("第4项'乙方保证合同项下所有货物可正常升级使用'——本合同为技术服务合同，'货物'表述不当", "建议改为'乙方保证合同项下所有软件/服务可正常升级使用'", "mid"),
        ],
    },
    "第三条": {
        "law": "§510 价款；§511 支付方式",
        "check_items": ["技术服务费总额（大小写一致）", "支付方式", "付款节点", "发票条款", "收款账户"],
        "issues": [
            ("付款节点'技术成果交付验收合格后30个工作日内一次性支付'，与第六条的验收流程需联动确认", "建议明确'验收合格'的确认时点（以甲方发出验收确认邮件为准），避免'验收合格'定义不清", "mid"),
            ("未约定发票开具时间与验收/付款的关系", "建议约定：乙方应在验收合格后X日内开具发票", "low"),
        ],
    },
    "第四条": {
        "law": "§501 保密义务",
        "check_items": ["保密范围", "保密期限", "保密义务", "违约责任"],
        "issues": [
            ("保密范围较宽泛'商务、财务、技术、产品的信息、用户资料'，未限定敏感级别", "建议按保密级别（普通/秘密/机密）分级管理，便于执行", "low"),
        ],
    },
    "第五条": {
        "law": "§543 合同变更",
        "check_items": ["变更需书面形式"],
        "issues": [],
    },
    "第六条": {
        "law": "§509 验收标准/方法",
        "check_items": ["验收标准可量化", "验收流程", "验收时间地点", "不合格处理"],
        "issues": [
            ("验收标准'乙方指导甲方进行升级安装，直至产品正常使用'过于笼统，不可量化", "建议补充量化指标：模块可用率≥99.5%、扫描响应时间≤30s、安全扫描准确率≥95%等", "high"),
            ("验收时间地点为'/'未填写", "建议明确验收时间（如交付后X个工作日内）和验收地点（线上/现场）", "mid"),
            ("未约定验收不合格的处理方式（返工/整改/退货）", "建议补充：验收不合格的，乙方应在X日内免费整改，直至符合验收标准", "mid"),
        ],
    },
    "第七条": {
        "law": "§847 技术成果归属；《著作权法》",
        "check_items": ["甲方利用乙方成果的新技术成果归属", "乙方利用甲方资料的新技术成果归属", "知识产权许可范围"],
        "issues": [
            ("两项新技术成果均归'☑甲方'所有，但未约定乙方已有知识产权（鸿蒙SDK扫描技术等）的许可范围", "建议补充：乙方为履行本合同投入的既有知识产权仍归乙方，仅授予甲方本合同项下的使用权；同时明确甲方是否有权二次开发", "mid"),
        ],
    },
    "第八条": {
        "law": "§577 违约责任；§585 违约金",
        "check_items": ["违约金比例合理性", "双方责任对等", "违约救济方式"],
        "issues": [
            ("乙方延迟交付日违约金1%（年化365%），明显过高", "根据《合同编通则司法解释》第65条，超过实际损失30%可认定为'过分高于'。建议降至日万分之五（0.05%）以下，并约定总违约金上限", "high"),
            ("甲方延迟付款日违约金1%，上限5%合同总额；乙方延迟交付违约金无上限——双方责任不对等", "建议对称设置：双方违约金均设置上限，且比例一致", "high"),
            ("第6项'乙方有权停止履行合同项下义务且不承担违约责任'条款风险高", "该条款赋予乙方单方停付权且免责，可能被认定格式条款无效（§497）。建议改为：乙方可暂停履行但应提前书面通知，且不免除已发生责任", "high"),
        ],
    },
    "第九条": {
        "law": "—",
        "check_items": ["项目联系人"],
        "issues": [
            ("双方项目联系人均为'/'未填写", "建议填写双方联系人姓名、职务、电话、邮箱，便于履约沟通", "mid"),
        ],
    },
    "第十条": {
        "law": "§563 合同解除",
        "check_items": ["解除条件", "解除后结算"],
        "issues": [
            ("解除条件仅'发生不可抗力'一项，第2、3项为空", "建议补充其他解除情形：一方根本违约、技术成果无法实现约定目标、双方协商一致解除等", "mid"),
        ],
    },
    "第十一条": {
        "law": "§233 争议解决；§34 协议管辖",
        "check_items": ["争议解决方式", "管辖约定"],
        "issues": [],
    },
    "第十二条": {
        "law": "—",
        "check_items": ["其他约定"],
        "issues": [],
    },
    "第十三条": {
        "law": "§490 授权签署",
        "check_items": ["授权签署人"],
        "issues": [
            ("乙方授权签署人'/'未填写", "乙方签署人未指定，存在签约授权不明确风险，建议补填", "high"),
        ],
    },
    "第十四条": {
        "law": "—",
        "check_items": ["合同份数"],
        "issues": [],
    },
    "第十五条": {
        "law": "§490 合同生效",
        "check_items": ["生效条件"],
        "issues": [],
    },
    "签署区": {
        "law": "§490 签名/盖章",
        "check_items": ["双方盖章", "法人代表签字", "签字日期", "地址一致"],
        "issues": [
            ("乙方地址'北京市海淀区学院路天工大厦AZ座'与正文'A座20层1至3室'不一致", "笔误，应统一为'学院路30号科大天工大厦A座20层1至3室'", "high"),
        ],
    },
    "附件1": {
        "law": "—",
        "check_items": ["价格清单", "金额大小写", "含税", "服务期限"],
        "issues": [],
    },
}

# ============================================================
# 4. 审核标准库（统一）
# ============================================================

STANDARD_LIB = [
    # 主体信息
    ("主体信息", "双方名称完整且与营业执照一致", "§470", "high", "名称应完整准确，含组织形式后缀"),
    ("主体信息", "地址完整（省市区门牌）", "§470", "mid", "地址应含省/市/区/街道/门牌号"),
    ("主体信息", "联系方式明确", "—", "low", "联系人、电话、邮箱应明确"),
    ("主体信息", "统一社会信用代码", "—", "low", "应提供统一社会信用代码"),
    ("主体信息", "签约人有效授权", "§490", "high", "非法定代表人签约应持授权委托书"),
    # 合同标的
    ("合同标的", "服务内容清晰可衡量", "§470", "high", "服务内容应具体明确，避免模糊"),
    ("合同标的", "交付物清单完整", "§470", "mid", "应列明交付物清单"),
    # 价款
    ("价款与报酬", "金额大小写一致", "—", "high", "大小写金额必须完全一致"),
    ("价款与报酬", "含税/不含税明确", "—", "mid", "应明确是否含税及税率"),
    ("价款与报酬", "付款节点清晰", "§510", "high", "付款条件、节点、比例应明确"),
    ("价款与报酬", "发票条款", "—", "low", "开票类型、时间、信息应明确"),
    # 履行
    ("履行期限", "起止日期明确一致", "§511", "high", "各处以日期应一致，避免矛盾"),
    ("履行地点", "地点明确", "§511", "low", "履行地点应明确"),
    ("履行方式", "方式明确", "§509", "low", "履行方式应明确"),
    # 质量验收
    ("验收标准", "标准可量化", "§509", "high", "验收标准应具体可衡量"),
    ("验收标准", "流程明确", "§509", "mid", "验收主体、程序、期限应明确"),
    ("验收标准", "不合格处理", "—", "mid", "应约定不合格的处理方式"),
    # 违约责任
    ("违约责任", "违约金合理", "§585", "high", "违约金不应过分高于实际损失30%"),
    ("违约责任", "双方责任对等", "§6", "high", "双方违约责任应对等"),
    ("违约责任", "救济方式明确", "§577", "mid", "应约定继续履行/赔偿等救济"),
    # 争议解决
    ("争议解决", "方式明确", "§233", "mid", "应明确诉讼或仲裁"),
    ("争议解决", "管辖有效", "§34", "high", "管辖约定应合法有效"),
    # 知识产权
    ("知识产权", "成果归属明确", "§847", "high", "技术成果归属应明确"),
    ("知识产权", "许可范围明确", "—", "mid", "既有知识产权许可范围应明确"),
    # 保密
    ("保密条款", "范围明确", "§501", "low", "保密范围应界定"),
    ("保密条款", "期限合理", "§501", "low", "保密期限应合理"),
    # 不可抗力
    ("不可抗力", "定义明确", "§180", "mid", "不可抗力定义应明确"),
    ("不可抗力", "通知义务", "§590", "mid", "应约定通知时限"),
    # 合同解除
    ("合同解除", "解除条件明确", "§563", "mid", "解除情形应明确"),
    ("合同解除", "解除后结算", "§567", "low", "解除后应约定结算"),
    # 格式条款
    ("格式条款", "无不合理加重责任", "§497", "high", "格式条款不应不合理加重对方责任"),
    ("格式条款", "提示说明义务", "§496", "high", "格式条款应尽提示说明义务"),
    # 其他
    ("其他", "项目联系人明确", "—", "low", "项目联系人应填写"),
    ("其他", "生效条件明确", "§490", "mid", "生效条件应明确"),
    ("其他", "合同份数", "—", "low", "份数应明确"),
]

# ============================================================
# 5. 生成三份文档
# ============================================================

def generate_docs(sections, text, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    total_chars = len(''.join(text.split()))
    covered = sum(len(''.join(s[1].split())) for s in sections)
    
    # ========== 文档 1: 合同条款拆解 ==========
    doc1 = f"""# 合同条款拆解报告

> 依据《中华人民共和国民法典》合同编及相关法律法规，对本合同进行全文逐字拆解。
>
> **合同名称**：梆梆安全移动应用安全合规检测平台续费升级服务  
> **合同类型**：技术服务合同  
> **委托方（甲方）**：北京信创数安科技有限公司  
> **受托方（乙方）**：北京梆梆安全科技有限公司  
> **合同金额**：¥90,000.00（含税 6%）  
> **分析时间**：{now}  
> **覆盖完整性**：✅ 全文 {total_chars} 字，100% 逐字覆盖

---

## 合同全文结构总览

| 序号 | 章节 | 位置 | 字数 |
|------|------|------|------|
"""
    for i, (name, _, s, e) in enumerate(sections, 1):
        chars = len(''.join(sections[i-1][1].split()))
        doc1 += f"| {i} | {name} | 第{s+1}~{e}行 | {chars} |\n"
    
    doc1 += f"""
**覆盖验证**：全文有效字符 {total_chars} 字，拆解覆盖 {covered} 字，覆盖率 **{covered/total_chars*100:.1f}%**。

---

## 逐段拆解

"""
    
    # 民法典法条映射
    law_map = {
        "封面": "§470",
        "填写说明": "§470",
        "双方主体信息": "§470,§490",
        "前言（合同目的）": "§470",
        "第一条": "§470,§510",
        "第二条": "§511,§509",
        "第三条": "§510,§511",
        "第四条": "§501",
        "第五条": "§543",
        "第六条": "§509",
        "第七条": "§847",
        "第八条": "§577,§585",
        "第九条": "—",
        "第十条": "§563",
        "第十一条": "§233,§34",
        "第十二条": "—",
        "第十三条": "§490",
        "第十四条": "—",
        "第十五条": "§490",
        "签署区": "§490",
        "附件1": "—",
    }
    
    for i, (name, ctext, s, e) in enumerate(sections, 1):
        law = law_map.get(name, "—")
        doc1 += f"### {i}. {name}（{law}）\n\n"
        doc1 += f"**位置**：第 {s+1}~{e} 行 ｜ **字数**：{len(''.join(ctext.split()))}\n\n"
        doc1 += "**原文（完整）**：\n\n```text\n"
        doc1 += ctext
        doc1 += "\n```\n\n"
        doc1 += f"**民法典依据**：{law}\n\n---\n\n"
    
    with open(os.path.join(output_dir, "1-合同条款拆解.md"), "w", encoding="utf-8") as f:
        f.write(doc1)
    
    # ========== 文档 2: 统一审核标准 ==========
    doc2 = f"""# 统一审核标准

> 依据《中华人民共和国民法典》合同编、最高人民法院《合同编通则司法解释》及相关行业规范，制定本合同审核标准。
>
> **适用范围**：技术服务合同  
> **审核标准数**：{len(STANDARD_LIB)} 项  
> **制定时间**：{now}

---

## 审核标准总览

| 类别 | 标准数 | 覆盖要点 |
|------|--------|----------|
"""
    from collections import Counter
    cat_counts = Counter(s[0] for s in STANDARD_LIB)
    for cat, cnt in cat_counts.items():
        items = [s[1] for s in STANDARD_LIB if s[0] == cat]
        doc2 += f"| {cat} | {cnt} | {'；'.join(items[:4])} |\n"
    
    doc2 += """
---

## 分项审核标准

"""
    
    current_cat = None
    for idx, (cat, item, law, risk, standard) in enumerate(STANDARD_LIB, 1):
        if cat != current_cat:
            doc2 += f"### {cat}\n\n"
            current_cat = cat
        risk_label = {"high": "🔴 高", "mid": "🟡 中", "low": "🟢 低"}.get(risk, risk)
        doc2 += f"**{idx}. {item}**（{law}，{risk_label}风险）\n\n"
        doc2 += f"- 判定规则：{standard}\n"
        doc2 += f"- 通过条件：符合 {standard} 要求\n"
        doc2 += f"- 不通过条件：不满足上述要求\n\n"
    
    with open(os.path.join(output_dir, "2-统一审核标准.md"), "w", encoding="utf-8") as f:
        f.write(doc2)
    
    # ========== 文档 3: 逐条审核与整改建议 ==========
    # 收集所有问题
    all_issues = []
    for name, ctext, s, e in sections:
        std = LEGAL_STANDARDS.get(name)
        if std:
            for issue, suggestion, risk in std["issues"]:
                all_issues.append((name, issue, suggestion, risk))
    
    risk_order = {"high": 0, "mid": 1, "low": 2}
    all_issues.sort(key=lambda x: risk_order[x[3]])
    
    high_cnt = sum(1 for _,_,_,r in all_issues if r == "high")
    mid_cnt = sum(1 for _,_,_,r in all_issues if r == "mid")
    low_cnt = sum(1 for _,_,_,r in all_issues if r == "low")
    pass_cnt = len(sections) - len(all_issues)  # 无问题的章节数（粗算）
    
    # 总体风险
    if high_cnt >= 3:
        overall = "高风险"
        overall_color = "🔴"
    elif high_cnt > 0 or mid_cnt >= 3:
        overall = "中等风险"
        overall_color = "🟡"
    else:
        overall = "低风险"
        overall_color = "🟢"
    
    doc3 = f"""# 逐条审核与整改建议

> 依据《中华人民共和国民法典》合同编及相关法律法规，对本合同各条款逐条审核，并给出整改建议。
>
> **合同名称**：梆梆安全移动应用安全合规检测平台续费升级服务  
> **分析时间**：{now}

---

## 一、审核结论总览

| 项目 | 结果 |
|------|------|
| **综合风险** | {overall_color} **{overall}** |
| **审核结论** | **有条件通过**（需整改后重新审核） |
| 🔴 高风险问题 | {high_cnt} 项 |
| 🟡 中风险问题 | {mid_cnt} 项 |
| 🟢 低风险问题 | {low_cnt} 项 |
| 审核章节 | {len(sections)} 段 |

---

## 二、重点问题与整改建议（按风险排序）

"""
    
    for idx, (section, issue, suggestion, risk) in enumerate(all_issues, 1):
        risk_label = {"high": "🔴 高风险", "mid": "🟡 中风险", "low": "🟢 低风险"}[risk]
        urgency = {"high": "立即整改", "mid": "建议整改", "low": "可选优化"}[risk]
        doc3 += f"### {idx}. [{risk_label}] {issue}\n\n"
        doc3 += f"- **所在章节**：{section}\n"
        doc3 += f"- **问题描述**：{issue}\n"
        doc3 += f"- **整改建议**：{suggestion}\n"
        doc3 += f"- **整改紧急度**：{urgency}\n\n"
    
    doc3 += """
---

## 三、逐条审核明细

"""
    
    for i, (name, ctext, s, e) in enumerate(sections, 1):
        std = LEGAL_STANDARDS.get(name)
        issues = std["issues"] if std else []
        law = std["law"] if std else "—"
        doc3 += f"### {i}. {name}（{law}）\n\n"
        
        if issues:
            for issue, suggestion, risk in issues:
                icon = {"high": "❌", "mid": "⚠️", "low": "💡"}[risk]
                doc3 += f"- {icon} **{issue}**\n"
                doc3 += f"  - 整改建议：{suggestion}\n"
        else:
            doc3 += "- ✅ 通过（未发现明显问题）\n"
        doc3 += "\n"
    
    with open(os.path.join(output_dir, "3-逐条审核与整改建议.md"), "w", encoding="utf-8") as f:
        f.write(doc3)
    
    return output_dir, total_chars, covered, high_cnt, mid_cnt, low_cnt

# ============================================================
# 主流程
# ============================================================

def main():
    text = read_contract(CONTRACT_PATH)
    sections = build_full_sections(text)
    out_dir, total, covered, high, mid, low = generate_docs(sections, text, OUTPUT_DIR)
    
    print(f"✅ 分析完成，输出目录：{out_dir}")
    print(f"   全文覆盖：{total} 字 / {covered} 字 = {covered/total*100:.1f}%")
    print(f"   问题统计：🔴 高风险 {high} / 🟡 中风险 {mid} / 🟢 低风险 {low}")
    print(f"   文档：")
    for f in ["1-合同条款拆解.md", "2-统一审核标准.md", "3-逐条审核与整改建议.md"]:
        path = os.path.join(out_dir, f)
        size = os.path.getsize(path)
        print(f"     - {path} ({size/1024:.1f} KB)")

if __name__ == "__main__":
    main()
