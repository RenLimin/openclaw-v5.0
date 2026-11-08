#!/usr/bin/env python3
"""audit_provenance.py — S7 溯源审计（fail-closed）

输入 (stdin JSON):
  {
    "report_md": "path/to/report.md",
    "raw": {tasks, projects, contracts, ...},
    "workItems": [...],
    "detail": [...],
    "audience": "external" | "internal"
  }

输出 (stdout JSON):
  {status: "PASS"|"BLOCK", missing: [{token, where}], checks: {...}}

退出码: 0=PASS, 2=BLOCK（禁止交付）
"""
import json
import re
import sys
import os
from collections import Counter


# ── 脱敏词表（external 版 grep 必须为 0）─────────────────────────────
REDACTION_TERMS = [
    "ONES", "OA", "BDMS", "GraphQL", "harbor", "SSXM",
    "内部任务号", "回款", "结算", "验收条款",
]


def load_report(path: str) -> str:
    """读取报告内容。"""
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def extract_numbers(text: str) -> list:
    """提取文本中的数字（含日期中的数字）。"""
    # 匹配整数、百分比、日期片段
    numbers = re.findall(r'\d+', text)
    return numbers


def check_numbers(report_text: str, detail: list) -> list:
    """检查报告中的汇总统计数字是否可由明细复算。
    
    只检查汇总数（total/done/in_progress/完成率），不检查合同编号片段、
    日期组件、任务编号等（这些由名词/合同名检查覆盖）。
    """
    missing = []
    # 从明细计算允许的汇总数字
    total = len(detail)
    done = sum(1 for i in detail if i.get("statusCategory") == "done")
    wip = total - done  # 口径与渲染层一致：未完成全部计在途
    allowed_numbers = {str(total), str(done), str(wip), "0"}
    # 完成率（整数百分比）
    if total > 0:
        allowed_numbers.add(str(round(done / total * 100)))

    # 提取报告中的汇总统计数字（只检查独立数字，排除日期/编号/百分比）
    # 策略：只检查 "合计" 行和 "完成率" 附近的数字
    summary_numbers = set()
    for line in report_text.split("\n"):
        if "合计" in line or "完成率" in line or "实际交付" in line:
            for num in re.findall(r'\d+', line):
                summary_numbers.add(num)
    
    for num in summary_numbers:
        if num in allowed_numbers:
            continue
        missing.append({
            "token": num,
            "where": "report summary number not traceable to detail",
            "type": "number",
        })
    return missing


# 模板固定词（报告结构词，非业务名词，不检查）
TEMPLATE_WORDS = {
    "统计周期", "实际交付", "完成率", "服务概览", "涉及合同清单",
    "交付明细", "在推进事项与方案", "交付价值与目标实现", "关键节点",
    "后续安排", "按工作类别", "按产品方向", "按季度", "目标实现状态",
    "已完成", "在途", "未开始", "合计", "数量", "类别", "日期",
    "合同编号", "产品方向", "工作类别", "事项", "状态", "方向",
    "部分实现", "推进中", "已实现", "基本实现", "能力已落地", "能力已建成",
    "往年已达成", "从明细中提取周期", "内里程碑事件", "继续推进",
    "项在途事项", "项目工作汇报", "对外版", "内部版", "合同名称",
    "服务期", "序号", "事项名称", "工作说明", "备注",
    # 常见截断/变体
    "交付价值与目标实", "交付价值与目标", "目标实现状态", "在推进事项",
    "涉及合同", "合同清单", "交付明细", "服务概览", "关键节点",
    "后续安排", "工作类别", "产品方向", "统计周期", "实际交付",
}

# 分类标签（issueType 枚举值，由 normalize 阶段定义，非任务名）
CATEGORY_LABELS = {
    "客户定制需求", "缺陷修复", "问题工单", "产研支持", "专项任务",
    "客户信息", "合同信息", "项目信息", "设备领用情况", "外包（外采）情况",
    "外包/外采情况", "项目履约义务",
}

# 产品方向标签（由映射表定义）
PRODUCT_LABELS = {
    "安全监测", "合规检测", "安卓/SDK 加固", "应用安全测评",
    "小程序加固", "H5/API 安全", "鸿蒙 NEXT 加固",
}


def strip_envelope_sections(text: str) -> str:
    """剥离统一信封区块（元信息块/溯源链/质量信号）。

    这些区块是方法论与审计元信息，不是业务论述；名词审计只扫业务正文。
    """
    out = []
    skip = False
    for line in text.split("\n"):
        stripped = line.strip()
        # 进入/离开可跳过章节：## 0. 溯源链、含「质量信号」的章节
        if stripped.startswith("## "):
            skip = bool(re.match(r"##\s*0?[.、]?\s*溯源链", stripped)) or ("质量信号" in stripped)
        if not skip:
            # 元信息块（H1 下的 > 引用块）也剔除
            if stripped.startswith(">") and ("生成时间" in stripped or "数据基准" in stripped):
                continue
            out.append(line)
    return "\n".join(out)


def check_nouns(report_text: str, detail: list, contracts: list = None) -> list:
    """检查技术/业务名词是否在任务名/描述中命中。

    只检查技术/业务名词，排除模板固定词、分类标签、产品方向标签、
    以及合同官方正式名（合法名词，来源为合同台账）。
    """
    missing = []
    # 合同官方名豁免（合法名词，不需要出现在任务名中）
    exempt_nouns = set()
    for c in (contracts or []):
        official = c.get("officialName") or c.get("projectName") or ""
        for m in re.finditer(r'[一-鿿]{4,8}', official):
            exempt_nouns.add(m.group())
    # 构建允许的名词集合（任务名中的词）
    allowed_nouns = set()
    for item in detail:
        name = item.get("name", "")
        # 提取中文词组（2-8 字）
        for m in re.finditer(r'[\u4e00-\u9fff]{2,8}', name):
            allowed_nouns.add(m.group())
        # 提取英文词
        for m in re.finditer(r'[A-Za-z][A-Za-z0-9_]{1,}', name):
            allowed_nouns.add(m.group())

    # 检查报告中的名词（只扫业务正文，剥离信封/溯源/质量信号）
    body_text = strip_envelope_sections(report_text)
    report_nouns = re.findall(r'[\u4e00-\u9fff]{4,8}', body_text)
    for noun in report_nouns:
        if noun not in allowed_nouns and len(noun) >= 4:
            # 排除模板固定词、分类标签、产品方向标签、合同官方名
            if (noun in TEMPLATE_WORDS or noun in CATEGORY_LABELS
                or noun in PRODUCT_LABELS or noun in exempt_nouns):
                continue
            # 排除包含允许词的子串
            if any(allowed in noun for allowed in allowed_nouns if len(allowed) >= 4):
                continue
            missing.append({
                "token": noun,
                "where": "report noun not found in task names",
                "type": "noun",
            })
    return missing


def check_redaction(report_text: str, audience: str) -> list:
    """检查对外版是否脱敏。"""
    if audience != "external":
        return []
    missing = []
    for term in REDACTION_TERMS:
        if term.lower() in report_text.lower():
            missing.append({
                "token": term,
                "where": f"redaction term found in external report",
                "type": "redaction",
            })
    return missing


def check_contract_names(report_text: str, contracts: list) -> list:
    """检查合同名是否为官方名。"""
    missing = []
    for c in contracts:
        official = c.get("officialName", "")
        if official and official not in report_text:
            # 官方名未出现，可能用了简称
            missing.append({
                "token": official,
                "where": "official contract name not found in report",
                "type": "contract_name",
            })
    return missing


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}"}))
        sys.exit(2)

    report_path = data.get("report_md", "")
    detail = data.get("detail", [])
    contracts = data.get("contracts", [])
    audience = data.get("audience", "internal")

    report_text = load_report(report_path)
    if not report_text:
        print(json.dumps({
            "status": "BLOCK",
            "missing": [{"token": report_path, "where": "report file not found",
                         "type": "file"}],
            "checks": {},
        }, ensure_ascii=False))
        sys.exit(2)

    all_missing = []
    all_missing.extend(check_numbers(report_text, detail))
    all_missing.extend(check_nouns(report_text, detail, contracts))
    all_missing.extend(check_redaction(report_text, audience))
    all_missing.extend(check_contract_names(report_text, contracts))

    # 去重
    seen = set()
    unique_missing = []
    for m in all_missing:
        key = (m["token"], m["type"])
        if key not in seen:
            seen.add(key)
            unique_missing.append(m)

    status = "PASS" if not unique_missing else "BLOCK"
    output = {
        "status": status,
        "missing": unique_missing,
        "checks": {
            "numbers": len(check_numbers(report_text, detail)),
            "nouns": len(check_nouns(report_text, detail, contracts)),
            "redaction": len(check_redaction(report_text, audience)),
            "contractNames": len(check_contract_names(report_text, contracts)),
        },
    }
    print(json.dumps(output, ensure_ascii=False))
    sys.exit(0 if status == "PASS" else 2)


if __name__ == "__main__":
    main()
