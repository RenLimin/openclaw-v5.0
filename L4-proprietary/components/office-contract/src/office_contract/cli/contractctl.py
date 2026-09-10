#!/usr/bin/env python3
"""
Office 合同审批 CLI (contractctl)
L4 专有业务层 — Office 合同审批统一入口

用法:
  python -m cli.contractctl init
  python -m cli.contractctl create --title "..." --party-b "..." --amount 100000
  python -m cli.contractctl submit --id 1
  python -m cli.contractctl risk-scan --id 1
  python -m cli.contractctl approve --id 1 --approver "张三" --role "销售经理"
  python -m cli.contractctl reject --id 1 --approver "李四" --role "法务" --comment "..."
  python -m cli.contractctl generate --id 1
  python -m cli.contractctl sign --id 1
  python -m cli.contractctl archive --id 1
  python -m cli.contractctl show --id 1
  python -m cli.contractctl list [--status draft]
"""

import argparse
import os
import sys
import json

# 确保能 import services
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from office_contract.services import (
    init_db, create_contract, submit_for_approval,
    approve, reject, sign_contract, archive_contract,
    risk_scan, generate_contract_doc, get_contract, list_contracts,
    get_approval_level,
)
from office_contract.config import CONTRACT_TYPES, OFFICE_APPROVAL_ROLES, APPROVAL_SLA_DAYS

STATUS_NAMES = {
    "draft": "起草",
    "review1": "一级审批",
    "review2": "二级审批",
    "review3": "三级审批",
    "approved": "审批通过",
    "signed": "已签署",
    "archived": "已归档",
    "rejected": "已驳回",
}


def cmd_init(args):
    init_db()
    print("✅ 数据库初始化完成")


def cmd_create(args):
    result = create_contract(
        title=args.title,
        party_b=args.party_b,
        amount=args.amount,
        contract_type=args.type,
        effective_date=args.effective_date,
        expiry_date=args.expiry_date,
        operator=args.operator,
    )
    level = result["approval_level"]
    print(f"✅ 合同创建成功")
    print(f"   合同ID:   {result['id']}")
    print(f"   合同编号: {result['contract_no']}")
    print(f"   合同金额: ¥{args.amount:,.2f}")
    print(f"   审批层级: {level} 级 ({APPROVAL_SLA_DAYS[level]} 工作日 SLA)")
    print(f"   审批角色: {' → '.join(result['approval_roles'])}")
    print(f"   当前状态: draft（起草）")


def cmd_submit(args):
    result = submit_for_approval(args.id, args.operator)
    print(f"✅ 已提交审批")
    print(f"   状态: {result['status']}（{STATUS_NAMES[result['status']]}）")
    print(f"   当前审批人: {result['current_approver']}")
    print(f"   进度: 第 {result['total_steps']} 级审批中的第 1 级")


def cmd_risk_scan(args):
    report = risk_scan(args.id)
    print(f"\n{'='*60}")
    print(f"📋 合同风险扫描报告")
    print(f"{'='*60}")
    print(f"合同: {report['title']} ({report['contract_no']})")
    print(f"综合风险: {'🔴 高' if report['overall_risk']=='high' else '🟡 中' if report['overall_risk']=='medium' else '🟢 低'}")
    s = report["summary"]
    print(f"统计: 通过 {s['pass']} / 警告 {s['warning']} / 不通过 {s['fail']}")

    for status in ["fail", "warning"]:
        items = [f for f in report["findings"] if f["status"] == status]
        if items:
            label = "❌ 不通过" if status == "fail" else "⚠️ 警告"
            print(f"\n--- {label} ({len(items)} 项) ---")
            for f in items:
                print(f"  [{f['id']}] {f['category']} - {f['item']}")
                print(f"       风险: {f['risk']} | 依据: {f['law']}")

    print(f"\n💡 注：本扫描为辅助工具，非法务专业判断")
    print(f"{'='*60}")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))


def cmd_approve(args):
    result = approve(args.id, args.approver, args.role, args.comment)
    print(f"✅ 审批通过")
    print(f"   审批人: {args.approver} ({args.role})")
    print(f"   状态: {result['from_status']} → {result['to_status']}")
    if result["next_approver"]:
        print(f"   下一审批人: {result['next_approver']}")
        print(f"   进度: 第 {result['step']}/{result['total_steps']} 级完成")
    else:
        print(f"   🎉 全部审批通过！")


def cmd_reject(args):
    result = reject(args.id, args.approver, args.role, args.comment)
    print(f"❌ 审批驳回")
    print(f"   驳回人: {args.approver} ({args.role})")
    print(f"   驳回层级: 第 {result['rejected_at_level']} 级")
    print(f"   原因: {result['reason']}")
    print(f"   合同已回退至 draft（起草）状态")


def cmd_generate(args):
    result = generate_contract_doc(args.id)
    print(f"✅ 合同文档已生成")
    print(f"   合同编号: {result['contract_no']}")
    print(f"   文件路径: {result['output_path']}")


def cmd_sign(args):
    result = sign_contract(args.id, args.operator)
    print(f"✅ 合同已签署")
    print(f"   合同编号: {result['contract_no']}")
    print(f"   状态: signed（已签署）")


def cmd_archive(args):
    result = archive_contract(args.id, args.operator)
    print(f"✅ 合同已归档")
    print(f"   合同编号: {result['contract_no']}")
    print(f"   状态: archived（已归档）")


def cmd_show(args):
    data = get_contract(args.id)
    if not data:
        print(f"❌ 合同 ID {args.id} 不存在")
        return

    c = data["contract"]
    print(f"\n{'='*60}")
    print(f"📄 合同详情")
    print(f"{'='*60}")
    print(f"合同编号: {c['contract_no']}")
    print(f"合同名称: {c['title']}")
    print(f"合同类型: {CONTRACT_TYPES.get(c['contract_type'], c['contract_type'])}")
    print(f"甲    方: {c['party_a']}")
    print(f"乙    方: {c['party_b']}")
    print(f"合同金额: ¥{c['amount']:,.2f}")
    level = get_approval_level(c["amount"])
    print(f"审批层级: {level} 级 ({' → '.join(OFFICE_APPROVAL_ROLES[level])})")
    print(f"有效期限: {c['effective_date']} ~ {c['expiry_date']}")
    print(f"当前状态: {c['status']}（{STATUS_NAMES.get(c['status'], c['status'])}）")
    if c["current_approver"]:
        print(f"当前审批人: {c['current_approver']}")
    print(f"创建时间: {c['created_at']}")

    if data["approvals"]:
        print(f"\n--- 审批记录 ({len(data['approvals'])} 条) ---")
        for a in data["approvals"]:
            icon = "✅" if a["action"] == "approve" else "❌"
            print(f"  {icon} [{a['created_at']}] L{a['approval_level']} "
                  f"{a['approver_name']}（{a['approver_role']}）: "
                  f"{'通过' if a['action']=='approve' else '驳回'}")
            if a["comment"]:
                print(f"     意见: {a['comment']}")

    if data["audit_logs"]:
        print(f"\n--- 审计日志 ({len(data['audit_logs'])} 条) ---")
        for a in data["audit_logs"]:
            flow = f" ({a['from_status']}→{a['to_status']})" if a["from_status"] else ""
            print(f"  [{a['created_at']}] {a['action']}{flow} by {a['operator']}")

    print(f"{'='*60}")


def cmd_list(args):
    rows = list_contracts(args.status)
    if not rows:
        print("暂无合同")
        return

    print(f"{'ID':<5} {'编号':<18} {'名称':<30} {'金额':>12} {'状态':<12} {'创建时间'}")
    print("-" * 95)
    for r in rows:
        status_label = STATUS_NAMES.get(r["status"], r["status"])
        print(f"{r['id']:<5} {r['contract_no']:<18} {r['title'][:28]:<30} "
              f"¥{r['amount']:>10,.2f} {status_label:<12} {r['created_at']}")
    print(f"\n共 {len(rows)} 份合同")


def main():
    parser = argparse.ArgumentParser(
        description="Office 合同审批 CLI (contractctl) - OFC-001",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", help="子命令")

    # init
    sub.add_parser("init", help="初始化数据库")

    # create
    p = sub.add_parser("create", help="创建合同")
    p.add_argument("--title", required=True, help="合同名称")
    p.add_argument("--party-b", required=True, help="乙方（客户）")
    p.add_argument("--amount", type=float, required=True, help="合同金额（元）")
    p.add_argument("--type", default="tech_service",
                   choices=list(CONTRACT_TYPES.keys()),
                   help="合同类型 (默认: tech_service)")
    p.add_argument("--effective-date", help="生效日期 YYYY-MM-DD")
    p.add_argument("--expiry-date", help="到期日期 YYYY-MM-DD")
    p.add_argument("--operator", default="Rex", help="操作人")

    # submit
    p = sub.add_parser("submit", help="提交审批")
    p.add_argument("--id", type=int, required=True, help="合同 ID")
    p.add_argument("--operator", default="Rex")

    # risk-scan
    p = sub.add_parser("risk-scan", help="风险扫描")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--json", action="store_true", help="输出 JSON")

    # approve
    p = sub.add_parser("approve", help="审批通过")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--approver", required=True, help="审批人姓名")
    p.add_argument("--role", required=True, help="审批角色")
    p.add_argument("--comment", default="", help="审批意见")

    # reject
    p = sub.add_parser("reject", help="审批驳回")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--approver", required=True)
    p.add_argument("--role", required=True)
    p.add_argument("--comment", required=True, help="驳回原因")

    # generate
    p = sub.add_parser("generate", help="生成合同文档")
    p.add_argument("--id", type=int, required=True)

    # sign
    p = sub.add_parser("sign", help="签署合同")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--operator", default="Rex")

    # archive
    p = sub.add_parser("archive", help="归档合同")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--operator", default="Rex")

    # show
    p = sub.add_parser("show", help="查看合同详情")
    p.add_argument("--id", type=int, required=True)

    # list
    p = sub.add_parser("list", help="列出合同")
    p.add_argument("--status", help="按状态筛选")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    handlers = {
        "init": cmd_init,
        "create": cmd_create,
        "submit": cmd_submit,
        "risk-scan": cmd_risk_scan,
        "approve": cmd_approve,
        "reject": cmd_reject,
        "generate": cmd_generate,
        "sign": cmd_sign,
        "archive": cmd_archive,
        "show": cmd_show,
        "list": cmd_list,
    }

    try:
        handlers[args.command](args)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
