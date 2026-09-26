# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""I-05: 本机导入连接器 — Excel/CSV 解析 + 字段映射。

对齐 DESIGN-DETAIL-INTEGRATION-v2.1.md §6.5。
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from bdms.core.db import get_connection
from .base import BaseConnector, ConnectorRegistry


@ConnectorRegistry.register
class LocalImportConnector(BaseConnector):
    """本机导入连接器：Excel/CSV → 暂存表 → 业务表。"""

    name = "local_import"
    data_source = "本机文件（Excel/CSV）"
    target_modules = ["delivery_report", "revenue", "project_management"]
    auth_type = "none"
    default_frequency = "manual"

    def authenticate(self) -> bool:
        return True  # 本机文件无需认证

    def fetch(self, file_path: str = "", **params) -> List[Dict[str, Any]]:
        """读取文件 → 原始行列表。"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        if path.suffix.lower() == ".csv":
            df = pd.read_csv(path, dtype=str).fillna("")
        elif path.suffix.lower() in (".xlsx", ".xls"):
            df = pd.read_excel(path, dtype=str).fillna("")
        else:
            raise ValueError(f"不支持的格式: {path.suffix}（支持 csv/xlsx/xls）")

        items = []
        for i, row in df.iterrows():
            items.append({
                "source_id": f"row_{i}",
                "data": {k: str(v) for k, v in row.items()},
            })
        return items

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """标准化：应用字段映射（int_field_mapping 配置）。"""
        data = raw.get("data", raw)
        mapping = self._load_mapping()
        if not mapping:
            return data  # 无映射配置，原样返回

        normalized = {}
        for source_field, target_field in mapping.items():
            if source_field in data:
                normalized[target_field] = data[source_field]
        # 未映射的字段保留原名
        for k, v in data.items():
            if k not in mapping:
                normalized.setdefault(k, v)
        return normalized

    def validate(self, normalized: Dict[str, Any]) -> List[str]:
        """校验：映射的必填字段非空。"""
        errors = []
        for field, required in self._required_fields().items():
            if required and not str(normalized.get(field, "")).strip():
                errors.append(f"必填字段为空: {field}")
        return errors

    # ─── 内部 ───

    def _load_mapping(self) -> Dict[str, str]:
        """加载字段映射配置。"""
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT source_field, target_field FROM int_field_mapping "
                "WHERE connector_name = ? ORDER BY sort_order",
                (self.name,),
            ).fetchall()
            return {r["source_field"]: r["target_field"] for r in rows}
        except Exception:
            return {}
        finally:
            conn.close()

    def _required_fields(self) -> Dict[str, bool]:
        """必填字段配置。"""
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT target_field, is_required FROM int_field_mapping "
                "WHERE connector_name = ? AND is_required = 1",
                (self.name,),
            ).fetchall()
            return {r["target_field"]: bool(r["is_required"]) for r in rows}
        except Exception:
            return {}
        finally:
            conn.close()
