#!/usr/bin/env python3
"""
合同审核引擎（核心）
组件: SCA-001 (L4)
功能: 整合条款解析器 + 审核标准库，逐条审核合同并输出结果

三大能力：
1. 条款解析：按民法典合同编 28 条核心条款类别，逐条解析合同原文
2. 审核标准：基于民法典 + 司法解释 + 行业规范，形成统一审核标准
3. 逐条审核：按标准逐条审核，输出结构化结果 + 修改建议
"""

import argparse
import json
import os
import re
import sqlite3
from datetime import datetime

from contract_parser import parse_contract, format_parsed_contract, ContractClause, CLAUSE_CATEGORIES
from audit_standard import AUDIT_CRITERIA, get_criterion_by_id, get_all_categories

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "contracts.db")


# ============================================================
# 审核结果数据结构
# ============================================================

class AuditResult:
    """单条审核结果"""
    def __init__(self, criterion_id, category, item, law_article, risk_level,
                 status, evidence="", issue="", suggestion="", reference_law=""):
        self.criterion_id = criterion_id
        self.category = category
        self.item = item
        self.law_article = law_article
        self.risk_level = risk_level
        self.status = status          # pass / warning / fail / na
        self.evidence = evidence      # 证据（合同原文引用）
        self.issue = issue            # 发现的问题
        self.suggestion = suggestion  # 修改建议
        self.reference_law = reference_law

    def to_dict(self):
        return {
            "id": self.criterion_id,
            "category": self.category,
            "item": self.item,
            "law": self.law_article,
            "risk": self.risk_level,
            "status": self.status,
            "evidence": self.evidence,
            "issue": self.issue,
            "suggestion": self.suggestion,
        }


class AuditReport:
    """完整审核报告"""
    def __init__(self, contract_no="", title=""):
        self.contract_no = contract_no
        self.title = title
        self.audit_time = datetime.now().isoformat()
        self.results = []
        self.parsed_clauses = []

    def add_result(self, result: AuditResult):
        self.results.append(result)

    @property
    def summary(self):
        pass_count = sum(1 for r in self.results if r.status == "pass")
        warning_count = sum(1 for r in self.results if r.status == "warning")
        fail_count = sum(1 for r in self.results if r.status == "fail")
        na_count = sum(1 for r in self.results if r.status == "na")
        return {
            "total": len(self.results),
            "pass": pass_count,
            "warning": warning_count,
            "fail": fail_count,
            "na": na_count,
        }

    @property
    def overall_risk(self):
        fail_high = sum(1 for r in self.results if r.status == "fail" and r.risk_level == "high")
        fail_mid = sum(1 for r in self.results if r.status == "fail" and r.risk_level == "medium")
        warn_high = sum(1 for r in self.results if r.status == "warning" and r.risk_level == "high")

        if fail_high > 0:
            return "high"
        elif fail_mid > 0 or warn_high >= 2:
            return "medium"
        else:
            return "low"

    @property
    def recommendation(self):
        risk = self.overall_risk
        if risk == "high":
            return "驳回（高风险项必须修改）"
        elif risk == "medium":
            return "有条件通过（建议修改后重新审核）"
        else:
            return "通过"


# ============================================================
# 逐条审核逻辑
# ============================================================

def audit_contract(text: str, parsed_clauses: list) -> AuditReport:
    """
    对合同进行逐条审核

    Args:
        text: 合同原文
        parsed_clauses: 条款解析结果

    Returns:
        AuditReport: 完整审核报告
    """
    report = AuditReport()

    # 将解析结果转为字典，方便查找
    clause_dict = {c.category: c for c in parsed_clauses}

    # 按审核标准逐条审核
    for criterion in AUDIT_CRITERIA:
        result = _audit_by_criterion(text, criterion, clause_dict)
        report.add_result(result)

    report.parsed_clauses = parsed_clauses
    return report


def _audit_by_criterion(text: str, criterion, clause_dict: dict) -> AuditResult:
    """按单个审核标准进行审核"""

    cat = criterion.category
    clause = clause_dict.get(cat)

    # 根据条款类别分发审核逻辑
    audit_functions = {
        "主体信息": _audit_主体信息,
        "合同标的": _audit_合同标的,
        "价款与报酬": _audit_价款与报酬,
        "付款条件": _audit_付款条件,
        "验收标准": _audit_验收标准,
        "违约责任": _audit_违约责任,
        "争议解决": _audit_争议解决,
        "知识产权": _audit_知识产权,
        "保密条款": _audit_保密条款,
        "不可抗力": _audit_不可抗力,
        "合同解除": _audit_合同解除,
        "合同变更": _audit_合同变更,
        "格式条款": _audit_格式条款,
        "合同生效": _audit_合同生效,
        "项目联系人": _audit_项目联系人,
        "质保条款": _audit_质保条款,
        "授权签署": _audit_授权签署,
    }

    audit_fn = audit_functions.get(cat)
    if audit_fn:
        return audit_fn(text, criterion, clause_dict)

    # 默认审核：检查条款是否存在
    return _audit_default(text, criterion, clause_dict)


def _audit_主体信息(text, criterion, clause_dict):
    """审核主体信息"""
    cid = criterion.id

    if cid == "1.1":
        names = re.findall(r'(甲方|乙方|委托方|受托方)[（(]?[^）)]*[）)]?[：:]\s*([\u4e00-\u9fa5（）\(\)]+?)(?:\n|地址)', text)
        if len(names) >= 2:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             f"甲方：{names[0][1]}；乙方：{names[1][1]}", "", criterion.reference_law)
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             f"仅提取到{len(names)}方名称",
                             "一方或双方名称格式不标准，可能影响主体识别",
                             criterion.suggestion_template, criterion.reference_law)

    elif cid == "1.2":
        addrs = re.findall(r'地址[：:]\s*(.+?)(?:\n|邮编)', text)
        if len(addrs) >= 2:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             f"双方地址已载明", "", criterion.reference_law)
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             f"仅提取到{len(addrs)}方地址",
                             "一方或双方地址不完整",
                             criterion.suggestion_template, criterion.reference_law)

    elif cid == "1.3":
        phones = re.findall(r'联系电话[：:]\s*(\d[\d\-]+)', text)
        emails = re.findall(r'([\w.+-]+@[\w-]+\.[\w]+)', text)
        if len(phones) >= 2 or len(emails) >= 2:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             f"电话：{len(phones)}个；邮箱：{len(emails)}个", "", "")
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "联系方式不足",
                             "双方联系方式不完整",
                             criterion.suggestion_template)

    elif cid == "1.4":
        credit = re.search(r'统一社会信用代码[：:]\s*(\d{18})', text)
        if credit:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             f"统一社会信用代码：{credit.group(1)}", "")
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "未提取到统一社会信用代码",
                             "建议补充统一社会信用代码",
                             criterion.suggestion_template)

    elif cid == "1.5":
        has_auth = "授权" in text and ("签署" in text or "签字" in text)
        has_seal = "盖章" in text or "签章" in text
        if has_auth:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             "已约定授权签署条款", "", criterion.reference_law)
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "授权签署条款不明确",
                             "建议补充授权签署条款",
                             criterion.suggestion_template, criterion.reference_law)

    return _audit_default(text, criterion, clause_dict)


def _audit_合同标的(text, criterion, clause_dict):
    """审核合同标的"""
    cid = criterion.id

    if cid == "2.1":
        content_match = re.search(r'技术服务的内容[：:]\s*(.+?)(?:\n\d|$)', text)
        if content_match and len(content_match.group(1).strip()) > 10:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             content_match.group(1).strip()[:100], "", criterion.reference_law)
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "服务内容描述较短或未提取到",
                             "服务内容描述不够详细",
                             criterion.suggestion_template, criterion.reference_law)

    elif cid == "2.2":
        method_match = re.search(r'技术服务的方式[：:]\s*(.+?)(?:\n\d|$)', text)
        if method_match:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             method_match.group(1).strip()[:100], "")
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "未提取到服务方式",
                             "服务方式未明确约定",
                             criterion.suggestion_template)

    elif cid == "2.3":
        # 检查是否有交付物清单
        has_deliverables = any(kw in text for kw in ["交付物", "交付清单", "交付成果", "工作成果"])
        if has_deliverables:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass", "已约定交付物", "")
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "未明确交付物清单",
                             "建议补充完整的交付物清单",
                             criterion.suggestion_template)

    elif cid == "2.4":
        dates = re.findall(r'\d{4}年\d{1,2}月\d{1,2}日', text)
        if len(dates) >= 2:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             f"起止日期：{dates[0]} 至 {dates[1]}", "", criterion.reference_law)
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             f"仅提取到{len(dates)}个日期",
                                         "服务期限日期不完整或格式不统一",
                             criterion.suggestion_template, criterion.reference_law)

    return _audit_default(text, criterion, clause_dict)


def _audit_价款与报酬(text, criterion, clause_dict):
    """审核价款与报酬"""
    cid = criterion.id

    if cid == "3.1":
        amount_match = re.search(r'[￥¥]\s*([\d,]+\.?\d*)\s*大写[：:]?\s*([\u4e00-\u9fa5零壹贰叁肆伍陆柒捌玖拾佰仟万亿元整]+)', text)
        if amount_match:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             f"¥{amount_match.group(1)}（{amount_match.group(2)}）", "")
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "未提取到完整的大小写金额",
                             "建议补充大写金额",
                             criterion.suggestion_template)

    elif cid == "3.2":
        tax_match = re.search(r'税率(\d+%)', text)
        if tax_match:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass", f"税率：{tax_match.group(1)}", "")
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "未提取到税率",
                             "建议明确税率",
                             criterion.suggestion_template)

    elif cid == "3.3":
        if "含税" in text:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass", "已约定含税", "")
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "未明确是否含税",
                             "建议明确价款是否含税",
                             criterion.suggestion_template)

    return _audit_default(text, criterion, clause_dict)


def _audit_付款条件(text, criterion, clause_dict):
    """审核付款条件"""
    cid = criterion.id

    if cid == "4.1":
        if "验收合格后" in text and "工作日" in text:
            day_match = re.search(r'(\d+)\s*个工作日', text)
            days = day_match.group(1) if day_match else "?"
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             f"验收合格后{days}个工作日内支付", "", criterion.reference_law)
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "付款条件不够明确",
                             "建议明确付款时间和条件",
                             criterion.suggestion_template, criterion.reference_law)

    elif cid == "4.2":
        if "转账" in text or "银行" in text:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass", "已约定银行转账", "")
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "未明确支付方式",
                             "建议明确支付方式",
                             criterion.suggestion_template)

    elif cid == "4.3":
        invoice = re.search(r'增值税专用发?票.*?税率(\d+%)', text)
        if invoice:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             f"增值税专用发票，税率{invoice.group(1)}", "")
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "发票要求不够明确",
                             "建议明确发票类型、税率、开具时间",
                             criterion.suggestion_template)

    return _audit_default(text, criterion, clause_dict)


def _audit_验收标准(text, criterion, clause_dict):
    """审核验收标准"""
    cid = criterion.id

    if cid == "5.1":
        standard_match = re.search(r'验收标准[：:]\s*(.+?)(?:\n\d|$)', text)
        if standard_match and len(standard_match.group(1).strip()) > 5:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             standard_match.group(1).strip()[:100], "", criterion.reference_law)
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "验收标准较简单",
                             "建议将验收标准量化",
                             criterion.suggestion_template, criterion.reference_law)

    elif cid == "5.2":
        method_match = re.search(r'验收方法[：:]\s*(.+?)(?:\n\d|$)', text)
        if method_match:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             method_match.group(1).strip()[:100], "")
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "未明确验收方法",
                             "建议明确验收流程",
                             criterion.suggestion_template)

    elif cid == "5.3":
        if "不合格" in text or "返工" in text or "扣款" in text:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass", "已约定不合格处理方式", "")
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "未约定不合格处理方式",
                             "建议补充不合格处理条款",
                             criterion.suggestion_template)

    return _audit_default(text, criterion, clause_dict)


def _audit_违约责任(text, criterion, clause_dict):
    """审核违约责任"""
    cid = criterion.id

    if cid == "6.1":
        # 检查双方违约责任是否对等
        section8 = re.search(r'第八条.*?(?=第九条|$)', text, re.DOTALL)
        if section8:
            text8 = section8.group(0)
            # 检查是否有甲乙双方的违约条款
            has_a = "甲方" in text8 and ("违约" in text8 or "违约金" in text8)
            has_b = "乙方" in text8 and ("违约" in text8 or "违约金" in text8)
            if has_a and has_b:
                return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                                 criterion.risk_level, "pass",
                                 "双方违约责任均已约定", "", criterion.reference_law)
            else:
                return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                                 criterion.risk_level, "warning",
                                 f"甲方违约：{'有' if has_a else '无'}；乙方违约：{'有' if has_b else '无'}",
                                 "双方违约责任不对等",
                                 criterion.suggestion_template, criterion.reference_law)
        return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                         criterion.risk_level, "warning", "未提取到违约责任条款",
                         "违约责任条款缺失", criterion.suggestion_template, criterion.reference_law)

    elif cid == "6.2":
        # 检查日违约金比例
        daily_rates = re.findall(r'每逾期一日.*?(\d+(?:\.\d+)?)\s*%', text)
        issues = []
        for rate in daily_rates:
            try:
                if float(rate) > 0.5:
                    issues.append(f"日违约金{rate}%偏高（年化{float(rate)*365:.0f}%）")
            except ValueError:
                pass

        if issues:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             f"日违约金比例：{daily_rates}",
                             "；".join(issues),
                             criterion.suggestion_template, criterion.reference_law)
        elif daily_rates:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             f"日违约金比例：{daily_rates}", "", criterion.reference_law)
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "na",
                             "未提取到日违约金比例", "")

    elif cid == "6.3":
        cap_match = re.search(r'最高不超过合同总额的(\d+)%', text)
        if cap_match:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             f"违约金上限：{cap_match.group(1)}%", "")
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "未约定违约金上限",
                             "建议约定违约金上限",
                             criterion.suggestion_template)

    elif cid == "6.4":
        if "继续履行" in text:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass", "已约定继续履行", "")
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "未约定继续履行",
                             "建议补充继续履行条款",
                             criterion.suggestion_template)

    return _audit_default(text, criterion, clause_dict)


def _audit_争议解决(text, criterion, clause_dict):
    """审核争议解决"""
    cid = criterion.id

    if cid == "7.1":
        court_match = re.search(r'依法向\s*(.+?)人民法院起诉', text)
        if court_match:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             f"管辖法院：{court_match.group(1)}人民法院", "", criterion.reference_law)
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "未明确管辖法院",
                             "建议明确管辖法院",
                             criterion.suggestion_template, criterion.reference_law)

    elif cid == "7.2":
        has_court = "人民法院" in text or "起诉" in text
        has_arbitration = "仲裁" in text
        if has_court and has_arbitration:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "同时约定了诉讼和仲裁",
                             "诉讼和仲裁只能选择一种",
                             criterion.suggestion_template)
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             "争议解决方式唯一", "")

    return _audit_default(text, criterion, clause_dict)


def _audit_知识产权(text, criterion, clause_dict):
    """审核知识产权"""
    cid = criterion.id

    if cid == "8.1":
        ip_match = re.search(r'新技术成果.*归.*所有', text)
        if ip_match:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             ip_match.group(0)[:80], "", criterion.reference_law)
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "知识产权归属约定不明确",
                             "建议明确知识产权归属",
                             criterion.suggestion_template, criterion.reference_law)

    elif cid == "8.2":
        if "背景" in text and "知识产权" in text:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass", "已约定背景知识产权", "")
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "na",
                             "未明确背景知识产权",
                             "建议补充背景知识产权条款",
                             criterion.suggestion_template)

    return _audit_default(text, criterion, clause_dict)


def _audit_保密条款(text, criterion, clause_dict):
    """审核保密条款"""
    cid = criterion.id

    if cid == "9.1":
        section4 = re.search(r'第四条.*?(?=第五条|$)', text, re.DOTALL)
        if section4 and "保密" in section4.group(0):
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             "已约定保密条款", "", criterion.reference_law)
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "保密条款缺失",
                             "建议补充保密条款",
                             criterion.suggestion_template, criterion.reference_law)

    elif cid == "9.2":
        if "保密" in text and ("终止" in text or "期满" in text):
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             "保密期限延续至合同终止后", "")
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "保密期限不明确",
                             "建议明确保密期限",
                             criterion.suggestion_template)

    elif cid == "9.3":
        if "律师费" in text or "赔偿" in text:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             "已约定违反保密的赔偿", "")
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "未约定保密违约责任",
                             "建议补充违反保密义务的赔偿责任",
                             criterion.suggestion_template)

    return _audit_default(text, criterion, clause_dict)


def _audit_不可抗力(text, criterion, clause_dict):
    """审核不可抗力"""
    cid = criterion.id

    if cid == "10.1":
        if "不可抗力" in text:
            # 检查是否有定义
            has_def = "不能预见" in text or "不能避免" in text or "客观情况" in text
            if has_def:
                return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                                 criterion.risk_level, "pass",
                                 "已定义不可抗力", "", criterion.reference_law)
            else:
                return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                                 criterion.risk_level, "warning",
                                 "提及不可抗力但无定义",
                                 "建议补充不可抗力的定义",
                                 criterion.suggestion_template, criterion.reference_law)
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "na",
                             "无不可抗力条款", "", criterion.reference_law)

    elif cid == "10.2":
        if "通知" in text and ("不可抗力" in text):
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             "已约定通知义务", "", criterion.reference_law)
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "未约定通知义务",
                             "建议补充通知义务和期限",
                             criterion.suggestion_template, criterion.reference_law)

    elif cid == "10.3":
        if "免责" in text or "延期" in text or "解除" in text:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             "已约定不可抗力后果", "")
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "未约定不可抗力后果",
                             "建议补充不可抗力的后果处理",
                             criterion.suggestion_template)

    return _audit_default(text, criterion, clause_dict)


def _audit_合同解除(text, criterion, clause_dict):
    """审核合同解除"""
    cid = criterion.id

    if cid == "11.1":
        section10 = re.search(r'第十条.*?(?=第十一条|$)', text, re.DOTALL)
        if section10 and "解除" in section10.group(0):
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             "已约定合同解除条件", "", criterion.reference_law)
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "合同解除条件不明确",
                             "建议明确解除条件",
                             criterion.suggestion_template, criterion.reference_law)

    elif cid == "11.2":
        if "结算" in text or "清理" in text:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             "已约定解除后结算", "")
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "未约定解除后结算",
                             "建议补充结算清理条款",
                             criterion.suggestion_template)

    return _audit_default(text, criterion, clause_dict)


def _audit_合同变更(text, criterion, clause_dict):
    """审核合同变更"""
    cid = criterion.id

    if cid == "12.1":
        if "协商一致" in text and "书面" in text:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             "已约定变更需协商一致+书面形式", "", criterion.reference_law)
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "合同变更程序不明确",
                             "建议明确变更条件",
                             criterion.suggestion_template, criterion.reference_law)

    return _audit_default(text, criterion, clause_dict)


def _audit_格式条款(text, criterion, clause_dict):
    """审核格式条款"""
    cid = criterion.id

    if cid == "13.1":
        # 检查是否有明显不对等的条款
        has_unfair = False
        evidence = ""
        # 检查：一方有权停止履行且不承担违约责任
        if re.search(r'有权停止履行.*不承担违约责任', text):
            has_unfair = True
            evidence = "存在'有权停止履行且不承担违约责任'的条款"
        # 检查：单方面变更权
        if re.search(r'有权单方面变更', text):
            has_unfair = True
            evidence += "；存在单方面变更权"

        if has_unfair:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning", evidence,
                             "可能存在不公平格式条款",
                             criterion.suggestion_template, criterion.reference_law)
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             "未发现明显不公平格式条款", "", criterion.reference_law)

    elif cid == "13.2":
        if re.search(r'排除.*权利|免除.*责任', text):
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "可能存在排除对方主要权利的条款",
                             "建议删除或修改",
                             criterion.suggestion_template, criterion.reference_law)
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             "未发现排除对方主要权利的条款", "", criterion.reference_law)

    return _audit_default(text, criterion, clause_dict)


def _audit_合同生效(text, criterion, clause_dict):
    """审核合同生效"""
    cid = criterion.id

    if cid == "14.1":
        if "签字盖章" in text and "生效" in text:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             "经双方签字盖章后生效", "", criterion.reference_law)
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "生效条件不明确",
                             "建议明确生效条件",
                             criterion.suggestion_template, criterion.reference_law)

    elif cid == "14.2":
        copies = re.search(r'一式\s*(\w+)\s*份', text)
        if copies:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             f"一式{copies.group(1)}份", "")
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "warning",
                             "未约定合同份数",
                             "建议明确合同份数",
                             criterion.suggestion_template)

    return _audit_default(text, criterion, clause_dict)


def _audit_项目联系人(text, criterion, clause_dict):
    """审核项目联系人"""
    cid = criterion.id

    if cid == "15.1":
        section9 = re.search(r'第九条.*?(?=第十条|$)', text, re.DOTALL)
        if section9:
            text9 = section9.group(0)
            contact_a = re.search(r'甲方指定\s*(.+?)\s*为', text9)
            contact_b = re.search(r'乙方指定\s*(.+?)\s*为', text9)

            a_name = contact_a.group(1).strip() if contact_a else "/"
            b_name = contact_b.group(1).strip() if contact_b else "/"

            if a_name in ["/", ""] or b_name in ["/", ""]:
                return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                                 criterion.risk_level, "warning",
                                 f"甲方：{a_name}；乙方：{b_name}",
                                 "项目联系人未填写",
                                 criterion.suggestion_template)
            else:
                return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                                 criterion.risk_level, "pass",
                                 f"甲方：{a_name}；乙方：{b_name}", "")
        return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                         criterion.risk_level, "warning", "未提取到项目联系人条款",
                         "项目联系人缺失", criterion.suggestion_template)

    return _audit_default(text, criterion, clause_dict)


def _audit_质保条款(text, criterion, clause_dict):
    """审核质保条款"""
    cid = criterion.id

    if cid == "16.1":
        if "质量保证期" in text:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             "已约定质量保证期", "")
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "na",
                             "未约定质量保证期",
                             "建议明确质量保证期",
                             criterion.suggestion_template)

    elif cid == "16.2":
        if "免费维修" in text or "响应时间" in text:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "pass",
                             "已约定质保服务", "")
        else:
            return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                             criterion.risk_level, "na",
                             "未约定质保范围和响应时间",
                             "建议明确",
                             criterion.suggestion_template)

    return _audit_default(text, criterion, clause_dict)


def _audit_授权签署(text, criterion, clause_dict):
    """审核授权签署"""
    cid = criterion.id

    if cid == "17.1":
        section13 = re.search(r'第十三条.*?(?=第十四条|$)', text, re.DOTALL)
        if section13:
            text13 = section13.group(0)
            auth_a = re.search(r'甲方授权\s*(.+?)\s*为', text13)
            auth_b = re.search(r'乙方授权\s*(.+?)\s*为', text13)

            a_name = auth_a.group(1).strip() if auth_a else "/"
            b_name = auth_b.group(1).strip() if auth_b else "/"

            if a_name in ["/", ""] or b_name in ["/", ""]:
                missing = []
                if a_name in ["/", ""]:
                    missing.append("甲方")
                if b_name in ["/", ""]:
                    missing.append("乙方")
                return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                                 criterion.risk_level, "warning",
                                 f"甲方签署人：{a_name}；乙方签署人：{b_name}",
                                 f"{'、'.join(missing)}授权签署人未填写",
                                 criterion.suggestion_template, criterion.reference_law)
            else:
                return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                                 criterion.risk_level, "pass",
                                 f"甲方签署人：{a_name}；乙方签署人：{b_name}", "",
                                 criterion.reference_law)
        return AuditResult(cid, criterion.category, criterion.item, criterion.law_article,
                         criterion.risk_level, "warning", "未提取到授权签署条款",
                         "授权签署条款缺失", criterion.suggestion_template, criterion.reference_law)

    return _audit_default(text, criterion, clause_dict)


def _audit_default(text, criterion, clause_dict):
    """默认审核：检查条款是否存在"""
    cat = criterion.category
    clause = clause_dict.get(cat)

    if clause and clause.original_text:
        return AuditResult(criterion.id, criterion.category, criterion.item,
                          criterion.law_article, criterion.risk_level, "pass",
                          clause.summary[:100], "", criterion.reference_law)
    else:
        return AuditResult(criterion.id, criterion.category, criterion.item,
                          criterion.law_article, criterion.risk_level, "na",
                          "该条款未在合同中明确提取", "")


# ============================================================
# 报告格式化输出
# ============================================================

def format_audit_report(report: AuditReport, contract_no: str = "", title: str = "") -> str:
    """格式化输出审核报告"""
    lines = []
    s = report.summary

    lines.append("=" * 70)
    lines.append("合同审核报告（基于《民法典》合同编）")
    lines.append("=" * 70)
    if contract_no:
        lines.append(f"合同编号：{contract_no}")
    if title:
        lines.append(f"合同名称：{title}")
    lines.append(f"审核时间：{report.audit_time}")
    lines.append(f"审核标准：基于《民法典》合同编 + 司法解释 + 行业规范")
    lines.append(f"审核项数：{s['total']} 项")
    lines.append("")
    lines.append(f"综合风险：{report.overall_risk.upper()}")
    lines.append(f"审核结论：{report.recommendation}")
    lines.append(f"统计：✅通过 {s['pass']} / ⚠️警告 {s['warning']} / ❌不通过 {s['fail']} / N/A {s['na']}")
    lines.append("")

    # 按类别分组输出
    categories = []
    seen = set()
    for r in report.results:
        if r.category not in seen:
            categories.append(r.category)
            seen.add(r.category)

    for cat in categories:
        cat_results = [r for r in report.results if r.category == cat]
        pass_n = sum(1 for r in cat_results if r.status == "pass")
        warn_n = sum(1 for r in cat_results if r.status == "warning")
        fail_n = sum(1 for r in cat_results if r.status == "fail")

        lines.append(f"【{cat}】（✅{pass_n} / ⚠️{warn_n} / ❌{fail_n}）")
        lines.append("-" * 50)

        for r in cat_results:
            icon = {"pass": "✅", "warning": "⚠️", "fail": "❌", "na": "N/A"}.get(r.status, "?")
            lines.append(f"  {icon} [{r.criterion_id}] {r.item}（{r.law_article}）")
            if r.evidence:
                lines.append(f"     证据：{r.evidence[:100]}")
            if r.issue:
                lines.append(f"     问题：{r.issue}")
            if r.suggestion:
                lines.append(f"     建议：{r.suggestion}")
            lines.append("")

    # 审核结论
    lines.append("=" * 70)
    lines.append("审核结论与建议")
    lines.append("=" * 70)

    # 必须修改项
    must_fix = [r for r in report.results if r.status in ("warning", "fail") and r.risk_level == "high"]
    if must_fix:
        lines.append("")
        lines.append("▶ 必须修改项（高风险）：")
        for i, r in enumerate(must_fix, 1):
            lines.append(f"  {i}. [{r.criterion_id}] {r.item}")
            lines.append(f"     问题：{r.issue}")
            lines.append(f"     建议：{r.suggestion}")
            lines.append("")

    # 建议修改项
    should_fix = [r for r in report.results if r.status == "warning" and r.risk_level in ("medium", "low")]
    if should_fix:
        lines.append("▶ 建议修改项（中/低风险）：")
        for i, r in enumerate(should_fix, 1):
            lines.append(f"  {i}. [{r.criterion_id}] {r.item}")
            if r.issue:
                lines.append(f"     问题：{r.issue}")
            if r.suggestion:
                lines.append(f"     建议：{r.suggestion}")
            lines.append("")

    lines.append("=" * 70)
    return "\n".join(lines)


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="合同审核引擎（基于民法典）")
    sub = parser.add_subparsers(dest="command")

    # audit contract from DB
    p_audit = sub.add_parser("audit", help="审核合同（从数据库）")
    p_audit.add_argument("--contract-id", type=int, required=True)
    p_audit.add_argument("--json", action="store_true", help="输出 JSON")

    # audit file
    p_file = sub.add_parser("audit-file", help="审核合同文件")
    p_file.add_argument("--file", required=True, help="合同文本文件路径")
    p_file.add_argument("--json", action="store_true", help="输出 JSON")

    # parse only
    p_parse = sub.add_parser("parse", help="仅解析条款")
    p_parse.add_argument("--file", required=True)

    args = parser.parse_args()

    if args.command == "audit":
        # 从数据库读取
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        contract = conn.execute("SELECT * FROM contracts WHERE id = ?", (args.contract_id,)).fetchone()
        conn.close()

        if not contract:
            print(f"❌ 合同 ID {args.contract_id} 不存在")
            return

        file_path = contract["file_path"]
        if file_path and os.path.exists(file_path):
            with open(file_path) as f:
                text = f.read()
        else:
            print(f"❌ 合同文件不存在: {file_path}")
            return

        # 解析 + 审核
        parsed = parse_contract(text)
        report = audit_contract(text, parsed.clauses)
        report.contract_no = contract["contract_no"]
        report.title = contract["title"]

        if args.json:
            output = {
                "contract_no": report.contract_no,
                "title": report.title,
                "audit_time": report.audit_time,
                "overall_risk": report.overall_risk,
                "recommendation": report.recommendation,
                "summary": report.summary,
                "results": [r.to_dict() for r in report.results],
            }
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            print(format_audit_report(report, report.contract_no, report.title))

    elif args.command == "audit-file":
        with open(args.file) as f:
            text = f.read()

        parsed = parse_contract(text)
        report = audit_contract(text, parsed.clauses)

        if args.json:
            output = {
                "audit_time": report.audit_time,
                "overall_risk": report.overall_risk,
                "recommendation": report.recommendation,
                "summary": report.summary,
                "results": [r.to_dict() for r in report.results],
            }
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            print(format_audit_report(report))

    elif args.command == "parse":
        with open(args.file) as f:
            text = f.read()
        parsed = parse_contract(text)
        print(format_parsed_contract(parsed))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
