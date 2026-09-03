#!/usr/bin/env python3
"""
销售合同审批流程引擎
组件: SCA-001 (L4)
功能: 合同 CRUD + 审批流转 + 审计日志
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime

# 数据库路径
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "contracts.db")

# 状态定义
STATUSES = {
    "draft": "起草",
    "review1": "业务初审",
    "review2": "法务审查",
    "review3": "财务审查",
    "approved": "审批通过",
    "signed": "已签署",
    "archived": "已归档",
    "rejected": "已驳回",
}

# 分级审批阈值
APPROVAL_LEVELS = [
    (0, 100000, 1, ["销售经理"]),
    (100000, 500000, 2, ["销售经理", "法务审查员"]),
    (500000, 2000000, 3, ["销售总监", "法务审查员", "财务"]),
    (2000000, float("inf"), 4, ["VP/CEO", "法务总监", "财务总监"]),
]


def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库"""
    conn = get_db()
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path) as f:
        conn.executescript(f.read())
    conn.close()
    print("✅ 数据库初始化完成")


def generate_contract_no():
    """生成合同编号 CON-YYYY-NNN"""
    conn = get_db()
    year = datetime.now().year
    cursor = conn.execute(
        "SELECT COUNT(*) FROM contracts WHERE contract_no LIKE ?", (f"CON-{year}-%",)
    )
    count = cursor.fetchone()[0] + 1
    conn.close()
    return f"CON-{year}-{count:03d}"


def get_approval_config(amount):
    """根据金额获取审批配置"""
    for min_amt, max_amt, level, roles in APPROVAL_LEVELS:
        if min_amt <= amount < max_amt:
            return level, roles
    return 1, ["销售经理"]


def log_audit(conn, contract_id, action, operator, from_status=None, to_status=None, detail=None):
    """写入审计日志"""
    conn.execute(
        """INSERT INTO audit_logs (contract_id, action, operator, from_status, to_status, detail)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (contract_id, action, operator, from_status, to_status, json.dumps(detail, ensure_ascii=False) if detail else None),
    )


def create_contract(args):
    """创建合同"""
    conn = get_db()
    contract_no = generate_contract_no()
    level, roles = get_approval_config(args.amount)

    cursor = conn.execute(
        """INSERT INTO contracts (contract_no, title, contract_type, party_a, party_b, amount,
           effective_date, expiry_date, status, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?)""",
        (contract_no, args.title, args.type, args.party_a, args.party_b,
         args.amount, args.effective_date, args.expiry_date, args.operator),
    )
    contract_id = cursor.lastrowid
    log_audit(conn, contract_id, "create", args.operator, None, "draft",
              {"title": args.title, "amount": args.amount, "approval_level": level})
    conn.commit()
    conn.close()

    print(f"✅ 合同创建成功")
    print(f"   合同编号: {contract_no}")
    print(f"   合同名称: {args.title}")
    print(f"   合同金额: ¥{args.amount:,.2f}")
    print(f"   审批层级: {level} 级 ({', '.join(roles)})")
    print(f"   当前状态: draft（起草）")
    return contract_id


def submit_approval(args):
    """提交审批"""
    conn = get_db()
    contract = conn.execute("SELECT * FROM contracts WHERE id = ?", (args.contract_id,)).fetchone()
    if not contract:
        print(f"❌ 合同 ID {args.contract_id} 不存在")
        return

    if contract["status"] != "draft":
        print(f"❌ 当前状态为 {contract['status']}，无法提交审批")
        return

    level, roles = get_approval_config(contract["amount"])
    next_status = "review1"

    conn.execute("UPDATE contracts SET status = ?, current_approver = ?, updated_at = ? WHERE id = ?",
                 (next_status, roles[0], datetime.now().isoformat(), args.contract_id))
    log_audit(conn, args.contract_id, "submit", args.operator, "draft", next_status,
              {"approval_level": level, "first_approver": roles[0]})
    conn.commit()
    conn.close()

    print(f"✅ 合同 {contract['contract_no']} 已提交审批")
    print(f"   当前状态: {next_status}（{STATUSES[next_status]}）")
    print(f"   当前审批人: {roles[0]}")


def approve_contract(args):
    """审批通过"""
    conn = get_db()
    contract = conn.execute("SELECT * FROM contracts WHERE id = ?", (args.contract_id,)).fetchone()
    if not contract:
        print(f"❌ 合同 ID {args.contract_id} 不存在")
        return

    current_status = contract["status"]
    if current_status not in ("review1", "review2", "review3"):
        print(f"❌ 当前状态为 {current_status}，无法审批")
        return

    level, roles = get_approval_config(contract["amount"])
    current_level = int(current_status.replace("review", ""))

    # 记录审批
    conn.execute(
        """INSERT INTO approvals (contract_id, approval_level, approver_role, approver_name, action, comment)
           VALUES (?, ?, ?, ?, 'approve', ?)""",
        (args.contract_id, current_level, args.approver_role, args.approver_name, args.comment),
    )

    # 判断下一状态
    if current_level >= level:
        next_status = "approved"
    else:
        next_status = f"review{current_level + 1}"

    conn.execute("UPDATE contracts SET status = ?, current_approver = ?, updated_at = ? WHERE id = ?",
                 (next_status, roles[current_level] if current_level < level else None,
                  datetime.now().isoformat(), args.contract_id))
    log_audit(conn, args.contract_id, "approve", args.approver_name, current_status, next_status,
              {"level": current_level, "comment": args.comment})
    conn.commit()
    conn.close()

    print(f"✅ 审批通过")
    print(f"   审批人: {args.approver_name}（{args.approver_role}）")
    print(f"   当前状态: {next_status}（{STATUSES[next_status]}）")
    if next_status != "approved":
        print(f"   下一审批人: {roles[current_level]}")


def reject_contract(args):
    """审批驳回"""
    conn = get_db()
    contract = conn.execute("SELECT * FROM contracts WHERE id = ?", (args.contract_id,)).fetchone()
    if not contract:
        print(f"❌ 合同 ID {args.contract_id} 不存在")
        return

    current_status = contract["status"]
    if current_status not in ("review1", "review2", "review3"):
        print(f"❌ 当前状态为 {current_status}，无法驳回")
        return

    current_level = int(current_status.replace("review", ""))

    conn.execute(
        """INSERT INTO approvals (contract_id, approval_level, approver_role, approver_name, action, comment)
           VALUES (?, ?, ?, ?, 'reject', ?)""",
        (args.contract_id, current_level, args.approver_role, args.approver_name, args.comment),
    )
    conn.execute("UPDATE contracts SET status = 'draft', current_approver = NULL, updated_at = ? WHERE id = ?",
                 (datetime.now().isoformat(), args.contract_id))
    log_audit(conn, args.contract_id, "reject", args.approver_name, current_status, "draft",
              {"level": current_level, "comment": args.comment})
    conn.commit()
    conn.close()

    print(f"❌ 审批驳回")
    print(f"   驳回人: {args.approver_name}（{args.approver_role}）")
    print(f"   驳回原因: {args.comment}")
    print(f"   回退至: draft（起草）")


def sign_contract(args):
    """签署合同"""
    conn = get_db()
    contract = conn.execute("SELECT * FROM contracts WHERE id = ?", (args.contract_id,)).fetchone()
    if not contract:
        print(f"❌ 合同 ID {args.contract_id} 不存在")
        return

    if contract["status"] != "approved":
        print(f"❌ 当前状态为 {contract['status']}，无法签署")
        return

    conn.execute("UPDATE contracts SET status = 'signed', updated_at = ? WHERE id = ?",
                 (datetime.now().isoformat(), args.contract_id))
    log_audit(conn, args.contract_id, "sign", args.operator, "approved", "signed")
    conn.commit()
    conn.close()

    print(f"✅ 合同 {contract['contract_no']} 已签署")
    print(f"   当前状态: signed（已签署）")


def archive_contract(args):
    """归档合同"""
    conn = get_db()
    contract = conn.execute("SELECT * FROM contracts WHERE id = ?", (args.contract_id,)).fetchone()
    if not contract:
        print(f"❌ 合同 ID {args.contract_id} 不存在")
        return

    if contract["status"] != "signed":
        print(f"❌ 当前状态为 {contract['status']}，无法归档")
        return

    conn.execute("UPDATE contracts SET status = 'archived', updated_at = ? WHERE id = ?",
                 (datetime.now().isoformat(), args.contract_id))
    log_audit(conn, args.contract_id, "archive", args.operator, "signed", "archived")
    conn.commit()
    conn.close()

    print(f"✅ 合同 {contract['contract_no']} 已归档")


def list_contracts(args):
    """列出合同"""
    conn = get_db()
    if args.status:
        rows = conn.execute(
            "SELECT * FROM contracts WHERE status = ? ORDER BY created_at DESC", (args.status,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM contracts ORDER BY created_at DESC").fetchall()
    conn.close()

    if not rows:
        print("暂无合同")
        return

    print(f"{'ID':<5} {'编号':<16} {'名称':<30} {'金额':>12} {'状态':<10} {'创建时间'}")
    print("-" * 90)
    for r in rows:
        print(f"{r['id']:<5} {r['contract_no']:<16} {r['title'][:28]:<30} ¥{r['amount']:>10,.2f} {STATUSES.get(r['status'], r['status']):<10} {r['created_at']}")


def show_contract(args):
    """查看合同详情"""
    conn = get_db()
    contract = conn.execute("SELECT * FROM contracts WHERE id = ?", (args.contract_id,)).fetchone()
    if not contract:
        print(f"❌ 合同 ID {args.contract_id} 不存在")
        return

    approvals = conn.execute(
        "SELECT * FROM approvals WHERE contract_id = ? ORDER BY created_at", (args.contract_id,)
    ).fetchall()

    audits = conn.execute(
        "SELECT * FROM audit_logs WHERE contract_id = ? ORDER BY created_at", (args.contract_id,)
    ).fetchall()
    conn.close()

    print(f"\n{'='*60}")
    print(f"合同编号: {contract['contract_no']}")
    print(f"合同名称: {contract['title']}")
    print(f"合同类型: {contract['contract_type']}")
    print(f"甲    方: {contract['party_a']}")
    print(f"乙    方: {contract['party_b']}")
    print(f"合同金额: ¥{contract['amount']:,.2f}")
    print(f"有效期限: {contract['effective_date']} 至 {contract['expiry_date']}")
    print(f"当前状态: {contract['status']}（{STATUSES.get(contract['status'], '')}）")
    print(f"创建时间: {contract['created_at']}")

    if approvals:
        print(f"\n--- 审批记录 ---")
        for a in approvals:
            print(f"  [{a['created_at']}] {a['approver_name']}（{a['approver_role']}）: {a['action']}")
            if a['comment']:
                print(f"    意见: {a['comment']}")

    if audits:
        print(f"\n--- 审计日志 ---")
        for a in audits:
            detail = f" ({a['from_status']} → {a['to_status']})" if a['from_status'] else ""
            print(f"  [{a['created_at']}] {a['action']}{detail} by {a['operator']}")

    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="销售合同审批流程引擎")
    sub = parser.add_subparsers(dest="command", help="子命令")

    # init
    sub.add_parser("init", help="初始化数据库")

    # create
    p_create = sub.add_parser("create", help="创建合同")
    p_create.add_argument("--title", required=True, help="合同名称")
    p_create.add_argument("--type", default="tech_service", choices=["tech_service", "software_license", "sow"])
    p_create.add_argument("--party-a", required=True, help="甲方（我方）")
    p_create.add_argument("--party-b", required=True, help="乙方（客户）")
    p_create.add_argument("--amount", type=float, required=True, help="合同金额")
    p_create.add_argument("--effective-date", help="生效日期 (YYYY-MM-DD)")
    p_create.add_argument("--expiry-date", help="到期日期 (YYYY-MM-DD)")
    p_create.add_argument("--operator", default="Rex", help="操作人")

    # submit
    p_submit = sub.add_parser("submit", help="提交审批")
    p_submit.add_argument("--contract-id", type=int, required=True)
    p_submit.add_argument("--operator", default="Rex")

    # approve
    p_approve = sub.add_parser("approve", help="审批通过")
    p_approve.add_argument("--contract-id", type=int, required=True)
    p_approve.add_argument("--approver-name", required=True, help="审批人姓名")
    p_approve.add_argument("--approver-role", required=True, help="审批角色")
    p_approve.add_argument("--comment", default="", help="审批意见")

    # reject
    p_reject = sub.add_parser("reject", help="审批驳回")
    p_reject.add_argument("--contract-id", type=int, required=True)
    p_reject.add_argument("--approver-name", required=True)
    p_reject.add_argument("--approver-role", required=True)
    p_reject.add_argument("--comment", required=True, help="驳回原因")

    # sign
    p_sign = sub.add_parser("sign", help="签署合同")
    p_sign.add_argument("--contract-id", type=int, required=True)
    p_sign.add_argument("--operator", default="Rex")

    # archive
    p_archive = sub.add_parser("archive", help="归档合同")
    p_archive.add_argument("--contract-id", type=int, required=True)
    p_archive.add_argument("--operator", default="Rex")

    # list
    p_list = sub.add_parser("list", help="列出合同")
    p_list.add_argument("--status", help="按状态筛选")

    # show
    p_show = sub.add_parser("show", help="查看合同详情")
    p_show.add_argument("--contract-id", type=int, required=True)

    args = parser.parse_args()

    if args.command == "init":
        init_db()
    elif args.command == "create":
        create_contract(args)
    elif args.command == "submit":
        submit_approval(args)
    elif args.command == "approve":
        approve_contract(args)
    elif args.command == "reject":
        reject_contract(args)
    elif args.command == "sign":
        sign_contract(args)
    elif args.command == "archive":
        archive_contract(args)
    elif args.command == "list":
        list_contracts(args)
    elif args.command == "show":
        show_contract(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
