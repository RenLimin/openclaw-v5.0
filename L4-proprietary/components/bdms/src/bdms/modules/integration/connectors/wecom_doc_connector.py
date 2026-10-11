"""I-04: 企微文档连接器 — API → 浏览器 → 本机导入三级降级."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from bdms.core.config import get_config
from ..base import BaseConnector, ConnectorRegistry
from .local_import_connector import LocalImportConnector


@ConnectorRegistry.register
class WecomDocConnector(BaseConnector):
    """I-04: 企微文档连接器 — API → 浏览器 → 本机导入三级降级."""

    name = "wecom_doc"
    data_source = "企业微信文档"
    target_modules = ["delivery_report", "revenue"]
    auth_type = "api_token"
    default_frequency = "manual"

    FALLBACK_CHAIN = ["api", "browser", "local_file"]

    def __init__(self):
        super().__init__()
        cfg = get_config()
        self._try_wecom_api = cfg.get("wecom.enable_api", True)
        self._try_browser = cfg.get("wecom.enable_browser", True)

    def authenticate(self) -> bool:
        return True  # 总是可用（走降级链）

    def fetch(self, doc_type: str = "", date_range: str = "",
              file_path: str = "", **params) -> List[Dict[str, Any]]:
        """三级降级获取。

        优先级：
          1. 本机导入（file_path 直接提供文件）
          2. 团队报告月度目录 CSV（企微黄金数据，month_dir/{month}确收凭证交接-*.csv）
          3. 企微导出缓存 CSV（ones_dir 下的 wecom_*.csv）
          4. 企微 API（wecom-cli）
          5. 浏览器自动化（Playwright CDP）

        Args:
            doc_type: 文档类型（确收交接 / 验收交接）
            date_range: 月份（YYYYMM）
            file_path: 本机文件绝对路径

        Returns:
            原始行列表（每行是 dict，键为 CSV 列名）。
            由调用方（pipeline）再调用 normalize() 包装成统一记录结构。
        """
        # 1. 本机导入（最高优先级：直接提供文件）
        if file_path and Path(file_path).exists():
            lc = LocalImportConnector(db_path=self.db_path)
            return lc.fetch(file_path=file_path)

        # 2. 团队报告月度目录 CSV（企微黄金数据）
        if doc_type and date_range:
            from bdms.core.paths import month_dir
            md = month_dir(date_range)
            if md.exists():
                filename_map = {
                    "确收交接": f"{date_range}确收凭证交接-确收.csv",
                    "验收交接": f"{date_range}确收凭证交接-验收.csv",
                }
                p = md / filename_map.get(doc_type, "")
                if p and p.exists():
                    try:
                        return self._read_csv(p)
                    except Exception:
                        pass

        # 3. 企微导出 CSV（ones_dir 缓存）
        from bdms.core.paths import ones_dir
        base = ones_dir()
        cache_names = {
            "确收交接": ["wecom_revenue.csv", "企微确收.csv"],
            "验收交接": ["wecom_acceptance.csv", "企微验收.csv"],
        }
        for name in cache_names.get(doc_type, []) + ["企微导出.csv"]:
            p = base / name
            if p.exists():
                try:
                    return self._read_csv(p)
                except Exception:
                    pass

        # 4. 企微 API（wecom-cli）
        if self._try_wecom_api:
            try:
                api_result = self._fetch_via_wecom_api(date_range, doc_type)
                if api_result:
                    return api_result
            except Exception:
                self._logger.warning("wecom-cli API 调用失败，降级到浏览器自动化")
                pass

        # 5. 浏览器自动化（Playwright CDP）
        if self._try_browser:
            try:
                browser_result = self._fetch_via_browser(date_range, doc_type)
                if browser_result:
                    return browser_result
            except Exception as e:
                self._logger.warning(f"浏览器自动化导出失败: {str(e)}，降级到无结果")
                pass

        # 兜底：无结果
        return []

    def _fetch_via_wecom_api(self, month: str, doc_type: str) -> Optional[List[Dict[str, Any]]]:
        """通过 wecom-cli API 拉取数据。

        按以下三步：
        1. doc search 搜索文档 → 获取 docid
        2. sheet get 获取 Sheet 列表 → 匹配 sheet_id
        3. sheet ranges get (mode=csv) 导出 CSV
        """
        from bdms.core.wecom import wecom_cli_call

        # 1. 年月格式转换：202606 → "2026年06月"
        year = month[:4]
        mon = month[4:]
        doc_keyword = f"{year}年{mon}月确收凭证交接"

        # 2. 搜索定位文档（在线表格类型）
        search_args = json.dumps({
            "keywords": [doc_keyword],
            "search_scope": "title",
            "doc_types": ["sheet"],
            "limit": 10,
        }, ensure_ascii=False)
        search_result = wecom_cli_call(["doc", "search", "--json", search_args])
        if not search_result or "docs" not in search_result or not search_result["docs"]:
            return None

        # 匹配标题精确的文档
        doc_id = None
        for doc in search_result["docs"]:
            if doc_keyword in doc["doc_name"]:
                doc_id = doc["docid"]
                break
        if not doc_id:
            doc_id = search_result["docs"][0]["docid"]

        # 3. 获取文档 Sheet 列表
        get_args = json.dumps({"docid": doc_id})
        doc_info = wecom_cli_call(["sheet", "get", "--json", get_args])
        if not doc_info or "sheets" not in doc_info:
            return None

        # 匹配目标 Sheet
        sheet_id = None
        for sheet in doc_info["sheets"]:
            if sheet["title"] == doc_type:
                sheet_id = sheet["sheet_id"]
                break
        if not sheet_id:
            return None

        # 4. 导出 Sheet 为 CSV
        from bdms.core.paths import output_dir
        output_dir = output_dir() / "wecom" / month
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / f"{month}_{doc_type}.csv"

        get_args = json.dumps({
            "docid": doc_id,
            "sheet_id": sheet_id,
            "mode": "csv",
        })
        csv_result = wecom_cli_call(["sheet", "ranges", "get", "--json", get_args])

        # 写入 CSV
        if "content" in csv_result:
            csv_path.write_text(csv_result["content"], encoding="utf-8-sig")
        elif "file_path" in csv_result:
            src = Path(csv_result["file_path"])
            csv_path.write_text(src.read_text(encoding="utf-8-sig"), encoding="utf-8-sig")
        else:
            return None

        # 解析 CSV
        return self._read_csv(csv_path)

    def _fetch_via_browser(self, month: str, doc_type: str) -> Optional[List[Dict[str, Any]]]:
        """通过 Playwright CDP 浏览器自动化拉取数据。

        前提：企微 Web 端已登录，Cookie 已注入到浏览器上下文，或者连接本地 Chrome 实例
        """
        from playwright.sync_api import Browser

        from bdms.core.browser import get_browser_context

        # 获取浏览器上下文
        browser_context = get_browser_context("wecom")
        if not browser_context:
            return None

        # 1. 打开企微文档
        year = month[:4]
        mon = month[4:]
        doc_name = f"{year}年{mon}月确收凭证交接"

        # 判断上下文来源：已连接本地实例还是新建
        if browser_context.browser:
            browser = browser_context.browser
        else:
            # 兼容老格式
            browser = browser_context
        page = browser.new_page()

        doc_url = self._get_doc_url_from_search(page, doc_name)
        if not doc_url:
            page.close()
            return None
        page.goto(doc_url, wait_until="networkidle")

        # 定位 Sheet 标签 → 点击切换
        # 匹配 doc_type Sheet（确收交接 / 验收交接）
        sheet_locator = page.locator(f"[data-title='{doc_type}']")
        if not sheet_locator.is_visible():
            page.close()
            return None
        sheet_locator.click()
        page.wait_for_load_state("networkidle")

        # 点击导出 → 下载 CSV
        with tempfile.TemporaryDirectory() as tmpdir:
            download_path = Path(tmpdir) / f"{month}_{doc_type}.csv"
            with page.expect_download() as download_info:
                # 点击导出按钮
                page.locator("[data-action='export']").click()
                page.locator("[data-format='csv']").click()
            download = download_info.value
            download.save_as(download_path)

            # 移动到输出目录
            from bdms.core.paths import output_dir
            target_dir = output_dir() / "wecom" / month
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / f"{month}_{doc_type}.csv"
            download_path.replace(target_path)

            page.close()

        # 解析 CSV
        return self._read_csv(target_path)
        return None

    @staticmethod
    def _read_csv(path: Path) -> List[Dict[str, Any]]:
        """读取 CSV 为原始行列表（保留全部列）."""
        import csv
        rows = []
        if not path.exists():
            return rows
        with open(path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append({k: row.get(k, "") for k in reader.fieldnames})
        return rows

    def _get_doc_url_from_search(self, page, doc_name: str) -> Optional[str]:
        """从企微文档搜索页获取文档 URL."""
        # 打开文档搜索页
        page.goto("https://work.weixin.qq.com/wework_admin/frame#apps/doc",
                  wait_until="networkidle")
        # 输入搜索关键词
        page.fill("[placeholder='搜索文档']", doc_name)
        page.keyboard.press("Enter")
        page.wait_for_load_state("networkidle")
        # 点击第一个搜索结果
        first_result = page.locator(".doc-search-result-item").first
        if not first_result.is_visible():
            return None
        doc_url = first_result.get_attribute("data-url")
        return doc_url

    def normalize(self, raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """企微文档数据 → 标准字段格式."""
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
