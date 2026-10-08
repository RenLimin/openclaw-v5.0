"""工时门户数据源适配器 — 浏览器自动化 + 本机导入。

对齐 DESIGN-DETAIL-INTEGRATION-v2.1.md §6.3。
工时数据通过浏览器自动化导出，支持本机导入降级。
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


class TimesheetAdapter:
    """工时门户数据源适配器。

    数据来源降级链：
    1. 本机文件（最高优先级，手动指定）
    2. 缓存 CSV/Excel（ones_exports 目录）
    3. 浏览器自动化导出（osascript 控制 Chrome）
    4. 失败报错
    """

    def __init__(self, timeout: int = 30):
        self._cache_dir = ones_dir()
        self._timeout = timeout
        self._downloads_dir = Path.home() / "Downloads"

    def fetch(self, project_id: str = "", month: str = "",
              file_path: str = "") -> List[Dict]:
        """获取工时数据。

        Args:
            project_id: 项目 ID（可选）
            month: 目标月份（YYYYMM）
            file_path: 本机文件路径

        Returns:
            List[Dict] 原始数据

        Raises:
            MissingSourceError: 数据源不可用
        """
        # 1. 本机文件
        if file_path and Path(file_path).exists():
            return self._read_file(Path(file_path))

        # 2. 工时导出 CSV/Excel
        base = self._cache_dir
        for name in ["工时填报.xlsx", "工时数据.csv", "timesheet.csv"]:
            p = base / name
            if p.exists():
                return self._read_file(p)

        # 3. 浏览器自动化导出
        if sys.platform == "darwin":
            exported = self._export_from_browser(project_id, month)
            if exported:
                return exported

        # 4. 报错
        raise MissingSourceError(
            f"工时数据不可用。请手动导出 {month} 工时数据到 {self._cache_dir}"
        )

    def _read_file(self, path: Path) -> List[Dict]:
        """读取 Excel 或 CSV 文件。"""
        if path.suffix == '.xlsx':
            import pandas as pd
            df = pd.read_excel(path)
            return df.to_dict(orient='records')
        with open(path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            return [{k: row.get(k, "") for k in reader.fieldnames} for row in reader]

    # ─── 浏览器自动化导出 ───

    def _export_from_browser(self, project_id: str,
                            month: str) -> Optional[List[Dict]]:
        """通过浏览器自动化从工时门户导出工时数据。

        使用 osascript 控制已打开的 Chrome 浏览器：
        1. 检查工时门户标签页
        2. 导航到导出页面
        3. 设置筛选条件（月份、项目）
        4. 触发导出
        5. 等待下载完成

        Returns:
            导出数据列表，失败返回 None
        """
        logger.info(f"开始浏览器自动化导出工时数据 (month={month}, project={project_id})...")

        try:
            self._check_chrome_available()
            self._ensure_timesheet_tab()
            self._navigate_to_export_page()
            self._set_filters(project_id, month)
            self._trigger_export()
            file_path = self._wait_for_download(month)
            if file_path and file_path.exists():
                logger.info(f"工时导出成功: {file_path} ({file_path.stat().st_size} bytes)")
                # 复制到缓存目录
                cached = self._cache_dir / file_path.name
                import shutil
                shutil.copy2(file_path, cached)
                return self._read_file(cached)
            return None
        except Exception as e:
            logger.warning(f"工时浏览器自动化导出失败: {e}")
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

    def _ensure_timesheet_tab(self) -> None:
        """检查工时门户标签页是否存在。"""
        try:
            result = subprocess.run(
                [
                    "osascript", "-e",
                    'tell application "Google Chrome" to return URL of '
                    '(first tab of first window whose URL contains "timesheet.bangcle.com")'
                ],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode != 0 or "timesheet.bangcle.com" not in result.stdout:
                raise RuntimeError(
                    "工时门户标签页未打开。请先在 Chrome 中打开 timesheet.bangcle.com 并登录。"
                )
            logger.info("工时门户标签页已打开")
        except subprocess.TimeoutExpired:
            raise RuntimeError("检查工时门户标签页超时")

    def _navigate_to_export_page(self) -> None:
        """导航到工时导出页面。

        尝试点击导出链接或导航到导出页面。
        """
        # 尝试查找导出相关的导航链接
        js = (
            "var links = [];"
            "document.querySelectorAll('a').forEach(function(a, i) {"
            "  var t = a.textContent.trim();"
            "  if (t.indexOf('导出') !== -1 || t.indexOf('Export') !== -1 || "
            "      t.indexOf('报表') !== -1 || t.indexOf('数据') !== -1) {"
            "    links.push({index: i, text: t});"
            "  }"
            "});"
            "JSON.stringify(links);"
        )

        result = self._run_timesheet_js(js)
        if result and result != "missing value":
            try:
                links = json.loads(result)
                if links:
                    link_index = links[0]["index"]
                    click_js = f"document.querySelectorAll('a')[{link_index}].click();'clicked'"
                    self._run_timesheet_js(click_js)
                    time.sleep(5)
                    return
            except (json.JSONDecodeError, KeyError):
                pass

        # 备选：直接导航到导出页面
        nav_js = "window.location.href = '/export';'navigating'"
        self._run_timesheet_js(nav_js)
        time.sleep(5)

    def _set_filters(self, project_id: str, month: str) -> None:
        """设置导出筛选条件。

        在导出页面设置月份和项目筛选。
        """
        if month:
            # 尝试设置月份输入框
            month_js = (
                "var inputs = document.querySelectorAll('input[type=text], input:not([type]), select');"
                "var found = false;"
                "inputs.forEach(function(inp) {"
                "  var placeholder = inp.placeholder || '';"
                "  var name = inp.name || '';"
                "  if (placeholder.indexOf('月') !== -1 || name.indexOf('month') !== -1 || "
                "      placeholder.indexOf('month') !== -1) {"
                "    inp.value = '" + month + "';"
                "    inp.dispatchEvent(new Event('input', {bubbles: true}));"
                "    found = true;"
                "  }"
                "});"
                "found ? 'set' : 'no_month_input';"
            )
            self._run_timesheet_js(month_js)
            time.sleep(1)

        if project_id:
            # 尝试设置项目筛选
            project_js = (
                "var selects = document.querySelectorAll('select');"
                "var found = false;"
                "selects.forEach(function(sel) {"
                "  if (sel.name && sel.name.indexOf('project') !== -1) {"
                "    sel.value = '" + project_id + "';"
                "    sel.dispatchEvent(new Event('change', {bubbles: true}));"
                "    found = true;"
                "  }"
                "});"
                "found ? 'set' : 'no_project_select';"
            )
            self._run_timesheet_js(project_js)
            time.sleep(1)

    def _trigger_export(self) -> None:
        """触发导出操作。

        查找导出按钮并点击。
        """
        # 查找导出按钮
        js = (
            "var buttons = [];"
            "document.querySelectorAll('button, a').forEach(function(b, i) {"
            "  var t = b.textContent.trim();"
            "  if (t.indexOf('导出') !== -1 || t.indexOf('Export') !== -1 || "
            "      t.indexOf('下载') !== -1 || t.indexOf('确认') !== -1) {"
            "    buttons.push({index: i, text: t, tag: b.tagName});"
            "  }"
            "});"
            "JSON.stringify(buttons);"
        )

        result = self._run_timesheet_js(js)
        if result and result != "missing value":
            try:
                buttons = json.loads(result)
                if buttons:
                    btn = buttons[0]
                    if btn["tag"] == "BUTTON":
                        click_js = (
                            f"var btns = document.querySelectorAll('button');"
                            f"if (btns.length > {btn['index']}) {{ "
                            f"btns[{btn['index']}].click(); 'clicked'; }} "
                            f"else {{ 'no_btn'; }}"
                        )
                    else:
                        click_js = (
                            f"var links = document.querySelectorAll('a');"
                            f"if (links.length > {btn['index']}) {{ "
                            f"links[{btn['index']}].click(); 'clicked'; }} "
                            f"else {{ 'no_link'; }}"
                        )
                    self._run_timesheet_js(click_js)
                    time.sleep(3)
                    return
            except (json.JSONDecodeError, KeyError):
                pass

        # 备选：尝试提交按钮
        submit_js = (
            "var btns = document.querySelectorAll('button[type=submit], input[type=submit]');"
            "if (btns.length > 0) { btns[0].click(); 'clicked'; }"
            "else { 'no_submit_btn'; }"
        )
        self._run_timesheet_js(submit_js)
        time.sleep(3)

    def _wait_for_download(self, month: str, timeout: int = 60) -> Optional[Path]:
        """等待下载完成。

        Args:
            month: 月份
            timeout: 超时时间

        Returns:
            下载文件路径，超时返回 None
        """
        logger.info("等待工时下载完成...")
        start_time = time.time()
        initial_csv = set(self._downloads_dir.glob("*.csv"))
        initial_xlsx = set(self._downloads_dir.glob("*.xlsx"))
        initial_all = initial_csv | initial_xlsx

        while time.time() - start_time < timeout:
            time.sleep(2)
            current_csv = set(self._downloads_dir.glob("*.csv"))
            current_xlsx = set(self._downloads_dir.glob("*.xlsx"))
            current_all = current_csv | current_xlsx
            new_files = current_all - initial_all

            for f in new_files:
                if ("工时" in f.name or "timesheet" in f.name.lower() or
                    "填报" in f.name or month in f.name or
                    "export" in f.name.lower() or "导出" in f.name):
                    size1 = f.stat().st_size
                    time.sleep(1)
                    size2 = f.stat().st_size
                    if size1 == size2 and size1 > 0:
                        return f

            # 检查通用导出文件名
            for name in ["工时填报.xlsx", "工时数据.csv", "timesheet.csv",
                         "全部工时.csv", "export.csv", "导出数据.csv"]:
                p = self._downloads_dir / name
                if p.exists() and p.stat().st_size > 0:
                    return p

        return None

    def _run_timesheet_js(self, js_code: str) -> str:
        """在工时门户标签页中执行 JavaScript。

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
            f'(first tab of first window whose URL contains "timesheet.bangcle.com") '
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
