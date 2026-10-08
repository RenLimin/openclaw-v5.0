"""ONES 数据源适配器 — 浏览器自动化 + CSV 缓存。

对齐 DESIGN-DETAIL-INTEGRATION-v2.1.md §6.1 + 复用 delivery-center ones_export_auto.py 验证过的方案。
ONES 连接器优先从 CSV 缓存读取，缓存缺失时触发浏览器自动化导出。
"""
from __future__ import annotations

import csv
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from bdms.core.paths import ones_dir

logger = logging.getLogger(__name__)


class MissingSourceError(Exception):
    """数据源缺失异常。当月数据不可用且无法自动提取时抛出。"""
    pass


class OnesAdapter:
    """ONES 项目管理数据源适配器。

    数据来源降级链：
    1. 本机文件（最高优先级，手动指定）
    2. 缓存 CSV（ones_exports 目录）
    3. 浏览器自动化导出（osascript 控制 Chrome，复用 ones_export_auto.py 验证过的选择器）
    4. 失败报错
    """

    # ONES 导出筛选器配置（tab_index 对应 .url-foldable-tabs-new-link 索引）
    FILTERS = {
        "sign": {
            "label": "签约项目统计",
            "tab_index": 7,
            "output_csv": "签约项目统计.csv",
            "month_prefix": True,  # 月份前缀匹配
        },
        "poc": {
            "label": "POC&提前实施统计",
            "tab_index": 8,
            "output_csv": "poc_提前实施.csv",
            "month_prefix": True,
        },
        "abnormal": {
            "label": "异常处置",
            "tab_index": 10,
            "output_csv": "异常处置.csv",
            "month_prefix": False,
        },
    }

    def __init__(self, timeout: int = 60):
        """
        Args:
            timeout: osascript 执行超时（秒）
        """
        self._cache_dir = ones_dir()
        self._timeout = timeout
        self._downloads_dir = Path.home() / "Downloads"

    def fetch(self, filter_name: str, month: str, use_cache: bool = True,
              file_path: str = None) -> List[Dict[str, Any]]:
        """获取 ONES 数据。

        Args:
            filter_name: sign | poc | abnormal | revenue | acceptance
            month: YYYYMM 格式
            use_cache: 是否使用缓存
            file_path: 本机文件路径（可选，最高优先级）

        Returns:
            List[Dict] 原始数据

        Raises:
            MissingSourceError: 数据源不可用
        """
        # 1. 本机文件
        if file_path and Path(file_path).exists():
            return self._read_csv(Path(file_path))

        # 2. 查找缓存 CSV
        if use_cache:
            csv_path = self._find_csv(filter_name, month)
            if csv_path:
                return self._read_csv(csv_path)

        # 3. 浏览器自动化导出（仅 macOS + darwin）
        if sys.platform == "darwin" and filter_name in self.FILTERS:
            exported = self._export_from_browser(filter_name, month)
            if exported:
                return exported

        # 4. 报错
        filter_config = self.FILTERS.get(filter_name, {})
        filter_label = filter_config.get("label", filter_name)
        raise MissingSourceError(
            f"ONES {filter_label} {month} 数据不可用。缓存不存在且浏览器自动化导出失败。"
            f"请手动导出 {filter_label} 数据到 {self._cache_dir}"
        )

    def _find_csv(self, filter_name: str, month: str) -> Optional[Path]:
        """查找当月缓存 CSV。"""
        filter_config = self.FILTERS.get(filter_name)
        if not filter_config:
            # revenue/acceptance 走 month_dir 查找
            return self._find_in_month_dir(month, filter_name)

        # 在 ones_exports 目录查找
        # 优先匹配带月份前缀的文件
        if filter_config.get("month_prefix"):
            month_file = self._cache_dir / f"{month}周报-{filter_config['output_csv']}"
            if month_file.exists():
                return month_file
            # 回退：不带月份前缀的通用名
            generic = self._cache_dir / filter_config["output_csv"]
            if generic.exists():
                return generic
        else:
            # 异常处置：匹配 {month}-签约项目异常处置.csv
            month_file = self._cache_dir / f"{month}-{filter_config['output_csv']}"
            if month_file.exists():
                return month_file
            generic = self._cache_dir / filter_config["output_csv"]
            if generic.exists():
                return generic

        # 回退前月
        try:
            prev_month = f"{int(month) - 1:06d}"
            if filter_config.get("month_prefix"):
                prev_file = self._cache_dir / f"{prev_month}周报-{filter_config['output_csv']}"
                if prev_file.exists():
                    return prev_file
            else:
                prev_file = self._cache_dir / f"{prev_month}-{filter_config['output_csv']}"
                if prev_file.exists():
                    return prev_file
        except (ValueError, IndexError):
            pass

        return None

    def _find_in_month_dir(self, month: str, filter_name: str) -> Optional[Path]:
        """在 month_dir 中查找 revenue/acceptance CSV。"""
        from bdms.core.paths import month_dir
        d = month_dir(month)
        if not d.exists():
            return None
        if filter_name == "revenue":
            for f in d.glob(f"{month}*确收*.csv"):
                if "验收" not in f.name:
                    return f
        elif filter_name == "acceptance":
            for f in d.glob(f"{month}*验收*.csv"):
                return f
        return None

    def _read_csv(self, path: Path) -> List[Dict[str, Any]]:
        """读取 CSV 文件。"""
        with open(path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            return [{k: row.get(k, "") for k in reader.fieldnames} for row in reader]

    # ─── 浏览器自动化导出（复用 ones_export_auto.py 验证过的方案）───

    def _run_js(self, js_code: str) -> str:
        """通过 osascript 在 Chrome ONES 标签中执行 JavaScript。

        使用临时文件传递 JS，避免 AppleScript 引号嵌套问题。
        """
        # 写 JS 到临时文件
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.js', delete=False, encoding='utf-8'
        ) as js_f:
            js_f.write(js_code)
            js_path = js_f.name

        # 写 AppleScript 到临时文件
        apple_script = (
            'on run argv\n'
            '  set jsFile to item 1 of argv\n'
            '  set jsStr to read POSIX file jsFile\n'
            '  tell application "Google Chrome"\n'
            '    set onsTab to (first tab of window 1 whose URL contains "ones.bangcle.com")\n'
            '    execute onsTab JavaScript jsStr\n'
            '  end tell\n'
            'end run'
        )
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.scpt', delete=False, encoding='utf-8'
        ) as scpt_f:
            scpt_f.write(apple_script)
            scpt_path = scpt_f.name

        try:
            result = subprocess.run(
                ["osascript", scpt_path, js_path],
                capture_output=True, text=True, timeout=self._timeout
            )
            if result.returncode != 0:
                logger.warning(f"osascript 错误: {result.stderr.strip()[:200]}")
                return ""
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            logger.warning(f"osascript 超时 ({self._timeout}s)")
            return ""
        except Exception as e:
            logger.warning(f"osascript 异常: {e}")
            return ""
        finally:
            os.unlink(js_path)
            os.unlink(scpt_path)

    def _export_from_browser(self, filter_name: str, month: str) -> Optional[List[Dict[str, Any]]]:
        """通过浏览器自动化从 ONES 导出数据。

        复用 ones_export_auto.py 验证过的选择器：
        - 筛选器子 tab: .url-foldable-tabs-new-link
        - 更多菜单: .more-menu-icon
        - 导出菜单项: .ones-dropdown-menu-item-content（文本匹配）
        - 确认按钮: button（文本匹配「确定」）
        """
        filter_config = self.FILTERS[filter_name]
        tab_index = filter_config["tab_index"]
        output_csv = filter_config["output_csv"]

        logger.info(f"开始浏览器自动化导出 ONES {filter_config['label']} (tab={tab_index})...")

        try:
            # Step 1: 确保 Chrome 已打开 ONES
            if not self._ensure_ones_tab():
                return None

            # Step 2: 点击筛选器子 tab
            self._click_filter_tab(tab_index)
            time.sleep(5)

            # Step 3: 点击更多菜单
            self._click_more_menu()
            time.sleep(1)

            # Step 4: 点击导出工作项
            self._click_export_item()
            time.sleep(3)

            # Step 5: 点击确认
            self._click_confirm()
            time.sleep(1)

            # Step 6: 等待下载完成
            downloaded = self._wait_for_download(timeout=180)
            if not downloaded:
                return None

            # Step 7: 复制到缓存目录
            cached = self._cache_dir / output_csv
            shutil.move(str(downloaded), str(cached))
            logger.info(f"导出成功: {cached} ({cached.stat().st_size:,} bytes)")
            return self._read_csv(cached)

        except Exception as e:
            logger.warning(f"浏览器自动化导出失败: {e}")
            return None

    def _ensure_ones_tab(self) -> bool:
        """确保 Chrome 已打开 ONES 标签页。"""
        try:
            result = subprocess.run(
                [
                    "osascript", "-e",
                    'tell application "Google Chrome" to (count of (every tab of every window whose URL contains "ones.bangcle.com"))'
                ],
                capture_output=True, text=True, timeout=10
            )
            count = int(result.stdout.strip())
            if count == 0:
                logger.warning("ONES 标签页未打开，尝试打开...")
                subprocess.run(
                    ["osascript", "-e",
                     'tell application "Google Chrome" to open location "https://ones.bangcle.com/project/#/workspace/home"'],
                    timeout=10
                )
                time.sleep(10)
            return True
        except Exception as e:
            logger.warning(f"检查 ONES 标签页失败: {e}")
            return False

    def _click_filter_tab(self, tab_index: int) -> bool:
        """点击筛选器子 tab（.url-foldable-tabs-new-link）。"""
        js = f"""
        (function() {{
            var tabs = document.querySelectorAll('.url-foldable-tabs-new-link');
            if (tabs.length > {tab_index}) {{
                tabs[{tab_index}].click();
                return 'clicked index {tab_index}: ' + tabs[{tab_index}].innerText;
            }}
            return 'not found, count=' + tabs.length;
        }})()
        """
        result = self._run_js(js)
        logger.info(f"筛选器 tab 点击: {result}")
        return "clicked" in result.lower()

    def _click_more_menu(self) -> bool:
        """点击更多菜单图标（.more-menu-icon）。"""
        js = """
        (function() {
            var icon = document.querySelector('.more-menu-icon');
            if (icon) {
                icon.click();
                return 'clicked more-menu-icon';
            }
            return 'more-menu-icon not found';
        })()
        """
        result = self._run_js(js)
        logger.info(f"更多菜单: {result}")
        return "clicked" in result.lower()

    def _click_export_item(self) -> bool:
        """点击导出工作项（.ones-dropdown-menu-item-content + 文本匹配）。"""
        js = """
        (function() {
            var items = document.querySelectorAll('.ones-dropdown-menu-item-content');
            for (var i = 0; i < items.length; i++) {
                var text = items[i].innerText || '';
                if (text.indexOf('导出') >= 0 && text.indexOf('工作项') >= 0) {
                    items[i].click();
                    return 'clicked: ' + text + ' (index ' + i + ')';
                }
            }
            return 'export item not found, count=' + items.length;
        })()
        """
        result = self._run_js(js)
        logger.info(f"导出菜单项: {result}")
        return "clicked" in result.lower()

    def _click_confirm(self) -> bool:
        """点击确认按钮（文本匹配「确定」或「确认」）。"""
        js = """
        (function() {
            var buttons = document.querySelectorAll('button');
            for (var i = 0; i < buttons.length; i++) {
                var text = (buttons[i].innerText || '').trim();
                if (text === '确定' || text === '确认') {
                    buttons[i].click();
                    return 'clicked: ' + text + ' (index ' + i + ')';
                }
            }
            return 'confirm button not found, count=' + buttons.length;
        })()
        """
        result = self._run_js(js)
        logger.info(f"确认按钮: {result}")
        return "clicked" in result.lower()

    def _wait_for_download(self, timeout: int = 180) -> Optional[Path]:
        """等待下载完成。"""
        logger.info(f"等待下载完成（最多 {timeout}s）...")
        before = set(self._downloads_dir.glob("*.csv"))
        before_times = {f: f.stat().st_mtime for f in before}

        for _ in range(timeout // 3):
            time.sleep(3)
            after = set(self._downloads_dir.glob("*.csv"))
            new_files = after - before
            if new_files:
                latest = max(new_files, key=lambda f: f.stat().st_mtime)
                time.sleep(2)
                if latest.stat().st_size > 0:
                    logger.info(f"下载完成: {latest.name} ({latest.stat().st_size:,} bytes)")
                    return latest
            # 检查已有文件是否更新
            for f in self._downloads_dir.glob("*.csv"):
                if f in before_times and f.stat().st_mtime > before_times[f] + 5:
                    logger.info(f"文件更新: {f.name} ({f.stat().st_size:,} bytes)")
                    return f

        logger.warning("下载超时")
        return None
