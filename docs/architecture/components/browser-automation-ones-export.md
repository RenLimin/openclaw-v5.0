# ONES 系统浏览器自动化数据导出详细设计

## 1. 环境信息

| 要素 | 值 |
|---|---|
| 目标系统名称 | ONES 项目管理平台 |
| 系统入口URL | `https://ones.bangcle.com/` |
| 环境类型 | 生产 |
| 浏览器类型及版本 | Google Chrome 最新稳定版 |
| 自动化框架 | osascript + Chrome Apple Events |
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
| 应用入口名称 | ONES 管理平台 |
| 菜单路径（逐级） | IAM 首页 → 点击「ONES 管理平台」→ 进入 ONES → 点击左侧筛选器链接 |
| 是否新开标签页 | 是，每次点击子菜单都开新标签页 |
| 目标页面URL特征 | `/filter/view/{id}` |
| 是否存在iframe | 否 |
| 页面加载等待时间 | 10 秒（SPA 加载） |

**已知筛选器链接索引**（可能随页面变化）：

| 筛选器名称 | 索引 | URL |
|---|---|---|
| 签约项目统计 | 20 | `/filter/view/5wY9X4m8` |
| POC&提前实施统计 | 21 | `/filter/view/KxnjPRY7` |
| 异常处置 | 23 | `/filter/view/NWPaa48w` |

## 4. 操作元素定义

| 要素 | 值 |
|---|---|
| 操作按钮名称 | 导出工作项 |
| 按钮位置 | 更多操作 → 下拉菜单 → 导出工作项 |
| 按钮选择器（主选） | `[class*=dropdown-menu-item-label]:nth-child(10)` |
| 按钮选择器（备选） | `text=导出工作项` |
| 所在DOM层级 | 父页面 |
| 点击后行为 | 弹出确认弹窗 |

**导出操作流程**：

1. 点击「更多操作」图标：`[class*=more-menu-icon]:nth-child(0)`
2. 等待 3 秒
3. 点击「导出工作项」：`[class*=dropdown-menu-item-label]:nth-child(10)`
4. 等待 5 秒
5. 点击「确认」按钮：`button:nth-child(7)`
6. 等待 15 秒（大文件下载）

## 5. 进度与等待策略

| 要素 | 值 |
|---|---|
| 进度弹窗位置 | 无（ONES 直接下载，无进度弹窗） |
| 轮询间隔 | 无需轮询 |
| 最大等待时间 | 15 秒 |

## 6. 结果处理

| 要素 | 值 |
|---|---|
| 文件下载方式 | Chrome 自动下载 |
| 默认下载目录 | `~/Downloads/` |
| 文件格式 | CSV |
| 文件名格式 | `2026周报-{筛选器名称}.csv` |
| 归档目录 | `~/.openclaw/data/ones_exports/` |
| 归档命名规则 | `{YYYYMM}周报-{筛选器名称}.csv` |
| 是否保留原始文件 | 是，归档使用复制不移动 |

**导出结果参考**：

| 筛选器 | 参考行数 | 导出列数 | 文件大小 |
|---|---|---|---|
| 签约项目统计 | ~16,600 | 40 | ~24MB |
| POC&提前实施 | ~5,030 | 40 | ~2MB |
| 异常处置 | ~362 | 40 | ~0.6MB |

## 7. 异常处理

| 异常场景 | 处理方式 |
|---|---|
| 登录失败 | 重试3次，仍失败则报错退出 |
| 菜单找不到 | 打印当前所有可见菜单，方便排查 |
| 导出按钮找不到 | 打印所有按钮文本，输出到日志 |
| 导出超时 | 超过最大等待时间后报错退出 |
| Chrome 未打开 | 提示用户打开 Chrome 并登录 |

## 8. 关键经验

1. **纯英文 JS**：`osascript` 执行的 JavaScript 不能包含中文字符（会导致 `missing value`）
2. **等待时间**：点击导出后必须等 **15 秒**以上（大文件下载需要时间）
3. **不要使用 `window.location.href` 导航**：ONES SPA 不会正确切换视图，必须用**点击左侧导航链接**的方式
4. **菜单索引可能变化**：每次同步前应重新探测索引

## 9. 代码实现

```python
import subprocess
import time
from pathlib import Path

def run_js(js: str) -> str:
    """在 ONES 标签页执行 JavaScript"""
    cmd = ['osascript', '-e',
        'tell application "Google Chrome" to execute (first tab of first window whose URL contains "ones.bangcle.com") javascript "' + js.replace('"', '\\"') + '"']
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    return r.stdout.strip()

def click_filter(filter_index: int) -> None:
    """点击左侧导航筛选器链接"""
    run_js(f"document.querySelectorAll('a')[{filter_index}].click();'clicked'")
    time.sleep(10)  # ONES SPA 加载数据

def click_export() -> None:
    """点击导出流程"""
    # 1. 点击更多操作
    run_js("document.querySelectorAll('[class*=more-menu-icon]')[0].click();'clicked'")
    time.sleep(3)
    
    # 2. 点击导出工作项（索引 10）
    run_js("document.querySelectorAll('[class*=dropdown-menu-item-label]')[10].click();'clicked'")
    time.sleep(5)
    
    # 3. 点击确定（索引 7）
    run_js("document.querySelectorAll('button')[7].click();'clicked'")
    time.sleep(15)  # 等待下载完成

def get_latest_download() -> Path:
    """获取最新下载的 CSV 文件"""
    downloads = Path('/Users/bangcle/Downloads')
    csv_files = list(downloads.glob('*.csv'))
    if not csv_files:
        raise FileNotFoundError("未找到下载的 CSV 文件")
    return max(csv_files, key=lambda p: p.stat().st_mtime)

# 使用示例
click_filter(20)  # 签约项目统计
click_export()
csv_file = get_latest_download()
print(f"导出完成: {csv_file}")
```
