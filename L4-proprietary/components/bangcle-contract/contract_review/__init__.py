"""contract_review — Bangcle 合同 MVP 四步分析闭环（段 1：P1-P3）。

模块：
- ingest.py    获取并落本地暂存
- digitize.py  PDF/docx 直读 + L2 OCR 兜底
- parser.py    最小正则浅解析
- risk.py      调用 L3 scan_text 风险编排
"""

__version__ = "1.0.0-seg1"
