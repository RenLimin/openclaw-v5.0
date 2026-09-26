# BDMS v2.1 Web UI + 网络安全 详细设计

> 版本：v2.1 Detail（2026-09-21）
> 层级：L4 专有业务层 — Web 前端 + 网络安全
> 继承：BDMS v1.0 `web/`（FastAPI + Jinja2）+ L2 web-common 组件库
> 状态：**追认文档**（代码已开发完成，本文档为事后追认对齐）
> 关联：`DESIGN-OUTLINE-v2.1.md` Phase 3、`DESIGN-WEB-UI-v2.1.md`（初版）

---

## 0. 追认说明

本文档对齐已实现的 Web UI 和网络安全功能。开发过程中未遵守"先设计后开发"流程，Rex 要求补文档追认。

**已开发完成的文件清单**：

| 文件 | 说明 |
|---|---|
| `src/bdms/security.py` | 网络安全核心模块（访问控制 + Token 鉴权） |
| `src/bdms/web/security_api.py` | 安全设置 API 路由 |
| `src/bdms/web/contract.py` | 合同管理 API 路由 |
| `src/bdms/web/project.py` | 项目管理 API 路由 |
| `src/bdms/web/dashboard_mvp.py` | Dashboard MVP API 路由 |
| `src/bdms/web/templates/contract.html` | 合同管理页面 |
| `src/bdms/web/templates/contract_new.html` | 新建合同页面 |
| `src/bdms/web/templates/project.html` | 项目管理页面 |
| `src/bdms/web/templates/project_new.html` | 新建项目页面（预留） |
| `src/bdms/web/templates/dashboard_mvp.html` | MVP 看板页面 |
| `src/bdms/web/templates/security.html` | 安全设置页面 |
| `src/bdms/web/static/js/contract.js` | 合同管理页面 JS |
| `src/bdms/web/static/js/project.js` | 项目管理页面 JS |
| `src/bdms/web/static/js/dashboard_mvp.js` | Dashboard 页面 JS |
| `src/bdms/web/static/img/logo.png` | Bangcle 品牌 Logo |
| `src/bdms/web/static/img/logo-white.png` | 深色主题 Logo |
| `src/bdms/web/static/img/favicon.png` | Favicon |
| `src/bdms/web/static/css/style.css` | 扩展样式（品牌色 + 开关 + 详情面板） |

---

## 1. 品牌设计

### 1.1 Bangcle Logo 集成

**Logo 来源**：`/Users/bangcle/Bangcle Workspace/00. Bangcle Manual/02. Bangcle Template/Logo/`

| 用途 | 文件 | 路径 |
|---|---|---|
| 侧边栏品牌（浅色） | `1-3-原色-标准logo.png` | `/static/app/img/logo.png` |
| 侧边栏品牌（深色） | `2-3-反白-标准logo.png` | `/static/app/img/logo-white.png` |
| Favicon | `1-1-原色-图形.png` | `/static/app/img/favicon.png` |

**Logo 使用方式**：

```html
<!-- base.html -->
<link rel="icon" type="image/png" href="{{ brand_favicon }}">

<!-- 侧边栏 brand 区（main.py） -->
"brand_logo": "/static/app/img/logo.png",
"brand_logo_white": "/static/app/img/logo-white.png",
```

深色主题切换：通过 CSS `[data-theme="dark"] .brand-logo` 切换 `content` 属性。

### 1.2 品牌色

在 `style.css` 中覆盖 web-common 的 CSS 变量：

```css
:root {
  --c-bangcle-blue: #1a56db;      /* Bangcle 主色 */
  --c-bangcle-blue-l: #3b7bf6;    /* 浅蓝 */
  --c-bangcle-blue-d: #0f3fa8;    /* 深蓝 */
  --c-primary: var(--c-bangcle-blue);
  --c-primary-l: var(--c-bangcle-blue-l);
  --c-primary-d: var(--c-bangcle-blue-d);
}
```

### 1.3 视觉规范

| 元素 | 规范 |
|---|---|
| 字体 | Inter（正文）+ Space Grotesk（标题），与 web-common 一致 |
| 圆角 | 8px（卡片）/ 12px（按钮）/ 16px（弹窗） |
| 阴影 | 与 web-common 一致 |
| 间距 | 8px 基准 |
| 状态色 | 蓝=进行中 / 绿=正常 / 黄=预警 / 红=异常 |

---

## 2. 网络安全模块

### 2.1 内外网访问控制

**核心文件**：`src/bdms/security.py`

**配置文件**：`data/security.json`（权限 600，仅所有者可读写）

**默认配置**：

```json
{
  "allow_external": false,
  "allow_internal": true,
  "token_auth_enabled": true,
  "tokens": { ... }
}
```

**判断逻辑**：

| 请求来源 | allow_external=false | allow_external=true |
|---|---|---|
| localhost (127.0.0.1/::1) | ✅ | ✅ |
| 内网 (10.x/172.16-31.x/192.168.x) | ✅（需 allow_internal=true） | ✅ |
| 外网 | ❌ 403 | ✅（需有效 Token） |

**内网 IP 判定范围**：
- `10.0.0.0/8`
- `172.16.0.0/12`（172.16-31.x）
- `192.168.0.0/16`

### 2.2 Token 鉴权

**Token 格式**：32 字节 URL-safe base64（43 字符）

**存储方式**：`data/security.json`，结构化存储：

```json
{
  "tokens": {
    "xxxxx": {
      "label": "admin",
      "created_at": "2026-09-21T10:00:00",
      "expires_at": null
    }
  }
}
```

**鉴权流程**：

```
请求 → 安全中间件
  → 白名单路径（/api/health, /login, /static）→ 放行
  → 从 Header("Authorization: Bearer xxx") 或 Cookie("bdms_token") 或 Query("token") 取 Token
  → is_token_valid(token)
    → Token 不存在 → 401
    → Token 过期 → 401
    → 有效 → 放行
```

**Token 管理 API**：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/security/tokens` | 列表（不含完整 Token） |
| POST | `/api/security/tokens` | 生成新 Token（label + expires_days） |
| DELETE | `/api/security/tokens/{preview}` | 撤销 Token |

### 2.3 登录页

**路由**：`GET /login`（页面）+ `POST /login`（提交）

**流程**：
1. 用户访问任意页面 → 中间件检测无有效 Token → 302 重定向到 `/login`
2. 用户输入 Bearer Token → POST `/login`
3. 验证成功 → Set-Cookie（HttpOnly, SameSite=Lax）→ 302 重定向到 `/`
4. 验证失败 → 401 + 错误提示

**安全特性**：
- Cookie 设置 `httponly=True`（JS 不可读）
- Cookie 设置 `samesite="lax"`（防 CSRF）
- 不存储明文密码（Token 即密钥）

### 2.4 安全设置页

**路由**：`GET /security`

**功能**：
- 外网访问开关（Toggle）
- 内网访问开关（Toggle）
- Token 鉴权开关（Toggle）
- Token 管理（生成 / 列表 / 撤销）
- 访问地址显示（本机 + 局域网）

### 2.5 FastAPI 中间件

```python
@app.middleware("http")
async def _security_middleware(request: Request, call_next):
    return await security_middleware(request, call_next)
```

中间件注册顺序：最先执行（最外层），确保所有后续路由都经过安全检查。

### 2.6 外网穿透方案（待配置）

当前状态：外网访问开关默认关闭，穿透工具未配置。

后续方案：

| 工具 | 命令 | 说明 |
|---|---|---|
| ngrok | `ngrok http 8812` | 需要 ngrok 账号 |
| frp | `frpc -c frpc.ini` | 需要公网服务器 |
| Tailscale | `tailscale funnel 8812` | 需要 Tailscale 账号 |

**安全机制**：即使穿透工具配置好，外网开关默认关闭。需手动在 `/security` 页面开启，用完后立即关闭。

---

## 3. 页面路由

### 3.1 新增页面路由

| 路由 | 模板 | 功能 |
|---|---|---|
| `/contract` | `contract.html` | 合同列表 + 筛选 + 详情 |
| `/contract/new` | `contract_new.html` | 新建合同表单 |
| `/project` | `project.html` | 项目列表 + 筛选 + 详情 |
| `/project/new` | `project_new.html` | 新建项目表单（预留） |
| `/dashboard-mvp` | `dashboard_mvp.html` | 8 个核心指标 |
| `/security` | `security.html` | 安全设置 |
| `/login` | 内联 HTML | Token 登录 |

### 3.2 侧边栏扩展

在 `main.py` 的 `sidebar_items` 中新增：

```python
# 合同管理
{"title": "合同管理", "items": [
    {"id": "contract", "label": "合同列表", "url": "/contract", "icon": "📄"},
    {"id": "contract-new", "label": "新建合同", "url": "/contract/new", "icon": "➕"},
]},
# 项目管理
{"title": "项目管理", "items": [
    {"id": "project", "label": "项目列表", "url": "/project", "icon": "📁"},
    {"id": "project-new", "label": "新建项目", "url": "/project/new", "icon": "➕"},
]},
# 系统分组新增安全设置
{"id": "security", "label": "安全设置", "url": "/security", "icon": "🔒"},
# 统计看板分组新增 MVP 看板
{"id": "dashboard-mvp", "label": "MVP 看板", "url": "/dashboard-mvp", "icon": "🎯"},
```

---

## 4. API 路由

### 4.1 合同管理 API（`/api/contract/*`）

**路由文件**：`src/bdms/web/contract.py`
**前缀**：`APIRouter(prefix="/contract")`（include 到 `/api` 下）

| 方法 | 路径 | 请求体 | 说明 |
|---|---|---|---|
| GET | `/list` | query: page, page_size, status, keyword | 列表 + 分页 |
| GET | `/{id}` | — | 详情（解密敏感字段） |
| POST | `/create` | ContractCreateRequest | 创建草稿 |
| POST | `/{id}/submit` | ApproveRequest | draft → review1 |
| POST | `/{id}/approve` | ApproveRequest | 当前节点 → 下一节点 |
| POST | `/{id}/reject` | ApproveRequest | → draft |
| POST | `/{id}/sign` | ApproveRequest | approved → signed |
| POST | `/{id}/archive` | ApproveRequest | signed → archived |
| GET | `/{id}/risks` | — | 风险扫描结果 |
| GET | `/{id}/audit-log` | — | 审批日志 + 审计追踪 |

### 4.2 项目管理 API（`/api/project/*`）

**路由文件**：`src/bdms/web/project.py`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/list` | 列表 + 分页 + 过滤 |
| GET | `/{id}` | 完整详情（含阶段/团队/成本/风险） |
| POST | `/create` | 创建项目（含 6 个默认阶段） |
| POST | `/{id}/start` | initiating → planning → executing |
| POST | `/{id}/submit-delivery` | 提交交付报告 |
| POST | `/{id}/accept` | delivering → accepting |
| POST | `/{id}/close` | accepting → closing → closed |
| POST | `/{id}/cancel` | → cancelled |
| POST | `/{id}/reactivate` | cancelled → initiating |
| POST | `/{id}/add-member` | 添加团队成员 |
| POST | `/{id}/report-risk` | 上报风险 |
| GET | `/{id}/dashboard` | 项目仪表盘 |

### 4.3 Dashboard MVP API（`/api/dashboard/mvp`）

**路由文件**：`src/bdms/web/dashboard_mvp.py`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/{month}` | 8 个核心指标（含缓存） |
| POST | `/refresh` | 强制刷新快照 |

### 4.4 安全 API（`/api/security/*`）

**路由文件**：`src/bdms/web/security_api.py`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/config` | 读取访问控制配置 |
| POST | `/config` | 更新开关 |
| GET | `/tokens` | Token 列表 |
| POST | `/tokens` | 生成 Token |
| DELETE | `/tokens/{preview}` | 撤销 Token |

### 4.5 路由注册

在 `src/bdms/web/api.py` 末尾：

```python
from .contract import router as contract_router
from .project import router as project_router
from .dashboard_mvp import router as dashboard_mvp_router
from .security_api import router as security_router

router.include_router(contract_router)
router.include_router(project_router)
router.include_router(dashboard_mvp_router)
router.include_router(security_router)
```

---

## 5. 前端详细设计

### 5.1 合同管理页面（`/contract`）

**模板**：`templates/contract.html`
**JS**：`static/js/contract.js`

**布局**：
- 顶部筛选栏（状态下拉 + 关键词搜索）
- 数据表格（合同编号/标题/类型/金额/状态/操作）
- 底部分页
- 右侧详情面板（点击"查看"滑出）

**状态标签色映射**：

| 状态 | CSS 类 | 颜色 |
|---|---|---|
| draft | `badge-gray` | ⚪ 灰 |
| review1~4 | `badge-blue` | 🔵 蓝 |
| approved | `badge-green` | 🟢 绿 |
| signed | `badge-purple` | 🟣 紫 |
| archived | `badge-gray` | ⚫ 灰 |
| rejected | `badge-red` | 🔴 红 |

**详情面板**：
- 基本信息（编号/标题/类型/金额/状态/日期）
- 操作按钮（根据当前状态动态显示）
- 审计日志时间线

### 5.2 项目管理页面（`/project`）

**模板**：`templates/project.html`
**JS**：`static/js/project.js`

**布局**：
- 筛选栏（状态下拉 + PM + 关键词）
- 数据表格（项目编号/名称/PM/状态/进度条/风险数/操作）
- 详情弹窗（Modal，Tab 结构）

**详情 Tab**：
| Tab | 内容 |
|---|---|
| 📊 概览 | 基本信息 + 状态 + 预算 |
| 📋 阶段 | 6 个默认阶段 + 进度 |
| 👥 团队 | 成员列表 + 角色 |
| 🚚 交付 | 交付报告 + 审核状态 |
| ⚠️ 风险 | 风险列表 + 等级 |
| 📈 财务 | 利润 + 健康度评分 |

**状态标签色**：

| 状态 | CSS 类 |
|---|---|
| initiating | `badge-gray` |
| planning / executing | `badge-blue` |
| delivering | `badge-yellow` |
| accepting / closing | `badge-green` |
| closed | `badge-gray` |
| cancelled | `badge-red` |

### 5.3 MVP 看板页面（`/dashboard-mvp`）

**模板**：`templates/dashboard_mvp.html`
**JS**：`static/js/dashboard_mvp.js`

**布局**：
- 顶部月份选择器 + 刷新按钮
- 2×4 KPI 卡片网格
- 趋势图表区（Chart.js）

**8 个 KPI 卡片**：

| 指标 | 图标 | 数据源 |
|---|---|---|
| 合同数 | 📄 | `cr_contracts COUNT` |
| 合同金额 | 💰 | `cr_contracts.amount SUM` |
| 项目数 | 📁 | `pm_projects COUNT` |
| 执行中 | 🔵 | `pm_projects active COUNT` |
| 交付中 | 🚚 | `pm_projects delivering COUNT` |
| 已结项 | ✅ | `pm_projects closed COUNT` |
| 风险数 | ⚠️ | `rk_risks COUNT` |
| 高风险 | 🔴 | `rk_risks high+critical COUNT` |

### 5.4 安全设置页（`/security`）

**模板**：`templates/security.html`
**JS**：内联 `<script>`

**功能区块**：
1. 访问控制（3 个 Toggle 开关）
2. Token 管理（生成表单 + 列表表格 + 撤销按钮）
3. 访问说明（本机/LAN URL + 安全提示）

### 5.5 CSS 扩展

在 `static/css/style.css` 中新增：

```css
/* Bangcle 品牌色覆盖 */
:root { --c-primary: #1a56db; ... }

/* Toggle 开关 */
.switch { ... } .slider { ... }

/* KPI 卡片 */
.kpi-card { ... }

/* 详情侧边栏 */
.detail-panel { position: fixed; right: 0; ... }

/* 弹窗 */
.modal { ... } .modal-content { ... }

/* 状态标签 */
.badge { ... } .badge-blue { ... } ...

/* 响应式 */
@media (max-width: 768px) { ... }
```

---

## 6. 启动方式

### 6.1 本机访问

```bash
cd L4-proprietary/components/bdms/src
python3 -m uvicorn bdms.web.main:app --host 127.0.0.1 --port 8812 --reload
```

### 6.2 局域网访问

```bash
python3 -m uvicorn bdms.web.main:app --host 0.0.0.0 --port 8812
```

### 6.3 获取初始 Token

首次启动时，`init_security()` 在 `data/security.json` 中生成 admin Token。

查看方式：
```bash
cat data/security.json | python3 -m json.tool
```

或通过 `/login` 页面输入 Token 登录。

---

## 7. 验收测试

### ⚠️ 测试方法强制要求

**必须使用真实 HTTP 请求（浏览器或 urllib）完成端到端测试，禁止使用 FastAPI TestClient。**

原因：TestClient 的 host 为 `testserver`，不走真实网络栈，无法覆盖以下场景：
- 内外网访问控制（localhost vs 外网判定）
- Cookie 读写流程（登录 → Set-Cookie → 带 Cookie 访问）
- 真实 HTTP 头（Authorization、User-Agent 等）

**标准测试流程**：

```python
import urllib.request, urllib.error, http.cookiejar

# 1. 启动服务（确保 data/bdms.db 已 init）
# 2. 创建 CookieJar 模拟浏览器
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# 3. 登录 → 获取 Cookie
data = urllib.parse.urlencode({'token': ADMIN_TOKEN}).encode()
req = urllib.request.Request(f'{BASE}/login', data=data, method='POST')
opener.open(req)  # Set-Cookie 自动存入 cj

# 4. 带 Cookie 访问页面（CookieJar 自动附带）
opener.open(f'{BASE}/contract')  # 200

# 5. 带 Cookie 调 API
opener.open(f'{BASE}/api/contract/list')  # 200
```

**⚠️ 浏览器真实操作路径覆盖（强制）**：

E2E 测试必须覆盖浏览器实际传什么格式/参数，不能只测 API 层：

| 场景 | 浏览器行为 | 测试必须覆盖 |
|---|---|---|
| 月份选择器 | `<input type="month">` 返回 `YYYY-MM` | 同时测 `YYYY-MM` 和 `YYYYMM` 两种格式 |
| 导出按钮 | `doExport()` 取 input 值拼 URL | 验证前端 JS 格式转换 + 后端兼容 |
| 页面跳转 | `window.location.href` 触发 GET | 验证返回 Content-Type 和文件内容 |

**后端 API 多格式兼容（强制）**：

- ✅ 后端 API 应同时兼容 `YYYY-MM` 和 `YYYYMM` 两种格式
- ✅ 不依赖前端做格式转换（前端可能缓存旧 JS、用户直接调 API 等）
- ❌ 禁止只接受一种格式而报错

### 7.1 功能验收

| # | 验收项 | 测试步骤 | 通过标准 |
|---|---|---|---|
| 1 | 登录 | POST `/login` → 带 Cookie 访问 `/` | 200，非重定向到 `/login` |
| 2 | 合同列表 | 登录后 GET `/contract` | 200，页面渲染 |
| 3 | 合同详情 | 登录后 GET `/api/contract/{id}` | 200，返回合同数据 |
| 4 | 项目列表 | 登录后 GET `/project` | 200，页面渲染 |
| 5 | 项目详情 | 登录后 GET `/api/project/{id}` | 200，含 phases/team/cost/risk |
| 6 | MVP 看板 | 登录后 GET `/dashboard-mvp` | 200，8 个 KPI 卡片 |
| 7 | Dashboard API | 登录后 GET `/api/dashboard/mvp/2026-09` | 200，返回 8 个指标 |
| 8 | 安全设置页 | 登录后 GET `/security` | 200，开关可操作 |
| 8a | **导出 Excel（浏览器路径）** | 模拟浏览器传 `YYYY-MM` 格式调 `/api/report/export/2026-05` | 200，返回 Excel 文件（后端兼容两种格式） |
| 8b | **导出 Excel（API 路径）** | 传 `YYYYMM` 格式调 `/api/report/export/202605` | 200，返回 Excel 文件 |
| 8c | **前端格式转换** | 验证 `doExport()` 将 `YYYY-MM` 转为 `YYYYMM` | 转换后 URL 不含横杠 |

### 7.2 安全验收

| # | 验收项 | 测试步骤 | 通过标准 |
|---|---|---|---|
| 9 | Token 鉴权 | 无 Cookie 访问 `/api/contract/list` | 401 |
| 10 | Cookie Token | 登录后带 Cookie 访问 API | 200（Cookie 中的 Token 被正确读取） |
| 11 | 外网关闭 | `allow_external=false` 时从外网访问 | 403 |
| 12 | localhost 放行 | 从 `127.0.0.1` 访问任意页面 | 200（不被当外网拦截） |
| 13 | IPv6 localhost | 从 `::1` 或 `::ffff:127.0.0.1` 访问 | 200 |
| 14 | Cookie 安全 | 检查 Set-Cookie 头 | HttpOnly + SameSite=Lax |

### 7.3 品牌验收

| # | 验收项 | 测试步骤 | 通过标准 |
|---|---|---|---|
| 15 | Logo 展示 | GET `/` 检查 HTML 含 logo.png | 页面含 Logo 图片标签 |
| 16 | Favicon | GET `/static/app/img/favicon.png` | 200 |
| 17 | 品牌色 | 检查 CSS `:root` 含 `--c-primary: #1a56db` | 品牌色正确 |

### 7.4 回归验收

| # | 验收项 | 测试步骤 | 通过标准 |
|---|---|---|---|
| 18 | v1.0 页面 | GET `/dashboard` `/revenue` `/report` | 全部 200 |
| 19 | 全量测试 | `python3 -m pytest tests/ -q` | 0 failed |
| 20 | 凭据扫描 | `grep -rn "password\|secret\|api_key" src/ --include="*.py"` | 无明文密钥 |

---

## 8. 工时估算

| 任务 | 预估 | 实际 |
|---|---|---|
| Logo 资源 + 品牌色 | 15 min | ✅ |
| 网络安全模块 | 45 min | ✅ |
| 合同 API 路由 | 30 min | ✅ |
| 项目 API 路由 | 30 min | ✅ |
| Dashboard API | 15 min | ✅ |
| 合同页面 + JS | 60 min | ✅ |
| 项目页面 + JS | 60 min | ✅ |
| Dashboard 页面 | 30 min | ✅ |
| 安全设置页 | 30 min | ✅ |
| 登录页 | 15 min | ✅ |
| 联调测试 | 30 min | ✅ |
| **合计** | **~6h** | ✅ |

---

## 9. 变更历史

- 2026-09-21: r1 初版（`DESIGN-WEB-UI-v2.1.md`），未包含网络安全
- 2026-09-21: r2 追认版 — 新增网络安全模块（内外网开关 + Token 鉴权 + 登录页），品牌设计细化（Bangcle Logo + 品牌色），工时从 ~4h 调整为 ~6h

---

<!-- project: github.com/RenLimin/openclaw-v5.0 -->
