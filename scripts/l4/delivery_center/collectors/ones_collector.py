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


def _extract_table_data(page) -> list[dict]:
    """从 ONES 项目列表页面提取表格数据（DOM 提取）"""
    data = page.evaluate("""() => {
        // 获取表头
        const headers = [];
        document.querySelectorAll('th, .ones-table-header-cell, [class*=header] [class*=cell]').forEach(th => {
            const text = th.textContent.trim();
            if (text && !headers.includes(text)) headers.push(text);
        });

        // 获取数据行
        const rows = [];
        document.querySelectorAll('tr, .ones-table-row, [class*=row]').forEach(tr => {
            const cells = tr.querySelectorAll('td, [class*=cell]');
            if (cells.length >= 5) {
                const row = {};
                cells.forEach((cell, i) => {
                    const key = headers[i] || `col_${i}`;
                    row[key] = cell.textContent.trim();
                });
                rows.push(row);
            }
        });

        return {headers, rows};
    }""")
    return data.get("rows", [])


def _navigate_to_filter(page, filter_name: str) -> bool:
    """导航到指定筛选器"""
    filter_map = {
        "2026周报-签约项目统计": {"project_type": "签约项目"},
        "2026周报-POC&提前实施统计": {"project_type": "POC、提前实施"},
        "2026-签约项目异常处置": {"project_type": "签约项目", "status": "异常"},
    }
    config = filter_map.get(filter_name, {})
    if not config:
        print(f"[ONES] 未知筛选器: {filter_name}")
        return False

    # 导航到项目列表
    page.goto(f"{ONES_BASE}/project/#/home/project", timeout=30000)
    time.sleep(8)

    # 如果有项目类型筛选
    if "project_type" in config:
        try:
            # 点击"筛选"按钮
            filter_btn = page.locator('text=筛选').first
            if filter_btn.count() > 0:
                filter_btn.click()
                time.sleep(2)
                # 选择项目类型
                type_input = page.locator('[placeholder*="项目类型"], [placeholder*="类型"]').first
                if type_input.count() > 0:
                    type_input.click()
                    time.sleep(1)
                    type_input.fill(config["project_type"])
                    time.sleep(1)
                    page.keyboard.press("Enter")
                    time.sleep(3)
        except Exception as e:
            print(f"[ONES] 筛选设置异常: {e}")

    return True


def collect(filter_name: str, export_dir: Optional[str] = None) -> Optional[str]:
    """导出指定筛选器的数据（DOM 提取 + 分页遍历）

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
        import csv
    except ImportError as e:
        print(f"依赖未安装: {e}")
        return None

    all_rows = []
    page_num = 1
    max_pages = 50  # 安全上限

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True, viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        try:
            # 确保 ONES 登录
            if not _ensure_ones_logged_in(context, page):
                print("❌ ONES 登录失败")
                return None

            # 导航到筛选器
            print(f"[ONES] 导航到筛选器: {filter_name}")
            if not _navigate_to_filter(page, filter_name):
                return None

            # 分页提取数据
            while page_num <= max_pages:
                print(f"[ONES] 提取第 {page_num} 页...")
                time.sleep(3)

                rows = _extract_table_data(page)
                if not rows:
                    print(f"[ONES] 第 {page_num} 页无数据，停止")
                    break

                all_rows.extend(rows)
                print(f"[ONES] 累计 {len(all_rows)} 行")

                # 尝试翻页
                next_btn = page.locator('[class*=next], [class*=pagination] [class*=next], text=下一页').first
                if next_btn.count() > 0 and next_btn.is_enabled():
                    next_btn.click()
                    time.sleep(3)
                    page_num += 1
                else:
                    print(f"[ONES] 无更多页")
                    break

        except Exception as e:
            print(f"❌ ONES 采集异常: {e}")
            if not all_rows:
                return None
        finally:
            browser.close()

    if not all_rows:
        print("❌ ONES 未采集到数据")
        return None

    # 保存 CSV
    output_path = output_dir / f"{filter_name}.csv"
    headers = list(all_rows[0].keys())
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"✅ ONES 采集完成: {len(all_rows)} 行 → {output_path}")
    return str(output_path)


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
