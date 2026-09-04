---
id: ADR-202609-027
title: "FIN-L4 家庭理财管理系统 — 架构决策"
layer: L4
layers:
  - L4
tags:
  - finance
  - architecture
  - L4
  - personal-finance
stage: design
status: proposed
date: 2026-09-04
---

# ADR-202609-027: FIN-L4 家庭理财管理系统 — 架构决策

| 字段 | 值 |
|---|---|
| 状态 | proposed |
| 决策日期 | 2026-09-04 |
| 决策者 | Rex |
| 层级 | L4 专有业务层 |
| 依赖 | ADR-202609-026 (L3 理财框架) |
| 相关 | FIN-001~006, FIN-L4-PF01 |

## 背景

L3 已完成 6 个通用理财引擎（账户/贷款/保险/利率/投资/建议），需要一个完整的 L4 管理系统来承载日常理财场景。

**业界调研结论**：
- Firefly III（PHP）：复式记账 + 规则引擎 + CSV导入 + REST API，但无贷款/保险/投资模块
- Actual（Node.js）：本地优先 + 跨设备同步，但无中文、无投资/保险
- GnuCash（C/GTK）：专业双分录桌面会计，UI 老旧
- Ghostfolio（TypeScript）：投资追踪专用，无记账
- **共识**：复式记账是底线、手动+CSV 是数据录入主流、本地存储是隐私标准

## 决策

建设独立的 FIN-L4 家庭理财管理系统，包含：

1. **Web UI**：FastAPI + Jinja2 模板，独立服务运行（端口 8500）
2. **CLI 交互**：`finctl` 命令行 + OpenClaw 对话双通道
3. **数据持久化**：SQLite + 自定义 Repository 模式
4. **报表导出**：Excel（openpyxl）+ Word（python-docx）
5. **利率同步**：定时任务（每周）+ 手动触发，LPR/央行利率
6. **L3 引擎复用**：所有计算委托 L3，L4 只做 CRUD + 编排

## 技术选型

| 层 | 选型 | 理由 |
|---|---|---|
| Web 框架 | FastAPI + Jinja2 | 轻量、异步、模板渲染、易部署 |
| ORM | 手写 Repository + sqlite3 | L3 已有零副作用约定，轻量 ORM足够 |
| 前端 | 原生 HTML/CSS/JS + Chart.js | 零构建步骤，够用 |
| Excel 导出 | openpyxl | L2 Office 011 已验证 |
| Word 导出 | python-docx | L2 Office 011 已验证 |
| 定时任务 | APScheduler | 轻量、内存调度、无需外部依赖 |
| CLI | Click | 标准 Python CLI 框架 |

## 架构约束

1. **零副作用边界**：L3 引擎不持有数据，L4 负责所有持久化
2. **数据隔离**：每个家庭一个 SQLite 文件（`fin_l4_{family_id}.db`）
3. **API 契约**：Web UI 和 OpenClaw 共享同一套 Service 层
4. **敏感操作**：不连银行/券商 API，不执行线上交易
5. **灵活部署**：单文件 `python -m fin_l4` 启动，支持 Docker

## 新增功能（Rex 2026-09-04 增补）

### N1: 外部数据接入层 (external_data_svc)

**定位**：可扩展的外部数据获取框架，当前支持利率，预留行情/汇率等。

```
external/
├── __init__.py
├── base.py              # DataSource 抽象基类 + Registry
├── rate_source.py       # 利率数据源（LPR/央行/商业银行）
├── market_source.py     # 行情数据源（预留：股票/基金净值）
├── fx_source.py         # 汇率数据源（预留：外币资产）
└── registry.py          # 数据源注册表
```

| 数据源 | 当前 | 预留 | 获取方式 |
|---|---|---|---|
| LPR 利率 | ✅ | — | 央行官网/API Ninjas |
| 央行基准利率 | ✅ | — | 央行官网 |
| 商业银行利率 | ✅ | — | 各银行官网 |
| 股票/基金行情 | — | ⏳ | 东方财富/新浪 API |
| 汇率 | — | ⏳ | 中国外汇交易中心 |
| 房价指数 | — | ⏳ | 国家统计局 |

**设计要点**：
- 每个数据源实现 `fetch() → DataSnapshot` 统一接口
- 自动缓存 + TTL（利率 24h，行情 15min）
- 数据源降级链：主源失败 → 备用源 → 缓存兜底
- 定时任务 + 手动触发双通道

### N2: 外部系统链接 (integration_svc)

**定位**：预留与外部理财/银行/券商系统的连接能力。

```
integration/
├── __init__.py
├── base.py              # IntegrationPlugin 接口
├── registry.py          # 插件注册表
├── links/               # 链接管理
│   ├── bank_links.py    # 银行网银链接（只读查看）
│   ├── broker_links.py  # 券商链接（只读查看）
│   └── fund_links.py    # 基金平台链接（只读查看）
└── plugins/             # 插件目录（未来）
    ├── __init__.py
    └── README.md        # 插件开发指南
```

**当前阶段**：链接管理（URL + 备注 + 跳转），不实现 API 集成

| 链接类型 | 功能 | 安全边界 |
|---|---|---|
| 银行网银 | URL 管理 + 跳转 | 只读，不存储凭据 |
| 券商系统 | URL 管理 + 跳转 | 只读，不存储凭据 |
| 基金平台 | URL 管理 + 跳转 | 只读，不存储凭据 |
| 第三方理财 | URL 管理 + 跳转 | 只读，不存储凭据 |

**预留扩展点**：
- `IntegrationPlugin` 接口：`auth() → sync() → disconnect()`
- 未来可接入：银行 OpenAPI、券商条件单、基金定投
- **安全红线**：所有外部凭据通过 L2 凭据管理，不写明文

### N3: 本地数据安全 (security_svc)

**定位**：家庭财务数据的本地安全管理。

```
security/
├── __init__.py
├── encryption.py        # 数据加密（AES-256-GCM）
├── access_control.py    # 访问控制（PIN/密码）
├── backup.py            # 备份/恢复
├── audit.py             # 审计日志
└── wipe.py              # 数据销毁
```

| 能力 | 实现 | 说明 |
|---|---|---|
| 数据库加密 | SQLCipher / 文件级 AES | 静态数据加密 |
| 访问控制 | PIN / 密码 | Web UI 登录保护 |
| 自动备份 | 定时 + 手动 | 本地 + 可选外部存储 |
| 备份加密 | AES-256-GCM | 备份文件加密 |
| 审计日志 | 操作记录 | 谁/何时/做了什么 |
| 数据销毁 | 安全擦除 | 覆写后删除 |

**安全分层**：
```
L1: 文件级加密（整个 .db 文件）— 防物理窃取
L2: 访问控制（PIN/密码）— 防未授权访问
L3: 审计日志（操作追踪）— 可追溯
L4: 加密备份 — 防备份泄露

## 模块划分

```
fin_l4/
├── __init__.py          # 包入口
├── main.py              # FastAPI 应用 + 路由
├── cli.py               # CLI 入口 (finctl)
├── config.py            # 配置管理
├── db/
│   ├── __init__.py      # 数据库连接 + 迁移
│   ├── models.py        # 数据模型 (Repository 模式)
│   └── repositories.py  # CRUD 操作
├── services/
│   ├── __init__.py
│   ├── account_svc.py   # 账户服务
│   ├── txn_svc.py       # 交易/记账服务
│   ├── loan_svc.py      # 贷款服务
│   ├── insurance_svc.py # 保险服务
│   ├── portfolio_svc.py # 投资服务
│   ├── report_svc.py    # 报表服务
│   ├── advise_svc.py    # 理财建议服务
│   └── rate_svc.py      # 利率同步服务
├── web/
│   ├── static/          # CSS/JS
│   └── templates/       # Jinja2 模板
├── templates/           # 报表模板
└── tests/
```

## 验证标准

- [ ] Web UI 启动，浏览器访问 http://localhost:8500
- [ ] 创建家庭 → 导入期初余额 → 记一笔 → 查余额 → 出报表
- [ ] 贷款管理：创建 → 还款计划 → 提前还款测算
- [ ] 保险管理：添加保单 → 现金价值 → 保障缺口
- [ ] 投资持仓：买入 → 更新价格 → 盈亏 → 再平衡建议
- [ ] 利率同步：手动触发 + 定时自动
- [ ] 报表导出：Excel + Word
- [ ] CLI 全流程可用
- [ ] OpenClaw 对话可用
- [ ] 100% 测试覆盖核心路径

