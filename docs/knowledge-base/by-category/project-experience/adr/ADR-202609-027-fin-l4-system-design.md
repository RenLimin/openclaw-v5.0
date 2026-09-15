---
id: ADR-202609-027
title: "FIN-L4 家庭理财管理系统 — 架构决策"
layers:
  - L4
tags:
  - finance
  - architecture
  - L4
  - personal-finance
stage: design
status: accepted
date: 2026-09-04
updated: 2026-09-15
---

# ADR-202609-027: FIN-L4 家庭理财管理系统 — 架构决策

| 字段 | 值 |
|---|---|
| 状态 | accepted |
| 决策日期 | 2026-09-04 |
| 决策者 | Rex |
| 层级 | L4 专有业务层 |
| 依赖 | ADR-202609-026 (L3 理财引擎框架) |
| 相关 | FIN-001~006, FIN-L4-PF01 |
| 更新 | M5 打磨: 2026-09-15 |

## 1. 背景

L3 已完成 6 个通用理财引擎（账户/贷款/保险/利率/投资/建议），需要一个完整的 L4 管理系统承载日常理财场景。

**业界调研结论**：

| 产品 | 技术栈 | 优势 | 不足 |
|---|---|---|---|
| Firefly III | PHP + MySQL | 复式记账 + 规则引擎 + CSV导入 + REST API | 无贷款/保险/投资模块 |
| Actual | Node.js + SQLite | 本地优先 + 跨设备同步 | 无中文、无投资/保险 |
| GnuCash | C/GTK + XML/SQL | 专业双分录桌面会计 | UI 老旧、学习曲线陡 |
| Ghostfolio | TypeScript + PostgreSQL | 投资追踪专用 | 无记账 |

**业界共识**：
- 复式记账是理财系统的底线
- 手动录入 + CSV 导入是数据录入的主流
- 本地存储是隐私敏感场景的标准

## 2. 决策

建设独立的 FIN-L4 家庭理财管理系统，定位为 **L4 专有业务层首个完整应用，包含：

1. **Web UI**：FastAPI + Jinja2 模板，独立服务运行
2. **CLI 交互**：`finctl` 命令行 + OpenClaw 对话双通道
3. **数据持久化**：SQLite + Repository 模式
4. **报表导出**：Excel（openpyxl）+ Word（python-docx）
5. **利率同步**：定时任务（每周）+ 手动触发，LPR/央行利率
6. **L3 引擎复用**：所有计算委托 L3，L4 只做 CRUD + 编排

## 3. 技术选型

| 层 | 选型 | 理由 |
|---|---|---|
| Web 框架 | FastAPI + Jinja2 | 轻量、异步、模板渲染、易部署 |
| 数据层 | 手写 Repository + sqlite3 stdlib | 零外部依赖最少、与 L3 零副作用约定一致 |
| 前端 | 原生 HTML/CSS/JS + ECharts | 零构建步骤，ECharts 图表能力足够 |
| Excel 导出 | openpyxl | L2 Office 011 已验证可用 |
| Word 导出 | python-docx | L2 Office 011 已验证可用 |
| 定时任务 | 内置简单实现，未来可扩展 APScheduler | 轻量、内存调度 |
| CLI | Click | Python CLI 框架 | 标准 Python  |

## 4. 架构约束

1. **零副作用边界**：L3 引擎不持有数据，L4 负责所有持久化
2. **数据隔离**：每个家庭一个 SQLite 文件（`fin_l4_{family_id}.db`）
3. **API 契约**：Web UI 和 OpenClaw 共享同一套 Service 层
4. **敏感操作**：不连银行/券商 API，不执行线上交易
5. **灵活部署**：单文件 `python -m fin_l4` 启动，支持 Docker

## 5. 核心能力矩阵 (M1-M5 全量)

### M1: 骨架 + 数据层 + 8 服务 + Web UI + CLI
- ✅ 账户管理（资产/负债/收入/支出/权益 5 大类）
- ✅ 复式记账（借贷恒等式保证一致性）
- ✅ 预算管理（按月/分类设置 + 进度追踪 + 超支预警）
- ✅ 贷款管理（等额本息/等额本金 + 还款计划 + 提前还款测算）
- ✅ 保险管理（保单录入 + 现金价值表 + 保障缺口分析）
- ✅ 投资管理（组合/持仓 / 盈亏 / 再平衡建议）
- ✅ 理财建议（健康检查 + 资产配置建议）
- ✅ 报表系统（资产负债表 / 利润表 / 现金流量表）

### M2: 智能分类 + 预算 + CSV 导入
- ✅ 银行流水智能分类引擎（规则 + 关键字 + 正则三级匹配）
- ✅ 4 种银行格式模板（招行/工行/支付宝/微信）
- ✅ 预算执行追踪 + 日均可用金额预警
- ✅ CSV / Excel 双格式导入

### M3: 贷款/保险/投资深度
- ✅ 贷款详细还款计划表 + 提前还款方案对比
- ✅ 保险现金价值推演 + 保障缺口分析
- ✅ 投资组合绩效 + 资产配置 + 再平衡

### M4: 导出 + CLI + Skill
- ✅ Excel 多 sheet 报表导出
- ✅ `finctl` CLI 工具
- ✅ OpenClaw Skill 集成（对话式理财）

### M5: UI 打磨 + 知识库
- ✅ Web UI 响应式优化 + 视觉统一（冷锐精工风格）
- ✅ UX 三件套：加载状态 / 空状态 / 错误提示
- ✅ 知识库配套文档（ADR + 经验卡片）
- ⚠️ 测试：178 passed（11 个 dashboard API 测试隔离问题修复中）

## 6. 系统架构

### 6.1 分层架构

```
┌─────────────────────────────────────────────────┐
│                  Web UI 层                       │
│  FastAPI + Jinja2 + ECharts                 │
├─────────────────────────────────────────────────┤
│                  Service 层 (L4)                       │
│  account / txn / budget / loan / insurance    │
│  portfolio / report / advise / rate     │
│  import / export / security / integration │
├─────────────────────────────────────────────────┤
│                  L3 引擎层 (计算)                │
│  AccountingEngine / LoanEngine / ...       │
├─────────────────────────────────────────────────┤
│                  数据层 (Repository)          │
│  SQLite + Repository 模式                  │
└─────────────────────────────────────────────────┘
```

### 6.2 核心数据模型

| 表 | 用途 | 关键字段 |
|---|---|---|
| `fin4_families` | 家庭（数据隔离单元） | id, name, created_at |
| `fin4_accounts` | 账户（5 大类） | id, family_id, name, type, parent_id |
| `fin4_transactions` | 交易（双分录） | id, family_id, date, debit_id, credit_id, amount |
| `fin4_budgets` | 预算 | id, family_id, category_id, month, amount |
| `fin4_loans` | 贷款 | id, family_id, name, principal, rate, term, start_date |
| `fin4_insurance_policies` | 保险单 | id, family_id, name, type, premium, sum_assured |
| `fin4_portfolios` | 投资组合 | id, family_id, name, description |
| `fin4_holdings` | 持仓 | id, portfolio_id, asset_name, shares, cost_basis |
| `fin4_import_bank_templates` | 银行模板 | id, bank_code, config_json |
| `fin4_classification_rules` | 分类规则 | id, pattern, category_id, priority |

### 6.3 借贷记账法实现

- 会计恒等式：资产 = 负债 + 权益
- 每笔交易必须有借方账户和贷方账户，金额相等
- 账户类型决定余额方向（资产/费用增加在借方，负债/收入/权益增加在贷方

### 6.4 Decimal 精度保证

- 所有金额使用 `decimal.Decimal`，精度 28 位
- 数据库存储为 TEXT（避免 SQLite REAL 类型精度丢失）
- 计算过程全程 Decimal，展示时才 round 到 2 位小数

## 7. 扩展功能 (N1-N3)

### N1: 外部数据接入层 (external/)

可扩展的外部数据获取框架，当前支持利率，预留行情/汇率等。

| 数据源 | 状态 | 获取方式 |
|---|---|---|
| LPR 利率 | ✅ | 央行官网 / API Ninjas |
| 央行基准利率 | ✅ | 央行官网 |
| 商业银行利率 | ✅ | 各银行官网 |
| 股票/基金行情 | ⏳ 预留 | 东方财富 / 新浪 API |
| 汇率 | ⏳ 预留 | 中国外汇交易中心 |

设计要点：统一 `fetch() → DataSnapshot` 接口 + 自动缓存 TTL + 降级链

### N2: 外部系统链接 (integration/)

预留与外部理财/银行/券商系统的连接能力。当前阶段为链接管理（URL + 备注 + 跳转），不实现 API 集成。

安全红线：所有外部凭据通过 L2 凭据管理，不写明文

### N3: 本地数据安全 (security/)

```
security/
├── encryption.py   # 数据加密（AES-256-GCM）
├── backup.py       # 备份/恢复（14 份循环保留）
└── audit.py        # 审计日志
```

安全分层：
- **L1**: 文件级加密 — 防物理窃取
- **L2**: 访问控制（PIN/密码）— 防未授权访问
- **L3**: 审计日志（操作追踪）— 可追溯
- **L4**: 加密备份 — 防备份泄露

## 8. Web UI 设计

### 8.1 技术栈

- **框架**: FastAPI + Jinja2 模板
- **样式**: L2 `web-common` 组件库（base/layout/components/forms 4 套 CSS）+ 业务层 style.css
- **图表**: ECharts 5.5（CDN 加载，支持深色主题切换）
- **交互**: 原生 JS + fetch API，无前端构建步骤

### 8.2 页面清单 (12 个)

| 页面 | 路由 | 功能 |
|---|---|---|
| 仪表盘 | `/` | 总览卡片 + 收支趋势 + 分类饼图 + 预算 + 投资 + 快捷记账 |
| 账户管理 | `/accounts` | 账户列表 + 余额 |
| 记账 | `/transactions` | 交易列表 + 搜索/筛选 |
| 预算 | `/budget` | 预算总览 + 分类进度 |
| 贷款 | `/loans` | 贷款列表 + 详情 + 提前还款 |
| 保险 | `/insurance` | 保单列表 + 详情 + 保障缺口 |
| 投资 | `/portfolio` | 组合列表 + 详情 + 持仓 + 再平衡 |
| 报表 | `/reports` | 资产负债 + 收支 + 现金流 |
| 建议 | `/advise` | 理财健康检查 + 建议 |
| 利率 | `/rates` | 利率列表 + 同步 |
| 导入 | `/import` | 银行流水 CSV/Excel 导入 + 预览 |
| 设置 | `/settings` | 数据管理 + 外观 + 关于 |

### 8.3 UX 设计规范

- **设计语言**: 冷锐精工（深蓝主色 + 绿/红/琥珀 强调 + 12px 圆角 + 柔和阴影）
- **响应式**: 4 档断点（1200 / 1024 / 768 / 480）
- **深色模式**: CSS 变量驱动，一键切换
- **UX 三件套**:
  - 加载状态：骨架屏 + spinner
  - 空状态：图标 + 标题 + 描述 + 行动按钮
  - 错误提示：错误横幅 + 重试/返回操作

## 9. 部署方式

- **裸机**: `python -m fin_l4.web.main` → uvicorn 启动
- **Docker**: `docker-compose up -d` → 单容器部署
- **macOS**: LaunchAgent / launchctl 管理

## 10. 验证标准

| 里程碑 | 状态 | 指标 |
|---|---|---|
| M1 基础功能 | ✅ | 8 服务 + Web UI + CLI 全通 |
| M2 智能分类 | ✅ | 4 银行格式 + 规则引擎 |
| M3 深度功能 | ✅ | 贷款/保险/投资 全通 |
| M4 导出/Skill | ✅ | Excel + CLI + Skill |
| M5 UI 打磨 | 🚧 | 响应式 + UX + 知识库 |
| 测试覆盖 | ⚠️ | 178 passed / 11 flaky（dashboard 测试隔离） |

## 11. 相关决策

- 依赖: ADR-202609-026 (L3 理财框架)
- 相关: ADR-202608-006 (持久化适配)
- 相关: ADR-202608-016 (Office 文档生成)

## 12. 变更历史

- 2026-09-04: 初始版本 (M1-M4)
- 2026-09-15: M5 打磨更新 — 补充 Web UI 设计、安全分层、页面清单、UX 规范、验证标准
