"""ONES 数据采集器

通过 Playwright 浏览器自动化访问 ONES 系统，导出项目数据。

登录流程：
  1. 优先使用已保存的 cookie（~/.openclaw/data/oa_exports/ones_auth.json）
  2. Cookie 过期时，用邮箱密码自动登录（limin.ren@bangcle.com）
  3. 登录成功后保存 cookie 供后续复用

ONES 认证方式：
  - ONES 不支持 IAM SSO 直接跳转（前端路由可跳，但后端 API 需要独立认证）
  - 需要通过 ONES 自己的登录页（邮箱+密码）完成认证
  - 认证成功后 ONES 设置 ones-lt cookie（= token）

3 个筛选器：
  1. 2026周报-签约项目统计
  2. 2026周报-POC&提前实施统计
  3. 2026-签约项目异常处置
"""

import json
import time
from pathlib import Path
from typing import Optional

from .iam_auth import ensure_logged_in, get_cookie, set_cookie, login_ones

ONES_BASE = "https://ones.bangcle.com"
EXPORT_DIR = Path.home() / ".openclaw" / "data" / "ones_exports"
AUTH_FILE = Path.home() / ".openclaw" / "data" / "oa_exports" / "ones_auth.json"

# 3 个筛选器配置（filter_id 待探索后填充）
FILTERS = [
    {"name": "2026周报-签约项目统计", "filter_id": ""},
    {"name": "2026周报-POC&提前实施统计", "filter_id": ""},
    {"name": "2026-签约项目异常处置", "filter_id": ""},
]


def _ensure_setup():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def _load_ones_cookies() -> list[dict]:
    """加载已保存的 ONES cookie"""
    if AUTH_FILE.exists():
        data = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
        return data.get("cookies", [])
    return []


def _inject_cookies(context, cookies: list[dict]):
    """注入 cookie 到 Playwright context"""
    for c in cookies:
        try:
            context.add_cookies([{
                "name": c["name"],
                "value": c["value"],
                "domain": c.get("domain", ".ones.bangcle.com"),
                "path": c.get("path", "/"),
                "secure": c.get("secure", True),
                "httpOnly": c.get("httpOnly", True),
            }])
        except Exception:
            pass


def _is_ones_authenticated(page) -> bool:
    """检查 ONES 是否已认证"""
    body = page.evaluate("() => document.body.innerText")
    return "工作台" in body or "交付中心" in body


def _ensure_ones_logged_in(context, page):
    """确保 ONES 已登录"""
    # 尝试用保存的 cookie
    cookies = _load_ones_cookies()
    if cookies:
        _inject_cookies(context, cookies)
        page.goto(f"{ONES_BASE}/project/", timeout=30000)
        time.sleep(15)
        if _is_ones_authenticated(page):
            print("[ONES] ✅ Cookie 认证成功")
            return True
        print("[ONES] ⚠️ Cookie 已过期，重新登录...")
    
    # Cookie 不可用，用邮箱密码登录
    print("[ONES] 邮箱密码登录...")
    if login_ones("limin.ren@bangcle.com", "March-123"):
        cookies = _load_ones_cookies()
        _inject_cookies(context, cookies)
        return True
    
    return False


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
            # 确保 ONES 登录
            if not _ensure_ones_logged_in(context, page):
                print("❌ ONES 登录失败")
                return None

            # TODO: 导航到筛选器并导出
            print(f"[ONES] 导出路径待确认: {filter_name}")
            return None

        except Exception as e:
            print(f"❌ ONES 导出失败: {e}")
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


if __name__ == "__main__":
    import sys
    filter_name = sys.argv[1] if len(sys.argv) > 1 else "2026周报-签约项目统计"
    result = collect(filter_name)
    if result:
        print(f"\n=== 导出完成 ===")
        print(f"文件: {result}")
    else:
        print("\n=== 导出失败 ===")
