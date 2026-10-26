#!/usr/bin/env python3
"""
销售合同风险扫描器
组件: SCA-001 (L4)
功能: 基于《民法典》合同编的 13 类条款风险扫描
"""

import argparse
import json
import os
import re
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "contracts.db")


# ============================================================
# 风险检查规则（基于《民法典》合同编）
# ============================================================

CHECK_RULES = [
    # 一、主体信息
    {
        "id": "1.1", "category": "主体信息",
        "item": "双方当事人名称完整",
        "risk": "high", "law": "§470",
        "check": lambda t: len(re.findall(r'(甲方|乙方|委托方|受托方)[：:]\s*[\u4e00-\u9fa5]{2,}', t)) >= 2,
    },
    {
        "id": "1.2", "category": "主体信息",
        "item": "双方地址完整",
        "risk": "medium", "law": "§470",
        "check": lambda t: len(re.findall(r'地址[：:]\s*[\u4e00-\u9fa5省市区县街道路号\d]+', t)) >= 2,
    },
    {
        "id": "1.3", "category": "主体信息",
        "item": "双方联系电话/邮箱",
        "risk": "low", "law": "—",
        "check": lambda t: len(re.findall(r'联系电话[：:]\s*\d{8,}', t)) >= 2 or len(re.findall(r'[\w.+-]+@[\w-]+\.[\w]+', t)) >= 2,
    },
    {
        "id": "1.5", "category": "主体信息",
        "item": "签字盖章",
        "risk": "high", "law": "§490",
        "check": lambda t: "盖章" in t or "签字" in t or "签章" in t,
    },

    # 二、合同标的
    {
        "id": "2.1", "category": "合同标的",
        "item": "服务内容描述清晰",
        "risk": "high", "law": "§470",
        "check": lambda t: "服务内容" in t or "服务目标" in t or "技术服务" in t,
    },
    {
        "id": "2.4", "category": "合同标的",
        "item": "服务期限/起止日期明确",
        "risk": "medium", "law": "§511",
        "check": lambda t: len(re.findall(r'\d{4}年\d{1,2}月\d{1,2}日', t)) >= 2,
    },

    # 三、金额与支付
    {
        "id": "3.1", "category": "金额与支付",
        "item": "合同金额大小写",
        "risk": "high", "law": "—",
        "check": lambda t: "大写" in t or "（大写）" in t or "整" in t,
    },
    {
        "id": "3.2", "category": "金额与支付",
        "item": "税率明确",
        "risk": "high", "law": "—",
        "check": lambda t: "%" in t and ("税率" in t or "税" in t),
    },
    {
        "id": "3.3", "category": "金额与支付",
        "item": "支付方式明确",
        "risk": "medium", "law": "§510",
        "check": lambda t: "支付" in t and ("转账" in t or "银行" in t or "工作日" in t),
    },
    {
        "id": "3.5", "category": "金额与支付",
        "item": "发票要求明确",
        "risk": "medium", "law": "—",
        "check": lambda t: "发票" in t or "增值税" in t,
    },

    # 五、验收标准
    {
        "id": "5.1", "category": "验收标准",
        "item": "验收标准/方式明确",
        "risk": "high", "law": "§509",
        "check": lambda t: "验收" in t,
    },

    # 六、违约责任
    {
        "id": "6.1", "category": "违约责任",
        "item": "违约责任条款存在",
        "risk": "high", "law": "§577",
        "check": lambda t: "违约" in t or "违约金" in t,
    },
    {
        "id": "6.2", "category": "违约责任",
        "item": "违约金比例合理（不超过实际损失30%）",
        "risk": "high", "law": "§585",
        "check": lambda t: _check_penalty_reasonable(t),
    },

    # 七、争议解决
    {
        "id": "7.1", "category": "争议解决",
        "item": "管辖法院/仲裁机构明确",
        "risk": "high", "law": "§507",
        "check": lambda t: "人民法院" in t or "仲裁" in t or "管辖" in t,
    },
    {
        "id": "7.3", "category": "争议解决",
        "item": "争议解决方式唯一",
        "risk": "medium", "law": "—",
        "check": lambda t: not ("人民法院" in t and "仲裁" in t and "起诉" in t),
    },

    # 八、知识产权
    {
        "id": "8.1", "category": "知识产权",
        "item": "知识产权归属明确",
        "risk": "medium", "law": "§847",
        "check": lambda t: "知识产权" in t or "成果" in t,
    },

    # 九、保密条款
    {
        "id": "9.1", "category": "保密条款",
        "item": "保密条款存在",
        "risk": "medium", "law": "§501",
        "check": lambda t: "保密" in t,
    },
    {
        "id": "9.2", "category": "保密条款",
        "item": "保密期限明确",
        "risk": "medium", "law": "—",
        "check": lambda t: "保密" in t and ("年" in t or "终止" in t),
    },

    # 十、不可抗力
    {
        "id": "10.1", "category": "不可抗力",
        "item": "不可抗力条款存在",
        "risk": "low", "law": "§180",
        "check": lambda t: "不可抗力" in t,
    },

    # 十一、合同解除
    {
        "id": "11.1", "category": "合同解除",
        "item": "合同解除条件明确",
        "risk": "medium", "law": "§563",
        "check": lambda t: "解除" in t,
    },

    # 十三、其他
    {
        "id": "13.1", "category": "其他",
        "item": "合同份数约定明确",
        "risk": "low", "law": "—",
        "check": lambda t: "份" in t and ("甲乙" in t or "双方" in t),
    },
    {
        "id": "13.2", "category": "其他",
        "item": "合同生效条件明确",
        "risk": "medium", "law": "—",
        "check": lambda t: "生效" in t,
    },
]


def _check_penalty_reasonable(text):
    """检查违约金是否合理"""
    # 查找违约金比例
    patterns = [
        r'违约金.*?(\d+(?:\.\d+)?)\s*%',
        r'百分之(\d+(?:\.\d+)?)',
        r'按.*?(\d+(?:\.\d+)?)\s*%',
    ]
    for pat in patterns:
        matches = re.findall(pat, text)
        for m in matches:
            try:
                val = float(m)
                if val > 30:
                    return False
            except ValueError:
                pass
    return True


def scan_text(text):
    """扫描合同文本，返回风险报告"""
    findings = []
    for rule in CHECK_RULES:
        passed = rule["check"](text)
        status = "pass" if passed else ("fail" if rule["risk"] == "high" else "warning")
        findings.append({
            "id": rule["id"],
            "category": rule["category"],
            "item": rule["item"],
            "status": status,
            "risk": rule["risk"],
            "law": rule["law"],
        })

    # 统计
    pass_count = sum(1 for f in findings if f["status"] == "pass")
    warning_count = sum(1 for f in findings if f["status"] == "warning")
    fail_count = sum(1 for f in findings if f["status"] == "fail")

    # 综合评级
    if fail_count > 0:
        overall = "high"
    elif warning_count > 2:
        overall = "medium"
    else:
        overall = "low"

    return {
        "scan_time": datetime.now().isoformat(),
        "overall_risk": overall,
        "summary": {"pass": pass_count, "warning": warning_count, "fail": fail_count},
        "findings": findings,
    }


def scan_contract(args):
    """扫描合同（从数据库读取）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    contract = conn.execute("SELECT * FROM contracts WHERE id = ?", (args.contract_id,)).fetchone()
    conn.close()

    if not contract:
        print(f"❌ 合同 ID {args.contract_id} 不存在")
        return

    # 从文件读取合同文本
    file_path = contract["file_path"]
    if file_path and os.path.exists(file_path):
        with open(file_path) as f:
            text = f.read()
    else:
        # 从数据库字段组装文本
        text = f"""
        合同编号：{contract['contract_no']}
        合同名称：{contract['title']}
        甲方：{contract['party_a']}
        乙方：{contract['party_b']}
        金额：{contract['amount']}
        有效期：{contract['effective_date']} 至 {contract['expiry_date']}
        """

    report = scan_text(text)
    report["contract_no"] = contract["contract_no"]
    report["title"] = contract["title"]

    # 输出报告
    print(f"\n{'='*60}")
    print(f"合同风险扫描报告")
    print(f"{'='*60}")
    print(f"合同编号: {report['contract_no']}")
    print(f"合同名称: {report['title']}")
    print(f"扫描时间: {report['scan_time']}")
    print(f"综合风险: {report['overall_risk'].upper()}")
    print(f"统计: 通过 {report['summary']['pass']} / 警告 {report['summary']['warning']} / 不通过 {report['summary']['fail']}")

    # 按状态分组输出
    for status in ["fail", "warning"]:
        items = [f for f in report["findings"] if f["status"] == status]
        if items:
            label = "❌ 不通过" if status == "fail" else "⚠️ 警告"
            print(f"\n--- {label} ---")
            for f in items:
                print(f"  [{f['id']}] {f['category']} - {f['item']}")
                print(f"    风险: {f['risk']} | 法条: {f['law']}")

    pass_items = [f for f in report["findings"] if f["status"] == "pass"]
    if pass_items:
        print(f"\n--- ✅ 通过 ---")
        for f in pass_items:
            print(f"  [{f['id']}] {f['category']} - {f['item']}")

    print(f"\n{'='*60}")

    # JSON 输出
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))


def scan_file(args):
    """扫描合同文件"""
    if not os.path.exists(args.file):
        print(f"❌ 文件不存在: {args.file}")
        return

    with open(args.file) as f:
        text = f.read()

    report = scan_text(text)
    report["file"] = args.file

    print(json.dumps(report, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="销售合同风险扫描器")
    sub = parser.add_subparsers(dest="command")

    # scan contract
    p_scan = sub.add_parser("scan", help="扫描合同（从数据库）")
    p_scan.add_argument("--contract-id", type=int, required=True)
    p_scan.add_argument("--json", action="store_true", help="输出 JSON")

    # scan file
    p_file = sub.add_parser("scan-file", help="扫描合同文件")
    p_file.add_argument("--file", required=True, help="合同文件路径")

    args = parser.parse_args()

    if args.command == "scan":
        scan_contract(args)
    elif args.command == "scan-file":
        scan_file(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
