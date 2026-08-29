"""OA 数据采集器 — 合同台账

通过浏览器自动化访问 OA 销售合同管理系统，采集合同台账数据。

SSO 流程：
  1. IAM 登录（limin.ren）
  2. 点击 OA 协同办公平台（触发 SSO 回调，新标签页）
  3. 导航到 销售合同管理系统（portal-14-5）
  4. 访问 合同台账（销售）页面（customid=179）
  5. 提取表格数据 / 导出 Excel

关键 URL：
  - 合同台账搜索页: /formmode/search/CustomSearchBySimple.jsp?customid=179
  - 重定向到: /spa/cube/index.html#/main/cube/search?customid=179
  - 菜单路径: 销售合同管理系统(14) > 合同基本信息管理(22) > 合同台账(销售)(16)
"""

import json
import time
from pathlib import Path
from typing import Optional

from .iam_auth import ensure_logged_in

OA_BASE = "https://oa.bangcle.com"
DOWNLOAD_DIR = Path.home() / ".openclaw" / "data" / "oa_exports"

# 合同台账页面 URL（Weaver 自定义搜索）
CONTRACT_LEDGER_URL = f"{OA_BASE}/formmode/search/CustomSearchBySimple.jsp?customid=179"


def _ensure_setup():
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ensure_logged_in()


def _login_iam_and_open_oa(page, context):
    """完成 IAM 登录并打开 OA 门户"""
    from playwright.sync_api import TimeoutError as PWTimeout

    # Step 1: IAM 登录
    page.goto(f"{OA_BASE.replace('oa', 'iam')}/#/login", timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(2)

    try:
        page.locator("input[type=text]").first.fill("limin.ren", timeout=5000)
        page.locator("input[type=password]").first.fill("June-123", timeout=5000)
    except PWTimeout:
        # 可能已经登录
        pass

    for btn in page.locator("button").all():
        if "登录" in (btn.text_content() or ""):
            btn.click()
            break

    page.wait_for_url("**/home/**", timeout=15000)
    time.sleep(3)

    # Step 2: 点击 OA 协同办公平台
    oa_el = page.get_by_text("OA协同办公平台", exact=False)
    if oa_el.count() == 0:
        raise RuntimeError("OA 入口未找到，可能未登录 IAM")

    oa_el.first.click()
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(5)

    # Step 3: 切换到 OA 新标签页
    pages = context.pages
    if len(pages) > 1:
        return pages[-1]

    return page


def collect_contract_ledger(
    month: str,
    export_dir: Optional[str] = None,
    headless: bool = True,
) -> Optional[dict]:
    """采集销售合同台账数据

    Args:
        month: 报告月份（YYYYMM）
        export_dir: 导出目录（默认 ~/.openclaw/data/oa_exports）
        headless: 是否无头模式

    Returns:
        {"rows": [...], "count": N, "file": "path"} 或 None
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
            args=["--disable-blink-features=AutomationControlled"] if headless else [],
        )
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            # SSO 登录
            page = _login_iam_and_open_oa(page, context)

            # Step 4: 导航到合同台账页面
            print(f"[OA] 导航到合同台账: {CONTRACT_LEDGER_URL}")
            page.goto(CONTRACT_LEDGER_URL, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(10)

            final_url = page.url
            print(f"[OA] 最终 URL: {final_url}")

            if "login" in final_url or "iam" in final_url:
                print("ERROR: SSO 认证失败，被重定向到登录页")
                return None

            # Step 5: 提取表格数据
            body = page.text_content("body") or ""
            if len(body) < 500:
                print("ERROR: 页面未正确渲染")
                return None

            # 提取表格行
            rows = page.evaluate("""
                function() {
                    var trs = document.querySelectorAll('table tbody tr');
                    var results = [];
                    for (var i = 0; i < trs.length; i++) {
                        var tds = trs[i].querySelectorAll('td');
                        var row = [];
                        for (var j = 0; j < tds.length; j++) {
                            row.push(tds[j].textContent.trim());
                        }
                        if (row.some(function(v) { return v.length > 0; })) {
                            results.push(row);
                        }
                    }
                    return {count: trs.length, rows: results};
                }
            """)

            row_count = rows.get("count", 0)
            row_data = rows.get("rows", [])
            print(f"[OA] 提取到 {row_count} 行数据")

            if row_count == 0:
                print("WARNING: 表格无数据，可能页面结构变化")
                return None

            # Step 6: 提取表头
            headers = page.evaluate("""
                function() {
                    var ths = document.querySelectorAll('th');
                    var results = [];
                    for (var i = 0; i < ths.length; i++) {
                        var text = ths[i].textContent.trim();
                        if (text) results.push(text);
                    }
                    return results;
                }
            """)
            print(f"[OA] 表头: {len(headers)} 列")

            # Step 7: 保存数据
            result = {
                "month": month,
                "source": "oa_contract_ledger",
                "url": final_url,
                "headers": headers,
                "rows": row_data,
                "count": row_count,
                "file": None,
            }

            # 保存 JSON
            output_file = output_dir / f"contract_ledger_{month}.json"
            output_file.write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            result["file"] = str(output_file)
            print(f"[OA] 数据已保存: {output_file}")

            # Step 8: 尝试导出 Excel
            export_btn = page.get_by_text("导出", exact=False)
            if export_btn.count() > 0:
                print("[OA] 发现导出按钮，尝试导出 Excel...")
                # TODO: 实现 Excel 导出（需要处理下载对话框）

            return result

        except Exception as e:
            print(f"ERROR: OA 采集失败: {e}")
            return None
        finally:
            browser.close()


def get_pending_approvals() -> Optional[list]:
    """获取待审批流程列表（待实现）"""
    print("TODO: OA 待审批流程获取")
    return None


if __name__ == "__main__":
    import sys
    month = sys.argv[1] if len(sys.argv) > 1 else "202608"
    result = collect_contract_ledger(month, headless=True)
    if result:
        print(f"\n=== 采集完成 ===")
        print(f"月份: {result['month']}")
        print(f"行数: {result['count']}")
        print(f"文件: {result['file']}")
    else:
        print("\n=== 采集失败 ===")
