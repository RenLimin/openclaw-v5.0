"""I-01: ONES 连接器 — Playwright 统一浏览器自动化。

对齐 DESIGN-DETAIL-INTEGRATION-v2.1.md §6.1。
替代旧的 osascript 方案（ones_adapter.py → deprecated）。
"""
from __future__ import annotations

import csv
import logging
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import BaseConnector, ConnectorRegistry
from .local_import_connector import LocalImportConnector
from ..adapters.browser_adapter import (
    BrowserAdapter, login_iam, ensure_logged_in, ONES_BASE,
)

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = Path.home() / ".openclaw" / "data" / "ones_exports"

FILTERS = {
    "sign": {"label": "签约项目统计", "tab_index": 7, "output_csv": "签约项目统计.csv"},
    "poc": {"label": "POC&提前实施统计", "tab_index": 8, "output_csv": "poc_提前实施.csv"},
    "abnormal": {"label": "异常处置", "tab_index": 10, "output_csv": "异常处置.csv"},
}


@ConnectorRegistry.register
class OnesConnector(BaseConnector):
    """I-01: ONES 连接器 — 浏览器自动化 + 本机导入降级。"""

    name = "ones"
    data_source = "ONES 项目管理"
    target_modules = ["project_management", "delivery_report"]
    auth_type = "browser_cookie"
    default_frequency = "manual"

    def authenticate(self) -> bool:
        return ensure_logged_in()

    def fetch(self, filter_name: str = "sign", month: str = "",
              use_cache: bool = True, file_path: str = "",
              **params) -> List[Dict[str, Any]]:
        """获取 ONES 数据。

        优先级：本机文件 > 缓存 CSV > 浏览器自动化
        """
        # 1. 本机文件
        if file_path and Path(file_path).exists():
            lc = LocalImportConnector(db_path=self.db_path)
            return lc.fetch(file_path=file_path)

        # 2. 缓存 CSV
        if use_cache:
            csv_path = self._find_cached_csv(filter_name, month)
            if csv_path:
                logger.info(f"使用缓存: {csv_path}")
                return self._read_csv(csv_path)

        # 3. 浏览器自动化
        if not self.authenticate():
            raise RuntimeError("Cookie 过期，请先调用 login_iam() 登录")

        result = self._export_via_browser(filter_name, month)
        if result:
            return result

        raise RuntimeError(f"ONES {filter_name} {month} 数据不可用")

    def normalize(self, raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """ONES CSV → 标准字段格式"""
        normalized = []
        for row in raw:
            record = {
                "source_id": str(row.get("BI履约ID", "")),
                "source_data": row,
                "normalized_data": {
                    "perf_id": row.get("BI履约ID"),
                    "sales_contract_no": row.get("销售合同编号"),
                    "contract_name": row.get("合同名称"),
                    "prod_line": row.get("所属产线"),
                    "status": row.get("状态"),
                    "owner": row.get("负责人"),
                    "dept": row.get("事业部（区域）"),
                },
                "target_module": "delivery_report",
                "target_table": "dr_sheet_row",
            }
            normalized.append(record)
        return normalized

    # ─── 内部方法 ───

    def _find_cached_csv(self, filter_name: str, month: str) -> Optional[Path]:
        """查找缓存 CSV"""
        if filter_name not in FILTERS:
            return None
        base = DOWNLOAD_DIR
        output_csv = FILTERS[filter_name]["output_csv"]
        # 优先匹配带月份前缀的文件
        month_file = base / f"{month}周报-{output_csv}"
        if month_file.exists():
            return month_file
        generic = base / output_csv
        if generic.exists():
            return generic
        return None

    def _read_csv(self, path: Path) -> List[Dict[str, Any]]:
        """读取 CSV"""
        with open(path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            return [{k: row.get(k, "") for k in reader.fieldnames} for row in reader]

    def _export_via_browser(self, filter_name: str, month: str) -> Optional[List[Dict[str, Any]]]:
        """通过 Playwright 浏览器自动化导出"""
        if filter_name not in FILTERS:
            logger.error(f"未知筛选器: {filter_name}")
            return None

        filter_config = FILTERS[filter_name]
        tab_index = filter_config["tab_index"]
        output_csv = filter_config["output_csv"]

        try:
            adapter = BrowserAdapter(headless=False)
            adapter.launch()
            try:
                # Step 1: 确保 ONES 标签页
                adapter.ones_ensure_tab()
                time.sleep(3)

                # Step 2: 点击筛选器子 tab
                adapter.ones_click_filter_tab(tab_index)

                # Step 3: 点击更多菜单
                adapter.ones_click_more_menu()

                # Step 4: 点击导出工作项
                adapter.ones_click_export_item()

                # Step 5: 点击确认
                adapter.ones_click_confirm()
                time.sleep(1)

                # Step 6: 等待下载完成
                downloaded = adapter.expect_download(timeout=180)
                if not downloaded:
                    logger.error("下载超时")
                    return None

                # 保存到缓存目录
                DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
                cached = DOWNLOAD_DIR / output_csv
                shutil.move(str(downloaded), str(cached))
                logger.info(f"导出成功: {cached} ({cached.stat().st_size:,} bytes)")
                return self._read_csv(cached)
            finally:
                adapter.close()
        except Exception as e:
            logger.error(f"浏览器自动化导出失败: {e}")
            return None
