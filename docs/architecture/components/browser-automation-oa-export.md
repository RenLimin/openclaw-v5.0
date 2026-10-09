# 浏览器自动化：OA系统全流程导出方法论

## 概述

本文档总结浏览器自动化从OA系统导出合同台账的完整方法论，适用于企业内部多iframe SPA系统浏览器自动化采集/导出场景。

---

## 一、核心设计原则

### 1. 环境隔离

**规则：** 永远不要操作用户正在使用的Chrome会话，必须使用独立Chrome实例进行自动化操作。

**实现方案：**
- 命令行启动独立Chrome：
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/Users/bangcle/.chrome-automation-profile \
  --no-first-run --disable-extensions --disable-sync \
  --disable-background-networking --disable-gpu \
  https://iam.bangcle.com/#/login
```
- 使用 `--user-data-dir` 指定独立用户配置目录，完全隔离用户数据
- Playwright 通过 `connect_over_cdp("http://127.0.0.1:9222")` 连接，不启动新浏览器
- 不影响用户现有Chrome会话，用户可以正常浏览其他网页

### 2. 等待策略

**规则：** 企业SPA系统加载慢，异步渲染，必须给足加载时间。

| 操作 | 建议等待时间 | 说明 |
|---|---|---|
| 点击菜单 | 8-10秒 | 等待子菜单展开或新页面加载 |
| 点击后跳转 | 5-10秒 | 等待异步路由跳转 |
| 目标页面完全加载 | 60秒+ | 大数据表格需要更长时间渲染DOM |
| 导出进度轮询 | 10秒间隔 | 不频繁查询，避免阻塞 |
| 最大导出等待 | 10分钟 | 符合实际导出大数据量需要 |

### 3. 元素定位降级策略

**规则：** 从不只依赖一种选择器，必须有多级降级匹配策略。

推荐匹配顺序：
1. 精确文本匹配：`text=导出`
2. CSS类选择器：`.ant-btn-primary:has-text("导出")`
3. 模糊文本匹配：`//*[contains(text(), "导出")]`
4. 位置推测：顶部工具栏找按钮
5. debug输出：找不到时输出所有按钮文本，便于人工修正

### 4. iframe处理规则

**规则：** 企业OA/Cube系统喜欢把主内容放在iframe中，必须特别处理。

查找顺序：
1. 先查找页面上所有iframe，记录数量和id/name
2. 找到主内容iframe，通常id是 `mainFrame`
3. 使用 `page.frame_locator('#mainFrame')` 在iframe内查找元素
4. 导出进度弹窗通常在父页面，所以要到父页面查找弹窗

### 5. 模态框/进度弹窗处理规则

**规则：** 导出进度弹窗位置变化大，需要检查多个位置。

查找顺序：
1. 首先检查iframe内是否有 `.ant-modal` / `[role=dialog]`
2. 如果没有，检查父页面（当前页面）的模态框
3. 找到后轮询进度，提取 `(\d+)/(\d+)` 格式进度输出

---

## 二、全流程操作模板（OA合同台账示例）

### 1. 基础信息配置

| 项目 | 内容 |
|---|---|
| IAM登录URL | `https://iam.bangcle.com/#/login` |
| OA应用入口名称 | `OA协同办公平台` |
| 菜单路径 | `门户` → `销售合同管理系统` → `合同基本信息管理` → `合同台账` |
| 导出按钮位置 | iframe `#mainFrame` → 按钮索引1 → 文本 `"导 出"` |
| 目标文件格式 | xlsx（Excel） |
| 默认下载路径 | `~/Downloads/` |
| 归档路径 | `~/.openclaw/data/oa_exports/` |

### 2. 全流程代码模板

```python
import os, sys, time, re
from pathlib import Path
from datetime import datetime
os.environ['no_proxy'] = '*'
from playwright.sync_api import sync_playwright

def export_oa_contract_ledger():
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = browser.contexts[0]

        # 1. 找到IAM首页，点击OA应用入口，打开新标签页
        iam_page = None
        for page in ctx.pages:
            if "iam.bangcle.com/#/home" in page.url:
                iam_page = page
                break
        # 找到OA应用并点击，等待新页面
        new_oa_page = None
        selectors = [
            "text=OA协同办公平台",
            "[class*=app]:has-text(\"OA协同办公平台\")",
            "div:has-text(\"OA协同办公平台\")",
        ]
        for sel in selectors:
            item = iam_page.locator(sel).first
            if item.count() > 0:
                with ctx.expect_page(timeout=15000) as p_info:
                    item.click()
                new_page = p_info.value
                new_page.wait_for_load_state("networkidle", timeout=30000)
                time.sleep(5)
                new_oa_page = new_page
                break
        current_page = new_oa_page

        # 2. 逐级点击菜单
        menu_path = ["门户", "销售合同管理系统", "合同基本信息管理", "合同台账"]
        for level, menu_text in enumerate(menu_path, 1):
            current_page.wait_for_load_state("networkidle", timeout=30000)
            time.sleep(5)
            if level <= 2:
                current_page.evaluate("window.scrollTo(0, 0)")
                time.sleep(2)
            found = False
            selectors = [
                f"text={menu_text}",
                f".ant-menu-submenu-title:has-text(\"{menu_text}\")",
                f"a:has-text(\"{menu_text}\")",
                f"span:has-text(\"{menu_text}\")",
                f"//*[contains(text(), \"{menu_text}\")]",
            ]
            for sel in selectors:
                item = current_page.locator(sel).first
                if item.count() > 0:
                    item.scroll_into_view_if_needed()
                    time.sleep(1)
                    # 检查是否新开页面
                    try:
                        with ctx.expect_page(timeout=15000) as p_info:
                            item.click()
                        new_page = p_info.value
                        new_page.wait_for_load_state("networkidle", timeout=30000)
                        time.sleep(8)
                        current_page = new_page
                        print(f"  ✅ Clicked, opened new page: {current_page.url}")
                    except Exception:
                        # 没有新开页面，是展开子菜单
                        item.click()
                        time.sleep(8)
                        print(f"  ✅ Clicked, expanded submenu")
                    found = True
                    break
            if not found:
                print(f"  ❌ Menu not found: {menu_text}")
                browser.close()
                sys.exit(1)

        # 3. 等待目标页面完全加载
        current_page.wait_for_load_state("networkidle", timeout=60000)
        time.sleep(60)  # 大数据表格需要更长时间加载

        # 4. 查找导出按钮（在mainFrame iframe内）
        iframe = current_page.frame_locator("#mainFrame").first
        export_button = None
        buttons = iframe.locator("button").all()
        for btn in buttons:
            text = btn.text_content().strip()
            if "导出" in text or ("导" in text and "出" in text):
                export_button = btn
                print(f"✅ Found export button: {text}")
                break
        if not export_button:
            print("❌ Export button not found in iframe")
            browser.close()
            sys.exit(1)

        # 5. 点击导出，等待进度弹窗（在父页面）
        export_button.click()
        time.sleep(5)

        # 6. 轮询等待导出完成，弹窗在父页面
        start_time = time.time()
        max_wait = 10 * 60  # 10分钟
        download_ready = False

        while (time.time() - start_time) < max_wait:
            time.sleep(10)
            download_link = current_page.locator("a:has-text(\"下载\")")
            if download_link.count() > 0:
                print("✅ Export completed, download link ready")
                download_ready = True
                break
            # 输出进度
            try:
                modal = current_page.locator(".ant-modal-body, [role=dialog]").first
                modal_text = modal.text_content()
                match = re.search(r"(\d+)/(\d+)", modal_text)
                if match:
                    cur, total = int(match.group(1)), int(match.group(2))
                    pct = 100 * cur / total if total > 0 else 0
                    print(f"  Progress: {cur}/{total} ({pct:.1f}%)")
            except Exception:
                pass

        if not download_ready:
            print(f"❌ Export timeout after {max_wait/60:.0f} minutes")
            browser.close()
            sys.exit(1)

        # 7. 下载完成，Chrome自动下载到Downloads，我们迁移到归档目录
        output_dir = Path.home() / ".openclaw" / "data" / "oa_exports"
        output_dir.mkdir(parents=True, exist_ok=True)

        # 找到最新下载的文件
        downloads_dir = Path.home() / "Downloads"
        csv_files = list(downloads_dir.glob("*.csv"))
        xlsx_files = list(downloads_dir.glob("*.xlsx"))
        all_files = csv_files + xlsx_files
        if not all_files:
            print("❌ No downloaded file found in Downloads")
            browser.close()
            sys.exit(1)
        # 取最新修改的文件
        latest_file = max(all_files, key=lambda f: f.stat().st_mtime)

        # 归档
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"oa_contract_ledger_{timestamp}{latest_file.suffix}"
        output_path = output_dir / filename
        shutil.copy(latest_file, output_path)

        file_size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"""
🎉 全自动化导出成功完成！
原始文件: {latest_file.resolve()}
归档文件: {output_path.resolve()}
文件大小: {file_size_mb:.2f} MB
""")

        browser.close()
        return output_path
```

### 3. 结果归档规则

| 项目 | 规则 |
|---|---|
| 原始文件位置 | 保留在Chrome默认下载目录 `~/Downloads/` |
| 归档位置 | `~/.openclaw/data/[project]/[type]/` |
| 文件名格式 | `[type]_[timestamp].[ext]` 保留原始后缀 |
| 不覆盖原有文件 | 使用时间戳保证唯一性 |

---

## 三、问题排查指南

### 1. 找不到菜单
- 检查URL是否正确进入到了正确页面
- 打印当前页面所有一级菜单，确认文本名称
- 如果文本名称有变化，更新菜单路径配置

### 2. 找不到导出按钮
- 检查iframe是否正确定位，是否有多个iframe
- 打印iframe内所有按钮文本，确认导出按钮位置和文本
- 如果是导出在父页面，调整查找范围

### 3. 导出长时间不完成
- 确认数据总量，如果数据量超过10万，导出通常需要5-10分钟，耐心等待
- 如果超过10分钟仍然没有完成，检查网络或系统负载

### 4. 导出完成但找不到文件
- 检查Chrome默认下载目录，确认文件是否已经下载
- 如果文件名不符合预期（比如后缀不对），手动修改后缀后归档

---

## 四、经验总结

1. **企业内网系统的特点**：DOM结构嵌套多（iframe多层）、加载慢、异步SPA、名称带空格，自动化需要更多容错和降级处理。
2. **环境隔离是底线**：绝对不能影响用户正在使用的Chrome会话，独立实例是必须的。
3. **足够的等待时间是关键**：不要着急，企业系统就是慢，给足时间自然能加载完成。
4. **多级降级匹配**：不要只依赖一种选择器，多种方式都找不到才失败，提高成功率。
5. **进度轮询输出**：定期输出进度，让操作者知道当前状态，不会以为卡住了。

