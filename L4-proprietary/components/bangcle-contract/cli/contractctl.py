"""contractctl — Bangcle 合同智能审查 CLI（DETAIL §8 / OPERATIONS §4）。

命令：
  review --file <path> [--source upload]
  review --oa-billid <billid>
  report <review_id> [--format md|xlsx]
  init-db
  oa-login

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
        import tempfile
        tmp = tempfile.mkdtemp(prefix="clm_oa_")
        data = get_contract_with_fallback(args.oa_billid, tmp)
        text = ""
        card_txt = data.get("card_text_snippet", "")
        if card_txt:
            text = card_txt
        else:
            # 结构化主字段拼成文本（无原文时的兜底）
            lines = []
            for k, v in (data.get("main_fields") or {}).items():
                lines.append("%s：%s" % (k, v))
            text = "\n".join(lines)
        contract_ref = "billid:%s" % args.oa_billid
        ocr_method = "oa_cube"
    else:
        _progress("摄取文件")
        ingested = ingest_file(args.file)
        contract_ref = ingested.original_name
        _progress("数字化")
        dt = digitize(ingested.local_path)
        text = dt.full_text
        ocr_method = dt.method
        ocr_conf = dt.ocr_confidence

    _progress("浅解析条款")
    parsed = parse_shallow(text)
    _progress("风险扫描")
    from contract_review.digitize import DigitizedText
    if isinstance(text, str):
        text = DigitizedText(full_text=text, method=ocr_method or "oa_cube")
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
