# browser-automation — 浏览器自动化基础设施（空占位）

> L2 基础设施层 · 浏览器自动化基础设施（**占位目录，无独立入口**）
>
> **2026-11-20**：补写根级设计文档，如实记录该目录为**空占位**，真实能力分布在
> `browser-isolated-chrome`（隔离 Chrome + CDP）与 L4 `delivery-center` collectors / `bdms` 浏览器适配层。
> 本文**不虚构架构**；所有指向均为真实代码路径（已逐条核对）。

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 组件类 | 浏览器自动化基础设施（占位） |
| 状态 | 📐 占位（目录存在、**0 文件**；本 DESIGN.md 为唯一内容） |
| 关联规范 | `capability-registry/registry.yaml` 条目 `browser-automation`（L2）与 `browser-isolated-chrome`（L2） |
| 能力注册表 entry | `L2-infra/components/browser-automation/ (空占位目录，无独立入口；实际能力 = browser-isolated-chrome)` |

**一句话定位**：本目录**不承载任何浏览器代码**，它是资产清单中「浏览器自动化基础设施」这一 L2 能力族的
占位锚点。真实的浏览器能力由两个既有条目承担：

1. **`browser-isolated-chrome`**（L2 能力族）——隔离 Chrome 实例（专用 profile + CDP 端口），
   红线：**禁止驱动用户现有 Chrome**；用后即关主进程并确认端口释放。
2. **L4 真实实现**——`delivery-center` collectors（OA/ONES/工时采集）与 `bdms` 的 Playwright/CDP 适配层。

> ⚠️ 不要在本目录内新建实现。新增浏览器能力请落到 `browser-isolated-chrome` 条目指向的
> profile/CDP 约定，或直接落在 L4 使用方（`delivery-center` / `bdms`）。

## 2. 设计约束

以下约束来自 registry.yaml 条目与真实代码实证，**不是本目录的代码**：

1. **隔离优先，绝不驱动用户现有 Chrome**：必须用独立 `--user-data-dir` 的 Chrome 实例（registry `browser-isolated-chrome` notes 引红线 commit `0a19971`）。实证：`docs/architecture/components/browser-automation-oa-export.md` §1「永远不要操作用户正在使用的 Chrome 会话」。
2. **专用持久化 profile + CDP 端口**：`~/.openclaw/data/chrome-profiles/oa-live` + CDP `http://127.0.0.1:9333`（registry 实测值）；调用方用 Playwright `connect_over_cdp` 连接，不另起浏览器。本机现存 profile：`oa-live` / `oa-recon` / `wecom`。
3. **用后即关 + 确认端口释放**：任务结束关闭主进程并确认端口释放，避免残留调试端口（安全暴露面）。
4. **CDP 复用登录态**：`bdms/src/bdms/modules/integration/adapters/browser_adapter.py` 的 `BrowserAdapter.launch(cdp_url=...)` 优先 `connect_over_cdp`，失败才回退新起浏览器；Cookie 池（`~/.openclaw/data/iam_cookies.json`，TTL 12h）跨系统共享。
5. **生产系统只读采集，不写业务**：所有真实实现均为「导航 → 定位 → 导出/复制 → 落盘」的采集路径，无对生产系统的写操作。
6. **凭据不入文档**：`docs/architecture/components/browser-automation-oa-export-detail.md` §2 明确红线「设计文档中禁止出现真实用户名密码」。

## 3. 架构（真实能力分布图）

```
        L2-infra/components/browser-automation/  ← 本目录（空占位，0 实现文件）
                          │
                          │ 能力族归属（registry.yaml）
                          ▼
        ┌───────────────────────────────────────────────────────────┐
        │  browser-isolated-chrome（L2 能力族）                      │
        │   ~/.openclaw/data/chrome-profiles/<name>                  │
        │   + CDP http://127.0.0.1:9333                              │
        │   红线：禁止驱动用户现有 Chrome；用后即关 + 端口释放        │
        └───────────────────────────┬───────────────────────────────┘
                                    │ 被以下真实实现消费
        ┌───────────────────────────┴───────────────────────────────┐
        ▼                                                           ▼
┌───────────────────────────────────────┐   ┌──────────────────────────────────────┐
│ L4 delivery-center collectors         │   │ L4 bdms 浏览器适配层                  │
│ src/delivery_center/v1/collectors/    │   │ src/bdms/modules/integration/        │
│  ├─ oa_collector.py（OA 合同台账）    │   │  adapters/browser_adapter.py         │
│  ├─ ones_collector.py（ONES 工作项）  │   │   ├─ BrowserAdapter（CDP + Cookie池） │
│  ├─ wecom_collector.py（企微文档）    │   │   ├─ login_iam / ensure_logged_in    │
│  └─ workhour_collector.py（工时）     │   │   ├─ _sso_login_if_needed             │
│ src/delivery_center/v2/oa_csv_exporter│   │   └─ find_frame / expect_download    │
│                                       │   │ src/bdms/core/browser.py            │
│ 方法论文：                             │   │   ├─ save/get_browser_cookies         │
│  docs/architecture/components/        │   │   ├─ connect_local_chrome(:9222)      │
│   browser-automation-oa-export.md     │   │   └─ import_wecom_mac_cookies        │
│   browser-automation-oa-export-detail │   │ scripts/start_wecom_chrome.py        │
│   browser-automation-wecom-doc.md     │   │   （launch_persistent_context + 9222）│
└───────────────────────────────────────┘   └──────────────────────────────────────┘
                                    │
                                    ▼
         L4-proprietary/skills/ones-browser-export（ONES 导出 skill，
         osascript 驱动「用户已登录的 Chrome」标签页——**注意：与本能力族
         「隔离实例」红线不同，属 ONES 特定路径，见该 SKILL.md 前置条件**）
```

### 3.1 真实能力入口（可用）

| 入口 | 路径 / 命令 | 说明 |
|---|---|---|
| 隔离 Chrome + CDP | `~/.openclaw/data/chrome-profiles/oa-live`，CDP `http://127.0.0.1:9333` | registry `browser-isolated-chrome` entry |
| 统一浏览器适配层 | `L4-proprietary/components/bdms/src/bdms/modules/integration/adapters/browser_adapter.py` → `BrowserAdapter` / `browser_session()` | Playwright CDP + IAM Cookie 池，统一 OA/ONES/工时 |
| OA 采集器 | `python -m delivery_center.v1.collectors.oa_collector <YYYYMM> [--headless]` | 合同台账；Cookie 池复用 + `expect_download()` |
| ONES 采集器 | `L4-proprietary/components/delivery-center/src/delivery_center/v1/collectors/ones_collector.py` | ONES 工作项导出 |
| 企微文档 Chrome | `python3 L4-proprietary/components/bdms/scripts/start_wecom_chrome.py` | `launch_persistent_context` + 持久化 profile + CDP 9222 |
| 方法论文档 | `docs/architecture/components/browser-automation-*.md` | 环境隔离 / 等待策略 / 定位降级 / iframe 处理 |

### 3.2 本目录的（预期）空结构

```
browser-automation/
└── DESIGN.md      ← 2026-11-20 新增，唯一文件
```

## 4. 接口与用法

本目录**没有接口**，也没有定时任务。使用真实能力请走 §3.1 入口。典型形态：

```bash
# 1) 隔离 Chrome（专用 profile + CDP）——见 browser-automation-oa-export.md §1 的完整命令行
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/Users/bangcle/.chrome-automation-profile \
  --no-first-run --disable-extensions --disable-sync \
  --disable-background-networking --disable-gpu \
  https://iam.bangcle.com/#/login

# 2) Playwright 连接（复用登录态），而非启动新浏览器
#    adapter = BrowserAdapter(); adapter.launch(cdp_url="http://127.0.0.1:9222")
```

> 端口说明：registry `browser-isolated-chrome` 记 `9333`；`bdms` 侧 `connect_local_chrome` 默认 `9222`，
> `start_wecom_chrome.py` 亦为 `9222`。两处为**不同 profile 的不同实例**（`oa-live` vs `wecom`），
> 使用时按 profile 选端口，并遵守「用后即关 + 端口释放」红线。

## 5. 业界对标

| 对标 | 借鉴点 | 参考 |
|---|---|---|
| Chrome DevTools Protocol（官方） | `connect_over_cdp` 复用已登录会话、独立 `--user-data-dir` 隔离 | Chrome DevTools Protocol 官方文档（chromedevtools.github.io） |
| Playwright 官方文档 | `launch_persistent_context` 持久化登录态、`expect_download` 接管下载、frame locator | playwright.dev 官方文档 |
| OWASP 凭据与浏览器安全 | 生产系统只读采集、凭据不入文档、调试端口用后释放 | OWASP Top 10 / OWASP Secure Coding Practices |
| Backstage 能力族建模 | 一个「能力族」占位 + 多个真实实现入口，而非单点组件 | backstage.io Software Catalog / 能力建模 |

## 6. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-10-09 | 目录创建（空占位） |
| 2026-11-20 | 补写根级 `DESIGN.md`：如实记录「空占位」定位，指向 `browser-isolated-chrome` 与 L4 真实能力入口 |
