"""contractctl — Bangcle 合同智能审查 CLI（DETAIL §8 / OPERATIONS §4）。

命令：
  review --file <path> [--source upload]
  review --oa-billid <billid>
  report <review_id> [--format md|xlsx]
  init-db
  oa-login
  ontology register/submit/approve/reject/status/proposals  （Contract Ontology Bridge）

分步进度：>10s 操作打印当前步骤（进度条铁律）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# 组件根注入（使 contract_review/repository/services 可导入）
COMPONENT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(COMPONENT_ROOT)))
L3_ROOT = os.path.join(REPO_ROOT, "L3-business", "components", "contract-management")
for _p in (COMPONENT_ROOT, L3_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _progress(step: str) -> None:
    """打印进度行（分步进度铁律）。"""
    print("[%s] %s ..." % (time.strftime("%H:%M:%S"), step), flush=True)


def cmd_init_db(args) -> int:
    from repository.db import init_db
    path = init_db(args.db)
    print("DB 已初始化:", path)
    return 0


def cmd_review(args) -> int:
    from contract_review.ingest import ingest_file
    from contract_review.digitize import digitize
    from contract_review.parser import parse_shallow
    from contract_review.risk import run_risk
    from contract_review.kb_match import run_kb_match
    from contract_review.report import write_markdown, build_excel
    from repository.db import Repository

    source = args.source or "upload"
    ocr_method = None
    ocr_conf = None

    if args.oa_billid:
        _progress("从 OA Cube 拉取合同 (billid=%s)" % args.oa_billid)
        from services.oa.entry import get_contract_with_fallback
        from contract_review.oa_text import digitize_oa_data
        from contract_review.digitize import DigitizedText
        import shutil
        import tempfile
        tmp = tempfile.mkdtemp(prefix="clm_oa_")
        contract_ref = "billid:%s" % args.oa_billid
        try:
            data = get_contract_with_fallback(args.oa_billid, tmp)
            # 1) 优先用合同附件原文走全文管线（pdf/docx/扫描件）
            oa_dt = digitize_oa_data(data)
            if oa_dt is not None:
                text = oa_dt
                ocr_method = oa_dt.method
                ocr_conf = oa_dt.ocr_confidence
            else:
                # 2) 无可用原文 → 回退卡片摘要 / 主字段拼接文本
                card_txt = data.get("card_text_snippet", "")
                fallback = card_txt or ""
                if not fallback:
                    lines = []
                    for k, v in (data.get("main_fields") or {}).items():
                        lines.append("%s：%s" % (k, v))
                    fallback = "\n".join(lines)
                text = fallback
                ocr_method = "oa_cube"
        finally:
            # 即用即焚：附件原文只在临时目录短暂存在，读完（或失败）即删
            shutil.rmtree(tmp, ignore_errors=True)
    else:
        _progress("摄取文件")
        ingested = ingest_file(args.file)
        contract_ref = ingested.original_name
        _progress("数字化")
        dt = digitize(ingested.local_path)
        text = dt.full_text
        ocr_method = dt.method
        ocr_conf = dt.ocr_confidence

    # 归一化为 DigitizedText（OA 全文路径已是；字段摘要/本地上传路径是 str）
    from contract_review.digitize import DigitizedText
    if isinstance(text, str):
        text = DigitizedText(full_text=text, method=ocr_method or "oa_cube")

    _progress("浅解析条款")
    parsed = parse_shallow(text.full_text)
    _progress("风险扫描")
    risk = run_risk(text)
    _progress("产品/服务参照")
    text_str = text.full_text if hasattr(text, "full_text") else text
    kb = run_kb_match(text_str, parsed=parsed)

    _progress("生成报告")
    out_md = os.path.join(args.out_dir, "report-%s.md" % contract_ref.replace("/", "_"))
    write_markdown(contract_ref=contract_ref, source=source,
                   risk=risk, kb=kb, out_path=out_md,
                   ocr_method=ocr_method, ocr_confidence=ocr_conf)
    report_path = out_md
    if args.format == "xlsx":
        out_xlsx = out_md.replace(".md", ".xlsx")
        build_excel(contract_ref=contract_ref, source=source,
                    risk=risk, kb=kb, out_path=out_xlsx)
        report_path = out_xlsx

    _progress("持久化")
    with Repository(args.db) as repo:
        review_id = repo.add_review(
            contract_ref=contract_ref, source=source,
            overall_risk=risk.get("overall_risk", "unknown"),
            satisfaction=kb.satisfaction,
            report_path=report_path,
        )
        for r in kb.items:
            repo.add_kb_match(
                review_id=review_id, input_name=r.input_name,
                matched_product=r.product, matched_sku=r.sku,
                score=r.score, alert=r.alert,
            )
        repo.append_audit_log(
            action="review_complete", operator="contractctl",
            review_id=review_id,
            detail=json.dumps({"overall_risk": risk.get("overall_risk"),
                               "satisfaction": kb.satisfaction,
                               "referenced": kb.referenced}, ensure_ascii=False),
        )

    print("\n✅ 审查完成")
    print("  review_id :", review_id)
    print("  综合风险   :", risk.get("overall_risk"))
    print("  产品满足度 :", kb.satisfaction, "(未做参照)" if not kb.referenced else "")
    print("  报告       :", report_path)
    return 0


def cmd_report(args) -> int:
    from repository.db import Repository
    with Repository(args.db) as repo:
        record = repo.get_review(args.review_id)
    if record is None:
        print("未找到 review_id=%s" % args.review_id)
        return 1
    print(json.dumps(record, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_oa_login(args) -> int:
    from services.oa.browser_fallback import heal_session
    _progress("IAM headless 登录（IMAP 验证码）")
    ok = heal_session()
    print("OA 会话:", "✅ 已建立" if ok else "❌ 失败（检查 secrets/网络）")
    return 0 if ok else 1


# =============================================================
# ontology 子命令（Contract Ontology Bridge，P1-P3）
# =============================================================

def _bridge(args):
    """构造 ContractOntologyBridge（ai_kb 默认与 contract db 同目录）。"""
    from contract_review.ontology_bridge import ContractOntologyBridge
    ai_kb = args.ai_kb or os.path.join(
        os.path.dirname(args.db), "ai_kb.db",
    )
    return ContractOntologyBridge(args.db, ai_kb)


def cmd_ont_register(args) -> int:
    """登记合同为运营对象（幂等）。"""
    from contract_review.ontology_bridge import ContractRegistry
    reg = ContractRegistry(args.db, args.ai_kb)
    for spec in args.specs:
        no, _, amount = spec.rpartition(":")
        try:
            amt = float(amount or 0)
        except ValueError:
            print(f"❌ 无效登记规格（期望 NO:AMOUNT）: {spec}")
            return 1
        result = reg.register(no, title=args.title or f"合同 {no}", amount=amt,
                              created_by=args.operator)
        print("✅ 登记 %s → identity %s (canonical=%s, created=%s, status=%s)" % (
            result["contract_no"], result["identity_id"],
            result["canonical_key"], result["created"], result["status"],
        ))
    return 0


def cmd_ont_submit(args) -> int:
    bridge = _bridge(args)
    _progress("submit %s (draft→review1, auto 审)" % args.contract_id)
    r = bridge.submit(args.contract_id, args.operator,
                      idempotency_key=args.idempotency_key)
    return _print_action_result(r)


def cmd_ont_approve(args) -> int:
    bridge = _bridge(args)
    _progress("approve %s (human 审)" % args.contract_id)
    r = bridge.approve(args.contract_id, args.operator,
                       approver_role=args.role, comment=args.comment,
                       idempotency_key=args.idempotency_key)
    return _print_action_result(r)


def cmd_ont_reject(args) -> int:
    bridge = _bridge(args)
    _progress("reject %s (human 审)" % args.contract_id)
    r = bridge.reject(args.contract_id, args.operator,
                      approver_role=args.role, comment=args.comment,
                      idempotency_key=args.idempotency_key)
    return _print_action_result(r)


def cmd_ont_status(args) -> int:
    bridge = _bridge(args)
    st = bridge.status(args.contract_id)
    print(json.dumps(st, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_ont_proposals(args) -> int:
    bridge = _bridge(args)
    items = bridge.proposals(status=args.status, limit=args.limit)
    if not items:
        print("(无提案)")
        return 0
    for p in items:
        print("#%s %-10s %-9s caller=%s/%s action=%s idem=%s" % (
            p["id"], p["status"], p.get("action_type_id") or "",
            p["caller_id"], p["caller_kind"],
            p.get("params", {}).get("contract_no", ""),
            p.get("idempotency_key") or "-",
        ))
    return 0


def _print_action_result(r: dict) -> int:
    """统一打印动作结果；失败返回 1（violations 输出）。"""
    if not r["ok"]:
        print("❌ 动作未执行")
        print("  proposal : #%s (%s)" % (r.get("proposal_id"), r.get("proposal_status")))
        for v in r.get("violations", []):
            print("  violation: [%s] %s" % (v.get("stage"), v.get("message")))
        return 1
    print("✅ 动作已提交")
    print("  proposal : #%s (%s)" % (r.get("proposal_id"), r.get("proposal_status")))
    print("  contract : #%s → %s" % (r.get("contract_id"), r.get("contract_status")))
    if r.get("idempotent_replay"):
        print("  (幂等重放：同 idempotency_key 既有提案)")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="contractctl", description="Bangcle 合同智能审查")
    parser.add_argument("--db", default=None, help="SQLite 路径（默认组件 data/）")
    parser.add_argument("--out-dir", default=None, help="报告输出目录（默认 data/reports）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init-db", help="初始化数据库")
    p_init.set_defaults(func=cmd_init_db)

    p_rev = sub.add_parser("review", help="审查合同（文件或 OA billid）")
    p_rev.add_argument("--file", help="合同文件路径")
    p_rev.add_argument("--oa-billid", help="OA Cube billid")
    p_rev.add_argument("--source", default="upload")
    p_rev.add_argument("--format", choices=["md", "xlsx"], default="md")
    p_rev.set_defaults(func=cmd_review)

    p_rep = sub.add_parser("report", help="取审查记录")
    p_rep.add_argument("review_id", type=int)
    p_rep.set_defaults(func=cmd_report)

    p_login = sub.add_parser("oa-login", help="建立 OA 会话")
    p_login.set_defaults(func=cmd_oa_login)

    # --- ontology 子命令（Contract Ontology Bridge） ---
    p_ont = sub.add_parser("ontology", help="合同运营对象（Proposal Gate）")
    ont_sub = p_ont.add_subparsers(dest="ont_cmd", required=True)

    p_oreg = ont_sub.add_parser("register", help="登记合同为运营对象（幂等）")
    p_oreg.add_argument("specs", nargs="+", help="NO:AMOUNT 列表（逗号分隔可多份）")
    p_oreg.add_argument("--title", default=None, help="合同标题（默认 合同 NO）")
    p_oreg.add_argument("--operator", default="contractctl", help="登记人")
    p_oreg.add_argument("--ai-kb", default=None, help="L2 ai_kb 库路径（默认与 contract db 同目录）")
    p_oreg.set_defaults(func=cmd_ont_register)

    p_osub = ont_sub.add_parser("submit", help="提交审批（draft→review1，auto 审）")
    p_osub.add_argument("contract_id", type=int)
    p_osub.add_argument("--operator", default="contractctl", help="操作人")
    p_osub.add_argument("--idempotency-key", default=None)
    p_osub.add_argument("--ai-kb", default=None)
    p_osub.set_defaults(func=cmd_ont_submit)

    p_oapp = ont_sub.add_parser("approve", help="审批通过（human 审）")
    p_oapp.add_argument("contract_id", type=int)
    p_oapp.add_argument("--operator", default="contractctl", help="审批人")
    p_oapp.add_argument("--role", default="", help="审批角色")
    p_oapp.add_argument("--comment", default="")
    p_oapp.add_argument("--idempotency-key", default=None)
    p_oapp.add_argument("--ai-kb", default=None)
    p_oapp.set_defaults(func=cmd_ont_approve)

    p_orej = ont_sub.add_parser("reject", help="驳回（human 审）")
    p_orej.add_argument("contract_id", type=int)
    p_orej.add_argument("--operator", default="contractctl", help="审批人")
    p_orej.add_argument("--role", default="", help="审批角色")
    p_orej.add_argument("--comment", default="")
    p_orej.add_argument("--idempotency-key", default=None)
    p_orej.add_argument("--ai-kb", default=None)
    p_orej.set_defaults(func=cmd_ont_reject)

    p_ost = ont_sub.add_parser("status", help="合同双视角状态")
    p_ost.add_argument("contract_id", type=int)
    p_ost.add_argument("--ai-kb", default=None)
    p_ost.set_defaults(func=cmd_ont_status)

    p_op = ont_sub.add_parser("proposals", help="列出提案（可按五态过滤）")
    p_op.add_argument("--status", default=None, help="pending/validated/rejected/committed/failed")
    p_op.add_argument("--limit", type=int, default=100)
    p_op.add_argument("--ai-kb", default=None)
    p_op.set_defaults(func=cmd_ont_proposals)

    args = parser.parse_args(argv)
    if args.out_dir is None:
        args.out_dir = os.path.join(COMPONENT_ROOT, "data", "reports")
    os.makedirs(args.out_dir, exist_ok=True)
    if args.db is None:
        from repository.db import default_db_path
        args.db = default_db_path()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
