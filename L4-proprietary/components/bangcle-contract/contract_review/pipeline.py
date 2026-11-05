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
            created_at=created_at,
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
