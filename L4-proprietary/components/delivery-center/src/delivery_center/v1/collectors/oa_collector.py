#!/usr/bin/env python3
"""OA 数据采集器 — 合同台账（2026-10-08 完整重写）

通过浏览器自动化访问 OA 销售合同管理系统，采集合同台账数据。
基于 9 轮调试验证的所有经验重写。

已验证的导航路径（2026-10-08）：
  1. IAM 登录 → 点击「应用入口」tab → 点击 OA 卡片中心 → 打开 OA 新标签页
  2. 关闭弹窗（.ant-modal-wrap / .wea-dialog）
  3. 点击「销售合同管理系统」→ 点击「合同基本信息管理」→ 点击「合同台账（销售）」
  4. 页面加载后，Cube iframe（frame[1]）中出现导出按钮
  5. 点击导出 → 异步生成 → 轮询进度 → 下载文件

关键经验（踩坑总结）：
  - IAM 首页必须先点「应用入口」tab，OA 卡片才渲染
  - OA 卡片用 evaluate 找，按面积排序取 candidates[1]（避开最大的外层容器）
  - OA 打开是新标签页，用 context.expect_page() 监听
  - OA 首页有弹窗遮罩，必须先关闭再操作菜单
  - 菜单项是 span，用 evaluate 点击（locator.click() 会被弹窗拦截超时）
  - 导出按钮在 Cube iframe 内，不在主页面 DOM
  - 导出按钮坐标 (1267, 11)，需要计算 iframe 偏移后用 page.mouse.click()
  - 导出是异步的，需要轮询进度弹窗，不能用 expect_download()
"""
import json
import time
import glob
from pathlib import Path
from typing import Optional

from .iam_auth import ensure_logged_in

OA_BASE = "https://oa.bangcle.com"
IAM_BASE = "https://iam.bangcle.com"
DOWNLOAD_DIR = Path.home() / ".openclaw" / "data" / "oa_exports"


def _ensure_setup():
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ensure_logged_in()


def _dismiss_dialogs(page):
    """关闭 OA 首页的弹窗/遮罩（.ant-modal-wrap / .wea-dialog）"""
    page.evaluate("""() => {
        ['.ant-modal-wrap', '.wea-dialog', '[role=dialog]', '.ant-modal', '.ant-modal-mask'].forEach(sel => {
            document.querySelectorAll(sel).forEach(el => el.remove());
        });
        // 删除所有 fixed 遮罩
        document.querySelectorAll('*').forEach(el => {
            const style = window.getComputedStyle(el);
            if (style.position === 'fixed' && parseInt(style.zIndex) > 100) {
                el.remove();
            }
        });
    }""")
    time.sleep(1)


def _click_oa_card(page, context, max_retries=3):
    """点击 IAM 首页的 OA 协同办公平台卡片，打开 OA 新标签页。

    实测：IAM 首页 OA 卡片文字为「OA 协同办公平台」，嵌套在多层 div 中。
    必须点击 cards[1]（按面积排序第二，避开最大的 1896x282 外层容器）。
    点击卡片右下角（箭头区域）最可靠。
    """
    for attempt in range(max_retries):
        # 确保在「应用入口」tab
        try:
            page.get_by_text("应用入口", exact=False).first.click()
            time.sleep(2)
        except Exception:
            pass

        # 找 OA 卡片
        card = page.evaluate("""() => {
            const candidates = [];
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
            let node;
            while (node = walker.nextNode()) {
                const text = (node.textContent || '').trim();
                if (text.includes('OA协同办公平台') && !text.includes('CRM') && !text.includes('EHR')) {
                    const rect = node.getBoundingClientRect();
                    if (rect.width > 50 && rect.height > 20 && rect.width < 600 && rect.height < 300) {
                        candidates.push({
                            x: Math.round(rect.x), y: Math.round(rect.y),
                            w: Math.round(rect.width), h: Math.round(rect.height),
                            area: rect.width * rect.height
                        });
                    }
                }
            }
            candidates.sort((a, b) => a.area - b.area);
            // 返回第二小的（避开最大的外层容器），如果只有一个就返回那个
            return candidates.length > 1 ? candidates[1] : (candidates[0] || null);
        }""")

        if not card:
            continue

        pages_before = len(context.pages)

        # 点击卡片右下角（箭头/进入区域）
        page.mouse.click(card['x'] + card['w'] - 15, card['y'] + card['h'] / 2)
        time.sleep(5)

        if len(context.pages) > pages_before:
            new_page = context.pages[-1]
            new_page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(3)
            return new_page

        # 备选：点击卡片中心
        pages_before = len(context.pages)
        page.mouse.click(card['x'] + card['w'] / 2, card['y'] + card['h'] / 2)
        time.sleep(5)

        if len(context.pages) > pages_before:
            new_page = context.pages[-1]
            new_page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(3)
            return new_page

    return None


def _click_menu_item(page, text):
    """点击左侧菜单项（用 evaluate 避免 locator 被弹窗拦截超时）"""
    _dismiss_dialogs(page)
    result = page.evaluate("""(t) => {
        const spans = document.querySelectorAll('span');
        for (const span of spans) {
            if (span.textContent.trim().includes(t)) {
                const rect = span.getBoundingClientRect();
                if (rect.x < 350 && rect.width > 50) {
                    span.click();
                    return {clicked: true, text: span.textContent.trim()};
                }
            }
        }
        return {clicked: false};
    }""", text)
    time.sleep(2)
    return result.get('clicked', False)


def _find_cube_frame(page):
    """查找 Cube iframe（URL 含 customid=179 或 cube/search）
    优先匹配 frame URL，后备检查 iframe src 属性。
    """
    # 方式1：检查 frame URL
    for frame in page.frames:
        if "customid=179" in frame.url or "cube/search" in frame.url:
            return frame

    # 方式2：后备——检查 iframe src 属性（frame 可能还未加载到 page.frames）
    iframes = page.locator("iframe")
    for i in range(iframes.count()):
        src = iframes.nth(i).get_attribute("src") or ""
        if "customid=179" in src or "cube/search" in src:
            # 等一下让 frame 加载
            time.sleep(3)
            for frame in page.frames:
                if "customid=179" in frame.url or "cube/search" in frame.url:
                    return frame
            # 如果还是找不到，返回第一个非主页面 frame
            for frame in page.frames:
                if "wui/index" not in frame.url and frame.url != "about:blank":
                    return frame

    return None


def _click_export_in_frame(page, frame):
    """在 Cube frame 中点击导出按钮（用 DOM 定位，不用坐标计算）。

    实测导出按钮在 frame 内坐标 (1267, 11)，但 bounding_box 经常超时。n    直接用 frame.locator 在 Cube iframe DOM 中找按钮更可靠。
    """
    # 方式1：用 frame.locator 直接找按钮
    export_btn = frame.locator("button").filter(has_text="导出").first
    if export_btn.count() == 0:
        # 备选：找含"导 出"（有空格）
        export_btn = frame.locator("button").filter(has_text="导 出").first
    
    if export_btn.count() > 0:
        export_btn.click()
        return True
    
    # 方式2：用 evaluate 在 frame 内点击
    result = frame.evaluate("""() => {
        const btns = document.querySelectorAll('button');
        for (const b of btns) {
            const t = b.textContent.trim();
            if (t.includes('导') && t.includes('出')) {
                b.click();
                return {ok: true, text: t};
            }
        }
        return {ok: false};
    }""")
    if result.get('ok'):
        return True
    
    # 兜底：用坐标计算
    log("  ⚠️ locator 失败，用坐标兜底")
    iframe_pos = page.evaluate("""() => {
        const iframe = document.querySelector('iframe');
        if (!iframe) return {x: 0, y: 0};
        const rect = iframe.getBoundingClientRect();
        return {x: rect.x, y: rect.y};
    }""")
    offset_x = iframe_pos['x']
    offset_y = iframe_pos['y']
    page.mouse.click(offset_x + 1296, offset_y + 26)
    return True


def _wait_for_export_complete(frame, timeout=600):
    """轮询导出进度，等待完成。

    OA 导出是异步的，进度弹窗显示「当前进度 ：N/113380%」。
    完成后弹窗中出现下载链接。
    """
    start = time.time()
    while time.time() - start < timeout:
        # 检查进度弹窗
        modal = frame.locator(".ant-modal-body")
        if modal.count() > 0:
            text = modal.first.text_content().strip()
            if "完成" in text or "下载" in text or "100%" in text:
                return True
        time.sleep(5)
    return False


def _wait_for_download(timeout=600):
    """等待下载文件出现"""
    start = time.time()
    while time.time() - start < timeout:
        files = glob.glob(str(Path.home() / "Downloads" / "*合同*"))
        if files:
            return files[0]
        files = glob.glob(str(Path.home() / "Downloads" / "*contract*"))
        if files:
            return files[0]
        time.sleep(5)
    return None


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
            # Step 1: 登录 IAM
            print("[OA] Step 1: 登录 IAM...")
            page.goto(f"{IAM_BASE}/#/login", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(2)
            page.locator("input[type=text]").first.fill("limin.ren")
            page.locator("input[type=password]").first.fill("June-123")
            page.locator("button").nth(1).click()  # button[1] = 登录
            page.wait_for_url("**/home/**", timeout=15000)
            time.sleep(5)
            print("  ✅ 登录成功")

            # Step 2: 进入 OA
            print("[OA] Step 2: 进入 OA 系统...")
            oa_page = _click_oa_card(page, context)
            if not oa_page:
                print("  ❌ 无法进入 OA")
                return None
            page = oa_page
            print(f"  ✅ OA: {page.url[:100]}")

            # Step 3: 关闭弹窗
            print("[OA] Step 3: 关闭弹窗...")
            _dismiss_dialogs(page)
            time.sleep(2)
            print("  ✅ 弹窗已关闭")

            # Step 4: 导航到合同台账
            print("[OA] Step 4: 导航到合同台账...")
            _click_menu_item(page, "销售合同管理系统")
            _click_menu_item(page, "合同基本信息管理")
            _click_menu_item(page, "合同台账")
            time.sleep(5)
            print(f"  当前 URL: {page.url[:100]}")

            # Step 5: 查找 Cube frame（需要等待异步加载）
            print("[OA] Step 5: 查找 Cube frame...")
            cube_frame = None
            for attempt in range(20):
                cube_frame = _find_cube_frame(page)
                if cube_frame:
                    print(f"  ✅ Cube frame 找到（第{attempt+1}次尝试）")
                    break
                time.sleep(3)
            
            if not cube_frame:
                print("  ❌ 未找到 Cube frame")
                print(f"  当前所有 frames:")
                for i, f in enumerate(page.frames):
                    print(f"    frame[{i}]: {f.url[:100]}")
                return None
            cube_frame.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(3)

            # Step 6: 点击导出按钮
            print("[OA] Step 6: 点击导出按钮...")
            _click_export_in_frame(page, cube_frame)
            print("  ✅ 已点击导出")

            # Step 7: 等待导出完成
            print("[OA] Step 7: 等待导出完成...")
            if _wait_for_export_complete(cube_frame, timeout=timeout):
                print("  ✅ 导出完成")
            else:
                print("  ⚠️ 导出超时，继续检查下载...")

            # Step 8: 等待下载文件
            print("[OA] Step 8: 等待下载文件...")
            downloaded = _wait_for_download(timeout=120)
            if not downloaded:
                print("  ❌ 未找到下载文件")
                return None

            # 保存文件
            output_file = output_dir / f"contract_ledger_{month}.xlsx"
            Path(downloaded).rename(output_file)
            size = output_file.stat().st_size
            print(f"  ✅ 已保存: {output_file} ({size} bytes)")

            return {
                "file": str(output_file),
                "size": size,
                "month": month,
                "source": "oa_export",
                "filename": output_file.name,
            }

        except Exception as e:
            print(f"ERROR: OA 采集失败: {e}")
            return None
        finally:
            browser.close()


def collect_contract_ledger_api(
    month: str,
    export_dir: Optional[str] = None,
) -> Optional[dict]:
    """采集销售合同台账 — 通过 API 方式（备用方案）"""
    _ensure_setup()
    output_dir = Path(export_dir) if export_dir else DOWNLOAD_DIR

    try:
        import requests as req_lib
    except ImportError:
        print("ERROR: requests 未安装")
        return None

    # 获取 cookies（简化版，不走浏览器）
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.goto(f"{IAM_BASE}/#/login", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(2)
            page.locator("input[type=text]").first.fill("limin.ren")
            page.locator("input[type=password]").first.fill("June-123")
            page.locator("button").nth(1).click()
            page.wait_for_url("**/home/**", timeout=15000)
            time.sleep(3)
            cookies = context.cookies()
            browser.close()
    except Exception as e:
        print(f"[OA-API] 获取 cookies 失败: {e}")
        return None

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
