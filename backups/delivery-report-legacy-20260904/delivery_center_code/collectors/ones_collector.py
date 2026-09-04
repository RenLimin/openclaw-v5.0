"""ONES 数据采集器

通过 Playwright 浏览器自动化访问 ONES 系统，导出项目数据。

登录流程：
  1. 优先使用已保存的 cookie（~/.openclaw/data/oa_exports/ones_auth.json）
  2. Cookie 过期时，用邮箱密码自动登录（limin.ren@bangcle.com）
  3. 登录成功后保存 cookie 供后续复用

ONES 认证方式（两种方案）：
  1. IAM SSO（推荐）：IAM 登录后点击 ONES 面板 → 打开新标签页 → 经过 OA shell 中转 → ONES 自动认证
  2. 邮箱密码（备用）：直接访问 ONES 登录页，输入 limin.ren@bangcle.com / March-123
  - 认证成功后 ONES 设置 ones-lt cookie（= token）
  - 注意：面板点击用 context.on('page') 监听，不能手动检查 context.pages

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


def _navigate_to_filter(page, filter_name: str) -> bool:
    """导航到指定筛选器（通过 我的工作台 → 筛选器 tab）

    操作步骤：
    1. 点击左侧菜单 '我的工作台'
    2. 点击右侧 '筛选器' tab
    3. 点击对应筛选器子 tab（如 '2026周报-签约项目'）
    """
    # 筛选器名称 → tab 显示名称映射
    filter_tab_map = {
        "2026周报-签约项目统计": "2026周报-签约项目",
        "2026周报-POC&提前实施统计": "2026周报-POC&提前实施",
        "2026-签约项目异常处置": "2026-签约项目异常处置",
    }
    tab_name = filter_tab_map.get(filter_name, filter_name)

    # Step 1: 点击左侧 '我的工作台'
    print(f"  [导航] 点击 '我的工作台'...")
    try:
        workspace_link = page.locator('a, span, div').filter(has_text='我的工作台').first
        if workspace_link.count() > 0:
            workspace_link.click()
            time.sleep(3)
        else:
            # 直接导航
            page.goto(f"{ONES_BASE}/project/#/workspace", timeout=20000)
            time.sleep(5)
    except Exception as e:
        print(f"  [警告] 点击工作台失败: {e}，尝试直接导航")
        page.goto(f"{ONES_BASE}/project/#/workspace", timeout=20000)
        time.sleep(5)

    # Step 2: 点击 '筛选器' tab
    print(f"  [导航] 点击 '筛选器' tab...")
    try:
        filter_tab = page.locator('[role=tab], [class*=tab], a, span, div').filter(has_text='筛选器').first
        if filter_tab.count() > 0:
            filter_tab.click()
            time.sleep(3)
        else:
            print("  [警告] 未找到 '筛选器' tab")
    except Exception as e:
        print(f"  [警告] 点击筛选器失败: {e}")

    # Step 3: 点击具体筛选器子 tab
    print(f"  [导航] 点击 '{tab_name}'...")
    try:
        sub_tab = page.locator('[role=tab], [class*=tab], a, span, div, li').filter(has_text=tab_name).first
        if sub_tab.count() > 0:
            sub_tab.click()
            time.sleep(5)
        else:
            print(f"  [警告] 未找到 '{tab_name}'，尝试部分匹配")
            sub_tab = page.locator('a, span, div, li').filter(has_text=tab_name[:6]).first
            if sub_tab.count() > 0:
                sub_tab.click()
                time.sleep(5)
    except Exception as e:
        print(f"  [警告] 点击子 tab 失败: {e}")

    return True


def _click_export(page, timeout: int = 30) -> Optional[str]:
    """点击导出按钮并等待下载

    操作步骤：
    1. 点击 ONES 功能菜单中的 '导出原始数据'
    2. 等待弹窗出现
    3. 点击 '确认' 按钮
    4. 等待下载完成

    Returns:
        下载文件路径或 None
    """
    print("  [导出] 点击 '导出原始数据'...")

    # 尝试多种方式找到导出按钮
    export_selectors = [
        'text=导出原始数据',
        'text=导出',
        '[class*=export]',
        '[class*=Export]',
        'button:has-text("导出")',
        'span:has-text("导出")',
        'div:has-text("导出")',
    ]

    for selector in export_selectors:
        try:
            btn = page.locator(selector).first
            if btn.count() > 0 and btn.is_visible():
                print(f"  [导出] 找到按钮: {selector}")
                with page.expect_download(timeout=timeout * 1000) as download_info:
                    btn.click()
                download = download_info.value
                suggested = download.suggested_filename
                download_path = EXPORT_DIR / suggested
                download.save_as(str(download_path))
                print(f"  [导出] 下载完成: {download_path}")
                return str(download_path)
        except Exception:
            continue

    # 如果上面的选择器都没找到，尝试通过功能菜单
    print("  [导出] 尝试通过功能菜单导出...")
    try:
        # 点击更多/功能菜单
        menu_btn = page.locator('[class*=more], [class*=menu], [class*=action]').first
        if menu_btn.count() > 0:
            menu_btn.click()
            time.sleep(1)
            # 再次查找导出按钮
            export_btn = page.locator('text=导出原始数据, text=导出').first
            if export_btn.count() > 0:
                with page.expect_download(timeout=timeout * 1000) as download_info:
                    export_btn.click()
                download = download_info.value
                download.save_as(str(EXPORT_DIR / download.suggested_filename))
                return str(EXPORT_DIR / download.suggested_filename)
    except Exception as e:
        print(f"  [导出] 导出失败: {e}")

    return None


def collect(filter_name: str, export_dir: Optional[str] = None) -> Optional[str]:
    """导出指定筛选器的数据（通过 ONES 自带导出功能）

    操作流程（基于人工操作截图）：
    1. 登录 ONES
    2. 点击左侧 '我的工作台'
    3. 点击右侧 '筛选器' tab
    4. 点击具体筛选器子 tab（如 '2026周报-签约项目'）
    5. 点击 '导出原始数据'
    6. 点击弹窗 '确认'
    7. 等待下载完成

    Args:
        filter_name: 筛选器名称
        export_dir: 导出目录

    Returns:
        导出的 CSV 文件路径
    """
    _ensure_setup()
    output_dir = Path(export_dir) if export_dir else EXPORT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        print(f"依赖未安装: {e}")
        return None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True, viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        try:
            # Step 1: 登录
            print(f"[ONES] Step 1: 登录...")
            if not _ensure_ones_logged_in(context, page):
                print("❌ ONES 登录失败")
                return None

            # Step 2-4: 导航到筛选器
            print(f"[ONES] Step 2-4: 导航到筛选器...")
            if not _navigate_to_filter(page, filter_name):
                return None

            # Step 5-7: 点击导出并等待下载
            print(f"[ONES] Step 5-7: 导出数据...")
            download_path = _click_export(page, timeout=60)
            if download_path:
                print(f"✅ ONES 采集完成: {download_path}")
                return download_path
            else:
                print("❌ 导出失败")
                return None

        except Exception as e:
            print(f"❌ ONES 采集异常: {e}")
            import traceback
            traceback.print_exc()
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


def load_ones_abnormal_projects() -> "pd.DataFrame":
    """加载 ONES 异常项目数据

    优先从已保存的 JSON 文件加载（快速），
    如果文件不存在则通过 ONES API 采集。

    Returns:
        异常项目 DataFrame
    """
    import urllib.request
    import urllib.error
    import pandas as pd

    # 方案1: 从已保存的 JSON 文件加载
    json_file = EXPORT_DIR / "ones_projects_api.json"
    if json_file.exists():
        all_projects = json.loads(json_file.read_text(encoding="utf-8"))
    else:
        # 方案2: 通过 ONES API 采集
        AUTH_FILE = Path.home() / ".openclaw" / "data" / "oa_exports" / "ones_auth.json"
        data = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
        cookies = data.get("cookies", [])
        cookie_str = "; ".join(f'{c["name"]}={c["value"]}' for c in cookies)

        url = "https://ones.bangcle.com/project/api/project/auth/login"
        payload = json.dumps({"email": "limin.ren@bangcle.com", "password": "March-123"}).encode()
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Cookie", cookie_str)
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read().decode())
        token = result["user"]["token"]
        user_id = result["user"]["uuid"]

        headers = {
            "Ones-User-Id": user_id,
            "Ones-Auth-Token": token,
            "Referer": "https://ones.bangcle.com/",
            "Content-Type": "application/json",
        }
        graphql_url = "https://ones.bangcle.com/project/api/project/team/RZxvwUZ8/items/graphql"

        all_projects = []
        offset = 0
        page_size = 200
        while True:
            query = f'{{ projects(limit: {page_size}, offset: {offset}) {{ uuid name type status {{ name }} owner {{ name }} createTime }} }}'
            gq = json.dumps({"query": query}).encode()
            req = urllib.request.Request(graphql_url, data=gq, method="POST", headers=headers)
            resp = urllib.request.urlopen(req, timeout=30)
            body = json.loads(resp.read().decode())
            projects = body.get("data", {}).get("projects", [])
            if not projects:
                break
            all_projects.extend(projects)
            offset += page_size
            if len(projects) < page_size:
                break

    # 筛选异常项目
    abnormal = [p for p in all_projects if p.get("status", {}).get("name") == "项目异常"]

    # 转换为 DataFrame
    df = pd.DataFrame(abnormal)
    if not df.empty:
        df["status_name"] = df["status"].apply(lambda x: x.get("name", "") if isinstance(x, dict) else "")
        df["owner_name"] = df["owner"].apply(lambda x: x.get("name", "") if isinstance(x, dict) else "")
        df = df.drop(columns=["status", "owner"], errors="ignore")
        df = df.rename(columns={"status_name": "状态", "owner_name": "项目经理", "uuid": "项目UUID", "name": "项目名称", "type": "类型", "createTime": "创建时间"})

    return df


if __name__ == "__main__":
    import sys
    filter_name = sys.argv[1] if len(sys.argv) > 1 else "2026周报-签约项目统计"
    result = collect(filter_name)
    if result:
        print(f"\n=== 导出完成 ===")
        print(f"文件: {result}")
    else:
        print("\n=== 导出失败 ===")
