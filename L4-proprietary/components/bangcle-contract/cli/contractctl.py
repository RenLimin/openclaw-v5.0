"""contractctl — Bangcle 合同智能审查 CLI（DETAIL §8 / OPERATIONS §4）。

命令：
  review --file <path> [--source upload]
  review --oa-billid <billid>
  report <review_id> [--format md|xlsx]
  init-db
  oa-login
  oa-project-mgmt --requestid <rid> --workflow wf_916|wf_815|wf_820  （项目实施管理批注建议，只读）
  clauses --file <path>           （条款拆解：L3 受控库，含必备条款缺失）
  history-delivery --contract-no <no> [--end-user <name>]  （历史交付问题盘点，BDMS 快照只读）
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


def cmd_oa_fetch(args) -> int:
    """按合同编号从 OA 拉取合同原文/附件（台账检索 → billid → 落盘）。"""
    from services.oa.ledger import fetch_contract_by_no, LedgerError
    _progress("台账检索 %s (modeId=112)" % args.contract_no)
    try:
        out = args.out_dir or None
        manifest = fetch_contract_by_no(
            args.contract_no,
            out_dir=out,
            heal_if_expired=args.heal,
        )
    except LedgerError as e:
        print("❌", e)
        return 1
    print("✅ 合同原文已拉取")
    print("  合同编号 :", manifest["contract_no"])
    print("  billid   :", manifest["billid"])
    for f in manifest["files"]:
        status = "✅" if f.get("local_path") else ("⚠️ " + (f.get("error") or "?"))
        print("  %s %s -> %s" % (status, f.get("name"), f.get("local_path") or ""))
    print("  manifest :", manifest["manifest_path"])
    return 0


def cmd_oa_login(args) -> int:
    from services.oa.browser_fallback import heal_session
    _progress("IAM headless 登录（IMAP 验证码）")
    ok = heal_session()
    print("OA 会话:", "✅ 已建立" if ok else "❌ 失败（检查 secrets/网络）")
    return 0 if ok else 1


def cmd_oa_enhance(args) -> int:
    """OA 销售合同审查增强（只读：履约义务 ONES 实时 + 概算一致性）。"""
    from services.oa.enhance.runner import run_enhance
    from services.oa.enhance.oa_form import OrderFormError
    from pathlib import Path as _Path

    _progress("增强核查 requestid=%s（只读）" % args.requestid)
    try:
        result = run_enhance(
            request_id=args.requestid,
            raw_dir=_Path(args.raw_dir),
            storage_state=_Path(args.storage_state) if args.storage_state else None,
            project_codes=args.project_codes,
        )
    except OrderFormError as e:
        print("❌", e)
        return 2

    out_md = os.path.join(args.out_dir, "oa-enhance-%s.md" % args.requestid)
    with open(out_md, "w", encoding="utf-8") as fh:
        fh.write(result["markdown"])
    r1 = result["r1"]
    r2 = result["r2"]
    print("✅ 增强核查完成")
    print("  R1 履约义务 :", r1.get("verdict"))
    print("  R2 概算一致 :", r2.get("verdict"), ("(skipped: %s)" % r2.get("skipped")) if r2.get("skipped") else "")
    print("  降级项      :", result["degraded"] or "无")
    print("  报告        :", out_md)
    return 0


def _read_text_arg(path: str) -> str:
    """读合同原文（txt/docx/pdf），失败抛 RuntimeError（由调用方转清晰错误）。"""
    p = Path(path)
    if not p.exists():
        raise RuntimeError("文件不存在: %s" % path)
    suffix = p.suffix.lower()
    if suffix in (".txt", ".md"):
        return p.read_text(encoding="utf-8", errors="replace")
    from contract_review.digitize import digitize
    dt = digitize(str(p), file_type=suffix.lstrip("."))
    return dt.full_text or ""


def cmd_clauses(args) -> int:
    """条款拆解（L3 contract_parser）：输出结构化条款清单 + 必备条款缺失。"""
    from contract_review.clause_extract import extract_clauses, ClauseExtractError

    try:
        text = _read_text_arg(args.file)
    except RuntimeError as exc:
        print("❌", exc)
        return 2

    _progress("条款拆解（L3 contract_parser）")
    try:
        data = extract_clauses(text)
    except ClauseExtractError as exc:
        print("❌", exc)
        return 2

    print("✅ 条款拆解完成")
    print("  标题     :", data.get("title") or "【未取到】")
    print("  条款类别 : %d/%d（必备 %d，缺失 %d）"
          % (data["stats"]["extracted"], data["stats"]["categories_total"],
             data["stats"]["required_total"], data["stats"]["missing_required"]))
    if data.get("party_a"):
        print("  甲方     :", data["party_a"].get("名称") or data["party_a"])
    if data.get("party_b"):
        print("  乙方     :", data["party_b"].get("名称") or data["party_b"])

    for c in data.get("clauses") or []:
        flag = "⚠️" if c.get("issues") else "  "
        print("  %s [%s] %s｜%s" % (flag, c.get("category"), c.get("law") or "-",
                                    (c.get("summary") or "")[:60]))
        for it in c.get("issues") or []:
            print("        问题：%s" % it)

    if data.get("missing_required"):
        print("必备条款缺失（warn，需人工复核）：")
        for i, m in enumerate(data["missing_required"], 1):
            print("  %d. %s（%s）— %s" % (i, m["category"], m.get("law") or "-",
                                          m.get("description", "")))
    if data.get("unsupported_categories"):
        print("无提取器的类别（不参与缺失判定）：%s"
              % "、".join(data["unsupported_categories"]))

    if args.out:
        out = os.path.abspath(args.out)
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        print("  JSON     :", out)
    return 0


def cmd_history_delivery(args) -> int:
    """历史签约项目/合同交付问题盘点（BDMS 快照，只读）。"""
    from services.oa.enhance.history_delivery import (
        check_history_delivery, HistoryDeliveryError,
    )

    _progress("历史交付盘点（BDMS dr_sheet_row 快照）")
    try:
        res = check_history_delivery(
            contract_no=args.contract_no or "", end_user=args.end_user or "")
    except HistoryDeliveryError as exc:
        print("❌", exc)
        return 2

    d = res.to_dict()
    print("✅ 历史交付盘点完成")
    print("  判定     :", d["verdict"])
    print("  匹配口径 :", d["match_basis"] or "（无键）")
    print("  命中行数 :", d["matched_rows"])
    print("  风险点   :", len(d["issues"]))
    for i, it in enumerate((d["issues"] or [])[:10], 1):
        print("  %d. [%s][%s] %s｜%s｜%s" % (
            i, it["level"], it["sheet"], it["issue_type"],
            it["end_user"] or "-", (it["detail"] or it["status"] or "-")[:60]))
    if len(d["issues"]) > 10:
        print("  …另有 %d 条" % (len(d["issues"]) - 10))
    for m in d.get("missing") or []:
        print("  ⚠️", m)
    if args.out:
        out = os.path.abspath(args.out)
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=2)
        print("  JSON     :", out)
    return 0


def cmd_oa_approval(args) -> int:
    """OA 销售合同审批：触发词「处理OA销售合同审批」的一条链编排（只读）。"""
    from services.oa.enhance.orchestrator import run_approval
    from services.oa.enhance.todo import OaSessionExpired
    from pathlib import Path as _Path

    _progress("OA 销售合同审批编排（workflowid=757，只读）")
    try:
        payload = run_approval(
            raw_dir=_Path(args.raw_dir),
            out_dir=_Path(args.out_dir) if args.out_dir else None,
            request_ids=args.requestid,
            contract_file=_Path(args.contract_file) if args.contract_file else None,
            storage_state=_Path(args.storage_state) if args.storage_state else None,
            discover=not args.no_discover,
        )
    except OaSessionExpired as e:
        print("❌", e)
        return 2

    s = payload["summary"]
    print("✅ 编排完成")
    print("  待办      :", len(payload["todos"]))
    print("  处理      :", s["total"], "｜退回项:", s["block"], "｜提示:", s["warn"],
          "｜转人工:", s["manual"], "｜失败:", s["error"])
    print("  输出目录  :", payload["out_dir"])
    for r in payload["results"]:
        if r.get("error"):
            print("  ⚠️  %s: %s" % (r["request_id"], r["error"]))
        else:
            verdict = [l for l in r["remark"].splitlines() if l.startswith("【审批建议】")]
            print("  • %s %s" % (r["request_id"], verdict[0] if verdict else ""))
    return 0


def cmd_oa_project_mgmt(args) -> int:
    """OA 项目实施管理「分配项目经理」批注建议（只读：916/815/820）。

    链路：OA 单（raw）→ 三流程解析 → ONES 参考项目 → 风险注 → 三段式批注。
    916 额外：合同审批流程→（757）异常备注核查。
    全程只读：不提交/不审批/不退回/不转发/不代派 PM。
    """
    from services.oa.enhance.pm.order import parse, PmAssetError
    from services.oa.enhance.pm.ones_refs import find_reference_projects, RefsError
    from services.oa.enhance.pm.risk import assess
    from services.oa.enhance.pm.render import render_remark, render_markdown
    from services.oa.enhance.pm.approval_notes import collect
    from pathlib import Path as _Path

    raw_dir = _Path(args.raw_dir)
    try:
        order = parse(raw_dir, args.requestid, args.workflow, args.title)
    except PmAssetError as e:
        print("❌", e)
        return 2

    _progress("ONES 参考项目核查（只读，最终客户=%s）" % order.final_user)
    try:
        refs, notes = find_reference_projects(
            final_user=order.final_user,
            customer=order.customer,
            product_codes=order.product_codes,
            product_names=order.product_names,
            product_categories=order.product_categories,
            project_code=order.project_code,
            workflow_id=order.workflow_id,
            apply_date=order.apply_time,
        )
    except RefsError as e:
        print("❌ ONES 核查失败:", e)
        return 2

    # 916：合同审批流程 → 757 异常备注（无链接则跳过；无权限自动降级）
    appr = None
    if order.workflow_id == "wf_916" and order.approval_flow_rid:
        _progress("757 合同审批流程核查（requestid=%s，只读）" % order.approval_flow_rid)
        try:
            appr = collect(order.approval_flow_rid)
        except Exception as e:  # noqa: BLE001 - 单链降级不阻断
            appr = None
            print("  ⚠️ 757 核查失败（已降级）:", e)

    risks = assess(order, refs, appr)

    # v1.2 C5：按参考项目 PM 所属部门判定指派人（任立民/冯刚）。
    # 企微通讯录不可用（850002/二进制缺失）→ assigner 为空 → 渲染层回退 C1，不伪造。
    assigner = ""
    assigner_note = ""
    pm_names = []
    for r in refs:
        if (r.pm or "").strip() and r.pm not in pm_names:
            pm_names.append(r.pm)
    if pm_names:
        try:
            from services.oa.enhance.pm.assigner import assigner_for
            decided = []
            for nm in pm_names:
                who = assigner_for(nm)
                if who and who not in decided:
                    decided.append(who)
            if len(decided) == 1:
                assigner = decided[0]
            elif decided:
                assigner = decided[0]
                assigner_note = "（参考项目 PM 分属多部门：%s，暂取首个；请人工确认）" % "、".join(decided)
        except Exception as e:  # noqa: BLE001 - 分流失败不阻断，回退 C1
            assigner = ""
            assigner_note = "（部门分流不可用，已回退 C1：%s）" % e

    remark = render_remark(order, refs, risks, args.pm or "", assigner=assigner)
    if assigner_note:
        print("  ⚠️", assigner_note)
    print()
    print(remark)
    print()
    print("参考项目:", len(refs), "｜风险:", len(risks),
          "｜指派人:", assigner or "（C1 口径）",
          "｜757:", (appr.degraded if appr and appr.degraded else ("已核查" if appr else "不适用/无链接")))

    if args.out:
        out_md = render_markdown(order, refs, risks, appr, args.pm or "",
                                 missing=notes, assigner=assigner)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(out_md)
        print("报告:", args.out)
    return 0


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

    p_fetch = sub.add_parser("oa-fetch", help="按合同编号拉取 OA 合同原文/附件")
    p_fetch.add_argument("contract_no", help="合同编号（如 XSZS2609020659）")
    p_fetch.add_argument("--heal", action="store_true",
                         help="会话失效时自动重建（耗一次 IMAP 验证码）")
    p_fetch.set_defaults(func=cmd_oa_fetch)

    p_enh = sub.add_parser("oa-enhance", help="OA 销售合同审查增强（只读：履约义务+概算）")
    p_enh.add_argument("--requestid", required=True, help="OA requestid（如 886377）")
    p_enh.add_argument("--raw-dir", required=True, help="oa_workflow_ones.py --capture 的 raw 根")
    p_enh.add_argument("--storage-state", default=None, help="Playwright storage_state（可空）")
    p_enh.add_argument("--project-codes", nargs="*", default=None, help="SSXM 编码（可空，空则 BDMS 定位）")
    p_enh.set_defaults(func=cmd_oa_enhance)

    p_appr = sub.add_parser(
        "oa-approval",
        help="OA 销售合同审批：触发词「处理OA销售合同审批」（发现757待办→核查→标准审批备注，只读）",
    )
    p_appr.add_argument("--raw-dir", default="tmp/oa-pif/raw",
                        help="oa_workflow_ones.py --capture 的 raw 根（默认 tmp/oa-pif/raw）")
    p_appr.add_argument("--out-dir", default=None, help="备注输出目录（默认 raw 根同级 oa-approval）")
    p_appr.add_argument("--requestid", nargs="*", default=None,
                        help="显式指定 requestid（给定则 --no-discover）")
    p_appr.add_argument("--contract-file", default=None,
                        help="合同原文（docx/pdf/txt，可选；缺失则 L2 核查转人工）")
    p_appr.add_argument("--storage-state", default=None, help="Playwright storage_state（可空）")
    p_appr.add_argument("--no-discover", action="store_true", help="跳过待办发现，仅处理 --requestid")
    p_appr.set_defaults(func=cmd_oa_approval)

    p_pm = sub.add_parser(
        "oa-project-mgmt",
        help="OA 项目实施管理「分配项目经理」批注建议（只读：916/815/820 → ONES 参考项目 + 三段式批注）",
    )
    p_pm.add_argument("--requestid", required=True, help="OA requestid（如 886453）")
    p_pm.add_argument("--workflow", required=True, choices=["wf_916", "wf_815", "wf_820"],
                      help="流程（916 销售合同下单 / 815 提前实施 / 820 PoC）")
    p_pm.add_argument("--title", default="", help="OA 单据标题（可空，用于语义标注）")
    p_pm.add_argument("--raw-dir", default="tmp/oa-pif/raw",
                      help="oa_workflow_ones.py --capture 的 raw 根（默认 tmp/oa-pif/raw）")
    p_pm.add_argument("--pm", default="", help="指定 PM 姓名（可空，空则用 OA 字段/待分配）")
    p_pm.add_argument("--out", default=None, help="Markdown 报告输出路径（可空）")
    p_pm.set_defaults(func=cmd_oa_project_mgmt)

    p_clauses = sub.add_parser(
        "clauses",
        help="条款拆解（L3 contract_parser）：类别/法条/摘要/原文/问题/建议 + 必备条款缺失",
    )
    p_clauses.add_argument("--file", required=True, help="合同原文（docx/pdf/txt）")
    p_clauses.add_argument("--out", default=None, help="JSON 输出路径（可空）")
    p_clauses.set_defaults(func=cmd_clauses)

    p_hd = sub.add_parser(
        "history-delivery",
        help="历史签约项目/合同交付问题盘点（BDMS 快照，只读；异常项目/应交未交/应验未验/验收异常）",
    )
    p_hd.add_argument("--contract-no", default="", help="合同编号（XSZS…，优先）")
    p_hd.add_argument("--end-user", default="", help="最终用户名称（合同编号缺失时兜底）")
    p_hd.add_argument("--out", default=None, help="JSON 输出路径（可空）")
    p_hd.set_defaults(func=cmd_history_delivery)

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
