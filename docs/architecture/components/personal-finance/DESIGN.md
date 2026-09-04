# L3/L4 家庭及个人理财系统 — DESIGN.md

> L3 通用引擎设计 + L4 管理系统详细设计
> 配套 ADR：[ADR-202609-026](../../knowledge-base/by-category/project-experience/adr/ADR-202609-026-personal-finance-framework-L3.md) (L3) · [ADR-202609-027](../../knowledge-base/by-category/project-experience/adr/ADR-202609-027-fin-l4-system-design.md) (L4)

## 0. 元信息

| 字段 | 值 |
|---|---|
| 文档版本 | 3.0 (2026-09-04) |
| 文档状态 | active |
| 决策 | ADR-202609-026 + ADR-202609-027 |
| 层级 | L3 通用 + L4 专有 |
| 依赖 L2 | 持久化适配(006)、Office 文档生成(011)、知识库工具链(010) |

---

## 第一部分：L3 通用引擎（已完成 ✅）

### 1.1 引擎清单

| 组件 | 标识 | 能力 | 测试 |
|---|---|---|---|
| 账户体系 | FIN-001 | 复式记账、试算平衡、对账 | 10/10 ✅ |
| 贷款核算 | FIN-002 | 4种还款方式、提前还款、PMT | 10/10 ✅ |
| 保险核算 | FIN-003 | 8种险种、现金价值、退保、IRR | 10/10 ✅ |
| 利率服务 | FIN-004 | LPR查询、央行利率、转换、缓存 | 14/14 ✅ |
| 投资持仓 | FIN-005 | 组合管理、盈亏、资产配置、再平衡 | 10/10 ✅ |
| 理财建议 | FIN-006 | 6KPI诊断、配置建议、债务优化、保障缺口 | 12/12 ✅ |

### 1.2 L3 设计原则

- **引擎模式**：纯计算，不持有数据，传入参数返回结果
- **零副作用**：不写数据库、不发网络请求（利率除外）、不修改配置
- **纯函数优先**：输入确定 → 输出确定
- **Decimal 精度**：所有金额用 Decimal，ROUND_HALF_UP

---

## 第二部分：L4 管理系统（本文重点）

## 2. 系统定位

### 2.1 概述

FIN-L4 是一个**完整的本地理财管理系统**，面向个人/家庭日常财务管理。

**核心理念**：
- 数据全本地（SQLite），不上云
- 不连银行/券商，纯手动录入 + CSV导入
- Web UI + CLI + OpenClaw 三通道交互
- 继承 L3 引擎的全部计算能力

### 2.2 业界对标

| 对标产品 | 我们继承 | 我们差异化 |
|---|---|---|
| Firefly III | 复式记账、规则引擎、CSV导入 | +贷款/保险/投资/利率同步/中文 |
| Actual Budget | 本地优先、跨设备 | +中文、+贷款/保险/投资 |
| GnuCash | 专业双分录 | +现代Web UI、+中文、+保险/投资 |
| Ghostfolio | 投资追踪 | +完整记账+贷款+保险 |

### 2.3 分层架构

```
┌───────────────────────────────────────────────────────────┐
│                    交互层 (Presentation)                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────────┐ │
│  │ Web UI   │  │ CLI      │  │ OpenClaw 对话             │ │
│  │ FastAPI  │  │ finctl   │  │ Jerry 辅助                │ │
│  │ :8500    │  │ Click    │  │                           │ │
│  └────┬─────┘  └────┬─────┘  └────────────┬─────────────┘ │
│       └──────────────┼─────────────────────┘               │
├──────────────────────┼────────────────────────────────────┤
│                    服务层 (Service)                         │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐         │
│  │Account  │ │Loan     │ │Insurance│ │Portfolio│         │
│  │Svc      │ │Svc      │ │Svc      │ │Svc      │         │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘         │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐         │
│  │Txn      │ │Report   │ │Advise   │ │Rate     │         │
│  │Svc      │ │Svc      │ │Svc      │ │Svc      │         │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘         │
├───────────────────────────────────────────────────────────┤
│                    数据层 (Data)                            │
│  ┌───────────────────────────────────────────────────┐    │
│  │ SQLite (fin_l4_{family_id}.db)                     │    │
│  │ Repository 模式 + 版本化迁移                        │    │
│  └───────────────────────────────────────────────────┘    │
├───────────────────────────────────────────────────────────┤
│                    引擎层 (L3 Engine)                      │
│  FIN-001~006 — 纯计算引擎，不持有数据                     │
└───────────────────────────────────────────────────────────┘
```

## 3. 数据模型

### 3.1 ER 图

```
family (家庭)
├── id, name, currency, created_at
│
├── accounts (账户) 1:N
│   ├── id, family_id, code, name, type, currency
│   ├── parent_id, opening_balance, created_at
│   │
│   └── transactions (交易) 1:N (作为 debit 或 credit)
│       ├── id, family_id, date, amount, note, category_id
│       ├── debit_account_id, credit_account_id
│       └── source (manual/imported/system), created_at
│
├── categories (分类) 1:N
│   ├── id, family_id, name, type (income/expense), parent_id
│   └── color, icon
│
├── budgets (预算) 1:N
│   ├── id, family_id, category_id, amount, period (month/year)
│   └── start_date, end_date
│
├── loans (贷款) 1:N
│   ├── id, family_id, name, principal, annual_rate
│   ├── term_months, method, start_date, status
│   └── extra_terms (JSON)
│
├── insurance_policies (保单) 1:N
│   ├── id, family_id, product_name, policy_type
│   ├── sum_assured, annual_premium, term_years, payment_years
│   ├── insured_name, insured_age, insured_gender, status
│   └── extra_terms (JSON)
│
├── portfolios (投资组合) 1:N
│   ├── id, family_id, name, base_currency
│   │
│   └── holdings (持仓) 1:N
│       ├── id, portfolio_id, asset_type, asset_name, asset_code
│       ├── shares, cost_basis_price, current_price
│       └── updated_at
│
├── rate_snapshots (利率快照) 1:N
│   ├── id, rate_type, term, rate, effective_date, source
│   └── fetched_at
│
└── import_rules (导入规则) 1:N
    ├── id, family_id, pattern, category_id, priority
    └── is_active
```

### 3.2 表前缀

所有表前缀 `fin4_`，与 L2 持久化层 `fin_` 区分。

## 4. 模块设计

### 4.1 账户模块 (account_svc)

| 功能 | API | 说明 |
|---|---|---|
| 创建账户 | `POST /accounts` | 指定 type/code/name/opening_balance |
| 查余额 | `GET /accounts/{id}/balance` | 含日期过滤 |
| 试算平衡 | `GET /accounts/trial-balance` | 借=贷验证 |
| 对账 | `POST /accounts/{id}/reconcile` | 外部对账单比对 |
| 账户树 | `GET /accounts/tree` | 层级展示 |

### 4.2 记账模块 (txn_svc)

| 功能 | API | 说明 |
|---|---|---|
| 记一笔 | `POST /transactions` | debit + credit + amount + note |
| 查明细 | `GET /transactions` | 按账户/日期/分类过滤 |
| 批量导入 | `POST /transactions/import` | CSV/OFX 文件 |
| 自动分类 | 导入时触发 | 基于 import_rules 匹配 |
| 预算检查 | 记账时触发 | 超额预警 |

**CSV 导入格式**：
```csv
date,description,amount,category
2026-09-01,工资收入,35000,工资
2026-09-02,餐饮消费,-50,餐饮
```

### 4.3 贷款模块 (loan_svc)

| 功能 | API | 说明 |
|---|---|---|
| 创建贷款 | `POST /loans` | 本金/利率/期限/方式 |
| 还款计划 | `GET /loans/{id}/schedule` | 调用 FIN-002 |
| 提前还款 | `POST /loans/{id}/prepay` | 调用 FIN-002 |
| 贷款概览 | `GET /loans` | 所有贷款摘要 |

### 4.4 保险模块 (insurance_svc)

| 功能 | API | 说明 |
|---|---|---|
| 添加保单 | `POST /insurance` | 险种/保费/保额 |
| 现金价值 | `GET /insurance/{id}/cash-value` | 调用 FIN-003 |
| 保障缺口 | `GET /insurance/gap-analysis` | 调用 FIN-006 |
| 保单列表 | `GET /insurance` | 全部保单 |

### 4.5 投资模块 (portfolio_svc)

| 功能 | API | 说明 |
|---|---|---|
| 创建组合 | `POST /portfolios` | 名称/币种 |
| 买入 | `POST /portfolios/{id}/buy` | 资产/数量/价格 |
| 卖出 | `POST /portfolios/{id}/sell` | 资产/数量/价格 |
| 更新价格 | `PATCH /portfolios/{id}/price` | 市价更新 |
| 盈亏分析 | `GET /portfolios/{id}/performance` | 调用 FIN-005 |
| 资产配置 | `GET /portfolios/{id}/allocation` | 调用 FIN-005 |
| 再平衡 | `GET /portfolios/{id}/rebalance` | 调用 FIN-005 |

### 4.6 报表模块 (report_svc)

| 功能 | 格式 | 说明 |
|---|---|---|
| 资产负债表 | 屏幕/Excel/Word | 时点快照 |
| 收支汇总表 | 屏幕/Excel/Word | 期间汇总 |
| 现金流 | 屏幕/Excel | 月度趋势 |
| 投资组合报告 | 屏幕/Excel/Word | 盈亏+配置+建议 |
| 贷款概览 | 屏幕/Excel | 所有贷款+还款计划 |
| 保险概览 | 屏幕/Excel | 保单+保障缺口 |
| 净值趋势 | 屏幕 | 多期净值变化 |

### 4.7 理财建议模块 (advise_svc)

| 功能 | API | 说明 |
|---|---|---|
| 健康诊断 | `GET /advise/health` | 调用 FIN-006, 6 KPI |
| 债务优化 | `GET /advise/debt` | 雪崩/雪球策略 |
| 配置建议 | `GET /advise/allocation` | 基于年龄/风险 |
| 综合报告 | `GET /advise/full-report` | 一键生成 |

### 4.8 利率同步模块 (rate_svc)

| 功能 | API | 说明 |
|---|---|---|
| 手动同步 | `POST /rates/sync` | 立即拉取 LPR + 央行利率 |
| 查询最新 | `GET /rates/latest` | 缓存优先 |
| 历史走势 | `GET /rates/history` | 多期数据 |
| 定时配置 | `GET/PUT /rates/schedule` | 自动同步频率 |

**定时任务**：
- LPR：每周一 09:00 拉取
- 央行利率：每月 1 日 09:00 拉取
- 缓存 TTL：24h



### 4.9 外部数据接入模块 (external_data_svc)

**定位**：可扩展的外部数据获取框架。当前实现利率同步，预留行情/汇率等数据源。

#### 数据源架构

```
external/
├── __init__.py
├── base.py              # DataSource 抽象基类 + Registry
├── rate_source.py       # 利率数据源（LPR/央行/商业银行）
├── market_source.py     # 行情数据源（预留：股票/基金净值）
├── fx_source.py         # 汇率数据源（预留：外币资产）
└── registry.py          # 数据源注册表
```

#### 已支持数据源

| 数据 | 来源 | 频率 | 缓存 |
|---|---|---|---|
| LPR 1年期 | 央行官网 | 每周一 09:00 | 24h |
| LPR 5年期+ | 央行官网 | 每周一 09:00 | 24h |
| 央行基准利率 | 央行官网 | 每月 1 日 09:00 | 24h |
| 商业银行利率 | 各银行官网 | 每月 1 日 | 24h |
| 股票/基金行情 | 预留 | 15min | 15min |
| 汇率 | 预留 | 每日 | 1h |

#### 降级策略

```
主源请求 → 成功 → 缓存 + 返回
         → 失败 → 备用源 → 成功 → 缓存 + 返回
                          → 失败 → 缓存兜底（标注"数据可能过期"）
                                   → 无缓存 → 返回错误 + 告警
```

#### API

| 功能 | API | 说明 |
|---|---|---|
| 手动同步 | `POST /external/sync` | 指定数据源立即拉取 |
| 查询最新 | `GET /external/{source}/latest` | 缓存优先 |
| 历史数据 | `GET /external/{source}/history` | 多期时间序列 |
| 数据源列表 | `GET /external/sources` | 已注册数据源 + 状态 |
| 定时配置 | `GET/PUT /external/schedule` | 自动同步频率 |

### 4.10 外部系统链接模块 (integration_svc)

**定位**：管理外部理财相关系统的链接，预留 API 集成扩展点。

#### 当前阶段：链接管理

| 链接类型 | 字段 | 说明 |
|---|---|---|
| 银行网银 | name, url, username_hint, note | 只读跳转 |
| 券商系统 | name, url, account_hint, note | 只读跳转 |
| 基金平台 | name, url, note | 只读跳转 |
| 第三方理财 | name, url, note | 只读跳转 |

#### 预留：插件接口

```python
class IntegrationPlugin(ABC):
    """外部系统集成插件接口"""
    
    @abstractmethod
    def auth(self, credentials: SecretRef) -> AuthToken:
        """认证（凭据通过 L2 凭据管理）"""
    
    @abstractmethod
    def sync(self, since: datetime) -> SyncResult:
        """同步数据"""
    
    @abstractmethod
    def disconnect(self) -> None:
        """断开连接"""
```

**安全红线**：
- 所有凭据通过 L2 凭据管理（SecretRef），不写明文
- 当前阶段**不实现**自动同步，只做链接管理
- 未来接入银行 OpenAPI 等需单独 ADR 审批

#### API

| 功能 | API | 说明 |
|---|---|---|
| 添加链接 | `POST /integrations` | 名称/类型/URL/备注 |
| 链接列表 | `GET /integrations` | 按类型分组 |
| 更新链接 | `PUT /integrations/{id}` | |
| 删除链接 | `DELETE /integrations/{id}` | |
| 跳转 | `GET /integrations/{id}/open` | 返回 URL（前端跳转） |
| 插件列表 | `GET /integrations/plugins` | 已安装插件（预留） |

### 4.11 本地数据安全模块 (security_svc)

**定位**：家庭财务数据的本地安全管理，含加密/访问控制/备份/审计/销毁。

#### 安全分层

```
L1: 文件级加密（SQLCipher/AES）     — 防物理窃取
L2: 访问控制（PIN/密码）             — 防未授权访问
L3: 审计日志（操作追踪）             — 可追溯
L4: 加密备份（AES-256-GCM）         — 防备份泄露
L5: 数据销毁（安全擦除）             — 防恢复
```

#### 能力清单

| 能力 | 实现 | 优先级 |
|---|---|---|
| 数据库加密 | SQLCipher / 文件级 AES-256-GCM | P0 |
| Web UI 登录 | PIN / 密码哈希（bcrypt） | P0 |
| 自动备份 | 定时 + 手动，保留 N 个版本 | P0 |
| 备份加密 | AES-256-GCM + 用户密码派生密钥 | P0 |
| 审计日志 | 操作记录（who/when/what） | P1 |
| 会话管理 | Token + 超时 | P1 |
| 数据销毁 | 覆写 3 遍 + 删除 | P1 |
| 字段级加密 | 敏感字段单独加密 | P2 |

#### 加密方案

```
密钥派生: password → PBKDF2-HMAC-SHA256 (100000 iterations) → 256-bit key
数据库加密: SQLCipher 或 应用层 AES-256-GCM
备份加密: AES-256-GCM + 用户密码派生密钥（非存储）
```

#### 审计日志表

```sql
CREATE TABLE fin4_audit_log (
    id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL,
    user TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    details JSON,
    ip TEXT,
    created_at TIMESTAMP
);
```

#### API

| 功能 | API | 说明 |
|---|---|---|
| 初始化安全 | `POST /security/init` | 设置 PIN/密码 |
| 登录 | `POST /security/login` | 验证 → 返回 Token |
| 修改密码 | `PUT /security/password` | 需旧密码 |
| 创建备份 | `POST /security/backup` | 手动触发 |
| 恢复备份 | `POST /security/restore` | 从 .enc 文件 |
| 备份列表 | `GET /security/backups` | 历史备份 |
| 审计日志 | `GET /security/audit` | 操作记录 |
| 数据销毁 | `DELETE /security/wipe` | 安全擦除（需确认） |


## 5. Web UI 设计

### 5.1 页面结构

```
/
├── /dashboard          仪表盘（净值/收支/资产分布）
├── /accounts           账户管理
│   ├── /create         创建账户
│   ├── /{id}           账户详情+明细
│   └── /reconcile      对账
├── /transactions       记账
│   ├── /new            记一笔
│   ├── /list           交易明细
│   └── /import         CSV导入
├── /loans              贷款管理
│   ├── /create         创建贷款
│   └── /{id}           贷款详情+还款计划
├── /insurance          保险管理
│   ├── /create         添加保单
│   └── /{id}           保单详情
├── /portfolio          投资持仓
│   ├── /create         创建组合
│   └── /{id}           持仓+盈亏+配置
├── /reports            报表中心
│   ├── /balance-sheet  资产负债表
│   ├── /income         收支汇总
│   ├── /cashflow       现金流
│   └── /export         导出Excel/Word
├── /advise             理财建议
│   ├── /health         健康评分
│   ├── /debt           债务优化
│   └── /allocation     配置建议
├── /rates              利率管理
│   ├── /current        当前利率
│   ├── /history        历史走势
│   └── /sync           手动同步
└── /settings           设置
    ├── /family         家庭画像
    ├── /categories     分类管理
    └── /import-rules   导入规则
```

### 5.2 仪表盘布局

```
┌─────────────────────────────────────────────────┐
│  💰 家庭净值: ¥XXX,XXX    📈 本月结余: ¥X,XXX   │
├────────────┬────────────┬────────────┬──────────┤
│  总资产    │  总负债    │  净资产    │ 资产负债率│
│  ¥XXX,XXX  │  ¥XXX,XXX  │  ¥XXX,XXX  │   XX%    │
├────────────┴────────────┴────────────┴──────────┤
│  [资产分布饼图]        │  [月度收支趋势折线图]     │
├───────────────────────┼─────────────────────────┤
│  [贷款还款进度]        │  [投资组合配置]           │
└───────────────────────┴─────────────────────────┘
```

## 6. CLI 设计

```bash
# 家庭管理
finctl family create --name "Rex 家庭" --currency CNY
finctl family show

# 账户
finctl account create --code 1001 --name "库存现金" --type asset --balance 5000
finctl account list
finctl account balance 1001

# 记账
finctl txn add --debit 5003 --credit 1001 --amount 50 --note "午餐"
finctl txn list --account 1001 --from 2026-09-01
finctl txn import --file bank.csv

# 贷款
finctl loan create --name "房贷" --principal 1000000 --rate 0.035 --term 360
finctl loan schedule <loan_id>
finctl loan prepay <loan_id> --amount 50000

# 保险
finctl insurance add --name "重疾险" --type critical_illness --premium 8000 --sum 300000
finctl insurance gap

# 投资
finctl portfolio create --name "我的组合"
finctl portfolio buy <portfolio_id> --code 600519 --name "茅台" --shares 100 --price 1600
finctl portfolio performance <portfolio_id>

# 报表
finctl report balance-sheet --format excel --output report.xlsx
finctl report income --from 2026-01-01 --to 2026-12-31 --format word

# 利率
finctl rate sync
finctl rate latest --type lpr

# 建议
finctl advise health
finctl advise debt --strategy avalanche
```

## 7. OpenClaw 集成

### 7.1 对话式交互

通过自然语言触发 L4 能力：

```
Rex: 今天午餐花了50块
Jerry: [调用 txn_svc] 已记录：生活支出 50.00 → 库存现金

Rex: 看看这个月的收支
Jerry: [调用 report_svc] 本月收入 35,000，支出 18,000，结余 17,000

Rex: 我的财务健康怎么样？
Jerry: [调用 advise_svc] 健康评分 85/100，建议增加应急资金

Rex: 帮我同步一下最新 LPR
Jerry: [调用 rate_svc] 5年期 LPR 已更新为 3.65%
```

### 7.2 Skill 封装

L4 封装为 OpenClaw skill：`finance-l4`
- 触发词：理财/记账/贷款/保险/投资/报表
- 调用路径：Skill → Service → L3 Engine

## 8. 部署设计

### 8.1 独立部署

```bash
# 安装
pip install fin-l4

# 初始化
finctl init --db ~/.fin-l4/data.db

# 启动 Web UI
python -m fin_l4.web --port 8500

# 或直接 Docker
docker run -v ~/.fin-l4:/data -p 8500:8500 fin-l4:latest
```

### 8.2 集成部署

```bash
# 作为 OpenClaw workspace 的一部分
cd workspace/finance-engine
python -m fin_l4.web --port 8500
```

### 8.3 端口分配

| 服务 | 端口 | 备注 |
|---|---|---|
| L4 Web UI | 8500 | 不与现有服务冲突 |
| L4 API | 8500 (同) | REST API |

## 9. 实施计划

### M1: 骨架 + 数据层
- [ ] 项目结构 + 依赖管理
- [ ] SQLite 初始化 + 迁移框架
- [ ] Repository 模式 + 全部 CRUD
- [ ] FastAPI 应用 + 路由注册
- [ ] 基础模板 + 静态资源

### M2: 核心业务
- [ ] 账户模块（创建/查询/试算平衡/对账）
- [ ] 记账模块（记一笔/明细/分类/预算）
- [ ] CSV 导入 + 自动分类规则
- [ ] 仪表盘页面

### M3: 贷款+保险+投资 ✅
- [x] 贷款模块（创建/还款计划/提前还款/结清/详情页）
- [x] 保险模块（保单/现金价值/退保/保障缺口/详情页）
- [x] 投资模块（组合/买卖/盈亏/配置/再平衡/详情页）

### M4: 报表+建议+利率 ✅
- [x] 报表模块（3 种报表 + Excel/Word 导出）
- [x] 理财建议（健康/债务/配置）
- [x] 利率同步（手动）
- [x] CLI 完整实现（11 命令组）
- [x] OpenClaw skill 封装

### M5: 打磨 + 测试
- [ ] 全量测试（单元 + 集成 + E2E）
- [ ] Web UI 交互优化
- [ ] 数据备份/恢复
- [ ] 文档 + 使用指南

## 10. 验证标准

| 验收项 | 标准 |
|---|---|
| Web UI | 浏览器访问 :8500，全部页面可交互 |
| 记账 | 创建账户→记一笔→试算平衡→出报表 |
| 贷款 | 创建→还款计划→提前还款→概览 |
| 保险 | 添加→现金价值→保障缺口 |
| 投资 | 买入→更新价格→盈亏→再平衡 |
| 报表 | 7 种报表 + Excel + Word 导出 |
| 利率 | 手动同步 + 定时自动 + 缓存 |
| CLI | finctl 全流程可用 |
| OpenClaw | 对话触发 L4 能力 |
| 测试 | 核心路径 100% 覆盖 |

---

## 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-09-04 | 3.0 | M3+M4 完成: 贷款/保险/投资深度 + 导出 + CLI + Skill |
| 2026-09-04 | 2.1 | 增补：外部数据接入(N1) + 系统链接(N2) + 数据安全(N3) |
| 2026-09-04 | 2.0 | L4 管理系统完整设计（M1-M5） |
| 2026-09-03 | 1.4 | P4 L4 实例落地（FIN-L4-PF01） |
| 2026-09-03 | 1.3 | P3 投资+建议落地 |
| 2026-09-03 | 1.2 | P2 保险+利率落地 |
| 2026-09-03 | 1.1 | P1 核心引擎落地 |
| 2026-09-03 | 1.0 | 初始设计 |
