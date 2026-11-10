"""ArtifactSet → office-generation（既有 L2 组件）的薄适配层。

不重写 Word 引擎；只把六类产物映射为 WordDocument 的 heading/table/list，
产出一份对内交付说明 Word 文档（微软雅黑，符合取数机确定字体）。
"""
from __future__ import annotations
import sys
from pathlib import Path

from .models import ArtifactSet

# 定位 L2 office-generation src（本组件在 L4/.../components，需上溯到仓库根）
REPO_ROOT = Path(__file__).resolve().parents[4]
OFFICE_SRC = REPO_ROOT / "L2-infra/components/office-generation/src"


def _short_party(name: str) -> str:
    n = (name or "").replace("中国建设银行股份有限公司", "")
    return n or "总行"


def render_docx(art: ArtifactSet, customer: str, out_path: str,
                date_label: str) -> str:
    if str(OFFICE_SRC) not in sys.path:
        sys.path.insert(0, str(OFFICE_SRC))
    from office_engine.word_engine import WordDocument  # 既有引擎

    w = WordDocument()
    w.set_font_default("Microsoft YaHei", 11)

    # 封面标题
    w.add_heading(f"{customer} 项目交付说明", level=1)
    w.add_paragraph(f"北京梆梆安全科技有限公司　{date_label}")

    # 一、关键指标
    w.add_heading("一、关键指标", level=1)
    net = round(sum(c.amount for c in art.contractRegister), 2)
    paid = round(sum(n.amount for t in art.paymentTracker
                     for n in t.paymentPlan if n.status.value == "paid"), 2)
    outstanding = round(sum(t.receivables.outstanding
                           for t in art.paymentTracker), 2)
    w.add_list([
        f"合同数：{len(art.contractRegister)} 份",
        f"签约净额：{net:,.2f} 元",
        f"已验收回款：{paid:,.2f} 元",
        f"应收未收：{outstanding:,.2f} 元",
    ])

    # 二、签约项目明细
    w.add_heading("二、签约项目明细", level=1)
    header = ["合同号", "客户/分行", "金额(元)", "服务期", "验收", "回款"]
    body = [[p.contractNo, _short_party(p.customer), f"{p.contractAmount:,.0f}",
             f"{p.startDate or '—'}~{p.endDate or '—'}",
             p.acceptanceStatus.value, p.paymentStatus.value]
            for p in art.projectRegister]
    w.add_table(rows=len(body) + 1, cols=len(header), data=[header] + body)

    # 三、履约义务与收入确认
    w.add_heading("三、履约义务与收入确认", level=1)
    po_header = ["合同号", "义务", "分摊金额", "已确认", "剩余"]
    po_body = [[o.contractNo, (o.description or "")[:24],
                f"{o.allocatedPrice:,.0f}", f"{o.recognizedAmount:,.0f}",
                f"{o.remainingAmount:,.0f}"] for o in art.performanceObligation]
    w.add_table(rows=len(po_body) + 1, cols=len(po_header),
                data=[po_header] + po_body)

    # 四、验收条款摘录
    w.add_heading("四、验收条款摘录（OA 台账原文）", level=1)
    for c in art.contractRegister:
        st = c.acceptance.initialAcceptance
        if st and st.criteria:
            w.add_heading(c.contractNo, level=2)
            w.add_paragraph(st.criteria)
        else:
            w.add_paragraph(f"{c.contractNo}：台账无验收条件，待人工补充。")

    # 五、回款跟踪
    w.add_heading("五、回款跟踪", level=1)
    pay_header = ["合同号", "应收(元)", "已收(元)", "未收(元)", "状态"]
    pay_body = []
    for t in art.paymentTracker:
        stt = t.paymentPlan[0].status.value if t.paymentPlan else "—"
        pay_body.append([t.contractNo, f"{t.receivables.totalReceivable:,.0f}",
                         f"{t.receivables.received:,.0f}",
                         f"{t.receivables.outstanding:,.0f}", stt])
    w.add_table(rows=len(pay_body) + 1, cols=len(pay_header),
                data=[pay_header] + pay_body)

    p = w.save(out_path)
    w.close()
    return p
