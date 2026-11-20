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
- **能力注册表（防重复建设）**：动手前先查
  `python3 L2-infra/components/config/capability-registry/capability_registry.py --query ones`
  本 skill 的权威能力 = `ones-export` / `ones-auth` / `oa-workflow-ones`。**禁止另写 ONES 导出/登录脚本**（pre-commit 会拦截）。

---

## OA 项目实施流程 → ONES 桥（只读，2026-11-18 固化）

**权威脚本**：`scripts/oa_workflow_ones.py`（v2）｜**字段映射**：`references/oa-workflow-fields.md`

### 用法

```bash
# A) 签约项目块（按 SSXM 编号直查 ONES，输出 Rex 确认样式）
python3 scripts/oa_workflow_ones.py --code SSXM-2026-0611-1491 SSXM-2026-0603-1405 \
    --pm 邓旭兵 --final-customer 中移动金融科技有限公司

# B) OA 待办桥（requestid）
python3 scripts/oa_workflow_ones.py --capture 886291      # Playwright 抓 OA 表单
python3 scripts/oa_workflow_ones.py 886291               # 读 raw/ → ONES 输出

# C) 待办全量分布（双口径对比，回答「某流程有几条待办」）
python3 scripts/oa_todo_dist.py --save                   # 落盘 tmp/oa-pif/full_todo_items.json
```

前置：OA `storage_state`（过期先 `refresh_oa_session()`）+ Chrome 已登录 ONES。

### 待办统计口径（重要）

OA 待办有**两个口径**，数字对不上是**正常**的：
- **树/计数口径**（`doingBaseInfo.treedata` / `doingCountInfo.treecount`）= 当前启用的流程节点；
- **列表口径**（`/api/ec/dev/table/datas` 全量分页）= 全部待办单据，**含历史流程定义的遗留单据**。

实证（2026-11-18）：树里只有 `wf_840 / wf_757 / wf_923`；列表另有 `wf_778=9`、`wf_752=2`
（均为旧版「销售合同验收文件归档流程」，被 840 取代但单据未销）。
→ **报数必须注明口径**；Never 用树节点缺失推断「某流程无待办」。详见 `references/oa-workflow-fields.md` 第七节。

### 签约项目块输出样式（固定，经 Rex 2026-11-18 确认）

每个项目一块，字段与顺序固定：
```
N. 项目编号：SSXM-…
   所属项目：【SSXM-…】…
   客户：<最终客户>（签约客户：<签约主体>）
   状态：已交付已验收（项目状态：验收完成，履约义务：验收文件已归档…）
   授权/维保期限：YYYY-MM-DD ~ YYYY-MM-DD（证据任务 NNNNNN）
   项目经理：<姓名>
   履约项人：<姓名>（<角色>） | …
   异常/变更：无
```
- 字段标签一律用全角冒号 `：`，值与标签间无空格；块内缩进 4 空格。
- 授权/维保期限取自【云端】license 任务 `descriptionText` 的「授权时间/授权期限 a-b」，**取区间结束日**。
- 项目经理 ONES 无字段（`_2jEz2XG9` 实测全空）→ 由 `--pm` 显式传入；未传标【缺失】，禁止编造。
- 客户 = 最终客户（`--final-customer` 或 OA `_CuG2EPnC`）+ 签约客户（确收/验收任务 `_RnWqUALs`）。
- 证据三档：字段缺失/无来源一律标【缺失】，不得用历史项目或推测填充。

### 已知坑

1. **编号在项目名里**：SSXM 编号只在 `projects.name`，任务名不含 → 用 `projects(filter:{name_match})`。
2. **授权/维保/PM 字段空**：ONES 自定义字段 `2jEz2XG9`/`ArYbG1Hf`/`6ehQSmch`/`THZBUbgx`/`QP2aBu2T`/`DECCCa8Z`/`2yD1cAR4` 对目标项目**实测全空**；只能从任务描述提取授权区间，PM 靠人工口径。
3. **枚举/标量选择集**：GraphQL 枚举字段加 `{value}`、标量不加，混用会报 Malformed.GraphQL。
4. **OA 会话**：过期跳 `iam.bangcle.com/#/login`，`--capture` / `oa_todo_dist.py` 会显式报错（exit 2），不静默。
5. **客户名不可反推项目**：`--final-customer` 只用于**最终客户字段**；禁止用任务名 `name_match` 反推项目
   （会命中历史项目）。无 SSXM 编号时只在 `projects.name` 里精确包含匹配，且结果标「需人工确认」。

### 镜像与根因（重要，防再犯）

sandbox 的 `skills/` 是 OpenClaw `workspace-skill-sync` 从权威源**单向镜像**：
`source = L2/L3/L4 各层 skills 目录` → `target = <sandbox>/skills`（拷贝，`shouldSyncSkillPath` 只排 `.git`/`node_modules`，**会放行 scripts/references**）。
因此**新增/修改 skill 文件必须落到权威源**（`L4-proprietary/skills/…`），否则下次同步会按权威源回拷、sandbox 本地改动丢失。
2026-11-18 事故：脚本/字段文档只提交在 sandbox，权威源无 → 同步后 sandbox 内文件被「权威源无此文件」清理，表现为 `D`。
