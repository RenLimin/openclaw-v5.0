# BDMS 浏览器自动化技术选型方案

> 版本：v1.0（2026-10-08）
> 层级：L4 专有业务层 — 横切基础设施
> 依据：已有的 12 份设计文档 + 14 个代码文件 + 9 轮实际踩坑经验
> 配套：`docs/knowledge-base/by-category/project-experience/adr/ADR-202610-001-browser-automation-selection.md`

---

## 1. 问题定义

BDMS 依赖 5 个外部系统的数据导入（ONES / OA / 工时门户 / 企微文档 / 本机导入），其中 3 个必须通过浏览器自动化获取数据。每次会话都在重复踩同样的坑，根本原因是**缺乏统一的技术选型和经验沉淀**。

---

## 2. 现有资产清单

### 2.1 IAM 认证基础设施

| 资产 | 位置 | 状态 |
|---|---|---|
| `iam_auth.py` | `delivery-center/src/.../collectors/` | ✅ 成熟，12h TTL + 自动刷新 |
| `iam_cookies.json` | `~/.openclaw/data/` | ⚠️ cookie 值为空，需重新登录 |
| `iam_sso_cookies.json` | `~/.openclaw/data/oa_exports/` | ⚠️ 37 天前过期 |
| `login_iam()` / `login_ones()` | `iam_auth.py` | ✅ 可用，需要凭据 |
| `inject_cookies_to_context()` | `iam_auth.py` | ✅ 可用 |

### 2.2 ONES 采集（已验证通过）

| 资产 | 位置 | 方案 | 状态 |
|---|---|---|---|
| `ones-browser-export` skill | `L4-proprietary/skills/` | osascript + Chrome | ✅ 成熟 |
| `ones_export_auto.py` | `delivery-center/scripts/` | osascript | ✅ 稳定 |
| `ones_collector.py` | `delivery-center/src/.../collectors/` | Playwright + cookie | ✅ 稳定 |
| `ones_explore.py` | `delivery-center/scripts/` | 探索页⾯结构 | 辅助 |
| `ones_adapter.py` | `bdms/.../adapters/` | osascript（旧） | ❌ 脆弱 |
| `ones_connector.py` | `bdms/.../connectors/` | Adapter 封装 | ⚠️ 依赖旧适配器 |

### 2.3 OA 采集（半残）

| 资产 | 位置 | 方案 | 状态 |
|---|---|---|---|
| `oa_collector.py` | `delivery-center/src/.../collectors/` | Playwright CDP | ⚠️ 有代码，未稳定 |
| `oa_adapter.py` | `bdms/.../adapters/` | osascript | ❌ 不适用于 OA 异步导出 |
| `oa_connector.py` | `bdms/.../connectors/` | Adapter 封装 | ⚠️ 依赖旧适配器 |
| `oa_export_playwright.py` | `bdms/scripts/` | Playwright CDP | ⚠️ 有代码，未测试通过 |
| `oa_export_full.py` | `bdms/scripts/` | Playwright CDP（自包含） | ⚠️ 有代码，未测试通过 |

### 2.4 工时门户（已通过）

| 资产 | 位置 | 方案 | 状态 |
|---|---|---|---|
| `workhour_collector.py` | `delivery-center/src/.../collectors/` | Playwright DOM 提取 | ✅ 稳定 |

### 2.5 企微文档（已验证通过）

| 资产 | 位置 | 方案 | 状态 |
|---|---|---|---|
| `wecom_collector.py` | `delivery-center/src/.../collectors/` | wecom_mcp API | ✅ 稳定 |
| `wecom_api_adapter.py` | `bdms/.../adapters/` | wecom_mcp API | ✅ 稳定 |

### 2.6 BDMS 集成框架（新建）

| 资产 | 位置 | 方案 | 状态 |
|---|---|---|---|
| `BaseConnector` | `bdms/.../base.py` | 抽象基类 | ✅ 已设计 |
| `IntegrationService` | `bdms/.../service.py` | 编排层 | ✅ 已设计 |
| `connectors/*.py` | `bdms/.../connectors/` | 5 个连接器 | ✅ 已实现 |
| `adapters/*.py` | `bdms/.../adapters/` | 数据源适配器 | ⚠️ 部分残旧 |

---

## 3. 各系统浏览器自动化方案对比

### 3.1 ONES 数据采集

| 维度 | osascript 方案 | Playwright 方案 |
|---|---|---|
| **稳定性** | ⭐⭐⭐⭐ 4 轮验证通过 | ⭐⭐⭐ 依赖 cookie 注入 |
| **性能** | ⭐⭐⭐⭐ 直接 Chrome 执行 | ⭐⭐⭐ 需启动浏览器 |
| **维护成本** | ⭐⭐⭐ 菜单索引可能变化 | ⭐⭐⭐⭐ DOM 选择器更灵活 |
| **跨系统复用** | ⭐⭐ ONES 专用 | ⭐⭐⭐⭐ 可复用于 OA/工时 |
| **异步交互** | ⭐⭐⭐⭐ 天然支持 SPA | ⭐⭐⭐⭐ 支持 wait_for |
| **下载处理** | ⭐⭐⭐ 等 Downloads 目录 | ⭐⭐⭐⭐ expect_download |

**推荐：** 保持 osascript（已稳定），但将 `ones_adapter.py` 从 osascript 升级为 Playwright 统一方案。

### 3.2 OA 合同台账导出

| 维度 | osascript 方案 | Playwright CDP | Playwright 自启动 |
|---|---|---|---|
| **异步进度弹窗** | ❌ 轮询困难 | ✅ 支持 DOM 轮询 | ✅ 支持 DOM 轮询 |
| **SSO 登录** | ⚠️ 依赖现有会话 | ✅ CDP 复用登录态 | ⚠️ 需重新登录 |
| **iframe 处理** | ❌ 无法跨 frame | ✅ frame.locator | ✅ frame.locator |
| **下载事件** | ❌ 不支持 | ✅ expect_download | ✅ expect_download |
| **进程生命周期** | ❌ exec 5 分钟超时 | ⚠️ CDP 需要长存活 | ⚠️ 需要长存活 |
| **代理干扰** | ⚠️ 部分影响 | ⚠️ SSL handshake 失败 | ⚠️ 需绕过代理 |

**推荐：** Playwright CDP + 长存活 background 进程（用 `background: true` 绕过 exec 超时）。

### 3.3 工时门户

**方案：** Playwright DOM 提取（已验证稳定）。

### 3.4 企微文档

**方案：** wecom_mcp API（已验证稳定）。

---

## 4. 统一技术选型方案

### 4.1 核心决策

| 决策 | 选择 | 原因 |
|---|---|---|
| **浏览器自动化引擎** | Playwright | 统一 API、iframe 支持、下载事件、异步轮询 |
| **登录态管理** | IAM Cookie 池 + CDP 复用 | 一次登录，多系统共享 |
| **进程管理** | `background: true` 长存活 | 避免 exec 5 分钟超时 |
| **网络代理** | `NO_PROXY=* no_proxy=*` | 避免本地 HTTPS 被代理干扰 |
| **经验沉淀** | SKILL.md + ADR + 本文档 | 避免每次从头踩坑 |

### 4.2 分层架构

```
┌─────────────────────────────────────────────────────────┐
│                 统一浏览器自动化层                         │
├─────────────────────────────────────────────────────────┤
│   IAM 认证基础设施                                        │
│   login_iam() → cookie pool → inject_cookies()           │
│   (12h TTL, 自动刷新)                                    │
├─────────────────────────────────────────────────────────┤
│   浏览器连接层                                            │
│   ├── CDP 复用（已有 Chrome，保留登录态）                 │
│   └── Playwright 自启动（全新 profile，兜底）             │
├─────────────────────────────────────────────────────────┤
│   系统特定导航层                                          │
│   ├── ONES: 筛选器切换 → 菜单 → 导出 → 下载              │
│   ├── OA: IAM→面板→菜单→Cube iframe→导出→轮询→下载       │
│   ├── 工时: IAM→面板→DOM 提取                            │
│   └── 企微: MCP API（不走浏览器）                         │
├─────────────────────────────────────────────────────────┤
│   数据标准化层                                            │
│   原始数据 → normalize → 暂存表 → 业务表                  │
└─────────────────────────────────────────────────────────┘
```

### 4.3 关键经验教训（不再踩坑）

| # | 教训 | 根因 | 解决 |
|---|---|---|---|
| 1 | OA 导出不能 `goto(oa.bangcle.com)` 直接访问 | IAM SSO 必须通过面板跳转触发换票 | 从 IAM 首页点击 OA 卡片 |
| 2 | OA 导出按钮在 Cube iframe 内 | frame[1] 是 Cube 搜索页 | 用 `frame.locator()` 跨 frame |
| 3 | OA 导出是异步的，不能 `expect_download()` | 服务端生成文件，进度弹窗轮询 | 轮询 `.ant-modal-body` 进度文本 |
| 4 | exec 5 分钟超时杀进程 | OA 导出需 5-10 分钟 | `background: true` 长存活 |
| 5 | Playwright 连 CDP 被代理干扰 | `http_proxy` 环境变量 | `NO_PROXY=*` 绕过 |
| 6 | osascript 处理不了 OA 异步弹窗 | osascript 是单次执行，无法轮询 | 用 Playwright 替代 |
| 7 | 全新 Chrome profile 没有 SSO cookie | IAM 换票只在已登录浏览器中有效 | CDP 复用已登录 Chrome |
| 8 | `iam_cookies.json` cookie 值为空 | 之前没真正保存 | 重新登录并验证 cookie 保存 |
| 9 | headless 浏览器被 OA IAM 反爬拦截 | headless 特征明显 | CDP + headful Chrome |

---

## 5. 实施计划

### Phase 1：修复 IAM 认证基础设施 ✅ 完成
- [x] 用凭据 `limin.ren / June-123` 重新登录 IAM
- [x] 验证 `iam_cookies.json` 保存了有效 cookie（JSESSIONID + x-access-token，长度 283）
- [x] 修复 `iam_auth.py` 的 `login_iam()`：
  - 根因：直接访问 `#/home/index` 跳过登录页，cookie 为空
  - 修复：导航到 `#/login` → 填表单 → 等待跳转 `#/home` → 获取 cookie → 按域名分组保存
  - 获取到 2 个 Cookie（JSESSIONID + x-access-token），长度 283

### Phase 2：统一 OA 导出为 Playwright CDP
- [ ] 修复 `oa_collector.py` 的 CDP 连接（绕过代理）
- [ ] 实现 IAM→OA 面板跳转（不直接 goto OA）
- [ ] 实现 Cube iframe 内导出按钮定位
- [ ] 实现异步进度轮询
- [ ] 用 `background: true` 跑，验证完整流程

### Phase 3：统一 ONES 为 Playwright
- [ ] 将 `ones_adapter.py` 从 osascript 升级为 Playwright
- [ ] 复用 IAM cookie 注入
- [ ] 验证筛选器切换 + 导出 + 下载全流程

### Phase 4：清理旧资产
- [ ] 删除 `oa_export_playwright.py` / `oa_export_full.py` / `oa_export_v2.py`（重复脚本）
- [ ] 将 `oa_adapter.py` 和 `ones_adapter.py` 标记为 deprecated
- [ ] 更新 `DESIGN-DETAIL-INTEGRATION-v2.1.md` 反映新方案

---

## 6. 验证标准

| 系统 | 验证方式 | 通过标准 |
|---|---|---|
| IAM 登录 | `login_iam()` + cookie 保存 | `is_cookie_valid()` 返回 True |
| ONES 签约导出 | `ones_collector.collect('sign')` | CSV 文件 > 1MB，行数 > 1000 |
| OA 合同台账导出 | `oa_collector.collect_contract_ledger_xlsx()` | XLSX 文件 > 1MB |
| 工时门户 | `workhour_collector.collect_workhour_data()` | CSV 文件 > 1KB |
| 企微文档 | `wecom_collector` | JSON 文件 > 1KB |

---

## 7. 变更历史

- 2026-10-08: v1.0 初版 — 全面梳理现有资产，明确技术选型
