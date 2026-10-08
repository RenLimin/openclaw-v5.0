"""同步调度器 — 管理 cron 和 event 两种模式的同步触发。

对齐 DESIGN-DETAIL-INTEGRATION-v2.1.md §7 频率配置设计。
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime
from typing import Optional

from bdms.core.db import get_connection

logger = logging.getLogger(__name__)


class SyncScheduler:
    """同步调度器。

    支持两种调度模式：
    1. cron — 定时任务，按 cron 表达式周期执行
    2. event — 事件驱动，监听业务事件触发同步

    使用 threading 实现后台调度，不依赖外部调度框架。
    """

    def __init__(self, service=None):
        """
        Args:
            service: IntegrationService 实例（可选，延迟注入）
        """
        self._service = service
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._event_handlers: dict[str, list[str]] = {}  # event_name -> [connector_name]
        self._cron_configs: dict[str, dict] = {}  # connector_name -> cron_config

    def set_service(self, service) -> None:
        """设置集成服务实例。"""
        self._service = service

    def load_configs(self) -> None:
        """从 DB 加载所有频率配置。"""
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM int_frequency_config WHERE enabled=1"
            ).fetchall()

            for row in rows:
                connector = row["connector_name"]
                schedule = row["schedule"]

                if schedule == "cron" and row["cron_expr"]:
                    self._cron_configs[connector] = {
                        "cron_expr": row["cron_expr"],
                        "last_triggered": row.get("last_triggered_at"),
                    }
                    logger.info(f"加载 cron 配置: {connector} = {row['cron_expr']}")

                elif schedule == "event" and row["event_triggers"]:
                    triggers = json.loads(row["event_triggers"])
                    for event_name in triggers:
                        self._event_handlers.setdefault(event_name, []).append(connector)
                    logger.info(f"加载 event 配置: {connector} triggers={triggers}")

        finally:
            conn.close()

    def handle_event(self, event_name: str, event_data: dict = None) -> None:
        """处理业务事件，触发相关连接器同步。

        Args:
            event_name: 事件名称
            event_data: 事件数据
        """
        connectors = self._event_handlers.get(event_name, [])
        for connector in connectors:
            logger.info(f"事件触发同步: {event_name} -> {connector}")
            self._run_sync(connector, event_data)

    def _run_sync(self, connector_name: str, params: dict = None) -> None:
        """执行同步并更新 last_triggered_at。"""
        if not self._service:
            logger.error("IntegrationService 未注入，无法执行同步")
            return

        try:
            sync_params = params or {}
            result = self._service.sync(connector_name, **sync_params)
            self._update_last_triggered(connector_name)
            logger.info(f"调度同步完成: {connector_name} = {result.get('status')}")
        except Exception as e:
            logger.error(f"调度同步失败: {connector_name}: {e}")

    def _update_last_triggered(self, connector_name: str) -> None:
        """更新 last_triggered_at 时间戳。"""
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE int_frequency_config SET last_triggered_at=? WHERE connector_name=?",
                (datetime.now().isoformat(), connector_name),
            )
            conn.commit()
        except Exception as e:
            logger.warning(f"更新 last_triggered_at 失败: {e}")
        finally:
            conn.close()

    def _parse_cron_expr(self, cron_expr: str) -> dict:
        """解析 cron 表达式（简化版，支持标准 5 位）。

        支持格式：minute hour day month weekday
        示例：0 2 * * * = 每天 02:00
        """
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            logger.warning(f"不支持的 cron 格式: {cron_expr}")
            return {}
        return {
            "minute": parts[0],
            "hour": parts[1],
            "day": parts[2],
            "month": parts[3],
            "weekday": parts[4],
        }

    def _should_run_cron(self, cron_config: dict) -> bool:
        """判断 cron 任务是否应该执行。"""
        import calendar
        from datetime import datetime

        parsed = self._parse_cron_expr(cron_config["cron_expr"])
        if not parsed:
            return False

        now = datetime.now()

        # 检查分钟
        if parsed["minute"] != "*" and int(parsed["minute"]) != now.minute:
            return False

        # 检查小时
        if parsed["hour"] != "*" and int(parsed["hour"]) != now.hour:
            return False

        # 检查日期
        if parsed["day"] != "*" and int(parsed["day"]) != now.day:
            return False

        # 检查月份
        if parsed["month"] != "*" and int(parsed["month"]) != now.month:
            return False

        # 检查星期（0=周日）
        if parsed["weekday"] != "*":
            weekday = now.weekday() + 1  # Python: 0=Mon, cron: 0=Sun
            if int(parsed["weekday"]) != weekday % 7:
                return False

        # 检查是否已经执行过（同一分钟内不重复执行）
        last = cron_config.get("last_triggered")
        if last:
            last_dt = datetime.fromisoformat(last)
            if (now - last_dt).total_seconds() < 60:
                return False

        return True

    def run_pending(self) -> None:
        """执行所有到期的 cron 任务。

        应在主循环中定期调用（如每分钟）。
        """
        for connector, config in self._cron_configs.items():
            if self._should_run_cron(config):
                logger.info(f"cron 触发: {connector}")
                self._run_sync(connector)

    def start_background(self, interval: int = 60) -> None:
        """启动后台调度线程。

        Args:
            interval: 检查间隔（秒）
        """
        if self._running:
            logger.warning("调度器已在运行")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._scheduler_loop, args=(interval,), daemon=True
        )
        self._thread.start()
        logger.info(f"调度器已启动，检查间隔 {interval}s")

    def stop_background(self) -> None:
        """停止后台调度线程。"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            logger.info("调度器已停止")

    def _scheduler_loop(self, interval: int) -> None:
        """调度器主循环。"""
        while self._running:
            try:
                self.run_pending()
            except Exception as e:
                logger.error(f"调度循环异常: {e}")
            time.sleep(interval)

    def get_status(self) -> dict:
        """获取调度器状态。"""
        return {
            "running": self._running,
            "cron_count": len(self._cron_configs),
            "event_count": len(self._event_handlers),
            "cron_configs": {
                name: config["cron_expr"]
                for name, config in self._cron_configs.items()
            },
            "event_handlers": {
                event: connectors
                for event, connectors in self._event_handlers.items()
            },
        }
