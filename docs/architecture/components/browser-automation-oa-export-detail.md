# OA 系统浏览器自动化数据导出详细设计

## 1. 环境信息

| 要素 | 值 |
|---|---|
| 目标系统名称 | OA 协同办公平台（合同台账） |
| 系统入口URL | `https://oa.bangcle.com/`（需通过 IAM 跳转） |
| 环境类型 | 生产 |
| 浏览器类型及版本 | Google Chrome 最新稳定版 |
| 自动化框架 | Playwright + Chrome CDP（连接已打开的 Chrome） |
| 操作系统 | macOS 14+ |

## 2. 认证信息

| 要素 | 值 |
|---|---|
| 认证方式 | IAM 统一身份认证（SSO） |
| 登录页URL | `https://iam.bangcle.com/#/login` |
| 用户名输入框选择器 | `input[type=text]` |
| 密码输入框选择器 | `input[type=password]` |
| 登录按钮选择器 | `button:has-text("登录")` |
| 登录后跳转验证 | URL 包含 `#/home`，页面标题变为「统一认证 - 首页」 |
| Cookie 有效期 | 12 小时 |
| 凭证存储位置 | 系统密钥链 / 环境变量 / 配置服务 |

**安全红线：** 设计文档中**禁止**出现真实用户名密码，只能说明凭证获取方式，不得泄露。

## 3. 导航路径

| 要素 | 值 |
|---|---|
| 应用入口名称 | OA 协同办公平台（IAM 首页面板） |
| 菜单路径（逐级） | IAM → OA 协同办公平台 → 门户 → 销售合同管理系统 → 合同基本信息管理 → 合同台账 |
| 是否新开标签页 | 是，每次点击子菜单都开新标签页 |
| 目标页面URL特征 | `customid=179`（但 URL 含动态 `_key` 参数，不可直接跳转） |
| 是否存在iframe | 是，主内容在 `#mainFrame` iframe 内 |
| iframe选择器 | `iframe#mainFrame` |
| 页面加载等待时间 | 60 秒（大数据表格） |

**⚠️ 禁止直接用 URL 跳转**：OA Cube 页面 URL 含动态 `_key` 参数，每次生成不同，直接 `page.goto()` 会失效，必须逐级点击菜单进入。

## 4. 操作元素定义

| 要素 | 值 |
|---|---|
| 操作按钮名称 | 导 出（带空格） |
| 按钮位置 | iframe 内顶部工具栏，搜索按钮右侧 |
| 按钮选择器（主选） | `iframe#mainFrame button:nth-child(2)` |
| 按钮选择器（备选） | `text=导 出` / `//*[contains(text(), "导出")]` |
| 所在DOM层级 | iframe `#mainFrame` 内 |
| 点击后行为 | 弹出进度模态框（在父页面） |

## 5. 进度与等待策略

| 要素 | 值 |
|---|---|
| 进度弹窗位置 | 父页面（不在 iframe 内） |
| 进度弹窗选择器 | `.ant-modal` / `[role=dialog]` |
| 进度文本格式 | `当前进度 ：N/113380%` |
| 进度提取正则 | `(\d+)/(\d+)` |
| 总数据量（预估） | ~11.3 万条 |
| 轮询间隔 | 10 秒 |
| 最大等待时间 | 10 分钟 |

## 6. 结果处理

| 要素 | 值 |
|---|---|
| 文件下载方式 | 点击"下载"链接，Chrome 自动下载 |
| 下载链接位置 | 父页面进度弹窗内 |
| 下载链接选择器 | `.ant-modal a:has-text("下载")` |
| 默认下载目录 | `~/Downloads/` |
| 文件格式 | xlsx（Excel） |
| 文件名格式 | `梆梆_销售合同信息查询台账-销售查询-[姓名]-[日期].xlsx` |
| 归档目录 | `~/.openclaw/data/oa_exports/` |
| 归档命名规则 | `oa_contract_ledger_[YYYYMMDD_HHHMMSS].xlsx` |
| 是否保留原始文件 | 是，归档使用复制不移动 |

## 7. 异常处理

| 异常场景 | 处理方式 |
|---|---|
| 登录失败 | 重试3次，仍失败则报错退出 |
| 菜单找不到 | 打印当前所有可见菜单，方便排查 |
| 导出按钮找不到 | 打印 iframe 内所有按钮文本，输出到日志 |
| 导出超时 | 超过最大等待时间后报错退出 |
| iframe 找不到 | 打印页面所有 iframe，输出到日志 |
| Chrome 崩溃 | 重新启动 Chrome 实例，从头开始 |

## 8. 关键经验

1. **按钮在 iframe 内**：导出按钮在 `#mainFrame` iframe 中，必须用 `frame_locator` 定位
2. **弹窗在父页面**：进度弹窗在父页面（不在 iframe 里），需要跨层级查找
3. **导出为 xlsx 格式**：不是 CSV，是 Excel 文件，文件名包含中文
4. **服务端异步生成**：导出需要5-10分钟，必须轮询等待
5. **导航必须逐级点击**：禁止 `page.goto()` 直接跳转，SPA 不会正确渲染
6. **Chrome 独立实例**：使用 `--remote-debugging-port=9222` 的独立 Chrome 配置文件

## 9. 代码实现

```python
import os, time, re
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright

def export_oa_contract_ledger():
    """OA 合同台账全自动化导出"""
    os.environ['no_proxy'] = '*'
    
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = browser.contexts[0]
        pages = ctx.pages

        # 1. 找到 IAM 首页，点击 OA 应用入口
        iam_page = None
        for page in pages:
            if "iam.bangcle.com/#/home" in page.url:
                iam_page = page
                break
        
        if not iam_page:
            raise Exception("IAM home page not found")

        # 2. 点击 OA 协同办公平台，打开新标签页
        new_oa_page = None
        for sel in ["text=OA协同办公平台", "[class*=app]:has-text(\"OA协同办公平台\")"]:
            item = iam_page.locator(sel).first
            if item.count() > 0:
                with ctx.expect_page(timeout=15000) as p_info:
                    item.click()
                new_oa_page = p_info.value
                new_oa_page.wait_for_load_state("networkidle", timeout=30000)
                time.sleep(5)
                break
        
        if not new_oa_page:
            raise Exception("OA app entry not found")

        current_page = new_oa_page

        # 3. 逐级点击菜单
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
                    
                    try:
                        with ctx.expect_page(timeout=15000) as p_info:
                            item.click()
                        new_page = p_info.value
                        new_page.wait_for_load_state("networkidle", timeout=30000)
                        time.sleep(8)
                        current_page = new_page
                    except Exception:
                        item.click()
                        time.sleep(8)
                    
                    found = True
                    break
            
            if not found:
                raise Exception(f"Menu not found: {menu_text}")

        # 4. 等待页面完全加载
        current_page.wait_for_load_state("networkidle", timeout=60000)
        time.sleep(60)

        # 5. 在 iframe 中找导出按钮
        iframe = current_page.frame_locator("#mainFrame").first
        export_button = None
        buttons = iframe.locator("button").all()
        
        for btn in buttons:
            text = btn.text_content().strip()
            if "导出" in text or ("导" in text and "出" in text):
                export_button = btn
                break
        
        if not export_button:
            raise Exception("Export button not found in iframe")

        # 6. 点击导出
        export_button.click()
        time.sleep(5)

        # 7. 轮询等待导出完成（弹窗在父页面）
        start_time = time.time()
        max_wait = 600  # 10 minutes
        download_ready = False

        while (time.time() - start_time) < max_wait:
            time.sleep(10)
            
            download_link = current_page.locator("a:has-text(\"下载\")")
            if download_link.count() > 0:
                download_ready = True
                break
            
            try:
                modal = current_page.locator(".ant-modal-body").first
                modal_text = modal.text_content()
                match = re.search(r"(\d+)/(\d+)", modal_text)
                if match:
                    cur, total = int(match.group(1)), int(match.group(2))
                    pct = 100 * cur / total if total > 0 else 0
                    print(f"Progress: {cur}/{total} ({pct:.1f}%)")
            except:
                pass

        if not download_ready:
            raise Exception("Export timeout")

        # 8. 下载文件
        output_dir = Path.home() / ".openclaw" / "data" / "oa_exports"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"oa_contract_ledger_{timestamp}.xlsx"
        output_path = output_dir / filename

        with current_page.expect_download(timeout=60000) as download_info:
            current_page.locator("a:has-text(\"下载\")").first.click()
        download = download_info.value
        download.save_as(output_path)

        file_size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"Export saved: {output_path.resolve()} ({file_size_mb:.2f} MB)")
        
        browser.close()
        return output_path
```
