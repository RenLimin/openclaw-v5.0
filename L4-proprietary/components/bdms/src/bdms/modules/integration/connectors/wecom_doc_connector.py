"""I-04: 企微文档连接器 — API → 浏览器 → 本机导入三级降级。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import BaseConnector, ConnectorRegistry
from .local_import_connector import LocalImportConnector


@ConnectorRegistry.register
class WecomDocConnector(BaseConnector):
    """I-04: 企微文档连接器 — API → 浏览器 → 本机导入三级降级。"""

    name = "wecom_doc"
    data_source = "企业微信文档"
    target_modules = ["delivery_report", "revenue"]
    auth_type = "api_token"
    default_frequency = "manual"

    FALLBACK_CHAIN = ["api", "browser", "local_file"]

    def authenticate(self) -> bool:
        return True  # 总是可用（走降级链）

    def fetch(self, doc_type: str = "", date_range: str = "",
              file_path: str = "", **params) -> List[Dict[str, Any]]:
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

    def normalize(self, raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """企微文档数据 → 标准字段格式。"""
        normalized = []
        for row in raw:
            # 确收凭证数据映射到 revenue 模块
            record = {
                "source_id": row.get("doc_id", row.get("id", "")),
                "source_data": row,
                "normalized_data": {
                    "voucher_id": row.get("voucher_id"),
                    "contract_no": row.get("contract_no"),
                    "amount": row.get("amount"),
                    "acceptance_date": row.get("acceptance_date"),
                    "status": row.get("status"),
                },
                "target_module": "revenue",
                "target_table": "rr_sheet_row",
            }
            normalized.append(record)
        return normalized
