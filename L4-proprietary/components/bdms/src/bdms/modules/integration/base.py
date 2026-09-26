# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""BaseConnector — 数据集成连接器抽象基类 + 注册表。

对齐 DESIGN-DETAIL-INTEGRATION-v2.1.md §3.3（连接器插件机制）。
同步管道: authenticate → fetch → normalize → validate → load_to_staging
"""
from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from bdms.core.db import get_connection


@dataclass
class SyncResult:
    """同步结果。"""
    connector_name: str
    batch_id: str
    status: str                      # success | partial | failed
    total_fetched: int = 0
    new_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    error_count: int = 0
    errors: List[Dict] = field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "connector_name": self.connector_name,
            "batch_id": self.batch_id,
            "status": self.status,
            "total_fetched": self.total_fetched,
            "new_count": self.new_count,
            "updated_count": self.updated_count,
            "unchanged_count": self.unchanged_count,
            "error_count": self.error_count,
            "errors": self.errors[:20],
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


class BaseConnector(ABC):
    """连接器抽象基类。

    子类实现:
    - name: 连接器标识
    - data_source: 数据源描述
    - target_modules: 目标模块列表
    - authenticate(): 认证（浏览器 Cookie / API token 等）
    - fetch(): 拉取原始数据
    - normalize(): 标准化（原始 → 统一格式）
    """

    name: str = ""
    data_source: str = ""
    target_modules: List[str] = []
    auth_type: str = "none"
    default_frequency: str = "manual"

    def __init__(self, db_path=None):
        self.db_path = db_path
        self._authenticated = False

    # ─── 子类必须实现 ───

    @abstractmethod
    def authenticate(self) -> bool:
        """认证。返回是否成功。"""

    @abstractmethod
    def fetch(self, **params) -> List[Dict[str, Any]]:
        """拉取原始数据。返回 [{source_id: str, data: dict}]。"""

    @abstractmethod
    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """标准化单条数据。"""

    # ─── 通用实现（子类可覆盖）───

    @property
    def target_module(self) -> str:
        return self.target_modules[0] if self.target_modules else "unknown"

    @property
    def target_table(self) -> str:
        return "int_staging"  # 默认暂存

    def validate(self, normalized: Dict[str, Any]) -> List[str]:
        """校验标准化数据。返回错误列表（空 = 通过）。"""
        return []

    def ensure_authenticated(self) -> None:
        if not self._authenticated:
            if not self.authenticate():
                raise ConnectionError(
                    f"{self.name} 连接器认证失败（auth_type={self.auth_type}）")
            self._authenticated = True

    def load_to_staging(self, batch_id: str,
                        items: List[Dict[str, Any]]) -> Dict[str, int]:
        """写入暂存表（幂等：UNIQUE(connector, batch, source_id)）。"""
        conn = get_connection(self.db_path)
        new_count = updated = 0
        try:
            for item in items:
                source_id = str(item.get("source_id", ""))
                raw = item.get("raw", {})
                normalized = item.get("normalized", {})

                errors = self.validate(normalized)
                status = "error" if errors else "pending"
                error_msg = "; ".join(errors) if errors else None

                cur = conn.execute(
                    """INSERT INTO int_staging
                       (connector_name, batch_id, source_id, status,
                        source_data, normalized_data, target_module,
                        target_table, error_msg)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(connector_name, batch_id, source_id)
                       DO UPDATE SET
                         source_data = excluded.source_data,
                         normalized_data = excluded.normalized_data,
                         status = excluded.status,
                         error_msg = excluded.error_msg""",
                    (self.name, batch_id, source_id, status,
                     json.dumps(raw, ensure_ascii=False, default=str),
                     json.dumps(normalized, ensure_ascii=False, default=str),
                     self.target_module, self.target_table, error_msg),
                )
                if errors:
                    continue
                # ON CONFLICT DO UPDATE 无法区分 insert/update，用 changes 判断
                updated += 1
            conn.commit()
            return {"written": len(items), "errors": 0}
        finally:
            conn.close()

    # ─── 同步入口 ───

    def sync(self, **params) -> SyncResult:
        """执行完整同步管道。"""
        batch_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        started = datetime.now().isoformat()

        try:
            self.ensure_authenticated()
            raw_items = self.fetch(**params)

            items = []
            errors: List[Dict] = []
            for raw in raw_items:
                try:
                    normalized = self.normalize(raw)
                    items.append({
                        "source_id": raw.get("source_id", ""),
                        "raw": raw.get("data", raw),
                        "normalized": normalized,
                    })
                except Exception as e:
                    errors.append({"source_id": str(raw.get("source_id", "")),
                                   "error": str(e)[:200]})

            self.load_to_staging(batch_id, items)

            status = "success" if not errors else "partial"
            if not items and errors:
                status = "failed"

            return SyncResult(
                connector_name=self.name,
                batch_id=batch_id,
                status=status,
                total_fetched=len(raw_items),
                new_count=len(items),
                error_count=len(errors),
                errors=errors,
                started_at=started,
                completed_at=datetime.now().isoformat(),
            )
        except Exception as e:
            return SyncResult(
                connector_name=self.name,
                batch_id=batch_id,
                status="failed",
                errors=[{"error": str(e)[:500]}],
                started_at=started,
                completed_at=datetime.now().isoformat(),
            )


# ─── 连接器注册表 ───

class ConnectorRegistry:
    """连接器注册表（插件机制）。"""

    _connectors: Dict[str, type] = {}

    @classmethod
    def register(cls, connector_class: type) -> type:
        """注册连接器类（装饰器用法）。"""
        if not issubclass(connector_class, BaseConnector):
            raise TypeError(f"{connector_class} 不是 BaseConnector 子类")
        if not connector_class.name:
            raise ValueError(f"{connector_class} 缺少 name 属性")
        cls._connectors[connector_class.name] = connector_class
        return connector_class

    @classmethod
    def create(cls, name: str, db_path=None) -> BaseConnector:
        """实例化连接器。"""
        if name not in cls._connectors:
            raise KeyError(
                f"未注册的连接器: {name}。已注册: {list(cls._connectors)}")
        return cls._connectors[name](db_path=db_path)

    @classmethod
    def list_names(cls) -> List[str]:
        return sorted(cls._connectors.keys())

    @classmethod
    def available(cls, name: str) -> bool:
        return name in cls._connectors
