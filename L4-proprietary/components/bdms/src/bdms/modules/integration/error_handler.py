"""错误处理模块 — 指数退避重试 + 死信队列 + 告警管理。

对齐 DESIGN-DETAIL-INTEGRATION-v2.1.md §9 错误处理与重试机制。
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from bdms.core.db import get_connection

logger = logging.getLogger(__name__)


class RetryHandler:
    """指数退避重试处理器。

    重试间隔：base_delay * (exponential_base ^ retry_count)
    例：1s → 2s → 4s → 8s → ...（不超过 max_delay）
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base

    def execute(self, func: Callable, *args, **kwargs):
        """执行函数，失败时指数退避重试。"""
        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = min(
                        self.base_delay * (self.exponential_base ** attempt),
                        self.max_delay,
                    )
                    logger.warning(
                        f"重试 {attempt + 1}/{self.max_retries}，"
                        f"等待 {delay:.1f}s: {e}"
                    )
                    time.sleep(delay)
                else:
                    logger.error(f"重试耗尽 ({self.max_retries} 次): {e}")
        raise last_exception


class DeadLetterQueue:
    """死信队列 — 存储无法自动处理的失败记录。"""

    def add(
        self, connector_name: str, batch_id: str,
        source_id: str, source_data: dict,
        error_msg: str, error_type: str = "system",
        target_module: str = "", target_table: str = "",
    ) -> None:
        """添加死信记录。"""
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO int_dead_letter "
                "(connector_name, batch_id, source_id, source_data, error_msg, error_type, target_module, target_table) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (connector_name, batch_id, source_id,
                 json.dumps(source_data, ensure_ascii=False, default=str),
                 error_msg, error_type, target_module, target_table),
            )
            conn.commit()
            logger.warning(f"死信记录已添加: {connector_name}/{batch_id}/{source_id}: {error_msg[:100]}")
        finally:
            conn.close()

    def list_pending(self, connector_name: str = None) -> list[dict]:
        """查询待处理的死信记录。"""
        conn = get_connection()
        try:
            sql = "SELECT * FROM int_dead_letter WHERE status='pending'"
            params = []
            if connector_name:
                sql += " AND connector_name=?"
                params.append(connector_name)
            sql += " ORDER BY created_at DESC"
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def resolve(self, dead_letter_id: int, resolved_by: str) -> None:
        """标记死信记录为已解决。"""
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE int_dead_letter SET status='resolved', "
                "resolved_at=datetime('now','localtime'), resolved_by=? WHERE id=?",
                (resolved_by, dead_letter_id),
            )
            conn.commit()
        finally:
            conn.close()

    def retry(self, dead_letter_id: int) -> None:
        """重试死信记录（重新加入暂存表）。"""
        conn = get_connection()
        try:
            record = conn.execute(
                "SELECT * FROM int_dead_letter WHERE id=?", (dead_letter_id,)
            ).fetchone()
            if not record:
                raise ValueError(f"死信记录不存在: {dead_letter_id}")

            # 重新加入暂存表
            conn.execute(
                "INSERT OR REPLACE INTO int_staging "
                "(connector_name, batch_id, source_id, status, source_data, normalized_data, target_module, target_table) "
                "VALUES (?, ?, ?, 'pending', ?, ?, ?, ?)",
                (record["connector_name"], record["batch_id"], record["source_id"],
                 record["source_data"], record.get("normalized_data", "{}"),
                 record.get("target_module", ""), record.get("target_table", "")),
            )

            # 更新死信状态
            conn.execute(
                "UPDATE int_dead_letter SET status='retrying', retry_count=retry_count+1 WHERE id=?",
                (dead_letter_id,),
            )
            conn.commit()
        finally:
            conn.close()

    def get_count(self, connector_name: str = None) -> int:
        """获取待处理死信数量。"""
        conn = get_connection()
        try:
            sql = "SELECT COUNT(*) FROM int_dead_letter WHERE status='pending'"
            params = []
            if connector_name:
                sql += " AND connector_name=?"
                params.append(connector_name)
            row = conn.execute(sql, params).fetchone()
            return row[0] if row else 0
        finally:
            conn.close()


class AlertManager:
    """告警管理器。"""

    def __init__(self):
        self._logger = logging.getLogger("integration.alert")

    def alert_sync_failed(self, connector_name: str, error: str, batch_id: str = None) -> None:
        """同步失败告警。"""
        self._logger.error(
            f"同步失败: connector={connector_name}, batch_id={batch_id}, error={error}"
        )

    def alert_auth_expired(self, connector_name: str) -> None:
        """认证过期告警。"""
        self._logger.error(f"认证过期: connector={connector_name}，请重新登录")

    def alert_dead_letter(self, connector_name: str, count: int) -> None:
        """死信队列积压告警。"""
        if count > 10:
            self._logger.warning(f"死信队列积压: connector={connector_name}, 待处理={count}")

    def alert_network_error(self, connector_name: str, error: str) -> None:
        """网络错误告警。"""
        self._logger.warning(f"网络错误: connector={connector_name}, error={error}")
