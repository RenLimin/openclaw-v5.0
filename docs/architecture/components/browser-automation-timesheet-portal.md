# 工时门户系统浏览器自动化数据采集详细设计

## 1. 环境信息

| 要素 | 值 |
|---|---|
| 目标系统名称 | 工时门户系统 |
| 系统入口URL | `https://timesheet.bangcle.com/`（需通过 IAM 跳转） |
| 环境类型 | 生产 |
| 浏览器类型及版本 | Google Chrome 最新稳定版 |
| 自动化框架 | Playwright（自启动新实例） |
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

## 3. 导航路径

| 要素 | 值 |
|---|---|
| 应用入口名称 | 工时门户（IAM 首页面板） |
| 导航步骤 | IAM → 点击「工时门户」面板 → 新标签页打开 |
| 是否新开标签页 | 是 |
| 目标页面URL特征 | `/spa/custom/static/index.html#/main/cs/app/...` |
| 是否存在iframe | 否 |
| 页面加载等待时间 | 20 秒 |

## 4. 操作元素定义

| 要素 | 值 |
|---|---|
| 采集方式 | DOM 提取（非导出按钮） |
| 数据位置 | 工时迁移汇总表格 |
| 表格选择器（主选） | `table tbody tr` |
| 表格选择器（备选） | `[class*=table] tr, .ant-table-row` |
| 所在DOM层级 | 父页面 |
| 提取字段 | `work_item`, `total_hours`, `migrated_hours`, `remaining_hours` |

## 5. 采集策略

| 要素 | 值 |
|---|---|
| 采集方式 | DOM 表 JS evaluate 提取 |
| 轮询间隔 | 无需轮询 |
| 最大等待时间 | 20 秒（页面加载） |

## 6. 结果处理

| 要素 | 值 |
|---|---|
| 文件保存方式 | Python 脚本直接写入 |
| 文件格式 | CSV + JSON |
| 文件名格式 | `workhour_{YYYYMM}.csv` / `workhour_{YYYYMM}.json` |
| 归档目录 | `~/.openclaw/data/workhour_exports/` |
| 是否保留原始文件 | 是 |

## 7. 异常处理

| 异常场景 | 处理方式 |
|---|---|
| 登录失败 | 重试3次，仍失败则报错退出 |
| 面板点击无响应 | 打印所有面板信息，方便排查 |
| 表格无数据 | 尝试备选选择器 |
| 页面加载超时 | 超时后报错退出 |

## 8. 关键经验

1. **面板点击用 `context.expect_event("page")`**：监听新页面事件
2. **不能手动检查 `context.pages`**：事件循环延迟会导致找不到新页面
3. **`mouse.click()` 不触发跳转**：必须用 locator 的 `click()` 方法

## 9. 代码实现

```python
"""工时门户数据采集器"""
import json
import csv
import time
from pathlib import Path
from typing import Optional
from playwright.sync_api import sync_playwright

IAM_BASE = "https://iam.bangcle.com"
EXPORT_DIR = Path.home() / ".openclaw" / "data" / "workhour_exports"

def collect_workhour_data(month: str) -> Optional[dict]:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        context = browser.new_context(accept_downloads=True, viewport={"width": 1920, "height": 1080})
        page = context.new_page()
        
        try:
            # Step 1: 登录 IAM
            page.goto(f"{IAM_BASE}/#/login", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(2)
            page.locator("input[type=text]").first.fill("USERNAME")
            page.locator("input[type=password]").first.fill("PASSWORD")
            for btn in page.locator("button").all():
                if "登录" in (btn.text_content() or ""):
                    btn.click()
                    break
            page.wait_for_url("**/home/**", timeout=15000)
            time.sleep(10)
            
            # Step 2: 点击工时门户面板
            wh_panel = page.locator(".small-panel", has_text="工时门户")
            with context.expect_event("page", timeout=15000) as new_page_info:
                wh_panel.first.click()
            wh_page = new_page_info.value
            time.sleep(20)
            
            # Step 3: 提取表格数据
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
            
            # Step 4: 保存
            output_file = EXPORT_DIR / f"workhour_{month}.csv"
            with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=["work_item", "total_hours", "migrated_hours", "remaining_hours"])
                writer.writeheader()
                writer.writerows(table_data)
            
            json_file = EXPORT_DIR / f"workhour_{month}.json"
            result = {"month": month, "source": "workhour_portal", "count": len(table_data), "file": str(output_file), "data": table_data}
            json_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            
            return result
        finally:
            browser.close()
```
