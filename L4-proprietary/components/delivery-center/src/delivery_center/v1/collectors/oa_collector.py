#!/usr/bin/env python3
"""OA 数据采集器 — 合同台账（2026-10-10 headless 稳定化重构）

通过浏览器自动化访问 OA 销售合同管理系统，采集合同台账数据。

## headless=True 模式核心修复（本次重构）

1. **下载路径**：用 Playwright 原生 `expect_download()` 接管下载，不再扫描
   `~/Downloads` 通配符（headless 下不可靠且文件可能残留旧数据）。
2. **Cookie 复用**：headless 下优先复用 `iam_auth` 的 Cookie 池，避免每次完整
   登录触发验证码/SSO 校验。
3. **菜单点击**：不再依赖 `rect.x < 350` 像素阈值（headless 默认 viewport
   下左侧菜单可能折叠），改为优先按"可见 + 在左半屏 + 文本匹配"语义判断。
4. **iframe 等待**：用 `wait_for_selector("iframe")` 替代纯 `time.sleep()` 轮询。
5. **导出按钮**：仍然走 frame 内 locator/evaluate，但点击后用
   `expect_download()` 监听（异步导出 + 下载链接 二段流程也能 cover，
   因为最终下载链接点击是同步动作）。
6. **常量补齐**：补回 `_CONTRACT_LEDGER_CUSTOMID = "179"`，修复
   `tests/test_collectors.py` ImportError。

## 已验证的导航路径（2026-10-08）

  1. IAM 登录 → 点击「应用入口」tab → 点击 OA 卡片中心 → 打开 OA 新标签页
  2. 关闭弹窗（.ant-modal-wrap / .wea-dialog）
  3. 点击「销售合同管理系统」→「合同基本信息管理」→「合同台账（销售）」
  4. 页面加载后，Cube iframe（frame URL 含 customid=179）中出现导出按钮
  5. 点击导出 → 异步生成 → 点击下载链接 → 浏览器触发下载

## 调用方式

  python -m delivery_center.v1.collectors.oa_collector 202610
  python -m delivery_center.v1.collectors.oa_collector 202610 --headless
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Optional

from .iam_auth import (
    ensure_logged_in,
    inject_cookies_to_context,
    is_cookie_valid,
    iam_credentials,
)

OA_BASE = "https://oa.bangcle.com"
IAM_BASE = "https://iam.bangcle.com"
DOWNLOAD_DIR = Path.home() / ".openclaw" / "data" / "oa_exports"

# 合同台账 Cube 报表 ID（仅用于 frame 识别，不用于 URL 跳转）
_CONTRACT_LEDGER_CUSTOMID = "179"

# IAM 凭据只从 ~/.openclaw/secrets 读取（禁止硬编码明文）
_IAM_USERNAME, _IAM_PASSWORD = iam_credentials()


def _ensure_setup():
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    # headless 模式下若 Cookie 失效会重新走完整登录
    ensure_logged_in()


def _dismiss_dialogs(page):
    """关闭 OA 首页的弹窗/遮罩（.ant-modal-wrap / .wea-dialog）。"""
    try:
        page.evaluate(
            """() => {
                ['.ant-modal-wrap', '.wea-dialog', '[role=dialog]',
                 '.ant-modal', '.ant-modal-mask'].forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => el.remove());
                });
                document.querySelectorAll('*').forEach(el => {
                    const style = window.getComputedStyle(el);
                    if (style.position === 'fixed' && parseInt(style.zIndex) > 100) {
                        el.remove();
                    }
                });
            }"""
        )
    except Exception:
        pass  # headless 下页面可能仍在加载，evaluate 失败可容忍
    time.sleep(1)


def _inject_cookies(context) -> bool:
    """把 iam_auth Cookie 池注入到 Playwright context。

    返回 True 表示注入成功，调用方可以跳过表单登录。
    """
    try:
        return bool(inject_cookies_to_context(context))
    except Exception:
        return False


def _login_iam(page, context, headless: bool) -> bool:
    """登录 IAM。优先复用 Cookie，失败再走表单。"""
    # 先访问首页，看 Cookie 是否生效
    page.goto(f"{IAM_BASE}/#/home", timeout=30000)
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    time.sleep(2)

    # Cookie 已生效 → 不在登录页
    if "/login" not in page.url:
        print("  ✅ Cookie 复用，跳过表单登录")
        return True

    # Cookie 失效 → 走表单登录
    print("  ℹ️  Cookie 失效，走表单登录")
    page.goto(f"{IAM_BASE}/#/login", timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(2)
    page.locator("input[type=text]").first.fill(_IAM_USERNAME)
    page.locator("input[type=password]").first.fill(_IAM_PASSWORD)
    page.locator("button").nth(1).click()  # button[1] = 登录

    page.wait_for_url("**/home/**", timeout=20000)
    time.sleep(3)
    return True


def _click_oa_card(page, context, max_retries: int = 3):
    """点击 IAM 首页的 OA 协同办公平台卡片，返回新打开的 OA Page。"""
    for attempt in range(max_retries):
        try:
            page.get_by_text("应用入口", exact=False).first.click()
            time.sleep(2)
        except Exception:
            pass

        card = page.evaluate(
            """() => {
                const candidates = [];
                const walker = document.createTreeWalker(
                    document.body, NodeFilter.SHOW_ELEMENT);
                let node;
                while (node = walker.nextNode()) {
                    const text = (node.textContent || '').trim();
                    if (text.includes('OA协同办公平台')
                            && !text.includes('CRM')
                            && !text.includes('EHR')) {
                        const rect = node.getBoundingClientRect();
                        if (rect.width > 50 && rect.height > 20
                                && rect.width < 600 && rect.height < 300) {
                            candidates.push({
                                x: Math.round(rect.x), y: Math.round(rect.y),
                                w: Math.round(rect.width), h: Math.round(rect.height),
                                area: rect.width * rect.height,
                            });
                        }
                    }
                }
                candidates.sort((a, b) => a.area - b.area);
                return candidates.length > 1 ? candidates[1]
                                             : (candidates[0] || null);
            }"""
        )
        if not card:
            time.sleep(2)
            continue

        pages_before = len(context.pages)
        # 点击右下角（箭头区）→ 中心点 兜底
        for cx, cy in [
            (card["x"] + card["w"] - 15, card["y"] + card["h"] / 2),
            (card["x"] + card["w"] / 2, card["y"] + card["h"] / 2),
        ]:
            page.mouse.click(cx, cy)
            time.sleep(5)
            if len(context.pages) > pages_before:
                new_page = context.pages[-1]
                try:
                    new_page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                time.sleep(2)
                return new_page
    return None


def _click_menu_item(page, text: str, max_retries: int = 3) -> bool:
    """点击左侧菜单项。

    headless 修复：
      - 旧逻辑 `rect.x < 350` 在小 viewport / 折叠菜单下失效；
      - 改为「可见 + 文本匹配 + 不在右侧主内容区」语义判断；
      - 折叠时先尝试展开侧边栏（点击 .menu-fold / trigger 按钮）。
    """
    _dismiss_dialogs(page)

    # 如果侧边栏折叠，先尝试展开
    try:
        page.evaluate(
            """() => {
                const triggers = document.querySelectorAll(
                    '.ant-menu-inline-collapsed-trigger,'
                    + ' .menu-fold,'
                    + ' [class*="menu-trigger"],'
                    + ' [class*="collapse-trigger"]');
                triggers.forEach(t => t.click());
            }"""
        )
        time.sleep(1)
    except Exception:
        pass

    for _ in range(max_retries):
        result = page.evaluate(
            """(t) => {
                const spans = document.querySelectorAll('span');
                const vw = window.innerWidth;
                for (const span of spans) {
                    if (!span.textContent.trim().includes(t)) continue;
                    const rect = span.getBoundingClientRect();
                    // 必须可见
                    if (rect.width === 0 || rect.height === 0) continue;
                    // 在左半屏（viewport 适配，不写死 350px）
                    if (rect.x > vw * 0.5) continue;
                    span.click();
                    return { clicked: true, text: span.textContent.trim(),
                             x: rect.x, vw };
                }
                return { clicked: false };
            }""",
            text,
        )
        if result.get("clicked"):
            time.sleep(2)
            return True
        time.sleep(1)
    return False


def _find_cube_frame(page, timeout_s: int = 60):
    """等待并查找 Cube iframe（URL 含 customid=179 或 cube/search）。

    headless 修复：先 wait_for_selector 等 iframe 挂载，再轮询 frames。
    """
    start = time.time()
    # 先等 iframe 元素出现在 DOM 里
    try:
        page.wait_for_selector("iframe", timeout=15000)
    except Exception:
        pass

    while time.time() - start < timeout_s:
        # 方式 1：page.frames
        for frame in page.frames:
            if _CONTRACT_LEDGER_CUSTOMID in frame.url or "cube/search" in frame.url:
                return frame

        # 方式 2：iframe[src] 属性（frame 还没注册到 page.frames）
        try:
            iframes = page.locator("iframe")
            for i in range(iframes.count()):
                src = iframes.nth(i).get_attribute("src") or ""
                if _CONTRACT_LEDGER_CUSTOMID in src or "cube/search" in src:
                    # 再轮询一次 frames
                    time.sleep(2)
                    for frame in page.frames:
                        if (_CONTRACT_LEDGER_CUSTOMID in frame.url
                                or "cube/search" in frame.url):
                            return frame
        except Exception:
            pass

        time.sleep(3)

    # 兜底：返回第一个非主页面 frame
    for frame in page.frames:
        if "wui/index" not in frame.url and frame.url != "about:blank":
            return frame
    return None


def _click_export_in_frame(page, frame) -> bool:
    """在 Cube frame 中点击导出按钮。"""
    # 方式 1：frame.locator 找按钮
    for text in ("导出", "导 出"):
        try:
            btn = frame.locator("button").filter(has_text=text).first
            if btn.count() > 0:
                btn.click()
                return True
        except Exception:
            pass

    # 方式 2：frame.evaluate
    try:
        result = frame.evaluate(
            """() => {
                const btns = document.querySelectorAll('button');
                for (const b of btns) {
                    const t = b.textContent.trim();
                    if (t.includes('导') && t.includes('出')) {
                        b.click();
                        return { ok: true, text: t };
                    }
                }
                return { ok: false };
            }"""
        )
        if result.get("ok"):
            return True
    except Exception:
        pass

    # 兜底：frame 内任何含"导出"的可点击元素
    try:
        result = frame.evaluate(
            """() => {
                const els = document.querySelectorAll('a, span, div, button');
                for (const el of els) {
                    const t = (el.textContent || '').trim();
                    if (t === '导出' || t === '导 出') {
                        el.click();
                        return { ok: true, text: t };
                    }
                }
                return { ok: false };
            }"""
        )
        if result.get("ok"):
            return True
    except Exception:
        pass

    return False


def _wait_for_export_ready(frame, timeout: int = 600) -> bool:
    """轮询导出进度，等待下载链接出现。

    OA 导出是异步生成 → 完成后弹窗内出现下载链接（通常是 <a>下载</a>）。
    """
    start = time.time()
    while time.time() - start < timeout:
        try:
            # 检查弹窗是否含 完成 / 下载 / 100%
            modal = frame.locator(".ant-modal-body")
            if modal.count() > 0:
                text = (modal.first.text_content() or "").strip()
                if ("完成" in text) or ("下载" in text) or ("100%" in text):
                    return True
        except Exception:
            pass
        time.sleep(5)
    return False


def _click_download_link(frame) -> bool:
    """在导出完成弹窗中点击下载链接，触发浏览器下载事件。"""
    try:
        result = frame.evaluate(
            """() => {
                // 优先 <a> 含"下载"或 href 含 file/download
                const links = document.querySelectorAll('a');
                for (const a of links) {
                    const t = (a.textContent || '').trim();
                    const href = a.getAttribute('href') || '';
                    if (t.includes('下载')
                            || href.includes('download')
                            || href.includes('.xlsx')
                            || href.includes('.csv')) {
                        a.click();
                        return { ok: true, text: t, href };
                    }
                }
                // 兜底：button 含"下载"
                const btns = document.querySelectorAll('button');
                for (const b of btns) {
                    const t = (b.textContent || '').trim();
                    if (t.includes('下载')) {
                        b.click();
                        return { ok: true, text: t };
                    }
                }
                return { ok: false };
            }"""
        )
        return bool(result.get("ok"))
    except Exception:
        return False


def collect_contract_ledger_xlsx(
    month: str,
    export_dir: Optional[str] = None,
    headless: bool = False,
    timeout: int = 600,
) -> Optional[dict]:
    """采集销售合同台账 — 通过 OA 自带导出功能生成 XLSX。

    Args:
        month:      报告月份（YYYYMM）
        export_dir: 导出目录（默认 ~/.openclaw/data/oa_exports）
        headless:   是否无头模式（本版本已修复 headless 下载问题）
        timeout:    导出超时秒数（默认 600s）

    Returns:
        {"file": "path", "size": N, "month": "YYYYMM", ...} 或 None
    """
    _ensure_setup()
    output_dir = Path(export_dir) if export_dir else DOWNLOAD_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: Playwright 未安装")
        return None

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            # headless 下 --start-maximized 无效；显式给 args 即可
            args=[] if headless else ["--start-maximized"],
        )
        context = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1920, "height": 1080},  # headless 下也固定 viewport
        )
        page = context.new_page()

        try:
            # Step 1: 注入 Cookie + 登录 IAM
            print(f"[OA] Step 1: 登录 IAM (headless={headless})...")
            _inject_cookies(context)
            if not _login_iam(page, context, headless):
                print("  ❌ IAM 登录失败")
                return None
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
            if not _click_menu_item(page, "销售合同管理系统"):
                print("  ⚠️  未点到「销售合同管理系统」")
            if not _click_menu_item(page, "合同基本信息管理"):
                print("  ⚠️  未点到「合同基本信息管理」")
            if not _click_menu_item(page, "合同台账"):
                print("  ⚠️  未点到「合同台账」")
            time.sleep(5)
            print(f"  当前 URL: {page.url[:100]}")

            # Step 5: 查找 Cube frame
            print("[OA] Step 5: 查找 Cube frame...")
            cube_frame = _find_cube_frame(page, timeout_s=90)
            if not cube_frame:
                print("  ❌ 未找到 Cube frame")
                print("  当前所有 frames:")
                for i, f in enumerate(page.frames):
                    print(f"    frame[{i}]: {f.url[:100]}")
                return None
            print(f"  ✅ Cube frame: {cube_frame.url[:100]}")
            try:
                cube_frame.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            time.sleep(3)

            # Step 6: 点击导出按钮
            print("[OA] Step 6: 点击导出按钮...")
            if not _click_export_in_frame(page, cube_frame):
                print("  ❌ 未找到导出按钮")
                return None
            print("  ✅ 已点击导出")

            # Step 7: 等导出进度完成 + 用 expect_download 捕获下载
            print("[OA] Step 7: 等待导出完成并捕获下载...")
            output_file = output_dir / f"contract_ledger_{month}.xlsx"

            # headless 修复：用 expect_download 替代 ~/Downloads glob
            # 两个动作并发：(a) 等导出进度 ready (b) 等下载链接出现并点击
            # 用 Playwright 的 context manager 监听 download
            try:
                with page.expect_download(timeout=timeout * 1000) as download_info:
                    # 等导出进度 ready
                    if not _wait_for_export_ready(cube_frame, timeout=timeout):
                        print("  ⚠️  导出进度等待超时，仍尝试点下载链接...")
                    # 点击弹窗内的"下载"链接，触发浏览器下载
                    if not _click_download_link(cube_frame):
                        print("  ❌ 未找到下载链接")
                        return None
                download = download_info.value
                download.save_as(str(output_file))
            except Exception as e:
                # 某些 OA 版本点导出后会直接触发下载（无中间弹窗）
                # 此时 expect_download 在点击导出时已结束，下面做兜底
                print(f"  ⚠️  expect_download 流程异常: {e}")
                print("  ℹ️  尝试兜底：重新挂 expect_download 后再点一次导出")
                try:
                    with page.expect_download(timeout=120_000) as download_info:
                        _click_export_in_frame(page, cube_frame)
                    download = download_info.value
                    download.save_as(str(output_file))
                except Exception as e2:
                    print(f"  ❌ 兜底下载也失败: {e2}")
                    return None

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
            import traceback
            traceback.print_exc()
            return None
        finally:
            try:
                context.close()
            except Exception:
                pass
            browser.close()


def collect_contract_ledger_api(
    month: str,
    export_dir: Optional[str] = None,
) -> Optional[dict]:
    """采集销售合同台账 — 通过 API 方式（备用方案，已 headless）。"""
    _ensure_setup()
    output_dir = Path(export_dir) if export_dir else DOWNLOAD_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        import requests as req_lib
    except ImportError:
        print("ERROR: requests 未安装")
        return None

    # 通过 headless Playwright 获取 cookies（API 模式始终 headless）
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            _inject_cookies(context)
            page = context.new_page()
            if not _login_iam(page, context, headless=True):
                print("[OA-API] 登录失败")
                browser.close()
                return None
            cookies = context.cookies()
            browser.close()
    except Exception as e:
        print(f"[OA-API] 获取 cookies 失败: {e}")
        return None

    cookie_dict = {c["name"]: c["value"] for c in cookies}

    session = req_lib.Session()
    session.cookies.update(cookie_dict)
    session.headers.update({
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36"),
        "Referer": OA_BASE + "/",
        "x-requested-with": "XMLHttpRequest",
    })

    all_rows = []
    page_num = 1
    page_size = 200

    print("[OA-API] 开始采集合同台账数据...")

    while True:
        resp = session.post(
            f"{OA_BASE}/api/cube/search/getList",
            data=(f"customid={_CONTRACT_LEDGER_CUSTOMID}&guid=search"
                  f"&page={page_num}&pageSize={page_size}"
                  f"&sortField=&sortOrder="),
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
    parser = argparse.ArgumentParser(description="OA 合同台账采集")
    parser.add_argument("month", nargs="?", default="202608", help="报告月份 YYYYMM")
    parser.add_argument("--headless", action="store_true",
                        help="启用无头模式（默认 headful）")
    parser.add_argument("--api", action="store_true",
                        help="跳过 XLSX 导出，直接走 API 备用方案")
    args = parser.parse_args()

    print("=== OA 合同台账采集 ===")
    print(f"月份: {args.month}  headless: {args.headless}")
    print()

    result = None
    if not args.api:
        print("[模式] XLSX 导出（OA 自带导出功能）")
        result = collect_contract_ledger_xlsx(args.month, headless=args.headless)

    if not result:
        if not args.api:
            print("\n=== XLSX 导出失败，回退到 API 方式 ===")
        result = collect_contract_ledger_api(args.month)

    if result:
        print("\n=== 采集完成 ===")
        print(f"文件: {result['file']}")
        if "size" in result:
            print(f"大小: {result['size']} bytes")
        if "count" in result:
            print(f"条数: {result['count']}")
    else:
        print("\n=== 采集失败 ===")
