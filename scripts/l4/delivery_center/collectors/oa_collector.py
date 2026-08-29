"""OA 数据采集器

通过浏览器自动化访问 OA 系统。
注意：OA 通过 IAM 认证，复用 IAM Cookie。

重要：OA 首页有独立的 SSO 流程，Playwright 中会卡在 IAM 回调。
解决方案：不访问 OA 首页，直接导航到目标子页面。

导航路径：
  合同台账：直接访问 OA 子页面（SPA 路由）
  工时门户：/spa/custom/static/index.html#/main/cs/app/9dec836e590a4ad79488c9bb7ef7401e_hoursRoot
"""

from pathlib import Path
from typing import Optional

from .iam_auth import ensure_logged_in, inject_cookies_to_context

OA_BASE = "https://oa.bangcle.com"
DOWNLOAD_DIR = Path.home() / ".openclaw" / "data" / "oa_exports"

# OA 合同台账页面路径（待确认实际路径）
# 已知：OA 使用 SPA 路由，左侧菜单"销售合同管理系统 > 合同基本信息管理 > 合同台账（销售）"
CONTRACT_LEDGER_PATH = "/spa/custom/static/index.html#/main/cs/app/contractRoot"


def _ensure_setup():
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ensure_logged_in()


def collect_contract_ledger(month: str, export_dir: Optional[str] = None) -> Optional[str]:
    """导出销售合同信息查询台账

    注意：不访问 OA 首页，直接访问合同台账子页面。

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

        # 注入 Cookie
        inject_cookies_to_context(context)

        page = context.new_page()

        try:
            # 直接访问合同台账子页面（绕过首页 SSO）
            # TODO: 确认合同台账的实际 SPA 路由路径
            page.goto(f"{OA_BASE}{CONTRACT_LEDGER_PATH}", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)

            # 检查是否需要登录
            if "iam" in page.url or "login" in page.url:
                print("Cookie 过期或无效，需要重新登录")
                return None

            # TODO: 确认导出按钮选择器
            print(f"OA 合同台账页面已加载: {page.url}")
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
