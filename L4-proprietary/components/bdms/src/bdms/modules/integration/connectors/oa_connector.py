"""I-02: OA 连接器 — Playwright CDP 统一浏览器自动化。

对齐 DESIGN-DETAIL-INTEGRATION-v2.1.md §6.2 + 复用 oa_collector.py 验证过的导航路径。
替代旧的 osascript 方案（oa_adapter.py → deprecated）。
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
    BrowserAdapter, login_iam, ensure_logged_in, OA_BASE, IAM_BASE,
)

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = Path.home() / ".openclaw" / "data" / "oa_exports"


@ConnectorRegistry.register
class OaConnector(BaseConnector):
    """I-02: OA 连接器 — 浏览器自动化 + 本机导入降级。"""

    name = "oa"
    data_source = "OA 合同流程"
    target_modules = ["contract_management", "project_management"]
    auth_type = "browser_cookie"
    default_frequency = "manual"

    def authenticate(self) -> bool:
        """检查 IAM Cookie 是否有效"""
        return ensure_logged_in()

    def fetch(self, contract_type: str = "", date_range: str = "",
              file_path: str = "", month: str = "",
              username: str = "", password: str = "",
              **params) -> List[Dict[str, Any]]:
        """获取 OA 合同数据。

        优先级：本机文件 > 缓存 CSV > 浏览器自动化 > API 降级
        """
        # 1. 本机导入降级
        if file_path and Path(file_path).exists():
            lc = LocalImportConnector(db_path=self.db_path)
            return lc.fetch(file_path=file_path)

        # 2. 缓存 CSV
        cached = self._find_cached_csv(month or contract_type)
        if cached:
            logger.info(f"使用缓存: {cached}")
            return self._read_csv(cached)

        # 3. 浏览器自动化导出
        if not self.authenticate():
            if username and password:
                login_iam(username, password)
            else:
                raise RuntimeError("Cookie 过期且未提供凭据，无法自动登录")

        result = self._export_via_browser(month, contract_type, date_range)
        if result:
            return result

        # 4. API 降级
        logger.warning("浏览器自动化失败，降级到 API")
        return self._export_via_api(month)

    def normalize(self, raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """OA CSV → 标准字段格式"""
        normalized = []
        for row in raw:
            record = {
                "source_id": str(row.get("合同编号", "")),
                "source_data": row,
                "normalized_data": {
                    "contract_no": row.get("合同编号"),
                    "title": row.get("合同名称"),
                    "party_a": row.get("甲方"),
                    "party_b": row.get("乙方"),
                    "amount": self._parse_amount(row.get("合同金额", "")),
                    "effective_date": row.get("生效日期"),
                    "expiry_date": row.get("到期日期"),
                    "status": self._map_status(row.get("状态", "")),
                },
                "target_module": "contract_management",
                "target_table": "cr_contracts",
            }
            normalized.append(record)
        return normalized

    # ─── 内部方法 ───

    def _find_cached_csv(self, month: str) -> Optional[Path]:
        """查找缓存 CSV"""
        base = DOWNLOAD_DIR
        base.mkdir(parents=True, exist_ok=True)
        for name in [f"contract_ledger_{month}.xlsx", f"contract_ledger_{month}.csv",
                     "oa_contracts.csv", "合同台账.csv", "oa_export.csv"]:
            p = base / name
            if p.exists():
                return p
        return None

    def _read_csv(self, path: Path) -> List[Dict[str, Any]]:
        """读取 CSV"""
        with open(path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            return [{k: row.get(k, "") for k in reader.fieldnames} for row in reader]

    def _parse_amount(self, amount_str: str) -> float:
        if not amount_str:
            return 0.0
        try:
            return float(str(amount_str).replace(",", "").replace("元", ""))
        except ValueError:
            return 0.0

    def _map_status(self, status_str: str) -> str:
        status_map = {"生效": "active", "已终止": "terminated", "草稿": "draft", "审批中": "pending"}
        return status_map.get(status_str.lower(), "unknown")

    def _export_via_browser(self, month: str, contract_type: str,
                            date_range: str) -> Optional[List[Dict[str, Any]]]:
        """通过 Playwright 浏览器自动化导出"""
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

                # Step 2: 进入 OA
                oa_page = adapter.oa_click_card_iam("OA协同办公平台", adapter._context)
                if not oa_page:
                    logger.error("无法进入 OA")
                    return None
                adapter._page = oa_page

                # Step 3: 关闭弹窗
                adapter.oa_dismiss_dialogs()

                # Step 4: 导航到合同台账
                adapter.oa_click_menu("销售合同管理系统")
                adapter.oa_click_menu("合同基本信息管理")
                adapter.oa_click_menu("合同台账")
                time.sleep(5)

                # Step 5: 查找 Cube frame
                cube_frame = adapter.find_frame("customid=179", timeout=60)
                if not cube_frame:
                    logger.error("未找到 Cube frame")
                    return None

                # Step 6: 点击导出
                export_btn = cube_frame.locator("button").filter(has_text="导出").first
                if export_btn.count() == 0:
                    export_btn = cube_frame.locator("button").filter(has_text="导 出").first
                if export_btn.count() > 0:
                    export_btn.click()
                else:
                    # 兜底：evaluate 点击
                    cube_frame.evaluate("""() => {
                        const btns = document.querySelectorAll('button');
                        for (const b of btns) {
                            if (b.textContent.includes('导') && b.textContent.includes('出')) {
                                b.click(); break;
                            }
                        }
                    }""")
                time.sleep(3)

                # Step 7: 等待下载
                downloaded = adapter.expect_download(timeout=600)
                if not downloaded:
                    logger.error("下载超时")
                    return None

                # 保存
                output_file = DOWNLOAD_DIR / f"contract_ledger_{month}.xlsx"
                DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
                shutil.move(str(downloaded), str(output_file))
                logger.info(f"导出成功: {output_file} ({output_file.stat().st_size} bytes)")

                return self._read_csv(output_file) if output_file.suffix == '.csv' else []
            finally:
                adapter.close()
        except Exception as e:
            logger.error(f"浏览器自动化导出失败: {e}")
            return None

    def _export_via_api(self, month: str) -> List[Dict[str, Any]]:
        """API 降级方案"""
        try:
            import requests as req_lib
        except ImportError:
            return []

        from ..adapters.browser_adapter import get_cookie, _load_cookies
        cookies = _load_cookies()
        cookie_str = None
        for domain in ["oa.bangcle.com", ".bangcle.com"]:
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
            "Referer": OA_BASE + "/",
            "x-requested-with": "XMLHttpRequest",
        })

        all_rows = []
        page_num = 1
        page_size = 200

        while True:
            resp = session.post(
                f"{OA_BASE}/api/cube/search/getList",
                data=f"customid=179&guid=search&page={page_num}&pageSize={page_size}",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            if resp.status_code != 200:
                break
            data = resp.json()
            datas = data.get("datas", [])
            if not datas:
                break
            all_rows.extend(datas)
            total = data.get("total", 0)
            if len(all_rows) >= total or len(datas) < page_size:
                break
            page_num += 1

        if all_rows:
            output_file = DOWNLOAD_DIR / f"contract_ledger_{month}_api.json"
            DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
            import json
            output_file.write_text(json.dumps({
                "month": month, "source": "oa_api", "count": len(all_rows),
                "file": str(output_file),
            }, ensure_ascii=False, indent=2), encoding="utf-8")

        return all_rows
