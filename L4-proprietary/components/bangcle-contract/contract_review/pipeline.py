"""ReviewService：串 5 阶段 + 持久化（编排核心，L4 只编排不算规则）。

2026-11-05 从 sandbox MVP 合并，适配主仓库已交付的 contract_review 真实 API：
- ingest.ingest_file → digitize.digitize → parser.parse_shallow → risk.run_risk → kb_match.run_kb_match
- repository.db.Repository（主仓库持久化契约）
- extract_items.extract_line_items（sandbox 新增能力：行项目抽取）
- report.build_markdown / build_excel（主仓库报告渲染）

与主仓库 CLI `contractctl review` 的关系：
- CLI 是"单文件审查"入口（含 OA 拉取 + 报告落盘）；
- 本模块是"可编程编排"入口（供测试/批量/其他调用方复用同一套 5 阶段）。
两者共享同一批 contract_review 模块，不重复实现规则。
"""
import os
import uuid
from datetime import datetime

from repository.db import Repository
from . import ingest as ing
from . import digitize as dig
from . import parser as par
from . import extract_items as ext
from . import risk as rsk
from . import kb_match as kbm
from . import report as rep
from . import clause_extract as cex
from . import risk_points as rpt
from .models import ReviewReport


class ReviewService:
    def __init__(self, db_path: str = None):
        self.repo = Repository(db_path)

    def review_file(self, path: str, out_dir: str = None,
                    formats=("md", "xlsx"), contract_ref: str = None) -> ReviewReport:
        review_id = str(uuid.uuid4())
        created_at = datetime.now().isoformat(timespec="seconds")
        self.repo.append_audit_log(
            action="review_start", operator="pipeline",
            detail='{"path": "%s"}' % path.replace('"', '\\"'),
        )

        # 1 获取（主仓库 API：ingest_file → IngestedFile）
        ingested = ing.ingest_file(path)
        contract_ref = contract_ref or ingested.original_name
        self.repo.append_audit_log(
            action="ingested", operator="pipeline",
            detail='{"file_type": "%s"}' % ingested.file_type,
        )

        # 2 数字化（主仓库 API：digitize → DigitizedText）
        digitized = dig.digitize(ingested.local_path)
        if not digitized.full_text.strip():
            self.repo.append_audit_log(
                action="digitize_empty", operator="pipeline", detail="空文本，继续标记",
            )
        self.repo.append_audit_log(
            action="digitized", operator="pipeline",
            detail='{"method": "%s"}' % digitized.method,
        )

        # 3 浅解析（主仓库 API：parse_shallow → ShallowParseResult）
        parsed = par.parse_shallow(digitized.full_text)

        # 4 行项目抽取（L4 新增能力）
        line_items = ext.extract_line_items(digitized.full_text, parsed)
        no_line_items = len(line_items) == 0
        self.repo.append_audit_log(
            action="items_extracted", operator="pipeline",
            detail="count=%d" % len(line_items),
        )

        # 5 风险扫描（主仓库 API：run_risk → dict）
        risk = rsk.run_risk(digitized)
        self.repo.append_audit_log(
            action="risk_scanned", operator="pipeline",
            detail=risk.get("overall_risk", "unknown"),
        )

        # 6 知识库参照
        #    主仓库 run_kb_match 内部走 items_from_text（依赖浅解析 items），
        #    对「1. … 2. …」枚举清单召回弱；extract_items 补此缺口（sandbox 新增能力）。
        #    故此处：extract_items 抽行项目 → kb_match 公开 API 匹配 + 判定。
        try:
            matcher = kbm.load_matcher()
            contract_items = [
                kbm.ContractItem(name=i.raw_name, model=i.model, price=i.price)
                for i in line_items
            ]
            kb_results = kbm.match_items(matcher, contract_items)
            satisfaction = kbm.decide_satisfaction(kb_results)
            kb = kbm.KbReview(satisfaction=satisfaction, referenced=True,
                              items=kb_results)
        except kbm.KbMatchError:
            # db 不可达：不抛异常、不中断（与主仓库 run_kb_match 语义一致）
            kb = kbm.KbReview(satisfaction="unsatisfied", referenced=False)
        self.repo.append_audit_log(
            action="kb_matched", operator="pipeline", detail=satisfaction,
        )

        # 6b 条款拆解（L3 contract_parser，Rex 2026-11-24 需求）
        clause_data: Dict[str, Any] = {"clauses": [], "missing_required": [],
                                       "unsupported_categories": [], "stats": {}}
        try:
            clause_data = cex.extract_clauses(digitized.full_text)
            self.repo.append_audit_log(
                action="clauses_extracted", operator="pipeline",
                detail="extracted=%d missing_required=%d" % (
                    clause_data["stats"].get("extracted", 0),
                    clause_data["stats"].get("missing_required", 0)),
            )
        except cex.ClauseExtractError as exc:
            self.repo.append_audit_log(
                action="clause_extract_failed", operator="pipeline", detail=str(exc),
            )

        # 6c 风险点视图（L3 规则 + 条款缺失合并，主视角）
        rp_data: Dict[str, Any] = {"points": [], "summary": {},
                                   "overall_risk": "unknown", "degraded": []}
        try:
            rp_data = rpt.build_risk_points(digitized)
            self.repo.append_audit_log(
                action="risk_points_built", operator="pipeline",
                detail="points=%d overall=%s" % (
                    len(rp_data.get("points", [])), rp_data.get("overall_risk")),
            )
        except Exception as exc:  # noqa: BLE001
            self.repo.append_audit_log(
                action="risk_points_failed", operator="pipeline", detail=str(exc),
            )

        clauses_section = _render_clauses_section(clause_data)
        risk_points_section = _render_risk_points_section(rp_data)

        report = ReviewReport(
            review_id=review_id,
            loaded=ingested,
            digitized=digitized,
            clauses=[],
            party_a=parsed.party_a or {},
            party_b=parsed.party_b or {},
            risk=risk,
            matches=kb.items,
            no_line_items=no_line_items,
            satisfaction=satisfaction,
            clauses=clause_data.get("clauses", []),
            risk_points=rp_data,
            created_at=created_at,
            clauses_section=clauses_section,
            risk_points_section=risk_points_section,
        )

        # 7 渲染（主仓库 API：build_markdown / build_excel）
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            base = os.path.join(out_dir, "review_%s" % review_id[:8])
            if "md" in formats:
                md_path = base + ".md"
                rep.write_markdown(
                    contract_ref=contract_ref, source=ingested.source,
                    risk=risk, kb=kb, out_path=md_path,
                    ocr_method=digitized.method,
                    ocr_confidence=digitized.ocr_confidence,
                    clauses_section=clauses_section,
                    risk_points_section=risk_points_section,
                )
                report.report_md_path = md_path
            if "xlsx" in formats:
                xlsx_path = base + ".xlsx"
                rep.build_excel(
                    contract_ref=contract_ref, source=ingested.source,
                    risk=risk, kb=kb, out_path=xlsx_path,
                )
                report.report_xlsx_path = xlsx_path
            report_path = report.report_md_path or report.report_xlsx_path or ""
        else:
            report_path = ""

        # 8 持久化（主仓库 Repository 契约）
        rid = self.repo.add_review(
            contract_ref=contract_ref, source=ingested.source,
            overall_risk=risk.get("overall_risk", "unknown"),
            satisfaction=satisfaction, report_path=report_path,
            rule_set_version=risk.get("rule_set_version"),
        )
        report.repo_review_id = rid
        for r in kb.items:
            self.repo.add_kb_match(
                review_id=rid, input_name=r.input_name,
                matched_product=r.product, matched_sku=r.sku,
                score=r.score, alert=r.alert,
            )
        self.repo.append_audit_log(
            action="review_done", operator="pipeline", review_id=rid,
            detail='{"satisfaction": "%s"}' % satisfaction,
        )
        return report

    def close(self):
        self.repo.close()



def _render_clauses_section(clause_data: Dict[str, Any]) -> str:
    """条款拆解章节（Markdown）。"""
    stats = clause_data.get("stats") or {}
    lines = [
        "## 条款拆解",
        "",
        "抽取条款类别：%d / %d（必备 %d，缺失 %d）；未实现提取器的类别 %d 个不参与缺失判定。"
        % (stats.get("extracted", 0), stats.get("categories_total", 0),
           stats.get("required_total", 0), stats.get("missing_required", 0),
           len(clause_data.get("unsupported_categories") or [])),
        "",
        rep._clauses_table_md(clause_data.get("clauses") or []),
    ]
    missing = clause_data.get("missing_required") or []
    if missing:
        lines += ["必备条款缺失："]
        for i, m in enumerate(missing, 1):
            lines.append("%d. %s（%s）— %s" % (i, m.get("category"), m.get("law", "-"),
                                              m.get("description", "")))
    return "\n".join(lines)


def _render_risk_points_section(rp_data: Dict[str, Any]) -> str:
    """风险点章节（Markdown，主视角）。"""
    summary = rp_data.get("summary") or {}
    degraded = rp_data.get("degraded") or []
    lines = [
        "## 风险点",
        "",
        "综合：**%s**　风险点 %d 条（high %d / medium %d / low %d；缺失条款 %d）"
        % (rp_data.get("overall_risk", "未知"), len(rp_data.get("points") or []),
           summary.get("high", 0), summary.get("medium", 0),
           summary.get("low", 0), summary.get("missing", 0)),
        "",
        rep._risk_points_table_md(rp_data.get("points") or []),
        "> 证据为原文片段；法条依据仅来自 L3 受控库。低置信/漏抽需人工复核。",
    ]
    if degraded:
        lines += ["", "> ⚠️ 降级：" + "；".join(str(d) for d in degraded)]
    return "\n".join(lines)
