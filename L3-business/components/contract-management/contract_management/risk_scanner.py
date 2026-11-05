"""风险扫描快速入口 — 复用 risk_engine（对齐去重，DETAIL T2.4）。

迁移源 skills/contract-approval/scripts/risk_scanner.py 的 scan_text 与
core/risk_engine.scan_text 的 22 条规则/评级逻辑完全一致（已实证），
按"单一实现"原则不复制第二份，此处为兼容 shim：L4 既有调用方
`from risk_scanner import scan_text` 保持可用，逻辑指向 risk_engine。
"""
from .risk_engine import scan_text, scan_text_dict, CHECK_RULES, RiskRule  # noqa: F401

__all__ = ["scan_text", "scan_text_dict", "CHECK_RULES", "RiskRule"]
