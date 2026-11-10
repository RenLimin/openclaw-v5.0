"""适配层：直接调用已建成的 delivery-center OA/ONES 自动化，不重复建设。

只负责：定位 delivery-center/src → import 既有 collector → 传参 → 归一返回。
（Rex 2026-11-10：OA/ONES 浏览器自动化已完整建成，禁止重写。）
"""
from __future__ import annotations
import sys
from pathlib import Path

# 解析 delivery-center/src：本文件在 <comp>/runner/，delivery-center 在同级 components 下
_HERE = Path(__file__).resolve()
COMPONENTS = _HERE.parents[2]                      # .../L4-proprietary/components
DELIVERY_SRC = COMPONENTS / "delivery-center" / "src"
if str(DELIVERY_SRC) not in sys.path:
    sys.path.insert(0, str(DELIVERY_SRC))


def fetch_oa_contract_ledger(month: str, export_dir: str, headless: bool = True) -> dict | None:
    """调用既有 OA 自动化：销售合同台账 XLSX。"""
    from delivery_center.v1.collectors.oa_collector import collect_contract_ledger_xlsx
    return collect_contract_ledger_xlsx(month, export_dir=export_dir, headless=headless)


def fetch_ones_filter(filter_name: str) -> str | None:
    """调用既有 ONES 自动化：导出指定筛选器 CSV（headless，自动登录）。"""
    from delivery_center.v1.collectors.ones_collector import collect
    return collect(filter_name)
