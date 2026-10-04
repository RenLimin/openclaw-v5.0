# FIN-L4 家庭理财管理系统 — 详细设计（DESIGN-DETAIL）

> 组件 ID：FIN-L4
> 版本：v1.0（2026-09-28 补录）
> 依据：PRD-v1.0 + DESIGN-OUTLINE-v1.0 + DESIGN.md + 源码实测
> 层级：L4 专有业务层（继承 L3 finance-engine 六大引擎）
> 状态：已上线（189 测试全绿）

---

## 目录

1. [整体架构](#1-整体架构)
2. [数据模型](#2-数据模型)
3. [模块详细设计](#3-模块详细设计)
   - [3.1 Web 层（web/）](#31-web-层web)
   - [3.2 CLI 层（cli.py）](#32-cli-层cli)
   - [3.3 服务层（services/）](#33-服务层services)
   - [3.4 数据访问层（db/）](#34-数据访问层db)
   - [3.5 安全模块（security/）](#35-安全模块security)
   - [3.6 配置模块（config.py）](#36-配置模块configpy)
   - [3.7 外部数据源（external/）](#37-外部数据源external)
   - [3.8 集成链接（integration/）](#38-集成链接integration)
4. [核心算法](#4-核心算法)
5. [依赖关系](#5-依赖关系)
6. [接口契约汇总](#6-接口契约汇总)
7. [错误处理](#7-错误处理)
8. [变更历史](#8-变更历史)

---

## 1. 整体架构

### 1.1 分层架构

```
┌─────────────────────────────────────────────────────────┐
│  L4 FIN-L4（业务层）                                      │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐   │
│  │ Web UI   │  │ CLI      │  │ OpenClaw skill       │   │
│  │ FastAPI  │  │ finctl   │  │ (对话触发)            │   │
│  │ 12 页面  │  │ 14 命令组 │  │                      │   │
│  └────┬─────┘  └────┬─────┘  └──────────┬───────────┘   │
│       │              │                   │               │
│       └──────────────┴───────────────────┘               │
│                      │                                   │
│              ┌───────▼───────┐                           │
│              │  Service 层   │  10+ 业务服务              │
│              │ (services/*)  │                           │
│              └───────┬───────┘                           │
│                      │                                   │
│         ┌────────────┼────────────┐                      │
│         │            │            │                      │
│    ┌────▼────┐  ┌────▼────┐  ┌───▼────┐                 │
│    │   DB    │  │Security │  │External│                 │
│    │  Repos  │  │ backup  │  │  Data  │                 │
│    │ (SQLite)│  │ encrypt │  │ Sources│                 │
│    │         │  │ audit   │  │        │                 │
│    └─────────┘  └─────────┘  └────────┘                 │
│                      │ sys.path 注入 import               │
└──────────────────────┼──────────────────────────────────┘
                       │
┌──────────────────────┼──────────────────────────────────┐
│  L3 finance-engine   │（纯计算引擎，零副作用）              │
│  FIN-001 核算        │ FIN-004 利率                       │
│  FIN-002 贷款        │ FIN-005 投资                       │
│  FIN-003 保险        │ FIN-006 建议                       │
└─────────────────────────────────────────────────────────┘
```

### 1.2 L3/L4 边界契约

| 职责 | L3（finance-engine） | L4（fin-l4） |
|---|---|---|
| 计算 | 纯计算逻辑（还款计划/现金价值/试算平衡） | 不实现计算 |
| 持久化 | 无（零副作用） | SQLite + Repository |
| 用户交互 | 无 | Web UI + CLI + skill |
| 数据校验 | 参数校验 | 业务规则校验 + 审计 |
| 调用方向 | L4 → L3（sys.path 注入） | L3 不感知 L4 |

### 1.3 三通道一致性

Web UI、CLI、skill 三个入口共享同一个 Service 层，操作同一个 SQLite 数据库。任何入口的数据变更对其他入口立即可见。

---

## 2. 数据模型

### 2.1 数据库表结构（18 张表）

#### 2.1.1 核心财务表

**fin4_family** — 家庭

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | TEXT | PRIMARY KEY | UUID |
| name | TEXT | NOT NULL | 家庭名称 |
| currency | TEXT | DEFAULT 'CNY' | 默认币种 |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 创建时间 |

**fin4_accounts** — 账户（会计科目）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | TEXT | PRIMARY KEY | UUID |
| family_id | TEXT | NOT NULL, FK→fin4_family | 所属家庭 |
| code | TEXT | NOT NULL | 科目代码（如 1001） |
| name | TEXT | NOT NULL | 科目名称 |
| type | TEXT | NOT NULL | ASSET/LIABILITY/EQUITY/INCOME/EXPENSE |
| currency | TEXT | DEFAULT 'CNY' | 币种 |
| parent_id | TEXT | FK→fin4_accounts | 父账户（层级结构） |
| opening_balance | TEXT | DEFAULT '0' | 期初余额（Decimal 字符串） |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 创建时间 |

**fin4_categories** — 分类

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | TEXT | PRIMARY KEY | UUID |
| family_id | TEXT | NOT NULL, FK→fin4_family | 所属家庭 |
| name | TEXT | NOT NULL | 分类名称 |
| type | TEXT | NOT NULL, CHECK | income / expense |
| parent_id | TEXT | | 父分类 |
| color | TEXT | | 显示颜色 |
| icon | TEXT | | 图标 |

**fin4_transactions** — 交易（借贷分录）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | TEXT | PRIMARY KEY | UUID |
| family_id | TEXT | NOT NULL, FK→fin4_family | 所属家庭 |
| date | TEXT | NOT NULL | 交易日期（YYYY-MM-DD） |
| amount | TEXT | NOT NULL | 金额（Decimal 字符串，正数） |
| note | TEXT | | 摘要/备注 |
| category_id | TEXT | FK→fin4_categories | 分类 |
| debit_account_id | TEXT | NOT NULL, FK→fin4_accounts | 借方账户 |
| credit_account_id | TEXT | NOT NULL, FK→fin4_accounts | 贷方账户 |
| source | TEXT | DEFAULT 'manual' | 来源：manual/imported |
| import_hash | TEXT | | 去重哈希（SHA-256 前 32 位） |
| import_batch_id | TEXT | FK→fin4_import_batches | 导入批次 |
| category_confidence | TEXT | DEFAULT 'low' | 分类置信度 |
| source_bank | TEXT | | 来源银行 |
| counterparty | TEXT | | 交易对手 |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 创建时间 |

**fin4_budgets** — 预算

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | TEXT | PRIMARY KEY | UUID |
| family_id | TEXT | NOT NULL, FK→fin4_family | 所属家庭 |
| category_id | TEXT | FK→fin4_categories | 关联分类 |
| amount | TEXT | NOT NULL | 预算金额 |
| period | TEXT | NOT NULL, CHECK | month / year |
| start_date | TEXT | | 开始日期（YYYY-MM） |
| end_date | TEXT | | 结束日期 |

#### 2.1.2 理财规划表

**fin4_loans** — 贷款

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | TEXT | PRIMARY KEY | UUID |
| family_id | TEXT | NOT NULL, FK→fin4_family | 所属家庭 |
| name | TEXT | NOT NULL | 贷款名称 |
| principal | TEXT | NOT NULL | 本金（Decimal 字符串） |
| annual_rate | TEXT | NOT NULL | 年利率（如 0.035） |
| term_months | INTEGER | NOT NULL | 期限（月） |
| method | TEXT | NOT NULL | equal_payment/equal_principal/interest_only/flexible |
| start_date | TEXT | NOT NULL | 起始日期 |
| status | TEXT | DEFAULT 'active' | active/closed |
| extra_terms | TEXT | | 扩展条款（JSON） |

**fin4_insurance_policies** — 保单

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | TEXT | PRIMARY KEY | UUID |
| family_id | TEXT | NOT NULL, FK→fin4_family | 所属家庭 |
| product_name | TEXT | NOT NULL | 产品名称 |
| policy_type | TEXT | NOT NULL | term_life/whole_life/endowment/critical_illness/medical/annuity/universal_life/tax_deferred |
| sum_assured | TEXT | NOT NULL | 保额 |
| annual_premium | TEXT | NOT NULL | 年缴保费 |
| term_years | INTEGER | NOT NULL | 保障期限（年） |
| payment_years | INTEGER | NOT NULL | 缴费年限 |
| insured_name | TEXT | | 被保人姓名 |
| insured_age | INTEGER | | 被保人年龄 |
| insured_gender | TEXT | | 被保人性别 |
| start_date | TEXT | | 生效日期 |
| status | TEXT | DEFAULT 'active' | active/surrendered/closed |
| extra_terms | TEXT | | 扩展条款（JSON） |

**fin4_portfolios** — 投资组合

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | TEXT | PRIMARY KEY | UUID |
| family_id | TEXT | NOT NULL, FK→fin4_family | 所属家庭 |
| name | TEXT | NOT NULL | 组合名称 |
| base_currency | TEXT | DEFAULT 'CNY' | 基准币种 |

**fin4_holdings** — 持仓

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | TEXT | PRIMARY KEY | UUID |
| portfolio_id | TEXT | NOT NULL, FK→fin4_portfolios | 所属组合 |
| asset_type | TEXT | NOT NULL | stock/bond/fund/cash/real_estate/insurance_cv/other |
| asset_name | TEXT | NOT NULL | 资产名称 |
| asset_code | TEXT | | 资产代码 |
| shares | TEXT | NOT NULL | 数量（Decimal 字符串） |
| cost_basis_price | TEXT | NOT NULL | 成本价 |
| current_price | TEXT | | 当前市价 |
| updated_at | TIMESTAMP | | 更新时间 |

#### 2.1.3 辅助表

**fin4_rate_snapshots** — 利率快照

| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | UUID |
| rate_type | TEXT | LPR / CENTRAL_BANK |
| term | TEXT | 1y / 5y / loan_1y 等 |
| rate | TEXT | 利率值 |
| effective_date | TEXT | 生效日期 |
| source | TEXT | 数据来源 |
| fetched_at | TIMESTAMP | 获取时间 |

**fin4_import_rules** — 导入规则

| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | UUID |
| family_id | TEXT FK | 所属家庭 |
| pattern | TEXT | 关键词模式（逗号分隔） |
| category_id | TEXT FK | 目标分类 |
| priority | INTEGER | 优先级 |
| is_active | INTEGER | 是否启用 |

**fin4_import_batches** — 导入批次

| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | UUID |
| family_id | TEXT FK | 所属家庭 |
| file_name | TEXT | 文件名 |
| source_type | TEXT | auto / cmb / icbc / alipay / wechat |
| detected_bank | TEXT | 识别的银行 |
| total_count | INTEGER | 总条数 |
| new_count | INTEGER | 新增条数 |
| duplicate_count | INTEGER | 重复条数 |
| error_count | INTEGER | 错误条数 |
| high_confidence | INTEGER | 高置信度条数 |
| medium_confidence | INTEGER | 中置信度条数 |
| low_confidence | INTEGER | 低置信度条数 |
| status | TEXT | pending / previewed / confirmed / cancelled / completed |
| preview_data | TEXT | 预览数据（JSON） |
| adjustments | TEXT | 用户调整（JSON） |
| created_at | TIMESTAMP | 创建时间 |
| completed_at | TIMESTAMP | 完成时间 |

**fin4_integrations** — 外部系统链接

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | TEXT PK | | UUID |
| family_id | TEXT FK | | 所属家庭 |
| name | TEXT | | 链接名称 |
| link_type | TEXT | CHECK | bank / broker / fund / other |
| url | TEXT | | URL |
| username_hint | TEXT | | 用户名提示 |
| note | TEXT | | 备注 |

**fin4_security_config** — 安全配置

| 字段 | 类型 | 说明 |
|---|---|---|
| family_id | TEXT PK | 家庭 ID |
| password_hash | TEXT | 密码哈希 |
| pin_hash | TEXT | PIN 哈希 |
| encryption_enabled | INTEGER | 加密启用 |
| backup_enabled | INTEGER | 备份启用 |
| backup_interval_days | INTEGER | 备份间隔 |
| backup_retention_count | INTEGER | 保留份数 |
| last_backup_at | TIMESTAMP | 最后备份时间 |

**fin4_audit_log** — 审计日志

| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | UUID |
| family_id | TEXT FK | 所属家庭 |
| user | TEXT | 操作用户 |
| action | TEXT | 操作名称 |
| entity_type | TEXT | 实体类型 |
| entity_id | TEXT | 实体 ID |
| details | TEXT | 详情（JSON） |
| ip | TEXT | 来源 IP |

**fin4_category_feedback** — 分类反馈学习

| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | UUID |
| family_id | TEXT FK | 所属家庭 |
| original_category_id | TEXT | 原始分类 |
| corrected_category_id | TEXT | 修正分类 |
| counterparty | TEXT | 交易对手 |
| summary | TEXT | 摘要 |
| amount | TEXT | 金额 |
| hit_count | INTEGER | 命中次数 |
| last_hit_at | TIMESTAMP | 最后命中时间 |

### 2.2 索引

```sql
CREATE INDEX idx_txn_date ON fin4_transactions(date);
CREATE INDEX idx_txn_account ON fin4_transactions(debit_account_id, credit_account_id);
CREATE INDEX idx_accounts_family ON fin4_accounts(family_id);
CREATE INDEX idx_audit_family ON fin4_audit_log(family_id, created_at);
CREATE UNIQUE INDEX idx_txn_import_hash ON fin4_transactions(family_id, import_hash);
CREATE INDEX idx_feedback_key ON fin4_category_feedback(family_id, counterparty, summary);
```

### 2.3 金额存储约定

- 所有金额字段使用 `TEXT` 类型存储（SQLite 无原生 Decimal）
- 值为 `Decimal` 的字符串表示（如 `"1000.50"`）
- 计算时转为 `decimal.Decimal`，杜绝浮点误差
- 余额方向：ASSET/EXPENSE 类账户 = 期初 + 借方 - 贷方；LIABILITY/EQUITY/INCOME 类 = 期初 + 贷方 - 借方

---

## 3. 模块详细设计

### 3.1 Web 层（web/）

#### 3.1.1 main.py — FastAPI 入口

**类/函数签名：**

```python
app = FastAPI(title="FIN-L4 家庭理财管理系统", version="0.1.0")

# 页面路由（12 个页面）
async def dashboard(request: Request) -> HTMLResponse          # GET /
async def budget_page(request: Request, month: str = None)    # GET /budget
async def import_page(request: Request)                        # GET /import
async def loans_page(request: Request)                         # GET /loans
async def loan_detail_page(request: Request, loan_id: str)     # GET /loans/{loan_id}
async def loan_prepay(request: Request, loan_id: str)          # POST /loans/{loan_id}/prepay
async def loan_close(request: Request, loan_id: str)           # POST /loans/{loan_id}/close
async def insurance_page(request: Request)                     # GET /insurance
async def insurance_detail_page(request: Request, policy_id: str)  # GET /insurance/{policy_id}
async def insurance_surrender(request: Request, policy_id: str)    # POST /insurance/{policy_id}/surrender
async def coverage_gap_page(request: Request)                  # GET /insurance/coverage-gap
async def portfolio_page(request: Request)                     # GET /portfolio
async def portfolio_detail_page(request: Request, portfolio_id: str)  # GET /portfolio/{portfolio_id}
async def accounts_page(request: Request)                      # GET /accounts
async def transactions_page(request: Request)                  # GET /transactions
async def rates_page(request: Request)                         # GET /rates
async def rules_page(request: Request)                         # GET /rules
async def settings_page(request: Request)                      # GET /settings
async def report_page(request: Request)                        # GET /reports
async def advise_page(request: Request)                        # GET /advise
async def health()                                             # GET /health

# 异常处理
async def value_error_handler(request: Request, exc: ValueError)
async def http_exception_handler(request: Request, exc: HTTPException)
async def generic_error_handler(request: Request, exc: Exception)
```

**模板引擎：** Jinja2，模板目录 `web/templates/`，复用 L2 web-common 宏。

**全局模板变量：**

```python
templates.env.globals = {
    "brand_name": "FIN-L4",
    "brand_icon": "💰",
    "storage_key": "fin-l4-theme",
    "sidebar_items": [...]  # 5 组 12 项导航
}
```

#### 3.1.2 api.py — REST API 路由

**路由前缀：** `/api/v1`

**Pydantic 请求模型：**

```python
class CreateFamilyRequest(BaseModel):
    name: str; currency: str = "CNY"

class CreateAccountRequest(BaseModel):
    code: str; name: str; type: str; currency: str = "CNY"
    parent_id: str = None; opening_balance: str = "0"

class RecordTxnRequest(BaseModel):
    date: str; amount: str; debit_account_id: str
    credit_account_id: str; note: str = None; category_id: str = None

class CreateLoanRequest(BaseModel):
    name: str; principal: str; annual_rate: str
    term_months: int; method: str = "equal_payment"; start_date: str = None

class CreateInsuranceRequest(BaseModel):
    product_name: str; policy_type: str; sum_assured: str
    annual_premium: str; term_years: int; payment_years: int
    insured_name: str = None; insured_age: int = None; insured_gender: str = None

class CreatePortfolioRequest(BaseModel):
    name: str; base_currency: str = "CNY"

class BuyHoldingRequest(BaseModel):
    asset_type: str; asset_name: str; asset_code: str
    shares: str; price: str

class SetBudgetRequest(BaseModel):
    category_id: str; month: str; amount: str

class ImportRuleRequest(BaseModel):
    pattern: str; category_id: str; priority: int = 0

class ConfirmImportRequest(BaseModel):
    import_id: str; adjustments: dict = {}
```

**API 端点清单：**

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/v1/families | 创建家庭 |
| GET | /api/v1/families | 列出家庭 |
| POST | /api/v1/accounts | 创建账户 |
| GET | /api/v1/accounts | 列出账户 |
| GET | /api/v1/accounts/trial-balance | 试算平衡 |
| POST | /api/v1/transactions | 记一笔 |
| GET | /api/v1/transactions | 查询交易 |
| POST | /api/v1/loans | 创建贷款 |
| GET | /api/v1/loans | 列出贷款 |
| GET | /api/v1/loans/{id}/schedule | 还款计划 |
| GET | /api/v1/loans/{id} | 贷款详情 |
| POST | /api/v1/loans/{id}/prepay | 提前还款 |
| POST | /api/v1/loans/{id}/close | 结清 |
| POST | /api/v1/insurance | 添加保单 |
| GET | /api/v1/insurance | 列出保单 |
| GET | /api/v1/insurance/{id} | 保单详情 |
| POST | /api/v1/insurance/{id}/surrender | 退保 |
| GET | /api/v1/insurance/coverage-gap | 保障缺口 |
| POST | /api/v1/portfolios | 创建组合 |
| GET | /api/v1/portfolios | 列出组合 |
| POST | /api/v1/portfolios/{id}/buy | 买入 |
| GET | /api/v1/portfolios/{id}/performance | 盈亏分析 |
| GET | /api/v1/portfolios/{id}/allocation | 资产配置 |
| GET | /api/v1/portfolios/{id} | 组合详情 |
| GET | /api/v1/reports/balance-sheet | 资产负债表 |
| GET | /api/v1/reports/income | 收支汇总 |
| GET | /api/v1/reports/cashflow | 现金流 |
| POST | /api/v1/rates/sync | 同步利率 |
| GET | /api/v1/rates/latest | 最新利率 |
| GET | /api/v1/rates/history | 利率历史 |
| GET | /api/v1/budgets | 列出预算 |
| POST | /api/v1/budgets | 设置预算 |
| GET | /api/v1/budgets/status | 预算执行状态 |
| POST | /api/v1/import/preview | 预览导入 |
| POST | /api/v1/import/do | 执行导入 |
| GET | /api/v1/import/banks | 支持银行 |
| GET | /api/v1/import/history | 导入历史 |
| POST | /api/v1/import/confirm | 确认导入 |
| GET | /api/v1/import/classification-rules | 分类规则 |
| GET | /api/v1/dashboard/overview | 仪表盘总览 |
| GET | /api/v1/dashboard/categories | 分类统计 |
| GET | /api/v1/dashboard/monthly-trend | 月度趋势 |
| GET | /api/v1/dashboard/budget | 预算进度 |
| GET | /api/v1/dashboard/investments | 投资概览 |
| GET | /api/v1/dashboard/transactions | 最近交易 |
| GET | /api/v1/export/balance-sheet | 导出资产负债表（Excel） |
| GET | /api/v1/export/transactions | 导出交易明细（Excel） |
| GET | /api/v1/export/report | 导出财务报告（Word） |
| POST | /api/v1/integrations | 添加外部链接 |
| GET | /api/v1/integrations | 列出外部链接 |

**内部辅助函数：**

```python
def _get_services() -> Dict:
    """延迟导入获取服务实例字典"""
    # 返回 { "account", "txn", "loan", "insurance", "portfolio", "report", "advise", "rate", "conn" }
```

---

### 3.2 CLI 层（cli.py）

**框架：** Click（多命令组嵌套）

**入口函数：**

```python
@click.group()
@click.option('--db', default=None)
@click.option('--family', 'family_id', default=None)
@click.pass_context
def cli(ctx, db, family_id):
    """FIN-L4 家庭理财管理 CLI"""
```

**命令组（14 组）：**

| 命令组 | 子命令 | 说明 |
|---|---|---|
| `family` | create, list | 家庭管理 |
| `account` | create, list, trial-balance | 账户管理 |
| `txn` | add, list | 记账 |
| `category` | create, list | 分类管理 |
| `budget` | set, status | 预算管理 |
| `loan` | create, list, schedule, summary | 贷款管理 |
| `insurance` | create, list | 保险管理 |
| `portfolio` | create, list, buy, performance | 投资管理 |
| `report` | balance-sheet, income, cashflow | 报表 |
| `rate` | sync, latest | 利率管理 |
| `export` | balance-sheet, transactions, report | 导出 |
| `advise` | health | 理财建议 |
| `imp` | file, list, confirm | 银行流水导入 |
| `rules` | list, add, bank | 分类规则管理 |

**账户解析策略（txn add）：**
- 优先按 ID 查找
- 失败则按科目代码（code）在家庭内解析
- 支持 `finctl txn add --debit 1001 --credit 6001 --amount 500`

---

### 3.3 服务层（services/）

#### 3.3.1 AccountService — 账户服务

```python
class AccountService:
    def __init__(self, conn)
    def create_account(self, family_id: str, code: str, name: str,
                       type: str, currency: str = "CNY",
                       parent_id: str = None,
                       opening_balance: str = "0") -> Dict
    def get_account(self, account_id: str) -> Optional[Dict]
    def list_accounts(self, family_id: str) -> List[Dict]
    def get_balance(self, account_id: str) -> Decimal
    def get_trial_balance(self, family_id: str) -> Dict
        # 返回 { debit_total, credit_total, is_balanced, account_count }
    def get_account_tree(self, family_id: str) -> List[Dict]
        # 层级结构，含 children + balance
```

**试算平衡算法：**
1. 从 SQLite 读取家庭全部账户
2. 灌入 FIN-001 AccountingEngine
3. 读取全部交易并录入引擎
4. 调用 `engine.get_trial_balance()` 返回 TrialBalance
5. 验证 `debit_total == credit_total`

#### 3.3.2 TransactionService — 记账服务

```python
class TransactionService:
    def __init__(self, conn)
    def record(self, family_id: str, date_str: str, amount: str,
               debit_account_id: str, credit_account_id: str,
               note: str = None, category_id: str = None) -> Dict
    def list_transactions(self, family_id: str, account_id: str = None,
                         from_date: str = None, to_date: str = None,
                         limit: int = 100) -> List[Dict]
    def import_csv(self, family_id: str, csv_content: str,
                   debit_map: Dict[str, str] = None,
                   credit_map: Dict[str, str] = None) -> Dict
        # 返回 { imported, errors }
```

**验证逻辑：**
- 金额必须为正数（`Decimal(amount) > 0`）
- 借贷账户必须存在且不同
- 写入后记录审计日志

#### 3.3.3 BudgetService — 预算服务

```python
@dataclass
class BudgetStatus:
    category_id: str
    category_name: str
    budget_amount: Decimal
    spent_amount: Decimal
    remaining: Decimal
    usage_pct: Decimal
    status: str       # ok / warning / exceeded
    days_left: int
    daily_budget: Decimal

class BudgetService:
    def __init__(self, conn)
    def set_budget(self, family_id: str, category_id: str,
                   month: str, amount: str) -> Dict
    def get_budget(self, family_id: str, category_id: str,
                   month: str) -> Optional[Dict]
    def list_budgets(self, family_id: str, month: str) -> List[Dict]
    def get_status(self, family_id: str, month: str) -> List[BudgetStatus]
    def get_overview(self, family_id: str, month: str) -> Dict
        # 返回 { month, total_budget, total_spent, total_remaining, categories, exceeded, warning, statuses[] }
```

**预算执行算法：**
1. 解析月份 → 起止日期
2. 按分类查询当月实际支出（按 category_id 匹配交易）
3. 计算 `remaining = budget - spent`
4. 计算 `usage_pct = spent / budget * 100`
5. 状态判定：≥100% exceeded / ≥80% warning / 其他 ok
6. 计算 `daily_budget = remaining / days_left`

#### 3.3.4 LoanService — 贷款服务

```python
class LoanService:
    def __init__(self, conn)
    def create_loan(self, family_id: str, name: str, principal: str,
                    annual_rate: str, term_months: int,
                    method: str = "equal_payment",
                    start_date: str = None) -> Dict
    def get_schedule(self, loan_id: str) -> List[Dict]
        # 调用 FIN-002 计算还款计划
        # 返回 [{ period, payment, principal, interest, remaining_balance }]
    def get_summary(self, loan_id: str) -> Dict
        # 返回 { name, monthly_payment, total_interest, remaining_balance, paid_periods, remaining_periods }
    def prepay(self, loan_id: str, amount: str) -> Dict
        # 返回 { interest_saved, break_even_months }
    def list_loans(self, family_id: str) -> List[Dict]
    def execute_prepay(self, loan_id: str, amount: str,
                       date_str: str = None) -> Dict
    def close_loan(self, loan_id: str) -> Dict
```

**L3 调用方式：**
1. 从 DB 读取贷款数据
2. 创建 `LoanEngine` 实例
3. 调用 `engine.create_loan()` 构建 L3 Loan 对象
4. 调用 `engine.calculate_amortization_schedule()` 或 `engine.get_loan_summary()`

#### 3.3.5 InsuranceService — 保险服务

```python
class InsuranceService:
    def __init__(self, conn)
    def add_policy(self, family_id: str, product_name: str,
                   policy_type: str, sum_assured: str, annual_premium: str,
                   term_years: int, payment_years: int,
                   insured_name: str = None, insured_age: int = None,
                   insured_gender: str = None, start_date: str = None,
                   extra_terms: str = None) -> Dict
    def get_cash_value(self, policy_id: str, as_of_year: int) -> Dict
        # 返回 { policy_id, as_of_year, guaranteed_cv, non_guaranteed_cv, total_cv, is_estimate }
    def list_policies(self, family_id: str) -> List[Dict]
    def get_policy_detail(self, policy_id: str) -> Dict
        # 含现金价值表（前10年）
    def surrender_policy(self, policy_id: str) -> Dict
        # 返回 { policy_id, cash_value, status }
    def get_coverage_gap(self, family_id: str,
                         monthly_income: str = "35000") -> List[Dict]
        # 建议保额 = 12倍年收入 × 系数
        # 返回 [{ type, type_name, current, recommended, gap }]
```

#### 3.3.6 PortfolioService — 投资服务

```python
class PortfolioService:
    def __init__(self, conn)
    def create_portfolio(self, family_id: str, name: str,
                         base_currency: str = "CNY") -> Dict
    def buy(self, portfolio_id: str, asset_type: str, asset_name: str,
            asset_code: str, shares: str, price: str) -> Dict
    def sell(self, holding_id: str, shares: str = None) -> Dict
    def update_price(self, holding_id: str, current_price: str) -> Dict
    def get_performance(self, portfolio_id: str) -> Dict
        # 返回 { portfolio_id, total_value, total_cost, total_gain, total_return_pct, holdings }
    def get_allocation(self, portfolio_id: str) -> Dict
        # 返回 { portfolio_id, allocation: [{ category, weight }] }
    def get_rebalance(self, portfolio_id: str,
                      target_alloc: Dict[str, str] = None) -> Dict
        # 默认目标: 股票40% 债券30% 基金20% 现金10%
    def list_portfolios(self, family_id: str) -> List[Dict]
    def get_holdings(self, portfolio_id: str) -> List[Dict]
```

#### 3.3.7 ReportService — 报表服务

```python
class ReportService:
    def __init__(self, conn)
    def balance_sheet(self, family_id: str) -> Dict
        # 返回 { date, assets[], total_assets, liabilities[], total_liabilities, equity[], total_equity, net_worth, is_balanced }
    def income_summary(self, family_id: str, from_date: str = None,
                       to_date: str = None) -> Dict
    def cashflow_monthly(self, family_id: str, months: int = 6) -> List[Dict]
    def loan_summary(self, family_id: str) -> List[Dict]
    def insurance_summary(self, family_id: str) -> List[Dict]
    def net_worth_trend(self, family_id: str) -> List[Dict]
    def asset_distribution(self, family_id: str) -> List[Dict]
    # 仪表盘专用
    def dashboard_overview(self, family_id: str) -> Dict
        # 返回 { total_assets, total_liabilities, net_worth, monthly_income, monthly_expense, monthly_savings, savings_rate, debt_ratio, month }
    def category_summary(self, family_id: str, month: str = None,
                        category_type: str = None) -> List[Dict]
    def monthly_trend(self, family_id: str, months: int = 12) -> List[Dict]
    def recent_transactions(self, family_id: str, limit: int = 20) -> List[Dict]
    def budget_progress(self, family_id: str, month: str = None) -> Dict
    def investment_summary(self, family_id: str) -> List[Dict]
```

**资产负债表算法：**
1. 列出家庭全部账户
2. 按 type 分三组（ASSET / LIABILITY / EQUITY）
3. 每组按 `AccountRepo.get_balance()` 计算余额
4. 验证恒等式：`total_assets == total_liabilities + total_equity`

#### 3.3.8 RateService — 利率服务

```python
class RateService:
    def __init__(self, conn)
    def sync_rates(self) -> Dict
        # 返回 { lpr[], central_bank[], errors[] }
    def get_latest(self, rate_type: str = "LPR",
                   term: str = None) -> Optional[Dict]
    def get_history(self, rate_type: str = "LPR",
                    term: str = None, limit: int = 50) -> List[Dict]
```

#### 3.3.9 AdviseService — 理财建议服务

```python
class AdviseService:
    def __init__(self, conn)
    def health_check(self, family_id: str, monthly_income: str,
                     monthly_expenses: str, age: int = 30,
                     risk_capacity: int = 3, risk_tolerance: int = 4) -> Dict
        # 返回 { health_score, summary, allocation, debt_plan, insurance_gap }
    def debt_optimization(self, family_id: str,
                          strategy: str = "avalanche") -> Dict
    def allocation_advice(self, age: int, risk_capacity: int,
                          risk_tolerance: int) -> Dict
```

#### 3.3.10 ExportService — 导出服务

```python
class ExportService:
    def __init__(self, conn)
    def export_balance_sheet_excel(self, family_id: str) -> bytes
    def export_transactions_excel(self, family_id: str,
                                  from_date: str = None,
                                  to_date: str = None) -> bytes
    def export_loan_schedule_excel(self, loan_data: Dict,
                                    schedule: List[Dict]) -> bytes
    def export_financial_report_word(self, family_id: str,
                                      health_result: Dict = None) -> bytes
```

**Excel 导出：** openpyxl，含样式（字体/填充/边框/列宽）
**Word 导出：** python-docx，含标题层级、表格、列表

#### 3.3.11 ImportService — CSV 导入服务（旧版）

```python
class ImportService:
    def __init__(self, conn)
    def preview_csv(self, family_id: str, csv_content: str,
                    date_col: str = "date",
                    amount_col: str = "amount",
                    desc_col: str = "description") -> List[Dict]
    def import_csv(self, family_id: str, csv_content: str,
                   default_debit_id: str = None,
                   default_credit_id: str = None, ...) -> Dict
    def add_rule(self, family_id: str, pattern: str,
                 category_id: str, priority: int = 0) -> str
    def list_rules(self, family_id: str) -> List[Dict]
```

#### 3.3.12 CategoryEngine — 智能分类引擎（旧版）

```python
@dataclass
class CategoryRule:
    id: str; category_id: str; keywords: List[str]
    priority: int = 0
    min_amount: Optional[str] = None
    max_amount: Optional[str] = None

class CategoryEngine:
    def __init__(self)
    def set_default(self, category_id: str)
    def add_rule(self, rule: CategoryRule)
    def classify(self, description: str, amount: str = None) -> Optional[str]
    def list_rules(self) -> List[Dict]
    @staticmethod
    def default_rules() -> 'CategoryEngine'
```

#### 3.3.13 银行流水导入模块（services/importer/）

##### StatementParser — 流水解析器

```python
@dataclass
class ParsedTransaction:
    txn_date: str; txn_time: str; amount: Decimal
    direction: str; currency: str; counterparty: str
    counterparty_account: str; summary: str; product: str
    category: str; balance: str; txn_type: str; status: str
    source_bank: str; raw_row: Dict; row_num: int; error: str
    @property
    def is_valid(self) -> bool
    def import_hash(self, family_id: str) -> str

@dataclass
class BankTemplate:
    bank_id: str; bank_name: str; encoding: List[str]
    skip_rows: int; has_header: bool
    column_mapping: Dict[str, List[str]]
    direction_rules: Dict; detection: Dict

class StatementParser:
    def __init__(self, templates: List[BankTemplate] = None)
    def parse_file(self, file_path: str,
                   source_type: str = "auto") -> ParseResult
    def parse_bytes(self, raw_bytes: bytes, file_name: str = "",
                    source_type: str = "auto") -> ParseResult
```

**解析流程：**
1. 读取文件 bytes
2. 检测格式（Excel 通过 magic bytes `PK` 或扩展名）
3. 解析为原始行（CSV/Excel）
4. 自动识别银行模板（关键词评分）
5. 应用模板映射为标准交易记录
6. 日期归一化（支持 YYYY-MM-DD/YYYYMMDD/YYYY/MM/DD/中文年月日）
7. 金额解析（去除逗号、货币符号）
8. 方向判断（收入/支出）

##### RuleClassifier — 规则分类器

```python
@dataclass
class ClassifyInput:
    description: str; counterparty: str; summary: str
    product: str; amount: Decimal; direction: str
    txn_date: str; txn_type: str

@dataclass
class ClassifyResult:
    category_id: str; category_name: str
    confidence: str  # high / medium / low
    matched_rules: List[str]; match_score: int

@dataclass
class ClassificationRule:
    id: str; category_id: str; name: str
    priority: int; confidence_level: str
    conditions: Dict[str, Any]
    def match(self, inp: ClassifyInput) -> bool

class RuleClassifier:
    def __init__(self)
    def add_rule(self, rule: ClassificationRule)
    def load_rules_from_yaml(self, path: str = None)
    def classify(self, description: str = "", counterparty: str = "",
                 summary: str = "", product: str = "",
                 amount: Decimal = None, direction: str = "",
                 txn_date: str = "", txn_type: str = "") -> ClassifyResult
    def classify_txn(self, txn) -> ClassifyResult
    def learn_feedback(self, counterparty: str, summary: str,
                       original_cat: str, corrected_cat: str,
                       amount: str = "")
    def get_feedback_suggestion(self, counterparty: str,
                                summary: str) -> Optional[str]
    def list_rules(self) -> List[Dict]
    @classmethod
    def default(cls) -> 'RuleClassifier'
```

**分类算法：**
1. 按优先级从高到低遍历规则
2. 条件评估支持 `all`/`any`/`keywords_in`/`amount_range`/`direction`
3. 收集所有匹配规则
4. 取最高优先级规则的分类
5. 置信度计算：多条规则同分类 → 提升置信度
6. 用户反馈学习：记录修正频次，≥2 次后自动建议

##### TransactionImporter — 导入服务

```python
@dataclass
class ImportPreview:
    import_id: str; file_name: str; source_type: str
    detected_bank: str; detected_bank_name: str; format: str
    total_count: int; valid_count: int; error_count: int
    duplicate_count: int; new_count: int
    transactions: List[Dict]; errors: List[str]
    confidence_stats: Dict[str, int]; category_stats: Dict[str, int]

@dataclass
class ImportResult:
    import_id: str; status: str; total_count: int
    new_count: int; duplicate_count: int; error_count: int
    high_confidence: int; medium_confidence: int; low_confidence: int
    category_stats: Dict[str, int]; errors: List[str]

class TransactionImporter:
    def __init__(self, conn)
    def preview_import(self, family_id: str, file_path: str,
                       source_type: str = "auto") -> ImportPreview
    def import_file(self, family_id: str, file_path: str,
                    source_type: str = "auto", ...) -> ImportResult
    def confirm_import(self, import_id: str, family_id: str,
                       adjustments: Dict = None, ...) -> ImportResult
    def get_import_history(self, family_id: str,
                           limit: int = 50) -> List[Dict]
    def ensure_category(self, family_id: str, category_id: str,
                        cat_type: str = "expense") -> Optional[str]
```

**导入流程：**
1. 解析文件 → ParseResult
2. 逐条分类 → ClassifyResult
3. 去重检查（import_hash 唯一索引）
4. 构建预览（不入库）
5. 确认导入 → INSERT OR IGNORE（幂等）
6. 更新批次状态 + 审计日志

**去重哈希：**
```python
sha256(family_id | date | amount | direction | counterparty | summary)[:32]
```

---

### 3.4 数据访问层（db/）

#### 3.4.1 数据库连接（db/\_\_init\_\_.py）

```python
_global_conn = None
DB_DIR = get_settings().db_dir

MIGRATIONS: List[str | Callable]  # 按顺序执行的迁移脚本

def get_db(db_path: str = None) -> sqlite3.Connection
def init_db(db_path: str = None) -> sqlite3.Connection
def get_db_path(family_id: str = None) -> str
```

**连接配置：**
- `PRAGMA journal_mode=WAL`（写前日志，提高并发）
- `PRAGMA foreign_keys=ON`（外键约束）
- `row_factory = sqlite3.Row`（字典式访问）

**迁移版本：**
- V1: 核心 13 张表 + 索引
- V2: fin4_integrations 表
- V3: fin4_security_config + fin4_audit_log + insurance.start_date
- V4: fin4_import_batches + 交易表扩展（import_hash/batch_id/confidence/bank/counterparty）+ fin4_category_feedback

#### 3.4.2 Repository 层（db/repositories.py）

**基类：**

```python
class BaseRepository:
    def __init__(self, conn, table: str)
    def _row_to_dict(self, row) -> Optional[Dict]
    def _rows_to_list(self, rows) -> List[Dict]
```

**各 Repository 方法汇总：**

| Repository | 方法 |
|---|---|
| FamilyRepository | create(name, currency), get(family_id), list_all() |
| AccountRepository | create(family_id, code, name, type, ...), get(id), list_by_family(family_id), get_by_code(family_id, code), get_balance(account_id) → Decimal |
| TransactionRepository | create(family_id, date, amount, debit_account_id, credit_account_id, ...), list_by_family(family_id, account_id?, from_date?, to_date?, limit?), list_by_account(account_id) |
| CategoryRepository | create(family_id, name, type, ...), list_by_family(family_id), get(category_id) |
| BudgetRepository | upsert(family_id, category_id, month, amount), get(family_id, category_id, month), list_by_family(family_id, month?) |
| ImportRuleRepository | create(family_id, pattern, category_id, priority), list_active(family_id), list_by_family(family_id), set_active(rule_id, active), delete(rule_id) |
| LoanRepository | create(family_id, name, principal, ...), list_by_family(family_id), get(loan_id), update_principal(loan_id, new_principal), update_status(loan_id, status) |
| InsuranceRepository | create(family_id, product_name, ...), update_status(policy_id, status), list_by_family(family_id), get(policy_id) |
| PortfolioRepository | create(family_id, name, base_currency), list_by_family(family_id) |
| HoldingRepository | create(portfolio_id, asset_type, ...), list_by_portfolio(portfolio_id), update_price(holding_id, current_price) |
| RateSnapshotRepository | save(rate_type, rate, term?, ...), get_latest(rate_type, term?), get_history(rate_type, term?, limit?) |
| IntegrationRepository | create(family_id, name, link_type, ...), list_by_family(family_id), delete(integration_id) |
| SecurityConfigRepository | get(family_id), upsert(family_id, **kwargs) |
| AuditLogRepository | log(family_id, user, action, ...), list_by_family(family_id, limit?) |

**AccountRepository.get_balance() 算法：**

```python
def get_balance(self, account_id: str) -> Decimal:
    opening = Decimal(account["opening_balance"])
    debits = SUM(amount) WHERE debit_account_id = account_id
    credits = SUM(amount) WHERE credit_account_id = account_id
    if account["type"] in ("ASSET", "EXPENSE"):
        return opening + debits - credits
    else:
        return opening + credits - debits
```

---

### 3.5 安全模块（security/）

#### 3.5.1 backup.py — 备份管理器

```python
_MAGIC = b"L4BK"
_FORMAT_VERSION = 1

class BackupManager:
    def __init__(self, db_path: str, backup_dir: str,
                 retention_count: int = 10, password: str = None)
    def create_backup(self, password: str = None) -> str
        # 返回备份文件路径
        # 流程: SQLite backup API → 加密 → 写入文件 → 清理旧备份
    def restore_backup(self, backup_file: str,
                       target_db_path: str = None,
                       password: str = None) -> str
        # 返回恢复后的数据库路径
        # 流程: 读取文件 → 解密 → 验证完整性 → 原子替换
    def list_backups(self) -> List[Dict]
    def latest_backup(self) -> Optional[Dict]
    def prune_old(self, keep_count: int = None) -> int
```

**备份文件格式：**
```
[4 bytes magic "L4BK"]
[2 bytes header_len]
[header_len bytes JSON header (plaintext, 作为 AES-GCM AAD)]
[encrypted blob (AES-256-GCM)]
```

**备份流程：**
1. `sqlite3.backup()` 在线热备份到临时文件
2. 构造 JSON header（version, db_path, size, created_at）
3. header 作为 AAD 调用 `encrypt_data()`
4. 写入：magic + header_len + header + encrypted
5. 清理临时文件
6. 按 retention_count 清理旧备份

**恢复流程：**
1. 读取并解析文件头
2. 验证 magic 和 version
3. header 作为 AAD 调用 `decrypt_data()`
4. 验证解密后大小
5. PRAGMA integrity_check
6. 原子替换（旧文件 → .bak，临时文件 → 正式文件）

#### 3.5.2 encryption.py — 加密工具

```python
_VERSION = 1
_KEY_LEN = 32
_NONCE_LEN = 12
_TAG_LEN = 16
_PBKDF2_ITERATIONS = 600_000

class EncryptionError(Exception): ...

def derive_key(password: str, salt: bytes,
               iterations: int = 600_000, key_len: int = 32) -> bytes
def generate_salt(length: int = 16) -> bytes
def encrypt_data(plaintext: bytes, password: str,
                 salt: Optional[bytes] = None,
                 associated_data: Optional[bytes] = None) -> bytes
    # 输出: version(1) + salt_len(2) + salt + nonce(12) + ciphertext + tag(16)
def decrypt_data(blob: bytes, password: str,
                 associated_data: Optional[bytes] = None) -> bytes
def encrypt_string(plaintext: str, password: str,
                   associated_data: Optional[bytes] = None) -> str
    # 返回 Base64 编码
def decrypt_string(ciphertext_b64: str, password: str,
                   associated_data: Optional[bytes] = None) -> str
```

**加密方案：**
- PBKDF2-HMAC-SHA256 密钥派生（600,000 轮迭代，OWASP 2023 推荐）
- AES-256-GCM 认证加密（机密性 + 完整性）
- 每条记录独立 salt + nonce
- 支持 associated_data（AAD）参与完整性校验

#### 3.5.3 audit.py — 审计日志

```python
class AuditLogger:
    def __init__(self, repo: AuditLogRepository,
                 default_user: str = "system")
    def log(self, family_id: str, action: str,
            user: str = None, entity_type: str = None,
            entity_id: str = None, details: Dict = None,
            ip: str = None) -> str
    def log_create(self, family_id: str, entity_type: str,
                   entity_id: str, user: str = None,
                   details: Dict = None, ip: str = None) -> str
    def log_update(...) -> str
    def log_delete(...) -> str
    def log_login(self, family_id: str, user: str,
                  success: bool = True, ip: str = None) -> str
    def log_backup(self, family_id: str, backup_file: str, ...) -> str
    def log_restore(self, family_id: str, backup_file: str, ...) -> str
    def list_logs(self, family_id: str, limit: int = 100,
                  action: str = None, entity_type: str = None) -> List[Dict]
```

**Action 命名约定：**
- `create_{entity_type}` / `update_{entity_type}` / `delete_{entity_type}`
- `login` / `logout`
- `backup` / `restore`
- `export` / `import` / `import_complete`
- `config_change`

---

### 3.6 配置模块（config.py）

```python
class Settings:
    def __init__(self)
        self.host = os.getenv("FIN4_HOST", "127.0.0.1")
        self.port = _get_env_int("FIN4_PORT", 8500)
        self.db_dir = Path(os.getenv("FIN4_DB_DIR") or "~/.fin-l4")
        self.family_id = os.getenv("FIN4_FAMILY_ID", "default")
        self.app_name = os.getenv("FIN4_APP_NAME", "FIN-L4 家庭理财管理系统")
        self.debug = os.getenv("FIN4_DEBUG", "0") == "1"
        self.external_readonly = os.getenv("FIN4_EXTERNAL_READONLY", "1") == "1"
    @property
    def db_path(self) -> str

def get_settings() -> Settings  # 模块级单例
```

**优先级：** 环境变量 > .env 文件 > 内置默认值

---

### 3.7 外部数据源（external/）

```python
@dataclass
class DataSnapshot:
    source: str; data_type: str; value: Decimal
    currency: str; effective_date: str
    fetched_at: datetime; metadata: Dict
    is_cached: bool; is_estimate: bool

class DataSource(ABC):
    @property name: str
    @property data_type: str
    @property ttl_seconds: int
    def fetch(self, **params) -> DataSnapshot
    def is_available(self) -> bool

class DataSourceRegistry:
    _sources: Dict[str, DataSource]
    @classmethod register(cls, source)
    @classmethod get(cls, name) -> Optional[DataSource]
    @classmethod list_all(cls) -> List[Dict]
    @classmethod list_by_type(cls, data_type) -> List[DataSource]

class RateSource(DataSource):      # 利率数据源（基于 FIN-004）
class MarketSource(DataSource):    # 行情数据源（预留占位）
class FxSource(DataSource):        # 汇率数据源（预留占位）
```

**自动注册：** 模块导入时调用 `register_all()` 注册全部数据源。

---

### 3.8 集成链接（integration/）

```python
VALID_LINK_TYPES = {"bank", "broker", "fund", "other"}

class LinkManager:
    def __init__(self, repo: IntegrationRepository)
    def create_link(self, family_id: str, name: str, link_type: str,
                    url: str, username_hint: str = None,
                    note: str = None) -> str
    def list_links(self, family_id: str,
                   link_type: str = None) -> List[Dict]
    def list_by_type(self, family_id: str) -> Dict[str, List[Dict]]
    def get_link(self, link_id: str) -> Optional[Dict]
    def update_link(self, link_id: str, **kwargs) -> bool
    def delete_link(self, link_id: str) -> bool
    def count_by_type(self, family_id: str) -> Dict[str, int]
```

**安全约束：** 不存储密码等敏感凭证，仅保存 URL + 用户名提示。

---

## 4. 核心算法

### 4.1 借贷记账法

**恒等式：** 资产 = 负债 + 权益

**记账规则：**
- 每笔交易必须有借方和贷方（有借必有贷，借贷必相等）
- ASSET/EXPENSE 类账户：借方增加、贷方减少
- LIABILITY/EQUITY/INCOME 类账户：贷方增加、借方减少

**试算平衡：**
- 全部账户借方发生额合计 = 贷方发生额合计
- 通过 FIN-001 AccountingEngine.get_trial_balance() 验证

### 4.2 账户余额计算

```
ASSET/EXPENSE 余额 = opening_balance + SUM(借方金额) - SUM(贷方金额)
LIABILITY/EQUITY/INCOME 余额 = opening_balance + SUM(贷方金额) - SUM(借方金额)
```

### 4.3 预算执行追踪

```
spent = SUM(amount) WHERE category_id = ? AND date IN [month_start, month_end]
remaining = budget_amount - spent
usage_pct = spent / budget_amount × 100
status = exceeded (≥100%) / warning (≥80%) / ok (<80%)
daily_budget = remaining / days_left
```

### 4.4 银行流水去重

```
import_hash = sha256(family_id | date | amount | direction | counterparty | summary)[:32]

SQL: INSERT OR IGNORE INTO fin4_transactions (...) VALUES (...)
UNIQUE INDEX: (family_id, import_hash)
```

### 4.5 智能分类

1. 按优先级从高到低遍历规则
2. 条件评估（关键词匹配 / 金额范围 / 收支方向）
3. 收集所有匹配规则，取最高优先级
4. 置信度：多条规则同分类 → 提升
5. 用户反馈学习：记录修正频次，≥2 次自动建议

### 4.6 备份加密

```
PBKDF2(password, salt, 600000 iterations) → AES-256 key
AES-256-GCM(key, nonce, plaintext, AAD=header) → ciphertext + tag

文件格式:
  magic(4) + header_len(2) + JSON_header + ciphertext + tag(16)
```

---

## 5. 依赖关系

### 5.1 外部依赖

| 依赖 | 版本约束 | 用途 |
|---|---|---|
| fastapi | ≥0.100 | Web 框架 |
| uvicorn | ≥0.20 | ASGI 服务器 |
| jinja2 | ≥3.1 | 模板引擎 |
| click | ≥8.0 | CLI 框架 |
| openpyxl | ≥3.1 | Excel 导出 |
| python-docx | ≥0.8 | Word 导出 |
| cryptography | ≥41 | AES-256-GCM 加密 |
| pyyaml | ≥6 | YAML 模板/规则加载 |

### 5.2 内部依赖

| 依赖 | 层级 | 方式 |
|---|---|---|
| finance-engine (FIN-001~006) | L3 | sys.path 注入 import |
| L2 web-common | L2 | 模板宏 + 静态文件 |
| L2 持久化 (006) | L2 | SQLite + Repository 模式 |
| L2 Office 生成 (011) | L2 | openpyxl / python-docx |

### 5.3 依赖方向

```
fin-l4 → finance-engine (L3) ✅
fin-l4 → L2 web-common ✅
fin-l4 → L2 持久化 ✅
fin-l4 → L2 Office 生成 ✅
finance-engine → fin-l4 ❌ (禁止反向依赖)
```

---

## 6. 接口契约汇总

### 6.1 REST API

全部端点以 `/api/v1` 前缀，详见 [3.1.2](#312-api-py--rest-api-路由)。

### 6.2 CLI

```bash
finctl [OPTIONS] COMMAND [ARGS]...
  --db PATH         数据库路径
  --family TEXT     家庭 ID

finctl family create --name TEXT [--currency CNY]
finctl account create --code TEXT --name TEXT --type TEXT [--balance 0]
finctl account list
finctl account trial-balance
finctl txn add --debit TEXT --credit TEXT --amount TEXT [--date DATE] [--note TEXT]
finctl txn list [--limit 20]
finctl category create --name TEXT --type {income,expense}
finctl budget set --category-id TEXT --month YYYY-MM --amount TEXT
finctl budget status [--month YYYY-MM]
finctl loan create --name TEXT --principal TEXT --rate TEXT --term INT [--method equal_payment]
finctl loan list / schedule / summary
finctl insurance create --name TEXT --type TEXT --premium TEXT --sum-assured TEXT --term-years INT --payment-years INT
finctl portfolio create / list / buy / performance
finctl report balance-sheet / income / cashflow
finctl rate sync / latest
finctl export balance-sheet / transactions / report
finctl advise health --income TEXT --expenses TEXT [--age 30]
finctl imp file PATH [--source auto|cmb|icbc|alipay|wechat] [--preview]
finctl imp list / confirm
finctl rules list / add / bank
```

### 6.3 数据库

SQLite 单文件，路径 `~/.fin-l4/fin_l4.db`（可通过 `FIN4_DB_DIR` 覆盖）。

---

## 7. 错误处理

### 7.1 异常层级

```
ValueError          — 业务规则校验（账户不存在/金额无效/类型错误）
HTTPException(400)  — REST API 参数错误
HTTPException(404)  — 资源不存在
EncryptionError     — 加密/解密失败
ClickException      — CLI 参数错误
```

### 7.2 Web 异常处理

- `ValueError` → 返回 400（API）/ 渲染错误页（页面）
- `HTTPException` → 返回对应状态码
- `Exception` → 返回 500（debug 模式显示详情，生产模式隐藏）

### 7.3 CLI 异常处理

- 未创建家庭 → `ClickException('尚未创建家庭，请先执行: finctl family create')`
- 账户不存在 → `ClickException('账户不存在: xxx（支持 id 或科目代码）')`
- 分类不存在 → 列出可用分类

---

## 8. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-09-02 | M1 | 骨架 + 数据层 + 8 服务 + Web UI + CLI |
| 2026-09-03 | M2 | 智能分类 + 预算 + CSV 导入 |
| 2026-09-04 | M3 | 贷款/保险/投资深度 |
| 2026-09-04 | M4 | 导出 + CLI + skill |
| 2026-09-28 | v1.0 | PRD/DESIGN/VERIFICATION/OPERATIONS/DESIGN-DETAIL 全套文档补录 |
