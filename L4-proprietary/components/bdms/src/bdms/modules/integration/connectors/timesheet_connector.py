"""I-03: 工时门户连接器 — Playwright 浏览器自动化。

对齐 DESIGN-DETAIL-INTEGRATION-v2.1.md §6.3 + 复用 workhour_collector.py 验证过的方案。
"""
from __future__ import annotations

import csv
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import BaseConnector, ConnectorRegistry
from .local_import_connector import LocalImportConnector
from ..adapters.browser_adapter import (
    BrowserAdapter, login_iam, ensure_logged_in, TIMESHEET_BASE, IAM_BASE,
)

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = Path.home() / ".openclaw" / "data" / "timesheet_exports"


@ConnectorRegistry.register
class TimesheetConnector(BaseConnector):
    """I-03: 工时门户连接器 — 浏览器自动化 + 本机导入降级。"""

    name = "timesheet"
    data_source = "工时门户"
    target_modules = ["profit_management"]
    auth_type = "browser_cookie"
    default_frequency = "manual"

    def authenticate(self) -> bool:
        return ensure_logged_in()

    def fetch(self, month: str = "", project_id: str = "",
              file_path: str = "", **params) -> List[Dict[str, Any]]:
        """获取工时数据。

        优先级：本机文件 > 浏览器自动化
        """
        # 1. 本机文件
        if file_path and Path(file_path).exists():
            lc = LocalImportConnector(db_path=self.db_path)
            return lc.fetch(file_path=file_path)

        # 2. 浏览器自动化
        if not self.authenticate():
            raise RuntimeError("Cookie 过期，请先调用 login_iam() 登录")

        result = self._export_via_browser(month, project_id)
        if result:
            return result

        raise RuntimeError(f"工时门户 {month} 数据不可用")

    def normalize(self, raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """化工时数据为标准格式"""
        normalized = []
        for row in raw:
            record = {
                "source_id": f"{row.get('person_id', row.get('人员ID', ''))}_{row.get('work_date', row.get('工作日期', ''))}",
                "source_data": row,
                "normalized_data": {
                    "person_id": row.get("person_id", row.get("人员ID")),
                    "work_date": row.get("work_date", row.get("工作日期")),
                    "hours": float(row.get("hours", row.get("工时", 0)) or 0),
                    "work_type": row.get("work_type", row.get("工作类型")),
                    "description": row.get("description", row.get("描述")),
                    "status": "submitted",
                },
                "target_module": "profit_management",
                "target_table": "pf_timesheet",
            }
            normalized.append(record)
        return normalized

    # ─── 内部方法 ───

    def _export_via_browser(self, month: str, project_id: str) -> Optional[List[Dict[str, Any]]]:
        """通过 Playwright 浏览器自动化导出工时数据"""
        try:
            adapter = BrowserAdapter(headless=False)
            adapter.launch()
            try:
                # Step 1: 登录 IAM
                adapter.navigate(f"{IAM_BASE}/#/login")
                adapter.fill("input[type=text]", "limin.ren")
                adapter.fill("input[type=password]", "June-123")
                adapter.click("button >> nth=1")
                adapter.wait_for_url("**/home/**")
                time.sleep(3)

                # Step 2: 点击工时门户卡片
                ts_page = adapter.oa_click_card_iam("工时", adapter._context)
                if not ts_page:
                    logger.error("无法进入工时门户")
                    return None
                adapter._page = ts_page

                # Step 3: 等待页面加载
                time.sleep(5)

                # Step 4: 提取数据（DOM 提取方式，与 workhour_collector.py 一致）
                data = self._extract_data_from_page(adapter, month, project_id)
                if data:
                    # 保存到缓存
                    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
                    output_file = DOWNLOAD_DIR / f"timesheet_{month}.json"
                    output_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                    logger.info(f"工时数据提取成功: {len(data)} 条")
                    return data

                logger.error("未提取到工时数据")
                return None
            finally:
                adapter.close()
        except Exception as e:
            logger.error(f"浏览器自动化导出失败: {e}")
            return None

    def _extract_data_from_page(self, adapter: BrowserAdapter, month: str,
                                project_id: str) -> List[Dict[str, Any]]:
        """从工时门户页面提取数据（DOM 提取方式）"""
        # 等待数据表格加载
        adapter._page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(3)

        # 尝试提取表格数据
        data = adapter.evaluate("""() => {
            const rows = document.querySelectorAll('table tbody tr, .ant-table-tbody tr');
            const result = [];
            for (const row of rows) {
                const cells = row.querySelectorAll('td');
                if (cells.length >= 4) {
                    result.push({
                        person_id: cells[0]?.textContent?.trim() || '',
                        work_date: cells[1]?.textContent?.trim() || '',
                        hours: cells[2]?.textContent?.trim() || '0',
                        work_type: cells[3]?.textContent?.trim() || '',
                        description: cells[4]?.textContent?.trim() || '',
                    });
                }
            }
            return result;
        }""")

        if data and isinstance(data, list) and len(data) > 0:
            return data

        # 备选：尝试从 API 获取
        logger.info("DOM 提取失败，尝试 API 方式")
        return self._extract_via_api(adapter, month, project_id)

    def _extract_via_api(self, adapter: BrowserAdapter, month: str,
                         project_id: str) -> List[Dict[str, Any]]:
        """通过 API 获取工时数据"""
        try:
            import requests as req_lib
            from ..adapters.browser_adapter import _load_cookies

            cookies = _load_cookies()
            cookie_str = None
            for domain in ["timesheet.bangcle.com", ".bangcle.com"]:
                if domain in cookies:
                    cookie_str = cookies[domain].get("cookie", "")
                    break

            if not cookie_str:
                return []

            session = req_lib.Session()
            for item in cookie_str.split("; "):
                if "=" in item:
                    k, v = item.split("=", 1)
                    session.cookies.set(k, v)

            session.headers.update({
                "User-Agent": "Mozilla/5.0",
                "Referer": TIMESHEET_BASE + "/",
            })

            # 尝试调用工时 API
            resp = session.get(
                f"{TIMESHEET_BASE}/api/timesheet/list",
                params={"month": month, "projectId": project_id},
                timeout=30,
            )

            if resp.status_code == 200:
                return resp.json().get("data", resp.json().get("list", []))

            return []
        except Exception as e:
            logger.error(f"API 获取工时数据失败: {e}")
            return []
