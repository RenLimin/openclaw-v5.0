"""合同管理 CLI — Click 命令组 `bdms contract`。

🔒 NO_TOKEN — 纯代码，零 AI 依赖。

命令列表：
  create / update / delete
  submit / approve / reject
  scan-risks / analyze-subject
  import（OCR）/ generate-docx / upload-signed
  sign / archive
  list / show / audit-log / risks
  export
"""

import json
import sys
import click
from pathlib import Path

from .service import ContractManagementService
from .exporter import ContractExporter
from .ocr_importer import ContractOCRImporter


# ─── 辅助 ───

def _get_service():
    return ContractManagementService()


def _get_exporter():
    return ContractExporter()


def _output(data, format: str = "table"):
    """输出结果。"""
    if format == "json":
        click.echo(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, (dict, list)):
                    click.echo(f"{k}: {json.dumps(v, ensure_ascii=False, default=str)}")
                else:
                    click.echo(f"{k}: {v}")
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    click.echo(" — " + ", ".join(f"{k}={v}" for k, v in item.items()))
                else:
                    click.echo(f" — {item}")
        else:
            click.echo(str(data))


# ─── CLI 命令组 ───

@click.group("contract")
@click.option("--format", type=click.Choice(["table", "json"]), default="table")
@click.pass_context
def contract_group(ctx, format):
    """合同管理命令组。"""
    ctx.ensure_object(dict)
    ctx.obj["format"] = format


# ─── create ───

@contract_group.command("create")
@click.option("--title", required=True, help="合同标题")
@click.option("--party-a", required=True, help="甲方名称")
@click.option("--party-b", required=True, help="乙方名称")
@click.option("--amount", type=float, default=0.0, help="合同金额")
@click.option("--contract-type", default="", help="合同类型")
@click.option("--effective-date", default="", help="生效日期 (YYYY-MM-DD)")
@click.option("--expiry-date", default="", help="到期日期 (YYYY-MM-DD)")
@click.option("--operator", default="", help="操作人")
@click.pass_context
def create(ctx, title, party_a, party_b, amount, contract_type,
           effective_date, expiry_date, operator):
    """创建合同。"""
    svc = _get_service()
    result = svc.create_contract({
        "title": title,
        "party_a": party_a,
        "party_b": party_b,
        "amount": amount,
        "contract_type": contract_type,
        "effective_date": effective_date,
        "expiry_date": expiry_date,
    }, operator=operator)
    _output(result, ctx.obj["format"])


# ─── update ───

@contract_group.command("update")
@click.argument("contract_id", type=int)
@click.option("--title", default=None, help="合同标题")
@click.option("--amount", type=float, default=None, help="合同金额")
@click.option("--status", default=None, help="状态")
@click.option("--operator", default="", help="操作人")
@click.pass_context
def update(ctx, contract_id, title, amount, status, operator):
    """更新合同字段。"""
    svc = _get_service()
    contract = svc.get_contract(contract_id)
    if not contract:
        click.echo(f"合同 {contract_id} 不存在", err=True)
        return

    data = {}
    if title is not None:
        data["title"] = title
    if amount is not None:
        data["amount"] = amount
    if status is not None:
        data["status"] = status

    if data:
        from bdms.core import db as _db
        conn = _db.get_connection(svc.db_path)
        try:
            set_parts = []
            values = []
            for k, v in data.items():
                set_parts.append(f"{k} = ?")
                values.append(v)
            set_parts.append("updated_at = ?")
            set_parts.append("updated_by = ?")
            from datetime import datetime
            values.append(datetime.now().isoformat())
            values.append(operator)
            values.append(contract_id)
            conn.execute(
                f"UPDATE cr_contracts SET {', '.join(set_parts)} WHERE id = ?",
                values,
            )
            conn.commit()
        finally:
            conn.close()

    result = svc.get_contract(contract_id)
    _output(result, ctx.obj["format"])


# ─── delete ───

@contract_group.command("delete")
@click.argument("contract_id", type=int)
@click.option("--operator", default="", help="操作人")
@click.pass_context
def delete(ctx, contract_id, operator):
    """软删除合同。"""
    svc = _get_service()
    result = svc.soft_delete(contract_id, operator)
    _output(result, ctx.obj["format"])


# ─── submit ───

@contract_group.command("submit")
@click.argument("contract_id", type=int)
@click.option("--operator", default="", help="操作人")
@click.option("--comment", default="", help="提交意见")
@click.pass_context
def submit(ctx, contract_id, operator, comment):
    """提交审批。"""
    svc = _get_service()
    result = svc.submit_approval(contract_id, operator, comment)
    _output(result, ctx.obj["format"])


# ─── approve ───

@contract_group.command("approve")
@click.argument("contract_id", type=int)
@click.option("--operator", default="", help="审批人")
@click.option("--role", default="", help="审批角色")
@click.option("--comment", default="", help="审批意见")
@click.pass_context
def approve(ctx, contract_id, operator, role, comment):
    """审批通过。"""
    svc = _get_service()
    result = svc.approve(contract_id, operator, role, comment)
    _output(result, ctx.obj["format"])


# ─── reject ───

@contract_group.command("reject")
@click.argument("contract_id", type=int)
@click.option("--operator", default="", help="审批人")
@click.option("--role", default="", help="审批角色")
@click.option("--comment", default="", help="驳回原因")
@click.pass_context
def reject(ctx, contract_id, operator, role, comment):
    """驳回合同。"""
    svc = _get_service()
    result = svc.reject(contract_id, operator, role, comment)
    _output(result, ctx.obj["format"])


# ─── sign ───

@contract_group.command("sign")
@click.argument("contract_id", type=int)
@click.option("--operator", default="", help="签署人")
@click.pass_context
def sign(ctx, contract_id, operator):
    """签署合同。"""
    svc = _get_service()
    result = svc.sign(contract_id, operator)
    _output(result, ctx.obj["format"])


# ─── archive ───

@contract_group.command("archive")
@click.argument("contract_id", type=int)
@click.option("--operator", default="", help="操作人")
@click.pass_context
def archive(ctx, contract_id, operator):
    """归档合同。"""
    svc = _get_service()
    result = svc.archive(contract_id, operator)
    _output(result, ctx.obj["format"])


# ─── scan-risks ───

@contract_group.command("scan-risks")
@click.argument("contract_id", type=int)
@click.option("--content", default="", help="合同文本内容")
@click.pass_context
def scan_risks(ctx, contract_id, content):
    """风险扫描。"""
    svc = _get_service()
    results = svc.scan_risks(contract_id, content)
    _output(results, ctx.obj["format"])


# ─── analyze-subject ───

@contract_group.command("analyze-subject")
@click.argument("contract_id", type=int)
@click.pass_context
def analyze_subject(ctx, contract_id):
    """标的对比分析。"""
    svc = _get_service()
    result = svc.analyze_subject(contract_id)
    _output(result, ctx.obj["format"])


# ─── import (OCR) ───

@contract_group.command("import")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--month", default="", help="月份 (YYYYMM)")
@click.pass_context
def import_ocr(ctx, file_path, month):
    """OCR 导入合同。"""
    if not month:
        from datetime import datetime
        month = datetime.now().strftime("%Y%m")

    importer = ContractOCRImporter()
    result = importer.import_all(Path(file_path), month)
    _output(result, ctx.obj["format"])


# ─── generate-docx ───

@contract_group.command("generate-docx")
@click.argument("contract_id", type=int)
@click.option("--template", default="", help="模板路径")
@click.option("--output", default="", help="输出路径")
@click.pass_context
def generate_docx(ctx, contract_id, template, output):
    """生成合同 Word 文档。"""
    svc = _get_service()
    result = svc.generate_docx(
        contract_id,
        template_path=template or None,
        output_path=output or None,
    )
    _output({"file": result}, ctx.obj["format"])


# ─── upload-signed ───

@contract_group.command("upload-signed")
@click.argument("contract_id", type=int)
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--operator", default="", help="操作人")
@click.pass_context
def upload_signed(ctx, contract_id, file_path, operator):
    """上传已签署的合同文件。"""
    svc = _get_service()
    contract = svc.get_contract(contract_id)
    if not contract:
        click.echo(f"合同 {contract_id} 不存在", err=True)
        return

    from bdms.core import db as _db
    conn = _db.get_connection(svc.db_path)
    try:
        # 获取当前最大版本号
        row = conn.execute(
            "SELECT MAX(version) AS max_ver FROM cr_contract_documents WHERE contract_id = ?",
            (contract_id,),
        ).fetchone()
        version = (row["max_ver"] or 0) + 1

        from datetime import datetime
        import hashlib

        file_path = Path(file_path)
        file_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()[:16]
        watermark = contract.get("status", "signed")

        conn.execute(
            """INSERT INTO cr_contract_documents
               (contract_id, version, file_path, file_hash, watermark, created_by, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (contract_id, version, str(file_path), file_hash, watermark,
             operator, datetime.now().isoformat()),
        )
        conn.commit()

        result = {"contract_id": contract_id, "version": version, "file": str(file_path)}
    finally:
        conn.close()

    _output(result, ctx.obj["format"])


# ─── list ───

@contract_group.command("list")
@click.option("--status", default="", help="按状态过滤")
@click.option("--contract-type", default="", help="按类型过滤")
@click.option("--keyword", default="", help="关键词搜索")
@click.option("--page", type=int, default=1, help="页码")
@click.option("--page-size", type=int, default=20, help="每页条数")
@click.pass_context
def list_contracts(ctx, status, contract_type, keyword, page, page_size):
    """合同列表。"""
    svc = _get_service()
    filters = {}
    if status:
        filters["status"] = status
    if contract_type:
        filters["contract_type"] = contract_type
    if keyword:
        filters["keyword"] = keyword

    result = svc.list_contracts(filters, page=page, page_size=page_size)
    _output(result, ctx.obj["format"])


# ─── show ───

@contract_group.command("show")
@click.argument("contract_id", type=int)
@click.pass_context
def show(ctx, contract_id):
    """查看合同详情。"""
    svc = _get_service()
    result = svc.get_contract(contract_id)
    if result:
        _output(result, ctx.obj["format"])
    else:
        click.echo(f"合同 {contract_id} 不存在", err=True)


# ─── audit-log ───

@contract_group.command("audit-log")
@click.argument("contract_id", type=int)
@click.pass_context
def audit_log(ctx, contract_id):
    """查看审计日志。"""
    svc = _get_service()
    result = svc.audit_log(contract_id)
    _output(result, ctx.obj["format"])


# ─── risks ───

@contract_group.command("risks")
@click.argument("contract_id", type=int)
@click.pass_context
def risks(ctx, contract_id):
    """查看风险扫描结果。"""
    svc = _get_service()
    contract = svc.get_contract(contract_id)
    if not contract:
        click.echo(f"合同 {contract_id} 不存在", err=True)
        return

    from bdms.core import db as _db
    conn = _db.get_connection(svc.db_path)
    try:
        rows = conn.execute(
            """SELECT * FROM cr_risk_scan_results
               WHERE contract_id = ? AND (deleted_at IS NULL OR deleted_at = '')
               ORDER BY created_at DESC""",
            (contract_id,),
        ).fetchall()
        results = [dict(r) for r in rows]
    finally:
        conn.close()

    _output(results, ctx.obj["format"])


# ─── export ───

@contract_group.command("export")
@click.option("--month", default="", help="月份 (YYYYMM)")
@click.option("--contract-id", type=int, default=None, help="合同ID")
@click.option("--type", "export_type", type=click.Choice([
    "overview", "risk", "approval", "audit", "all"
]), default="overview", help="导出类型")
@click.option("--output", default="", help="输出路径")
@click.pass_context
def export(ctx, month, contract_id, export_type, output):
    """导出合同数据。"""
    exporter = _get_exporter()

    if export_type == "overview":
        result = exporter.export_contract_overview(month=month or None, out_path=Path(output) if output else None)
    elif export_type == "risk":
        result = exporter.export_risk_details(contract_id=contract_id, out_path=Path(output) if output else None)
    elif export_type == "approval":
        result = exporter.export_approval_log(contract_id=contract_id, out_path=Path(output) if output else None)
    elif export_type == "audit":
        result = exporter.export_audit_trail(contract_id=contract_id, out_path=Path(output) if output else None)
    elif export_type == "all":
        # 导出概览 + 风险
        result1 = exporter.export_contract_overview(month=month or None)
        result2 = exporter.export_risk_details(contract_id=contract_id)
        result = f"概览: {result1}, 风险: {result2}"
    else:
        result = exporter.export_contract_overview(month=month or None)

    _output({"file": str(result)}, ctx.obj["format"])


# ─── 入口 ───

if __name__ == "__main__":
    contract_group()
