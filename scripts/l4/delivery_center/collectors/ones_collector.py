"""ONES 数据采集器

通过 Playwright 浏览器自动化访问 ONES 系统，导出项目数据。
3 个筛选器：
  1. 2026周报-签约项目统计
  2. 2026周报-POC&提前实施统计
  3. 2026-签约项目异常处置
"""

from pathlib import Path
from typing import Optional

from .iam_auth import ensure_logged_in, get_cookie

ONES_BASE = "https://ones.bangcle.com"
EXPORT_DIR = Path.home() / ".openclaw" / "data" / "ones_exports"

# 3 个筛选器配置
FILTERS = [
    {"name": "2026周报-签约项目统计", "filter_id": ""},
    {"name": "2026周报-POC&提前实施统计", "filter_id": ""},
    {"name": "2026-签约项目异常处置", "filter_id": ""},
]


def _ensure_setup():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    ensure_logged_in()


def collect(filter_name: str, export_dir: Optional[str] = None) -> Optional[str]:
    """导出指定筛选器的数据

    Args:
        filter_name: 筛选器名称
        export_dir: 导出目录

    Returns:
        导出的 CSV 文件路径
    """
    _ensure_setup()
    output_dir = Path(export_dir) if export_dir else EXPORT_DIR

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright 未安装")
        return None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            page.goto(ONES_BASE, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)

            # 检查是否需要登录
            if "iam" in page.url or "login" in page.url:
                ensure_logged_in()
                cookie = get_cookie("ones.bangcle.com")
                if cookie:
                    for item in cookie.split("; "):
                        if "=" in item:
                            k, v = item.split("=", 1)
                            context.add_cookies([{"name": k, "value": v, "domain": ".bangcle.com", "path": "/"}])
                    page.goto(ONES_BASE, timeout=30000)
                    page.wait_for_load_state("networkidle", timeout=15000)

            # TODO: 导航到筛选器并导出
            print(f"ONES 导出路径待确认: {filter_name}")
            return None

        except Exception as e:
            print(f"ONES 导出失败: {e}")
            return None
        finally:
            browser.close()


def collect_all(export_dir: Optional[str] = None) -> list[str]:
    """导出所有筛选器的数据

    Returns:
        导出的文件路径列表
    """
    results = []
    for f in FILTERS:
        path = collect(f["name"], export_dir)
        if path:
            results.append(path)
    return results
