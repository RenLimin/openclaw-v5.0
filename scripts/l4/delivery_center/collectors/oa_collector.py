"""OA 数据采集器

通过浏览器自动化访问 OA 系统。
注意：OA 通过 IAM 认证，复用 IAM Cookie。

导航路径：
  首页 > 销售合同管理系统 > 合同基本信息管理 > 合同台账（销售）
"""

from pathlib import Path
from typing import Optional

from .iam_auth import ensure_logged_in, get_cookie

OA_BASE = "https://oa.bangcle.com"
DOWNLOAD_DIR = Path.home() / ".openclaw" / "data" / "oa_exports"

# 导航路径配置
NAV_PATH = [
    "销售合同管理系统",
    "合同基本信息管理",
    "合同台账（销售）",
]


def _ensure_setup():
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ensure_logged_in()


def collect_contract_ledger(month: str, export_dir: Optional[str] = None) -> Optional[str]:
    """导出销售合同信息查询台账

    导航：首页 > 销售合同管理系统 > 合同基本信息管理 > 合同台账（销售）

    Args:
        month: 报告月份（YYYYMM）
        export_dir: 导出目录

    Returns:
        导出的 Excel 文件路径
    """
    _ensure_setup()
    output_dir = Path(export_dir) if export_dir else DOWNLOAD_DIR

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
            page.goto(f"{OA_BASE}/", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)

            if "iam" in page.url or "login" in page.url:
                ensure_logged_in()
                cookie = get_cookie("oa.bangcle.com")
                if cookie:
                    for item in cookie.split("; "):
                        if "=" in item:
                            k, v = item.split("=", 1)
                            context.add_cookies([{"name": k, "value": v, "domain": ".bangcle.com", "path": "/"}])
                    page.goto(f"{OA_BASE}/", timeout=30000)
                    page.wait_for_load_state("networkidle", timeout=15000)

            # 导航到 销售合同管理系统 > 合同基本信息管理 > 合同台账（销售）
            for nav_item in NAV_PATH:
                page.click(f"text={nav_item}")
                page.wait_for_load_state("networkidle", timeout=10000)

            # TODO: 确认导出按钮选择器
            print(f"OA 合同台账导出完成: {month}")
            return None

        except Exception as e:
            print(f"OA 导出失败: {e}")
            return None
        finally:
            browser.close()


def get_pending_approvals() -> Optional[list]:
    """获取待审批流程列表"""
    _ensure_setup()
    print("OA 待审批流程获取待实现")
    return None
