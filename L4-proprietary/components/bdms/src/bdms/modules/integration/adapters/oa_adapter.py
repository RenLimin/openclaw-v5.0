"""OA 数据源适配器 — 本机导入 + 浏览器自动化。

对齐 DESIGN-DETAIL-INTEGRATION-v2.1.md §6.2。
OA 合同数据通过浏览器自动化导出，支持本机导入降级。
"""
from __future__ import annotations
import csv
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Dict, Optional

from bdms.core.paths import ones_dir

logger = logging.getLogger(__name__)


class MissingSourceError(Exception):
    pass


class OaAdapter:
    """OA 合同流程数据源适配器。

    数据来源降级链：
    1. 本机文件（最高优先级，手动指定）
    2. 缓存 CSV（ones_exports 目录）
    3. 浏览器自动化导出（osascript 控制 Chrome）
    4. 失败报错
    """

    def __init__(self, timeout: int = 30):
        self._cache_dir = ones_dir()
        self._timeout = timeout
        self._downloads_dir = Path.home() / "Downloads"

    def fetch(self, contract_type: str = "", date_range: str = "",
              file_path: str = "") -> List[Dict]:
        """获取 OA 数据。

        Args:
            contract_type: 数据类型（contract / project_init / project_close）
            date_range: 日期范围（YYYY-MM-DD,YYYY-MM-DD）
            file_path: 本机文件路径

        Returns:
            List[Dict] 原始数据

        Raises:
            MissingSourceError: 数据源不可用
        """
        # 1. 本机文件
        if file_path and Path(file_path).exists():
            return self._read_csv(Path(file_path))

        # 2. OA 导出 CSV
        base = self._cache_dir
        for name in ["oa_contracts.csv", "合同台账.csv", "oa_export.csv"]:
            p = base / name
            if p.exists():
                return self._read_csv(p)

        # 3. 浏览器自动化导出
        if sys.platform == "darwin":
            exported = self._export_from_browser(contract_type, date_range)
            if exported:
                return exported

        # 4. 报错
        raise MissingSourceError(
            f"OA 数据不可用。请手动导出合同数据到 {self._cache_dir}"
        )

    def _read_csv(self, path: Path) -> List[Dict]:
        """读取 CSV 文件。"""
        with open(path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            return [{k: row.get(k, "") for k in reader.fieldnames} for row in reader]

    # ─── 浏览器自动化导出 ───

    def _export_from_browser(self, contract_type: str,
                            date_range: str) -> Optional[List[Dict]]:
        """通过浏览器自动化从 OA 导出合同数据。

        使用 osascript 控制已打开的 Chrome 浏览器：
        1. 检查 OA 标签页
        2. 导航到合同列表页
        3. 设置筛选条件
        4. 触发导出
        5. 等待下载完成

        Returns:
            导出数据列表，失败返回 None
        """
        logger.info(f"开始浏览器自动化导出 OA 合同数据 (type={contract_type})...")

        try:
            self._check_chrome_available()
            self._ensure_oa_tab()
            self._navigate_to_contract_list()
            self._trigger_export()
            csv_path = self._wait_for_download("oa", date_range)
            if csv_path and csv_path.exists():
                logger.info(f"OA 导出成功: {csv_path} ({csv_path.stat().st_size} bytes)")
                # 复制到缓存目录
                cached = self._cache_dir / csv_path.name
                import shutil
                shutil.copy2(csv_path, cached)
                return self._read_csv(cached)
            return None
        except Exception as e:
            logger.warning(f"OA 浏览器自动化导出失败: {e}")
            return None

    def _check_chrome_available(self) -> None:
        """检查 osascript 和 Chrome 是否可用。"""
        if sys.platform != "darwin":
            raise RuntimeError(f"浏览器自动化仅支持 macOS (darwin)，当前: {sys.platform}")

        try:
            result = subprocess.run(
                ["osascript", "-e", 'return "ok"'],
                capture_output=True, timeout=5
            )
            if result.returncode != 0:
                raise RuntimeError(f"osascript 不可用: {result.stderr.decode()}")
        except FileNotFoundError:
            raise RuntimeError("osascript 未找到")

    def _ensure_oa_tab(self) -> None:
        """检查 OA 标签页是否存在。"""
        try:
            result = subprocess.run(
                [
                    "osascript", "-e",
                    'tell application "Google Chrome" to return URL of '
                    '(first tab of first window whose URL contains "oa.bangcle.com")'
                ],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode != 0 or "oa.bangcle.com" not in result.stdout:
                raise RuntimeError(
                    "OA 标签页未打开。请先在 Chrome 中打开 oa.bangcle.com 并登录。"
                )
            logger.info("OA 标签页已打开")
        except subprocess.TimeoutExpired:
            raise RuntimeError("检查 OA 标签页超时")

    def _navigate_to_contract_list(self) -> None:
        """逐级菜单导航到合同台账（销售）。
        
        实测路径（DESIGN-DETAIL §5.2.0）：
        IAM 登录 → 点击「门户」→「销售合同管理系统」→
        「合同基本信息管理」→「合同台账（销售）」
        
        ⚠️ 禁止 window.location.href 直接跳转 — OA Cube 页面 URL 含
        动态 _key 参数，直接 page.goto() 会失效，必须逐级点击菜单。
        """
        menu_path = ["门户", "销售合同管理系统", "合同基本信息管理", "合同台账"]
        for label in menu_path:
            if not self._click_menu_item(label):
                logger.warning(f"菜单项「{label}» 未找到，停止导航")
                return
            time.sleep(2)
        logger.info("逐级菜单导航完成 → 合同台账（销售）")

    def _click_menu_item(self, text: str) -> bool:
        """在 OA 左侧导航中逐级点击含指定文字的菜单项。
        匹配逻辑：先精确匹配 textContent，再 fallback 到模糊包含。
        """
        # 精确匹配（含去空格后相等）
        js_exact = (
            "var found = false;"
            "document.querySelectorAll('.ant-menu-item, .ant-menu-submenu-title, a[role=menuitem], a[class*=menu], span[class*=menu]').forEach(el => {"
            "  var t = el.textContent.trim();"
            "  if (t === '" + text + "') { el.click(); found = true; }"
            "});"
            "found;"
        )
        res = self._run_oa_js(js_exact)
        if res == "true":
            return True

        # 模糊匹配：textContent 包含关键词
        js_fuzzy = (
            "var found = false;"
            "document.querySelectorAll('.ant-menu-item, .ant-menu-submenu-title, a[role=menuitem], a[class*=menu], span[class*=menu]').forEach(el => {"
            "  var t = el.textContent.trim();"
            "  if (t.indexOf('" + text + "') !== -1 && !found) { el.click(); found = true; }"
            "});"
            "found;"
        )
        res = self._run_oa_js(js_fuzzy)
        return res == "true"

    def _trigger_export(self) -> None:
        """触发 OA 导出操作。
        流程：点导出按钮 → 等待进度弹窗完成 → 从弹窗拿下载链接。
        """
        # 查找导出按钮
        js = (
            "var buttons = [];"
            "document.querySelectorAll('button, a').forEach(function(b, i) {"
            "  var t = b.textContent.trim();"
            "  if (t.indexOf('导出') !== -1 || t.indexOf('Export') !== -1) {"
            "    buttons.push({index: i, text: t, tag: b.tagName});"
            "  }"
            "});"
            "JSON.stringify(buttons);"
        )
        result = self._run_oa_js(js)
        if result and result != "missing value":
            try:
                buttons = json.loads(result)
                if buttons:
                    btn = buttons[0]
                    if btn["tag"] == "BUTTON":
                        click_js = (
                            "var btns = document.querySelectorAll('button');"
                            "if (btns.length > " + str(btn["index"]) + ") { "
                            "btns[" + str(btn["index"]) + "].click(); 'clicked'; } "
                            "else { 'no_btn'; }"
                        )
                    else:
                        click_js = (
                            "var links = document.querySelectorAll('a');"
                            "if (links.length > " + str(btn["index"]) + ") { "
                            "links[" + str(btn["index"]) + "].click(); 'clicked'; } "
                            "else { 'no_link'; }"
                        )
                    self._run_oa_js(click_js)
                    logger.info("已点击导出按钮，等待进度弹窗...")
                    time.sleep(3)
                    return
            except (json.JSONDecodeError, KeyError):
                pass

        # 备选：更多菜单中的导出
        more_js = (
            "var icons = document.querySelectorAll('[class*=more], [class*=action], [class*=menu-icon]');"
            "if (icons.length > 0) { icons[0].click(); 'clicked'; }"
            "else { 'no_more_icon'; }"
        )
        self._run_oa_js(more_js)
        time.sleep(2)
        export_js = (
            "var items = document.querySelectorAll('[class*=dropdown] a, [class*=menu] a, [class*=dropdown-menu] span');"
            "var found = false;"
            "items.forEach(function(item) {"
            "  if (item.textContent.trim().indexOf('导出') !== -1 && !found) {"
            "    item.click(); found = true;"
            "  }"
            "});"
            "found ? 'clicked' : 'no_export_item';"
        )
        self._run_oa_js(export_js)
        time.sleep(3)

    def _wait_for_download(self, prefix: str, date_range: str,
                           timeout: int = 180) -> Optional[Path]:
        """等待 OA 异步导出完成。
        
        OA 导出流程：点导出 → 进度弹窗 → 100% 完成 → 弹窗内出现下载链接。
        本函数先等弹窗消失（或进度=100%），然后从弹窗或 Downloads 取文件。
        """
        logger.info("等待 OA 异步导出完成...")
        start_time = time.time()
        initial_files = set(self._downloads_dir.glob("*.csv"))

        while time.time() - start_time < timeout:
            time.sleep(3)
            
            # 方式1：检查页面是否有下载链接（弹窗内）
            download_link_js = (
                "var link = null;"
                "document.querySelectorAll('a').forEach(function(a) {"
                "  if (a.href && (a.href.indexOf('download') !== -1 || a.textContent.indexOf('下载') !== -1)) {"
                "    link = a.href;"
                "  }"
                "});"
                "link || 'no_link';"
            )
            result = self._run_oa_js(download_link_js)
            if result and result != "no_link" and result != "missing value":
                logger.info(f"发现下载链接: {result}")
                # 在浏览器中打开下载链接
                open_js = "window.location.href = '" + result + "';'opening'"
                self._run_oa_js(open_js)
                time.sleep(5)
            
            # 方式2：检查 Downloads 目录是否有新 CSV
            current_files = set(self._downloads_dir.glob("*.csv"))
            new_files = current_files - initial_files
            for f in new_files:
                size1 = f.stat().st_size
                time.sleep(1)
                size2 = f.stat().st_size
                if size1 == size2 and size1 > 1000:
                    return f
            
            # 方式3：检查进度弹窗是否还在（若在则继续等）
            progress_js = (
                "var progress = document.querySelector('[class*=progress], [class*=modal]');"
                "progress ? 'waiting' : 'done';"
            )
            progress_res = self._run_oa_js(progress_js)
            if progress_res == "done":
                # 弹窗消失了，检查是否有下载按钮
                dl_btn_js = (
                    "var found = false;"
                    "document.querySelectorAll('button, a').forEach(function(b) {"
                    "  var t = b.textContent.trim();"
                    "  if (t.indexOf('下载') !== -1 || t.indexOf('Download') !== -1) { found = true; }"
                    "});"
                    "found;"
                )
                dl_res = self._run_oa_js(dl_btn_js)
                if dl_res == "true":
                    # 有下载按钮，点击
                    click_dl_js = (
                        "var found = false;"
                        "document.querySelectorAll('button, a').forEach(function(b) {"
                        "  var t = b.textContent.trim();"
                        "  if (t.indexOf('下载') !== -1 || t.indexOf('Download') !== -1) {"
                        "    b.click(); found = true;"
                        "  }"
                        "});"
                        "found;"
                    )
                    self._run_oa_js(click_dl_js)
                    time.sleep(5)

        return None

    def _run_oa_js(self, js_code: str) -> str:
        """在 OA 标签页中执行 JavaScript。

        Args:
            js_code: 纯英文 JS 代码

        Returns:
            执行结果字符串
        """
        safe_js = js_code.replace('\n', ' ').replace('\r', '').strip()
        safe_js = safe_js.replace('"', '\\"')

        cmd = [
            "osascript", "-e",
            f'tell application "Google Chrome" to execute '
            f'(first tab of first window whose URL contains "oa.bangcle.com") '
            f'javascript "{safe_js}"'
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self._timeout
            )
            if result.returncode != 0:
                error_msg = result.stderr.strip()
                logger.warning(f"osascript 执行失败: {error_msg[:200]}")
                return "missing value"
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            logger.warning(f"osascript 执行超时 ({self._timeout}s)")
            return "missing value"
