# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""BDMS 项目利润管理模块（Profit Management）。

模块编码: profit_management
层级: L4 BDMS 核心域（v2.1 全新模块）
引擎: ProfitEngine（利润计算 + 预算告警 + 聚合）
服务: ProfitService（工时 + 差旅导入 + 报表）

成本数据走 pf_* 新表（v2.1 成本迁移后口径）。
对齐 DESIGN-DETAIL-PROFIT-MANAGEMENT-v2.1.md。
"""
from .engine import ProfitEngine
from .service import ProfitService

__all__ = ["ProfitEngine", "ProfitService"]
