"""ArtifactSet → bangcle-ppt 引擎（既有 L4 组件）的薄适配层。

不重写 PPT 引擎/模板；只把六类产物映射为 bangcle-ppt DSL，再调其
TemplateEngine.render_from_spec 产出符合 Bangcle VI 的 .pptx。
"""
from __future__ import annotations
import sys
from pathlib import Path

from .models import ArtifactSet

# 定位同级 bangcle-ppt 组件 src
COMPONENTS = Path(__file__).resolve().parents[2]
PPT_SRC = COMPONENTS / "bangcle-ppt" / "src"


def _short_party(name: str) -> str:
    n = (name or "").replace("中国建设银行股份有限公司", "")
    return n or "总行"


def _kpi_intro(art: ArtifactSet) -> list[dict]:
    net = round(sum(c.amount for c in art.contractRegister), 2)
    arch_amount = round(sum(
        n.amount for t in art.paymentTracker for n in t.paymentPlan
        if n.status.value == "paid"), 2)
    outstanding = round(sum(t.receivables.outstanding for t in art.paymentTracker), 2)
    return [
        {"value": str(len(art.contractRegister)), "label": "合同数", "suffix": "份"},
        {"value": f"{net:,.0f}", "label": "签约净额", "suffix": "元"},
        {"value": f"{arch_amount:,.0f}", "label": "已验收回款", "suffix": "元"},
        {"value": f"{outstanding:,.0f}", "label": "应收未收", "suffix": "元"},
    ]


def build_spec(art: ArtifactSet, customer: str, date_label: str) -> dict:
    def slide(page_type, name, data, theme="light"):
        return {"meta": {"name": name, "page_type": page_type, "theme": theme},
                "layout": {}, "data": data}

    slides = []
    # 1 封面
    slides.append(slide("cover-light", "封面", {
        "title": f"{customer}\n项目交付汇报",
        "subtitle": "CUSTOMER DELIVERY REPORT",
        "presenter": "北京梆梆安全科技有限公司",
        "company": "Bangcle Security", "date": date_label,
        "slogan": "稳如泰山 · 值得托付"}))
    # 2 目录
    slides.append(slide("toc-light", "目录", {"items": [
        {"number": "01", "title": "项目总览", "subtitle": "OVERVIEW"},
        {"number": "02", "title": "签约项目", "subtitle": "CONTRACTS"},
        {"number": "03", "title": "履约与验收", "subtitle": "DELIVERY"},
        {"number": "04", "title": "回款跟踪", "subtitle": "PAYMENT"}]}))
    # 3 章节1
    slides.append(slide("section-light", "第一章", {
        "part_label": "PART ONE", "chapter_number": "01",
        "title": "项目总览", "subtitle": "OVERVIEW"}))
    # 4 KPI
    slides.append(slide("kpi-cards-light", "关键指标", {
        "title": "关键指标总览", "cards": _kpi_intro(art)}))
    # 5 章节2
    slides.append(slide("section-light", "第二章", {
        "part_label": "PART TWO", "chapter_number": "02",
        "title": "签约项目", "subtitle": "CONTRACTS"}))
    # 6 项目明细表（分页，每页 <=8 行数据）
    header = ["合同号", "客户/分行", "金额(元)", "服务期", "验收", "回款"]
    body = []
    for p in art.projectRegister:
        body.append([
            p.contractNo, _short_party(p.customer), f"{p.contractAmount:,.0f}",
            f"{p.startDate or '—'}~{p.endDate or '—'}",
            p.acceptanceStatus.value, p.paymentStatus.value])
    rows_per = 8
    chunks = [body[i:i+rows_per] or [[]] for i in range(0, len(body), rows_per)]
    for i, ch in enumerate(chunks):
        slides.append(slide("table-light", f"签约项目明细 {i+1}", {
            "title": "签约项目明细", "has_header": True,
            "table_data": [header] + ch}))
    # 7 章节3
    slides.append(slide("section-light", "第三章", {
        "part_label": "PART THREE", "chapter_number": "03",
        "title": "履约与验收", "subtitle": "DELIVERY"}))
    # 8 履约义务表
    po_header = ["合同号", "义务", "分摊金额", "已确认", "剩余"]
    po_body = [[o.contractNo, (o.description or "")[:18],
                f"{o.allocatedPrice:,.0f}", f"{o.recognizedAmount:,.0f}",
                f"{o.remainingAmount:,.0f}"] for o in art.performanceObligation]
    for i in range(0, len(po_body), rows_per):
        slides.append(slide("table-light", "履约义务", {
            "title": "履约义务与收入确认", "has_header": True,
            "table_data": [po_header] + po_body[i:i+rows_per]}))
    # 9 章节4
    slides.append(slide("section-light", "第四章", {
        "part_label": "PART FOUR", "chapter_number": "04",
        "title": "回款跟踪", "subtitle": "PAYMENT"}))
    # 10 回款明细
    pay_header = ["合同号", "应收(元)", "已收(元)", "未收(元)", "状态"]
    pay_body = []
    for t in art.paymentTracker:
        st = t.paymentPlan[0].status.value if t.paymentPlan else "—"
        pay_body.append([t.contractNo, f"{t.receivables.totalReceivable:,.0f}",
                         f"{t.receivables.received:,.0f}",
                         f"{t.receivables.outstanding:,.0f}", st])
    for i in range(0, len(pay_body), rows_per):
        slides.append(slide("table-light", "回款明细", {
            "title": "回款跟踪明细", "has_header": True,
            "table_data": [pay_header] + pay_body[i:i+rows_per]}))
    # 11 结束
    slides.append(slide("closing-light", "结束", {
        "main_text": "谢谢观看", "subtitle": "THANK YOU",
        "slogan": "稳如泰山 · 值得托付"}))
    return {"title": f"{customer} 项目交付汇报", "theme": "light", "slides": slides}


def render_pptx(art: ArtifactSet, customer: str, out_path: str,
                date_label: str) -> str:
    if str(PPT_SRC) not in sys.path:
        sys.path.insert(0, str(PPT_SRC))
    from bangcle_ppt import TemplateEngine, REGISTRY  # 既有引擎
    spec_dict = build_spec(art, customer, date_label)
    from bangcle_ppt.dsl.schema import PresentationSpec
    spec = PresentationSpec(**spec_dict)
    templates_dir = str(PPT_SRC / "bangcle_ppt" / "templates")
    engine = TemplateEngine(templates_dir=templates_dir, theme="light")
    engine.register_renderers(REGISTRY)
    return engine.render_from_spec(spec, out_path)
