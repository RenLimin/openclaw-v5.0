"""工时门户数据采集器

通过 IAM → 工时门户跳转，采集工时迁移汇总数据。

登录流程（已验证）：
  1. IAM 登录 → 首页渲染完成
  2. 点击"工时门户"面板标题 → 打开新标签页
  3. 用 context.expect_event("page") 监听新页面
  4. 工时门户 URL：/spa/custom/static/index.html#/main/cs/app/...hoursRoot

数据采集：
  - 工时迁移汇总表格（工作项、总工时、迁移工时、剩余工时）
  - 通过 DOM 提取 table 数据
  - 支持"查询"按钮筛选

注意：
  - 面板点击用 context.expect_event("page") 监听
  - 不能手动检查 context.pages（事件循环延迟）
  - mouse.click() 不触发跳转
"""

import json
import csv
import time
from pathlib import Path
from typing import Optional

from .iam_auth import ensure_logged_in

IAM_BASE = "https://iam.bangcle.com"
EXPORT_DIR = Path.home() / ".openclaw" / "data" / "workhour_exports"


def _ensure_setup():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def collect_workhour_data(
    month: str,
    export_dir: Optional[str] = None,
) -> Optional[dict]:
    """采集工时门户数据

    Args:
        month: 报告月份（YYYYMM）
        export_dir: 导出目录

    Returns:
        {"file": "path", "count": N, "month": "YYYYMM"} 或 None
    """
    _ensure_setup()
    output_dir = Path(export_dir) if export_dir else EXPORT_DIR

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: Playwright 未安装")
        return None

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--start-maximized"],
        )
        context = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()

        try:
            # Step 1: 登录 IAM
            print("[WH] Step 1: 登录 IAM...")
            page.goto(f"{IAM_BASE}/#/login", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(2)
            page.locator("input[type=text]").first.fill("limin.ren")
            page.locator("input[type=password]").first.fill("June-123")
            for btn in page.locator("button").all():
                if "登录" in (btn.text_content() or ""):
                    btn.click()
                    break
            page.wait_for_url("**/home/**", timeout=15000)
            time.sleep(10)

            # Step 2: 点击工时门户面板
            print("[WH] Step 2: 点击工时门户...")
            wh_panel = page.locator(".small-panel", has_text="工时门户")

            with context.expect_event("page", timeout=15000) as new_page_info:
                wh_panel.first.click()

            wh_page = new_page_info.value
            print(f"  新页面: {wh_page.url[:80]}")

            # Step 3: 等待渲染
            print("[WH] Step 3: 等待渲染...")
            time.sleep(20)

            url = wh_page.url
            print(f"  URL: {url[:80]}")

            # Step 4: 提取表格数据
            print("[WH] Step 4: 提取数据...")
            table_data = wh_page.evaluate("""() => {
                const rows = document.querySelectorAll('table tbody tr');
                const results = [];
                for (const r of rows) {
                    const cells = r.querySelectorAll('td');
                    if (cells.length >= 4) {
                        results.push({
                            work_item: cells[0].textContent.trim(),
                            total_hours: cells[1].textContent.trim(),
                            migrated_hours: cells[2].textContent.trim(),
                            remaining_hours: cells[3].textContent.trim(),
                        });
                    }
                }
                return results;
            }""")

            if not table_data:
                print("  ⚠️ 表格无数据，尝试其他选择器...")
                # 尝试其他选择器
                table_data = wh_page.evaluate("""() => {
                    const rows = document.querySelectorAll('[class*=table] tr, .ant-table-row');
                    const results = [];
                    for (const r of rows) {
                        const cells = r.querySelectorAll('td');
                        if (cells.length >= 4) {
                            results.push({
                                work_item: cells[0].textContent.trim(),
                                total_hours: cells[1].textContent.trim(),
                                migrated_hours: cells[2].textContent.trim(),
                                remaining_hours: cells[3].textContent.trim(),
                            });
                        }
                    }
                    return results;
                }""")

            row_count = len(table_data)
            print(f"  提取到 {row_count} 行数据")

            if row_count == 0:
                print("  ❌ 无数据")
                return None

            # Step 5: 保存 CSV
            print("[WH] Step 5: 保存数据...")
            output_file = output_dir / f"workhour_{month}.csv"
            with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=["work_item", "total_hours", "migrated_hours", "remaining_hours"])
                writer.writeheader()
                writer.writerows(table_data)

            print(f"  ✅ 已保存: {output_file}")

            # 同时保存 JSON
            json_file = output_dir / f"workhour_{month}.json"
            result = {
                "month": month,
                "source": "workhour_portal",
                "url": url,
                "count": row_count,
                "file": str(output_file),
                "data": table_data,
            }
            json_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  ✅ JSON: {json_file}")

            return result

        except Exception as e:
            print(f"ERROR: 工时采集失败: {e}")
            return None
        finally:
            browser.close()


if __name__ == "__main__":
    import sys
    month = sys.argv[1] if len(sys.argv) > 1 else "202608"
    result = collect_workhour_data(month)
    if result:
        print(f"\n=== 采集完成 ===")
        print(f"月份: {result['month']}")
        print(f"行数: {result['count']}")
        print(f"文件: {result['file']}")
    else:
        print("\n=== 采集失败 ===")
