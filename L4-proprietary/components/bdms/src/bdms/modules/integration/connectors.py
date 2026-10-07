# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""I-01~I-05 数据集成连接器。

ONES/OA 连接器：读取已导出的 CSV 文件（浏览器自动化导出后可复用）。
工时/企微：支持浏览器自动化 + 本机导入降级。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseConnector, ConnectorRegistry
from .local_import_connector import LocalImportConnector


def _browser_available() -> bool:
    """macOS osascript 可用性检查。"""
    if sys.platform != "darwin":
        return False
    try:
        subprocess.run(["osascript", "-e", 'return "ok"'],
                       capture_output=True, timeout=5)
        return True
    except Exception:
        return False


def _find_ones_csv(month: str, kind: str) -> Optional[Path]:
    """查找 ONES 导出 CSV（支持月份回退）。"""
    from bdms.core.paths import ones_dir
    base = ones_dir()
    patterns = {
        "sign": [f"{month}周报-签约项目统计.csv", "签约项目统计.csv"],
        "poc": [f"{month}周报-POC&提前实施统计.csv", "POC&提前实施统计.csv"],
        "exception": [f"{month}-签约项目异常处置.csv", "异常处置.csv"],
    }
    if kind not in patterns:
        return None
    # 先当月
    for name in patterns[kind]:
        p = base / name
        if p.exists():
            return p
    # 回退前月
    prev_month = f"{int(month) - 1:06d}"
    for name in [f"{prev_month}周报-{'签约项目统计' if kind == 'sign' else 'POC&提前实施统计'}.csv",
                 f"{prev_month}-签约项目异常处置.csv" if kind == "exception" else ""]:
        if not name:
            continue
        p = base / name
        if p.exists():
            return p
    return None


@ConnectorRegistry.register
class OnesConnector(BaseConnector):
    """I-01: ONES 连接器 — 浏览器自动化 / 导出 CSV。"""

    name = "ones"
    data_source = "ONES 项目管理"
    target_modules = ["delivery_report", "project_management"]
    auth_type = "browser_cookie"
    default_frequency = "manual"

    def authenticate(self) -> bool:
        return _browser_available()

    def fetch(self, filter_id: str = "", month: str = "", **params) -> List[Dict]:
        """获取 ONES 数据：优先读已导出 CSV，否则走浏览器自动化。"""
        import csv

        # 1. 查找已导出 CSV
        csv_path = _find_ones_csv(month, filter_id or "sign")
        if csv_path:
            try:
                with open(csv_path, newline='', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    return [{k: row.get(k, "") for k in reader.fieldnames} for row in reader]
            except Exception:
                pass

        # 2. 浏览器自动化导出（ones-browser-export 技能）
        # TODO: 通过 ones-browser-export 技能浏览器控制 ONES 导出
        # 当前依赖手动导出 CSV 到 ones_exports 目录
        return []

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """ONES CSV → 标准字段。"""
        return raw.get("data", raw)


@ConnectorRegistry.register
class OaConnector(BaseConnector):
    """I-02: OA 连接器 — 本机导出 + 浏览器自动化备选。"""

    name = "oa"
    data_source = "OA 系统"
    target_modules = ["contract_management"]
    auth_type = "browser_cookie"
    default_frequency = "manual"

    def authenticate(self) -> bool:
        return _browser_available()

    def fetch(self, contract_type: str = "", date_range: str = "",
              file_path: str = "", **params) -> List[Dict]:
        """优先读本地导出文件，否则走浏览器自动化降级。"""
        # 1. 本机导入降级
        if file_path and Path(file_path).exists():
            lc = LocalImportConnector(db_path=self.db_path)
            return lc.fetch(file_path=file_path)

        # 2. OA 导出 CSV（oa_exports 目录）
        from bdms.core.paths import ones_dir  # OA 导出通常也在同一目录
        base = ones_dir()
        for name in ["oa_contracts.csv", "合同台账.csv", "oa_export.csv"]:
            p = base / name
            if p.exists():
                try:
                    import csv
                    with open(p, newline='', encoding='utf-8-sig') as f:
                        reader = csv.DictReader(f)
                        return [{k: row.get(k, "") for k in reader.fieldnames} for row in reader]
                except Exception:
                    pass

        # 3. 浏览器自动化导出（待实现）
        return []

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return raw.get("data", raw)


@ConnectorRegistry.register
class TimesheetConnector(BaseConnector):
    """I-03: 工时门户连接器 — 浏览器自动化 / 本机导入。"""

    name = "timesheet"
    data_source = "工时填报门户"
    target_modules = ["profit_management"]
    auth_type = "browser_cookie"
    default_frequency = "monthly"

    def authenticate(self) -> bool:
        return _browser_available()

    def fetch(self, project_id: str = "", month: str = "",
              file_path: str = "", **params) -> List[Dict]:
        """获取工时数据：优先本机文件，其次浏览器自动化。"""
        # 1. 本机导入
        if file_path and Path(file_path).exists():
            lc = LocalImportConnector(db_path=self.db_path)
            return lc.fetch(file_path=file_path)

        # 2. 工时导出 Excel/CSV
        from bdms.core.paths import ones_dir
        base = ones_dir()
        for name in ["工时填报.xlsx", "工时数据.csv", "timesheet.csv"]:
            p = base / name
            if p.exists():
                try:
                    import pandas as pd
                    df = pd.read_excel(p) if p.suffix == '.xlsx' else pd.read_csv(p)
                    return df.to_dict(orient='records')
                except Exception:
                    pass

        return []

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return raw.get("data", raw)


@ConnectorRegistry.register
class WecomDocConnector(BaseConnector):
    """I-04: 企微文档连接器 — API → 浏览器 → 本机导入三级降级。"""

    name = "wecom_doc"
    data_source = "企业微信文档"
    target_modules = ["delivery_report"]
    auth_type = "api_token"
    default_frequency = "manual"

    FALLBACK_CHAIN = ["api", "browser", "local_file"]

    def authenticate(self) -> bool:
        return True  # 总是可用（走降级链）

    def fetch(self, doc_type: str = "", date_range: str = "",
              file_path: str = "", **params) -> List[Dict]:
        """三级降级获取。"""
        # 1. 本机导入（最高优先级：直接提供文件）
        if file_path and Path(file_path).exists():
            lc = LocalImportConnector(db_path=self.db_path)
            return lc.fetch(file_path=file_path)

        # 2. 企微导出 CSV（wecom_exports 目录）
        from bdms.core.paths import ones_dir
        base = ones_dir()
        for name in ["wecom_revenue.csv", "wecom_acceptance.csv", "企微导出.csv"]:
            p = base / name
            if p.exists():
                try:
                    import csv
                    with open(p, newline='', encoding='utf-8-sig') as f:
                        reader = csv.DictReader(f)
                        return [{k: row.get(k, "") for k in reader.fieldnames} for row in reader]
                except Exception:
                    pass

        # 3. 企微 API（需配置 corpId/corpSecret/agentId）
        # TODO: 对接企微开放平台 API
        return []

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return raw.get("data", raw)
