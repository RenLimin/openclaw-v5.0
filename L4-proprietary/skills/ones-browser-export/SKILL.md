---
name: ones-browser-export
description: "ONES 数据获取：浏览器自动化导出 CSV + GraphQL API 查询。支持签约项目统计/POC统计/异常处置等视图导出，以及工作项/用户/字段等结构化查询。"
---
# ONES 浏览器自动化数据导出

## 触发条件
- 需要从 ONES 导出筛选器数据（签约/POC/异常等）
- 月报生成需要 ONES 原始数据
- ONES API 不可用或受限时

## 前置条件
- Chrome 已打开 ONES 页面（已登录）
- macOS 环境（使用 `osascript`）
- Python 3 + subprocess

## 核心流程

### 1. 确认 ONES 标签页
```python
import subprocess
def run_js(js):
    cmd = ['osascript', '-e',
        'tell application "Google Chrome" to execute (first tab of first window whose URL contains "ones.bangcle.com") javascript "' + js + '"']
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    return r.stdout.strip()
```

### 2. 切换筛选器（点击左侧导航链接）
```python
# 查找筛选器链接索引（每次页面加载后可能变化）
links = run_js("var r=[];document.querySelectorAll('a').forEach(function(a,i){var t=a.textContent.trim();if(t.indexOf('签约项目统计')!==-1)r.push({i:i,t:t})});JSON.stringify(r)")
# 点击链接
run_js("document.querySelectorAll('a')[INDEX].click();'clicked'")
# ⚠️ 必须等待 10 秒（ONES SPA 加载数据）
```

**已知筛选器（2026-10-10 更新）**：

| 视图全称 | 索引（参考） | filter/view ID |
|---|---|---|
| 2026周报-签约项目统计 | 20 | `5wY9X4m8` |
| 2026周报-POC&提前实施统计 | 21 | `KxnjPRY7` |
| 2026-签约项目异常处置 | 23 | `NWPaa48w` |

> ⚠️ 索引可能随页面加载变化，优先用**文本匹配**找链接，不要硬编码索引。

### 3. 点击"更多操作"→"导出工作项"→"确定"
```python
# 3a: 点击更多操作
run_js("document.querySelectorAll('[class*=more-menu-icon]')[0].click();'clicked'")
time.sleep(3)

# 3b: 点击导出工作项（索引 10）
run_js("document.querySelectorAll('[class*=dropdown-menu-item-label]')[10].click();'clicked'")
time.sleep(5)

# 3c: 点击确定（索引 7）
run_js("document.querySelectorAll('button')[7].click();'clicked'")
time.sleep(15)  # 等待下载完成
```

### 4. 检查下载文件
```python
from pathlib import Path
downloads = Path('/Users/bangcle/Downloads')
newest = max(downloads.glob('*.csv'), key=os.path.getmtime)
# 检查文件大小和行数确认导出成功
```

## 关键经验

### ⚠️ 必须遵守的规则
1. **纯英文 JS**：`osascript` 执行的 JavaScript 不能包含中文字符（会导致 `missing value`）
2. **等待时间**：点击导出后必须等 **15 秒**以上（大文件下载需要时间）
3. **菜单索引**："导出工作项"在 `dropdown-menu-item-label` 中的索引是 **10**
4. **确定按钮**：弹窗中的"确定"按钮索引是 **7**
5. **不要使用 `window.location.href` 导航**：ONES SPA 不会正确切换视图，必须用**点击左侧导航链接**的方式

### ❌ 失败方案（不要重复尝试）
- `window.location.href` 导航 → SPA 不切换视图
- `page.on('request')` 拦截 → headless 模式下不稳定
- GraphQL `buckets` 查询 → groupBy 字段名未知
- REST API → 全部 404
- Playwright `page.goto` → 频繁卡住

### ✅ 可靠方案
- `osascript` + `execute tab javascript` + `read POSIX file`（可选）
- 点击左侧导航链接切换筛选器
- 菜单索引点击（不依赖文字匹配）

## 导出结果参考

| 筛选器 | 参考行数 | 导出列数 | 文件名 |
|---|---|---|---|
| 2026周报-签约项目统计 | ~16,600 | 40 | `2026周报-签约项目统计.csv` |
| 2026周报-POC&提前实施统计 | ~5,030 | 40 | `全部工作项.csv` |
| 2026-签约项目异常处置 | ~362 | 40 | `2026-签约项目异常处置.csv` |

---

## GraphQL API 能力（备用方案）

当浏览器导出不稳定或需要结构化查询时，用 ONES GraphQL API。

### 端点
```
POST https://ones.bangcle.com/project/api/project/team/RZxvwUZ8/items/graphql
Headers:
  Content-Type: application/json
  Ones-Auth-Token: <token>
  Ones-User-Id: REccSDPA
```

### 登录获取 token
```bash
curl -X POST "https://ones.bangcle.com/project/api/project/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"limin.ren@bangcle.com","password":"<密码>","captcha":""}'
```

### 常用查询

**查用户 UUID：**
```graphql
{ users(filter: { name_equal: "姓名" }) { uuid name email } }
```

**查项目 UUID：**
```graphql
{ projects(filter: {name_equal: "项目名"}) { uuid name } }
```

**查工作项类型：**
```graphql
{ issueTypes { uuid name key } }
```

**查字段定义：**
```graphql
{ fields(projectUuid: "<project_uuid>") { uuid name type required options { uuid value color } } }
```

**查 schema（探索可用字段）：**
```graphql
{ __schema { queryType { fields { name } } } }
```

## 相关文件
- 导出脚本：`scripts/l4/delivery_center/generators/generate_report_202606.py`
- 数据目录：`~/.openclaw/data/ones_exports/`
- 月报生成器：`scripts/l4/delivery_center/generators/delivery_report.py`
- ONES 官方文档：`~/Downloads/ones/`（数据字典、私有部署手册、SQL说明）

## 知识库引用
- 工作前先搜知识库：`python3 L2-infra/components/knowledge-base/kb_index.py --query ...`
