"""I-04: 企微文档连接器 — API → 浏览器 → 本机导入三级降级.

对齐 DESIGN-DETAIL-INTEGRATION-v2.1.md §6.4。

优先级链：
  1. 本机导入（file_path 直接提供）
  2. 团队报告月度目录 CSV（企微黄金数据）
  3. 企微导出缓存 CSV（ones_dir 下的 wecom_*.csv）
  4. 企微 API（wecom-cli 二进制）
  5. 浏览器自动化（Playwright CDP）
"""
from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from bdms.core.config import get_config
from ..base import BaseConnector, ConnectorRegistry
from .local_import_connector import LocalImportConnector

logger = logging.getLogger(__name__)


@ConnectorRegistry.register
class WecomDocConnector(BaseConnector):
    """I-04: 企微文档连接器 — API → 浏览器 → 本机导入三级降级."""

    name = "wecom_doc"
    data_source = "企业微信文档"
    target_modules = ["delivery_report", "revenue"]
    auth_type = "api_token"
    default_frequency = "manual"

    FALLBACK_CHAIN = ["api", "browser", "local_file"]

    def __init__(self, db_path=None):
        super().__init__(db_path=db_path)
        cfg = get_config()
        self._try_wecom_api = cfg.get("wecom.enable_api", True)
        self._try_browser = cfg.get("wecom.enable_browser", True)

    def authenticate(self) -> bool:
        return True  # 总是可用（走降级链）

    def fetch(self, doc_type: str = "", date_range: str = "",
              file_path: str = "", **params) -> List[Dict[str, Any]]:
        """三级降级获取。

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
                    except Exception as e:
                        logger.warning(f"月度目录 CSV 读取失败: {e}")

        # 3. 企微导出缓存 CSV（wecom_exports 目录）
        from bdms.core.paths import ones_dir
        base = Path.home() / ".openclaw" / "data" / "wecom_exports"
        cache_names = {
            "确收交接": [
                f"revenue_{date_range}.csv" if date_range else "",
                "wecom_revenue.csv",
                "企微确收.csv",
            ],
            "验收交接": [
                f"acceptance_{date_range}.csv" if date_range else "",
                "wecom_acceptance.csv",
                "企微验收.csv",
            ],
        }
        for name in [n for n in cache_names.get(doc_type, []) if n]:
            p = base / name
            if p.exists():
                try:
                    return self._read_csv(p)
                except Exception as e:
                    logger.warning(f"缓存 CSV 读取失败: {e}")

        # 4. 企微 API（wecom-cli）
        if self._try_wecom_api and doc_type and date_range:
            try:
                api_result = self._fetch_via_wecom_api(date_range, doc_type)
                if api_result:
                    return api_result
            except Exception as e:
                logger.warning(f"wecom-cli API 调用失败: {e}，降级")

        # 5. 浏览器自动化（Playwright CDP）
        if self._try_browser and doc_type and date_range:
            try:
                browser_result = self._fetch_via_browser(date_range, doc_type)
                if browser_result:
                    return browser_result
            except Exception as e:
                logger.warning(f"浏览器自动化导出失败: {e}，降级到无结果")

        # 兜底：无结果
        return []

    def _fetch_via_wecom_api(self, month: str, doc_type: str) -> Optional[List[Dict[str, Any]]]:
        """通过 wecom-cli 拉取数据。

        三步流程：
        1. doc search 搜索文档 → 获取 docid
        2. sheet get 获取 Sheet 列表 → 匹配 sheet_id
        3. sheet ranges get (mode=csv) 导出 CSV

        常见错误码：
        - 853000: botId/secret 无效
        - 853007: 文档权限未授权（需要管理员在企微后台重新授权）
        """
        from bdms.core.wecom import wecom_cli_call

        if not wecom_cli_call:
            return None

        # 1. 年月格式转换：202606 → "2026年06月确收凭证交接"
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
        if not search_result:
            return None

        # 错误处理
        if "errcode" in search_result and search_result["errcode"] != 0:
            logger.warning(
                f"wecom-cli doc search 失败: [{search_result['errcode']}] "
                f"{search_result.get('errmsg', '')}"
            )
            return None

        docs = search_result.get("docs", [])
        if not docs:
            return None

        # 匹配标题精确的文档
        doc_id = None
        for doc in docs:
            if doc_keyword in doc.get("doc_name", ""):
                doc_id = doc.get("docid")
                break
        if not doc_id:
            doc_id = docs[0].get("docid")
        if not doc_id:
            return None

        # 3. 获取文档 Sheet 列表
        get_args = json.dumps({"docid": doc_id})
        doc_info = wecom_cli_call(["sheet", "get", "--json", get_args])
        if not doc_info or "sheets" not in doc_info:
            return None

        # 匹配目标 Sheet
        sheet_id = None
        for sheet in doc_info["sheets"]:
            if sheet.get("title") == doc_type:
                sheet_id = sheet.get("sheet_id")
                break
        if not sheet_id:
            return None

        # 4. 导出 Sheet 为 CSV
        from bdms.core.paths import output_dir
        out_dir = output_dir() / "wecom" / month
        out_dir.mkdir(parents=True, exist_ok=True)
        csv_path = out_dir / f"{month}_{doc_type}.csv"

        range_args = json.dumps({
            "docid": doc_id,
            "sheet_id": sheet_id,
            "mode": "csv",
        }, ensure_ascii=False)
        csv_result = wecom_cli_call(["sheet", "ranges", "get", "--json", range_args])
        if not csv_result:
            return None

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

        工作原理：
        1. 连接本地已登录企微的 Chrome 实例（CDP 端口 9222）
        2. 定位目标智能表格页面
        3. 切换到对应 Sheet tab（.tab-bar-item 选择器）
        4. Cmd+A 全选 + Cmd+C 复制（TSV 格式）
        5. 解析剪贴板数据为 CSV

        前提：Chrome 已开 --remote-debugging-port=9222 且已登录企微文档。
        登录态持久化目录：/tmp/chrome-wecom-profile-final/
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning("playwright 未安装，跳过浏览器自动化")
            return None

        import csv
        import io
        from bdms.core.paths import output_dir

        year = month[:4]
        mon = month[4:]
        doc_name = f"{year}年{mon}月确收凭证交接"

        # Sheet 名称映射（doc_type → 页面上的 tab 文本）
        sheet_tab_map = {
            "确收交接": "确收",
            "验收交接": "验收",
        }
        tab_text = sheet_tab_map.get(doc_type, doc_type)

        cdp_port = get_config().get("wecom.browser_cdp_port", 9222)

        with sync_playwright() as p:
            try:
                browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
            except Exception as e:
                logger.warning(f"连接 CDP 端口 {cdp_port} 失败: {e}")
                return None

            try:
                context = browser.contexts[0]
                # 找目标文档页面
                page = None
                for pg in context.pages:
                    if "确收凭证交接" in pg.title() or doc_name in pg.title():
                        page = pg
                        break
                if not page:
                    # 新开页面访问目标文档
                    page = context.new_page()
                    doc_url = get_config().get("wecom.doc_url", "")
                    if not doc_url:
                        logger.warning("未配置 wecom.doc_url，无法打开文档")
                        return None
                    page.goto(doc_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(3000)

                page.bring_to_front()

                # 切换 Sheet tab
                try:
                    tab = page.locator(".tab-bar-item").filter(has_text=tab_text).first
                    if tab.count() == 0:
                        logger.warning(f"找不到 Sheet tab: {tab_text}")
                        return None
                    tab.click(timeout=5000)
                    page.wait_for_timeout(3000)
                except Exception as e:
                    logger.warning(f"切换 Sheet 失败: {e}")
                    return None

                # 点击表格区域获得焦点，然后全选复制
                try:
                    grid = page.locator("[role='grid']").first
                    if grid.count() > 0:
                        grid.click()
                        page.wait_for_timeout(500)
                except Exception:
                    pass

                page.keyboard.press("Meta+a")
                page.wait_for_timeout(1500)
                page.keyboard.press("Meta+c")
                page.wait_for_timeout(2000)

                # 读取剪贴板
                clipboard_text = page.evaluate(
                    "() => navigator.clipboard.readText().catch(e => '')"
                )
                if not clipboard_text or len(clipboard_text) < 100:
                    logger.warning("剪贴板数据为空或过少")
                    return None

                # TSV 解析 + 数据清洗
                lines = clipboard_text.strip().split("\n")
                data = [line.split("\t") for line in lines]
                data = [row for row in data if any(cell.strip() for cell in row)]

                # 自动定位表头行：找到包含核心字段（ID、标题、BI履约ID）的行
                # 全选复制可能带进来表格外的元数据行（如"财务是否接收"等），需要跳过
                header_keywords = ["ID", "标题", "BI履约ID"]
                header_idx = -1
                for i, row in enumerate(data[:10]):
                    matches = sum(1 for kw in header_keywords if kw in row)
                    if matches >= 2:
                        header_idx = i
                        break
                if header_idx > 0:
                    data = data[header_idx:]
                elif header_idx == -1:
                    logger.warning("找不到表头行，数据可能不完整")
                    return None

                if len(data) < 2:
                    logger.warning(f"数据行过少: {len(data)}")
                    return None

                # 过滤明显不是数据的行（ID 列像中文描述的跳过）
                # 正常 ID 格式：以#开头的数字、纯数字、或下划线连接的ID
                import re
                header = data[0]
                id_idx = -1
                for kw in ["ID", "id"]:
                    if kw in header:
                        id_idx = header.index(kw)
                        break
                if id_idx >= 0:
                    cleaned = [data[0]]  # 保留表头
                    for row in data[1:]:
                        if id_idx >= len(row):
                            continue
                        id_val = row[id_idx].strip()
                        # 过滤：空ID、纯中文、纯描述性文本
                        if not id_val:
                            continue
                        # 中文占比超过 60% 的视为脏行
                        chinese_count = sum(1 for ch in id_val if '\u4e00' <= ch <= '\u9fff')
                        if len(id_val) > 0 and chinese_count / len(id_val) > 0.6:
                            continue
                        cleaned.append(row)
                    logger.info(f"数据清洗: {len(data)-1} → {len(cleaned)-1} 行有效数据")
                    data = cleaned

                # 保存到缓存目录
                out_dir = output_dir() / "wecom" / month
                out_dir.mkdir(parents=True, exist_ok=True)
                csv_path = out_dir / f"{month}_{doc_type}.csv"

                with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerows(data)

                logger.info(
                    f"浏览器导出成功: {doc_type} {len(data)-1} 行 → {csv_path}"
                )
                return self._read_csv(csv_path)

            finally:
                # 注意：不要关闭 browser（会关掉用户的 Chrome）
                # 只断开连接
                try:
                    browser.close()
                except Exception:
                    pass

        return None

    @staticmethod
    def _read_csv(path: Path) -> List[Dict[str, Any]]:
        """读取 CSV 为原始行列表（保留全部列）。

        注意：不能直接用 csv.DictReader —— 当表头存在重复列名时
        （如验收 CSV 的两个「截至目前全部/部分验收」），dict 键相同会互相覆盖，
        导致第二列（pandas 语义下为「截至目前全部/部分验收.1」）丢失。
        这里用 pandas 读取，自动对重复列名加 .1 后缀（与 pandas read_csv 语义一致），
        保证两列数据都保留。
        """
        import pandas as pd
        rows = []
        if not path.exists():
            return rows
        try:
            df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
        except Exception:
            # 兜底：utf-8 尝试
            try:
                df = pd.read_csv(path, dtype=str, encoding="utf-8")
            except Exception:
                return rows
        df = df.fillna("")
        for _, row in df.iterrows():
            rows.append({str(k): ("" if v is None else v) for k, v in row.items()})
        return rows

    def _get_doc_url_from_search(self, page, doc_name: str) -> Optional[str]:
        """从企微文档搜索页获取文档 URL."""
        page.goto("https://work.weixin.qq.com/wework_admin/frame#apps/doc",
                  wait_until="networkidle")
        page.fill("[placeholder='搜索文档']", doc_name)
        page.keyboard.press("Enter")
        page.wait_for_load_state("networkidle")
        first_result = page.locator(".doc-search-result-item").first
        if not first_result.is_visible():
            return None
        return first_result.get_attribute("data-url")

    def normalize(self, raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """企微文档数据 → 标准字段格式.

        支持确收交接和验收交接两种文档类型。
        通过行内容自动判断类型（确收有「销售部门」「是否接收」字段，验收有「验收方式」字段）。
        """
        normalized = []
        for row in raw:
            # 自动判断文档类型
            if row.get("验收方式") or row.get("验收单编号-财务端"):
                doc_type = "acceptance"
            else:
                doc_type = "revenue"

            source_id = (
                row.get("ID")
                or row.get("BI履约ID")
                or row.get("合同编号")
                or ""
            )

            record = {
                "source_id": source_id,
                "source_data": row,
                "normalized_data": {
                    "title": row.get("标题", ""),
                    "doc_id": row.get("ID", ""),
                    "bi_performance_id": row.get("BI履约ID", ""),
                    "contract_no": row.get("合同编号", ""),
                    "customer_name": row.get("客户名称", ""),
                    "project_manager": row.get("项目经理", ""),
                    "handover_date": row.get("交接日期", ""),
                },
                "target_module": doc_type,
                "target_table": "rr_sheet_row" if doc_type == "revenue" else "acceptance_sheet_row",
            }

            # 确收特有字段
            if doc_type == "revenue":
                record["normalized_data"].update({
                    "sales_dept": row.get("销售部门", ""),
                    "finance": row.get("财务", ""),
                    "is_received": row.get("是否接收", ""),
                })
            # 验收特有字段
            else:
                record["normalized_data"].update({
                    "contract_name": row.get("合同名称", ""),
                    "acceptance_no": row.get("验收单编号-财务端", ""),
                    "acceptance_method": row.get("验收方式", ""),
                })

            normalized.append(record)
        return normalized
