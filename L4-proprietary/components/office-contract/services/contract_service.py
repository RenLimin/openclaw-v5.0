"""
合同服务层 (L4)
封装 SCA-001 审批引擎，提供 Office 场景的业务操作。
"""

import os
import sys
import json
import sqlite3
from datetime import datetime

# 接入 SCA-001 (L3 通用合同审批能力)
_SCA_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..",
    "L3-business", "skills", "contract-approval", "scripts"
))
if _SCA_DIR not in sys.path:
    sys.path.insert(0, _SCA_DIR)

import config





def _get_db():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库（复用 SCA-001 schema）"""
    schema_path = os.path.join(_SCA_DIR, "schema.sql")
    conn = _get_db()
    with open(schema_path) as f:
        conn.executescript(f.read())
    conn.close()
    return True



def _generate_contract_no(conn):
    """生成合同编号 CON-YYYY-NNN（使用传入的连接，保证在同一数据库）"""
    from datetime import datetime
    year = datetime.now().year
    cursor = conn.execute(
        "SELECT COUNT(*) FROM contracts WHERE contract_no LIKE ?", (f"CON-{year}-%",)
    )
    count = cursor.fetchone()[0] + 1
    return f"CON-{year}-{count:03d}"

def get_approval_level(amount):
    """根据金额获取审批层级"""
    if amount < 100000:
        return 1
    elif amount < 500000:
        return 2
    elif amount < 2000000:
        return 3
    else:
        return 4


def create_contract(title, party_b, amount, contract_type="tech_service",
                    effective_date=None, expiry_date=None, operator="Rex",
                    party_a=None):
    """创建合同（Office 场景：甲方默认我方公司）"""

    conn = _get_db()
    contract_no = _generate_contract_no(conn)
    level = get_approval_level(amount)
    roles = config.OFFICE_APPROVAL_ROLES[level]

    _party_a = party_a or config.DEFAULT_PARTY_A

    cursor = conn.execute(
        """INSERT INTO contracts (
            contract_no, title, contract_type, party_a, party_b,
            amount, effective_date, expiry_date, status, created_by,
            party_a_address
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)""",
        (contract_no, title, contract_type, _party_a, party_b,
         amount, effective_date, expiry_date, operator, config.DEFAULT_PARTY_A_ADDRESS),
    )
    contract_id = cursor.lastrowid

    # 审计日志
    conn.execute(
        """INSERT INTO audit_logs (contract_id, action, operator,
           from_status, to_status, detail)
           VALUES (?, 'create', ?, NULL, 'draft', ?)""",
        (contract_id, operator, json.dumps({
            "title": title,
            "amount": amount,
            "approval_level": level,
            "approval_roles": roles,
        }, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()

    return {
        "id": contract_id,
        "contract_no": contract_no,
        "approval_level": level,
        "approval_roles": roles,
        "sla_days": config.APPROVAL_SLA_DAYS[level],
    }


def submit_for_approval(contract_id, operator="Rex"):
    """提交审批"""
    conn = _get_db()
    contract = conn.execute(
        "SELECT * FROM contracts WHERE id = ?", (contract_id,)
    ).fetchone()
    if not contract:
        raise ValueError(f"合同 ID {contract_id} 不存在")
    if contract["status"] != "draft":
        raise ValueError(f"当前状态 {contract['status']}，无法提交")

    level = get_approval_level(contract["amount"])
    roles = config.OFFICE_APPROVAL_ROLES[level]
    next_status = "review1"

    conn.execute(
        "UPDATE contracts SET status = ?, current_approver = ?, updated_at = ? WHERE id = ?",
        (next_status, roles[0], datetime.now().isoformat(), contract_id),
    )
    conn.execute(
        """INSERT INTO audit_logs (contract_id, action, operator,
           from_status, to_status, detail)
           VALUES (?, 'submit', ?, 'draft', ?, ?)""",
        (contract_id, operator, next_status, json.dumps({
            "approval_level": level,
            "first_approver": roles[0],
            "sla_days": config.APPROVAL_SLA_DAYS[level],
        }, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()

    return {
        "status": next_status,
        "current_approver": roles[0],
        "approval_level": level,
        "total_steps": level,
    }


def approve(contract_id, approver_name, approver_role, comment=""):
    """审批通过"""
    conn = _get_db()
    contract = conn.execute(
        "SELECT * FROM contracts WHERE id = ?", (contract_id,)
    ).fetchone()
    if not contract:
        raise ValueError(f"合同 ID {contract_id} 不存在")

    current_status = contract["status"]
    if current_status not in ("review1", "review2", "review3"):
        raise ValueError(f"当前状态 {current_status}，无法审批")

    level = get_approval_level(contract["amount"])
    current_level = int(current_status.replace("review", ""))

    # 记录审批
    conn.execute(
        """INSERT INTO approvals (contract_id, approval_level, approver_role,
           approver_name, action, comment)
           VALUES (?, ?, ?, ?, 'approve', ?)""",
        (contract_id, current_level, approver_role, approver_name, comment),
    )

    # 下一状态
    if current_level >= level:
        next_status = "approved"
        next_approver = None
    else:
        next_status = f"review{current_level + 1}"
        next_approver = config.OFFICE_APPROVAL_ROLES[level][current_level]

    conn.execute(
        "UPDATE contracts SET status = ?, current_approver = ?, updated_at = ? WHERE id = ?",
        (next_status, next_approver, datetime.now().isoformat(), contract_id),
    )
    conn.execute(
        """INSERT INTO audit_logs (contract_id, action, operator,
           from_status, to_status, detail)
           VALUES (?, 'approve', ?, ?, ?, ?)""",
        (contract_id, approver_name, current_status, next_status,
         json.dumps({"level": current_level, "comment": comment}, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()

    return {
        "from_status": current_status,
        "to_status": next_status,
        "next_approver": next_approver,
        "step": current_level,
        "total_steps": level,
    }


def reject(contract_id, approver_name, approver_role, comment):
    """审批驳回"""
    conn = _get_db()
    contract = conn.execute(
        "SELECT * FROM contracts WHERE id = ?", (contract_id,)
    ).fetchone()
    if not contract:
        raise ValueError(f"合同 ID {contract_id} 不存在")

    current_status = contract["status"]
    if current_status not in ("review1", "review2", "review3"):
        raise ValueError(f"当前状态 {current_status}，无法驳回")

    current_level = int(current_status.replace("review", ""))

    conn.execute(
        """INSERT INTO approvals (contract_id, approval_level, approver_role,
           approver_name, action, comment)
           VALUES (?, ?, ?, ?, 'reject', ?)""",
        (contract_id, current_level, approver_role, approver_name, comment),
    )
    conn.execute(
        "UPDATE contracts SET status = 'draft', current_approver = NULL, updated_at = ? WHERE id = ?",
        (datetime.now().isoformat(), contract_id),
    )
    conn.execute(
        """INSERT INTO audit_logs (contract_id, action, operator,
           from_status, to_status, detail)
           VALUES (?, 'reject', ?, ?, 'draft', ?)""",
        (contract_id, approver_name, current_status,
         json.dumps({"level": current_level, "comment": comment}, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()

    return {"rejected_at_level": current_level, "reason": comment}


def sign_contract(contract_id, operator="Rex"):
    """签署合同"""
    conn = _get_db()
    contract = conn.execute(
        "SELECT * FROM contracts WHERE id = ?", (contract_id,)
    ).fetchone()
    if not contract:
        raise ValueError(f"合同 ID {contract_id} 不存在")
    if contract["status"] != "approved":
        raise ValueError(f"当前状态 {contract['status']}，无法签署")

    conn.execute(
        "UPDATE contracts SET status = 'signed', updated_at = ? WHERE id = ?",
        (datetime.now().isoformat(), contract_id),
    )
    conn.execute(
        """INSERT INTO audit_logs (contract_id, action, operator,
           from_status, to_status)
           VALUES (?, 'sign', ?, 'approved', 'signed')""",
        (contract_id, operator),
    )
    conn.commit()
    conn.close()

    return {"status": "signed", "contract_no": contract["contract_no"]}


def archive_contract(contract_id, operator="Rex"):
    """归档合同"""
    conn = _get_db()
    contract = conn.execute(
        "SELECT * FROM contracts WHERE id = ?", (contract_id,)
    ).fetchone()
    if not contract:
        raise ValueError(f"合同 ID {contract_id} 不存在")
    if contract["status"] != "signed":
        raise ValueError(f"当前状态 {contract['status']}，无法归档")

    conn.execute(
        "UPDATE contracts SET status = 'archived', updated_at = ? WHERE id = ?",
        (datetime.now().isoformat(), contract_id),
    )
    conn.execute(
        """INSERT INTO audit_logs (contract_id, action, operator,
           from_status, to_status)
           VALUES (?, 'archive', ?, 'signed', 'archived')""",
        (contract_id, operator),
    )
    conn.commit()
    conn.close()

    return {"status": "archived", "contract_no": contract["contract_no"]}


def risk_scan(contract_id):
    """风险扫描（复用 SCA-001 risk_scanner）"""
    from risk_scanner import scan_text

    conn = _get_db()
    contract_row = conn.execute(
        "SELECT * FROM contracts WHERE id = ?", (contract_id,)
    ).fetchone()
    conn.close()

    if not contract_row:
        raise ValueError(f"合同 ID {contract_id} 不存在")
    contract = dict(contract_row)

    # 组装合同文本用于扫描（优先读文件，否则用字段）
    file_path = contract["file_path"]
    if file_path and os.path.exists(file_path):
        with open(file_path) as f:
            text = f.read()
    else:
        # 基于合同数据生成模拟文本
        text = f"""
{contract['title']}
合同编号：{contract['contract_no']}
甲方：{contract['party_a']}
地址：{contract.get('party_a_address', '')}
乙方：{contract['party_b']}
地址：{contract.get('party_b_address', '')}

第一条 技术服务的内容
服务内容：{contract['title']}
服务期限：{contract.get('effective_date', '')} 至 {contract.get('expiry_date', '')}

第二条 技术服务报酬
合同金额：{contract['amount']}元（大写人民币：--整）
税率：{int(contract.get('tax_rate', 0.06) * 100)}%
支付方式：银行转账，验收后30个工作日内支付

第三条 验收标准
验收方式：双方确认

第四条 保密条款
双方负有保密义务，保密期限为合同终止后2年

第五条 违约责任
违约金按迟延金额每日1%计算，最高不超过合同总额5%

第六条 争议解决
协商不成，向甲方所在地人民法院起诉

第七条 知识产权
服务成果知识产权归双方共有

第八条 不可抗力
因不可抗力不能履行的，部分或全部免除责任

第九条 合同解除
双方协商一致可解除合同

第十条 其他
本合同一式肆份，双方各执贰份，具有同等法律效力。
本合同自双方签字盖章之日起生效。

甲方（盖章）：{contract['party_a']}
乙方（盖章）：{contract['party_b']}
"""

    report = scan_text(text)
    report["contract_no"] = contract["contract_no"]
    report["title"] = contract["title"]
    report["contract_id"] = contract_id

    # 持久化扫描结果到审计日志
    conn = _get_db()
    conn.execute(
        """INSERT INTO audit_logs (contract_id, action, operator, detail)
           VALUES (?, 'risk_scan', 'system', ?)""",
        (contract_id, json.dumps({
            "overall_risk": report["overall_risk"],
            "summary": report["summary"],
        }, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()

    return report


def generate_contract_doc(contract_id):
    """生成合同文档（复用 SCA-001 contract_gen 能力）"""
    try:
        from contract_gen import amount_to_chinese
    except ImportError:
        # 兼容：如果 import 失败，用本地实现
        pass
    try:
        from docx import Document
        from docx.shared import Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH
    except ImportError:
        raise RuntimeError("需要安装 python-docx: pip install python-docx")

    conn = _get_db()
    contract_row = conn.execute(
        "SELECT * FROM contracts WHERE id = ?", (contract_id,)
    ).fetchone()
    conn.close()
    if not contract_row:
        raise ValueError(f"合同 ID {contract_id} 不存在")
    data = dict(contract_row)

    amount_cn = amount_to_chinese(data["amount"])

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "宋体"
    style.font.size = Pt(12)

    # 标题
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run(data["title"])
    run.bold = True
    run.font.size = Pt(22)

    # 合同编号
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.add_run(f"合同编号：{data['contract_no']}").font.size = Pt(10)

    doc.add_paragraph()

    # 双方信息
    p = doc.add_paragraph()
    p.add_run(f"甲方（委托方）：{data['party_a']}").bold = True
    p = doc.add_paragraph()
    p.add_run(f"地址：{data.get('party_a_address') or '___________'}")

    doc.add_paragraph()

    p = doc.add_paragraph()
    p.add_run(f"乙方（受托方）：{data['party_b']}").bold = True
    p = doc.add_paragraph()
    p.add_run(f"地址：{data.get('party_b_address') or '___________'}")

    doc.add_paragraph()

    # 前言
    p = doc.add_paragraph()
    p.add_run(
        f"甲方委托乙方就 {data['title']} 项目进行专项技术服务，"
        f"并支付相应的技术服务报酬。双方经过平等协商，"
        f"根据《中华人民共和国民法典》的规定，达成如下协议。"
    )

    # 条款
    sections = [
        ("第一条 技术服务内容", [
            f"1. 服务目标：{data['title']}",
            "2. 服务内容：详见双方约定的服务清单。",
            "3. 服务方式：远程交付为主，必要时现场支持。",
        ]),
        ("第二条 服务期限", [
            f"服务期限：{data.get('effective_date') or '____年__月__日'} 至 "
            f"{data.get('expiry_date') or '____年__月__日'}。",
        ]),
        ("第三条 服务报酬与支付", [
            f"1. 服务费总额：¥{data['amount']:,.2f}（大写人民币：{amount_cn}）。",
            "2. 支付方式：甲方于服务成果交付验收合格后 30 个工作日内一次性支付。",
            f"3. 发票：乙方出具等额增值税专用发票（税率 {int(data.get('tax_rate', 0.06)*100)}%）。",
        ]),
        ("第四条 验收标准", [
            "1. 验收标准：按双方确认的服务交付物清单。",
            "2. 验收期限：甲方应在收到交付物后 10 个工作日内完成验收。",
        ]),
        ("第五条 保密条款", [
            "双方对履行合同过程中知悉的对方商业秘密负有保密义务，"
            "保密期限为合同终止后 3 年。",
        ]),
        ("第六条 知识产权", [
            "服务过程中产生的知识产权，除另有约定外归双方共有。",
        ]),
        ("第七条 违约责任", [
            "1. 乙方迟延交付的，每逾期一日按迟延部分价款 1‰ 支付违约金。",
            "2. 甲方迟延付款的，每逾期一日按迟延金额 1‰ 支付违约金，"
            "最高不超过合同总额的 5%。",
        ]),
        ("第八条 不可抗力", [
            "因不可抗力不能履行合同的，部分或全部免除责任。",
        ]),
        ("第九条 合同解除", [
            "双方协商一致可解除合同；一方根本违约的，另一方有权解除。",
        ]),
        ("第十条 争议解决", [
            "协商、调解不成的，依法向甲方所在地人民法院起诉。",
        ]),
        ("第十一条 其他", [
            "本合同一式肆份，甲乙双方各执贰份，具有同等法律效力。",
            "本合同经双方签字盖章后生效。",
        ]),
    ]

    for heading, items in sections:
        doc.add_heading(heading, level=2)
        for item in items:
            doc.add_paragraph(item)

    # 签署区
    doc.add_paragraph()
    doc.add_paragraph()
    doc.add_paragraph(f"甲方（盖章）：{data['party_a']}")
    doc.add_paragraph("法定代表人（签字）：__________________")
    doc.add_paragraph("签字日期：______年____月____日")
    doc.add_paragraph()
    doc.add_paragraph(f"乙方（盖章）：{data['party_b']}")
    doc.add_paragraph("法定代表人（签字）：__________________")
    doc.add_paragraph("签字日期：______年____月____日")

    output_path = os.path.join(config.OUTPUT_DIR, f"{data['contract_no']}.docx")
    doc.save(output_path)

    return {"output_path": output_path, "contract_no": data["contract_no"]}


def get_contract(contract_id):
    """获取合同详情"""
    conn = _get_db()
    contract = conn.execute(
        "SELECT * FROM contracts WHERE id = ?", (contract_id,)
    ).fetchone()
    if not contract:
        return None

    approvals = conn.execute(
        "SELECT * FROM approvals WHERE contract_id = ? ORDER BY created_at",
        (contract_id,),
    ).fetchall()

    audits = conn.execute(
        "SELECT * FROM audit_logs WHERE contract_id = ? ORDER BY created_at",
        (contract_id,),
    ).fetchall()
    conn.close()

    return {
        "contract": dict(contract),
        "approvals": [dict(a) for a in approvals],
        "audit_logs": [dict(a) for a in audits],
    }


def list_contracts(status=None):
    """列出合同"""
    conn = _get_db()
    if status:
        rows = conn.execute(
            "SELECT * FROM contracts WHERE status = ? ORDER BY created_at DESC",
            (status,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM contracts ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================================================
# Web UI 扩展：列表分页、筛选、统计、更新
# ============================================================

def list_contracts_paged(page=1, page_size=20, status=None, party_b=None,
                         min_amount=None, max_amount=None,
                         date_from=None, date_to=None, sort_by="created_at",
                         sort_order="desc"):
    """带分页和筛选的合同列表"""
    conn = _get_db()
    query = "SELECT * FROM contracts WHERE 1=1"
    count_query = "SELECT COUNT(*) as cnt FROM contracts WHERE 1=1"
    params = []

    if status:
        query += " AND status = ?"
        count_query += " AND status = ?"
        params.append(status)
    if party_b:
        query += " AND party_b LIKE ?"
        count_query += " AND party_b LIKE ?"
        params.append(f"%{party_b}%")
    if min_amount is not None:
        query += " AND amount >= ?"
        count_query += " AND amount >= ?"
        params.append(min_amount)
    if max_amount is not None:
        query += " AND amount <= ?"
        count_query += " AND amount <= ?"
        params.append(max_amount)
    if date_from:
        query += " AND date(created_at) >= date(?)"
        count_query += " AND date(created_at) >= date(?)"
        params.append(date_from)
    if date_to:
        query += " AND date(created_at) <= date(?)"
        count_query += " AND date(created_at) <= date(?)"
        params.append(date_to)

    # 排序
    valid_sort = {"created_at", "updated_at", "amount", "contract_no"}
    if sort_by not in valid_sort:
        sort_by = "created_at"
    if sort_order not in ("asc", "desc"):
        sort_order = "desc"
    query += f" ORDER BY {sort_by} {sort_order.upper()}"

    # 总数
    total = conn.execute(count_query, params).fetchone()["cnt"]

    # 分页
    offset = (page - 1) * page_size
    query += " LIMIT ? OFFSET ?"
    params.extend([page_size, offset])

    rows = conn.execute(query, params).fetchall()
    conn.close()

    return {
        "items": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }


def update_contract(contract_id, **kwargs):
    """更新合同字段（仅 draft 状态可更新核心字段，其他状态仅允许更新非核心字段）"""
    conn = _get_db()
    contract = conn.execute(
        "SELECT * FROM contracts WHERE id = ?", (contract_id,)
    ).fetchone()
    if not contract:
        conn.close()
        raise ValueError(f"合同 ID {contract_id} 不存在")

    # 可更新字段白名单
    allowed_fields = {
        "title", "contract_type", "party_a", "party_a_address",
        "party_b", "party_b_address", "amount", "effective_date",
        "expiry_date", "file_path", "tax_rate",
    }

    # 非 draft 状态不允许改核心业务字段
    if contract["status"] != "draft":
        allowed_fields = {"file_path"}

    updates = {}
    for k, v in kwargs.items():
        if k in allowed_fields and v is not None:
            updates[k] = v

    if not updates:
        conn.close()
        return {"updated": 0}

    # 金额变化需要更新审批级别（如果在 draft 状态）
    if "amount" in updates and contract["status"] == "draft":
        level = get_approval_level(updates["amount"])
        # 仅记录，审批级别在提交时才实际生效

    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    set_clause += ", updated_at = ?"
    values = list(updates.values()) + [datetime.now().isoformat()]
    values.append(contract_id)

    conn.execute(f"UPDATE contracts SET {set_clause} WHERE id = ?", values)
    conn.execute(
        """INSERT INTO audit_logs (contract_id, action, operator, detail)
           VALUES (?, 'update', 'web-user', ?)""",
        (contract_id, json.dumps({"fields": list(updates.keys())}, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()

    return {"updated": len(updates), "fields": list(updates.keys())}


def get_stats():
    """统计数据"""
    conn = _get_db()

    # 各状态计数
    rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM contracts GROUP BY status"
    ).fetchall()
    status_counts = {r["status"]: r["cnt"] for r in rows}

    # 待审批总数（所有 review 状态）
    pending_count = sum(
        status_counts.get(s, 0) for s in ("review1", "review2", "review3")
    )

    # 本月新增
    this_month = datetime.now().strftime("%Y-%m")
    monthly_new = conn.execute(
        "SELECT COUNT(*) as cnt FROM contracts WHERE strftime('%Y-%m', created_at) = ?",
        (this_month,),
    ).fetchone()["cnt"]

    # 通过率（已通过 / (已通过 + 被驳回次数)）
    approved_count = status_counts.get("approved", 0) + status_counts.get("signed", 0) + status_counts.get("archived", 0)
    reject_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM approvals WHERE action = 'reject'"
    ).fetchone()["cnt"]
    if approved_count + reject_count > 0:
        approval_rate = round(approved_count / (approved_count + reject_count) * 100, 1)
    else:
        approval_rate = 0.0

    # 平均审批时长（从 submit 到 approved 的耗时）
    avg_duration_days = 0.0
    duration_rows = conn.execute("""
        SELECT 
            julianday(a2.created_at) - julianday(a1.created_at) as days
        FROM audit_logs a1
        JOIN audit_logs a2 ON a1.contract_id = a2.contract_id
        WHERE a1.action = 'submit' 
          AND a2.action = 'approve'
          AND a2.to_status = 'approved'
    """).fetchall()
    if duration_rows:
        avg_duration_days = round(
            sum(r["days"] for r in duration_rows) / len(duration_rows), 1
        )

    # 近 30 天趋势
    trend_rows = conn.execute("""
        SELECT date(created_at) as d, COUNT(*) as cnt
        FROM contracts
        WHERE created_at >= date('now', '-30 days')
        GROUP BY date(created_at)
        ORDER BY d ASC
    """).fetchall()
    trend = {r["d"]: r["cnt"] for r in trend_rows}

    # 高风险合同（最近一次 risk_scan 标记为 high 的）
    high_risk = conn.execute("""
        SELECT c.id, c.contract_no, c.title, c.amount, c.status, c.party_b
        FROM contracts c
        JOIN audit_logs a ON a.contract_id = c.id
        WHERE a.action = 'risk_scan'
          AND a.detail LIKE '%"overall_risk": "high"%'
        GROUP BY c.id
        ORDER BY a.created_at DESC
        LIMIT 10
    """).fetchall()

    conn.close()

    return {
        "status_counts": status_counts,
        "pending_count": pending_count,
        "approved_count": approved_count,
        "monthly_new": monthly_new,
        "approval_rate": approval_rate,
        "avg_duration_days": avg_duration_days,
        "trend_30d": trend,
        "high_risk": [dict(r) for r in high_risk],
        "draft_count": status_counts.get("draft", 0),
        "rejected_count": status_counts.get("rejected", 0),
    }


def get_history(contract_id):
    """获取审批历史（audit_logs + approvals 合并）"""
    result = get_contract(contract_id)
    if not result:
        return None
    return {
        "approvals": result["approvals"],
        "audit_logs": result["audit_logs"],
    }
