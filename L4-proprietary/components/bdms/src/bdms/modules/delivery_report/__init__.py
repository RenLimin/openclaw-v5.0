# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""BDMS 交付月报模块（Delivery Report Module）。

模块编码: delivery_report
层级: L4 BDMS 核心域模块 #3
引擎: DeliveryReportEngine（复用 delivery-center v2 计算）
服务: DeliveryReportService（三模式幂等编排 + 分步校验）
校验: DeliveryReportValidator（12 条规则 + 存疑数据 + 人工调整）
导出: DeliveryReportExporter（15 Sheet）
图例: seed_legend（黄金基准 Sheet-15 预落盘）

对齐 DESIGN-DETAIL-DELIVERY-REPORT-v2.1.md。
"""
from .engine import DeliveryReportEngine
from .service import DeliveryReportService
from .validator import DeliveryReportValidator
from .exporter import DeliveryReportExporter

__all__ = [
    "DeliveryReportEngine",
    "DeliveryReportService",
    "DeliveryReportValidator",
    "DeliveryReportExporter",
]
