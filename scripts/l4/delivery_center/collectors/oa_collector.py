"""OA 数据采集器 — 合同台账

通过浏览器自动化访问 OA 销售合同管理系统，采集合同台账数据。
使用 OA 自带导出功能（doExcelExpost API）生成 XLSX 文件。

导出流程（已实测验证 2026-08-31）：
  1. IAM 登录 → OA 协同办公平台
  2. 导航到合同台账页面（customid=179）
  3. 点击"导出"按钮 → OA 后台异步生成 XLSX
  4. page.expect_download() 拦截下载事件
  5. 保存到 DOWNLOAD_DIR

技术要点：
  - headful 模式（headless 无法拦截下载事件）
  - 导出按钮在 cube iframe 内（customid=179 页面）
  - 导出 API: POST /api/cube/search/doExcelExpost
  - 进度轮询: GET /api/cube/search/getExcelExpProgress
  - 下载链接只能通过浏览器 JS 事件获取，requests 无法替代

关键 URL：
  - 合同台账页面: /spa/cube/index.html#/main/cube/search?customid=179
  - IAM 登录: https://iam.bangcle.com/#/login
"""

import json
import time
from pathlib import Path
from typing import Optional

from .iam_auth import ensure_logged_in

OA_BASE = "https://oa.bangcle.com"
IAM_BASE = "https://iam.bangcle.com"
DOWNLOAD_DIR = Path.home() / ".openclaw" / "data" / "oa_exports"

# 合同台账页面 URL（直接导航，不走 OA 首页避免 SSO 回调卡住）
CONTRACT_LEDGER_URL = f"{OA_BASE}/spa/cube/index.html#/main/cube/search?customid=179"


def _ensure_setup():
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ensure_logged_in()


def _login_iam_and_get_cookies(headless: bool = False) -> list:
    """登录 IAM 并返回 cookies"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()

        page.goto(f"{IAM_BASE}/#/login", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(2)

        page.locator("input[type=text]").first.fill("limin.ren", timeout=5000)
        page.locator("input[type=password]").first.fill("June-123", timeout=5000)

        for btn in page.locator("button").all():
            if "登录" in (btn.text_content() or ""):
                btn.click()
                break

        page.wait_for_url("**/home/**", timeout=15000)
        time.sleep(3)

        # 点击 OA 协同办公平台
        oa_el = page.get_by_text("OA协同办公平台", exact=False)
        if oa_el.count() > 0:
            oa_el.first.click()
            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(5)

        cookies = context.cookies()
        browser.close()
        return cookies


def collect_contract_ledger_xlsx(
    month: str,
    export_dir: Optional[str] = None,
    headless: bool = False,
    timeout: int = 600,
) -> Optional[dict]:
    """采集销售合同台账 — 通过 OA 自带导出功能生成 XLSX

    Args:
        month: 报告月份（YYYYMM）
        export_dir: 导出目录（默认 ~/.openclaw/data/oa_exports）
        headless: 是否无头模式（默认 False，headful 才能拦截下载）
        timeout: 导出超时秒数（默认 600s）

    Returns:
        {"file": "path", "size": N, "month": "YYYYMM"} 或 None
    """
    _ensure_setup()
    output_dir = Path(export_dir) if export_dir else DOWNLOAD_DIR

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: Playwright 未安装")
        return None

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--start-maximized"] if not headless else [],
        )
        context = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()

        try:
            # Step 1: IAM 登录 + 跳转 OA
            print("[OA] Step 1: 登录 IAM...")
            page = _login_iam_and_open_oa_page(page, context)

            # Step 2: 导航到合同台账
            print(f"[OA] Step 2: 导航到合同台账 (customid=179)...")
            page.goto(CONTRACT_LEDGER_URL, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(15)

            final_url = page.url
            print(f"[OA] 页面就绪: {final_url[:80]}")

            if "login" in final_url or "iam" in final_url:
                print("ERROR: SSO 认证失败")
                return None

            # Step 3: 点击导出按钮
            print("[OA] Step 3: 点击导出按钮...")
            export_btn = page.locator("button.ant-btn-primary", has_text="导 出")
            if export_btn.count() == 0:
                print("ERROR: 未找到导出按钮")
                return None

            # Step 4: 等待下载
            print("[OA] Step 4: 等待下载...")
            try:
                with page.expect_download(timeout=timeout * 1000) as download_info:
                    export_btn.first.click()
                    print("[OA] 已点击导出，等待下载事件...")

                download = download_info.value
                suggested = download.suggested_filename
                print(f"[OA] 下载事件触发! 文件名: {suggested}")

                # 保存文件
                output_file = output_dir / f"contract_ledger_{month}.xlsx"
                download.save_as(str(output_file))
                size = output_file.stat().st_size
                print(f"[OA] 已保存: {output_file} ({size} bytes)")

                return {
                    "file": str(output_file),
                    "size": size,
                    "month": month,
                    "source": "oa_export",
                    "filename": suggested,
                }
            except Exception as e:
                print(f"[OA] 下载超时或失败: {e}")
                # 检查弹窗状态
                modal = page.locator(".ant-modal-body")
                if modal.count() > 0:
                    print(f"[OA] 弹窗: {modal.first.text_content().strip()}")
                return None

        except Exception as e:
            print(f"ERROR: OA 采集失败: {e}")
            return None
        finally:
            browser.close()


def _login_iam_and_open_oa_page(page, context):
    """登录 IAM 并打开 OA，返回 OA 页面"""
    from playwright.sync_api import TimeoutError as PWTimeout

    page.goto(f"{IAM_BASE}/#/login", timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(2)

    try:
        page.locator("input[type=text]").first.fill("limin.ren", timeout=5000)
        page.locator("input[type=password]").first.fill("June-123", timeout=5000)
    except PWTimeout:
        pass

    for btn in page.locator("button").all():
        if "登录" in (btn.text_content() or ""):
            btn.click()
            break

    page.wait_for_url("**/home/**", timeout=15000)
    time.sleep(3)

    oa_el = page.get_by_text("OA协同办公平台", exact=False)
    if oa_el.count() > 0:
        oa_el.first.click()
        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(5)

        pages = context.pages
        if len(pages) > 1:
            return pages[-1]

    return page


def collect_contract_ledger_api(
    month: str,
    export_dir: Optional[str] = None,
) -> Optional[dict]:
    """采集销售合同台账 — 通过 API 方式（备用方案）

    使用 OA 的 table/datas 接口直接获取 JSON 数据。
    注意：API 方式客户名称等字段返回 ID 而非显示文本。

    Args:
        month: 报告月份（YYYYMM）
        export_dir: 导出目录

    Returns:
        {"file": "path", "count": N, "month": "YYYYMM"} 或 None
    """
    _ensure_setup()
    output_dir = Path(export_dir) if export_dir else DOWNLOAD_DIR

    try:
        import requests as req_lib
    except ImportError:
        print("ERROR: requests 未安装")
        return None

    # 获取 cookies
    cookies = _login_iam_and_get_cookies(headless=True)
    cookie_dict = {c["name"]: c["value"] for c in cookies}

    session = req_lib.Session()
    session.cookies.update(cookie_dict)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": OA_BASE + "/",
        "x-requested-with": "XMLHttpRequest",
    })

    all_rows = []
    page_num = 1
    page_size = 200

    print(f"[OA-API] 开始采集合同台账数据...")

    while True:
        resp = session.post(
            f"{OA_BASE}/api/cube/search/getList",
            data=f"customid=179&guid=search&page={page_num}&pageSize={page_size}&sortField=&sortOrder=",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )

        if resp.status_code != 200:
            print(f"[OA-API] 请求失败: {resp.status_code}")
            break

        data = resp.json()
        datas = data.get("datas", [])

        if not datas:
            break

        all_rows.extend(datas)
        total = data.get("total", 0)

        print(f"[OA-API] 页 {page_num}: {len(datas)} 条, 累计 {len(all_rows)}/{total}")

        if len(all_rows) >= total or len(datas) < page_size:
            break

        page_num += 1

    if not all_rows:
        print("[OA-API] 无数据")
        return None

    # 保存 JSON
    output_file = output_dir / f"contract_ledger_{month}_api.json"
    result = {
        "month": month,
        "source": "oa_api",
        "count": len(all_rows),
        "file": str(output_file),
        "note": "API 方式：客户名称等字段为 ID 值，非显示文本",
    }
    output_file.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[OA-API] 采集完成: {len(all_rows)} 条, 保存到 {output_file}")
    return result


def get_pending_approvals() -> Optional[list]:
    """获取待审批流程列表（待实现）"""
    print("TODO: OA 待审批流程获取")
    return None


if __name__ == "__main__":
    import sys
    month = sys.argv[1] if len(sys.argv) > 1 else "202608"

    print("=== OA 合同台账采集 ===")
    print(f"月份: {month}")
    print()

    # 优先使用 XLSX 导出方式
    print("[模式] XLSX 导出（OA 自带导出功能）")
    result = collect_contract_ledger_xlsx(month, headless=False)

    if result:
        print(f"\n=== 采集完成 ===")
        print(f"文件: {result['file']}")
        print(f"大小: {result['size']} bytes")
    else:
        print("\n=== XLSX 导出失败，回退到 API 方式 ===")
        result = collect_contract_ledger_api(month)
        if result:
            print(f"\n=== 采集完成（API 方式） ===")
            print(f"文件: {result['file']}")
            print(f"条数: {result['count']}")
        else:
            print("\n=== 采集失败 ===")
