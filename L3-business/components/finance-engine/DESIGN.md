# finance-engine

## 设计目标

提供纯函数式理财计算引擎，覆盖复式记账、贷款核算、保险测算、利率服务、投资组合、理财建议六大领域。作为 L3 通用层，为 L4 专有业务（fin-l4）提供可复用的计算能力。

## 架构决策

- **纯函数式设计**：输入 → 计算 → 输出，不修改全局状态，无副作用
- **无持久化**：不直接读写数据库，数据由 L4 层注入，计算结果返回给 L4
- **单向依赖**：L4 → L3（L4 import L3），L3 不感知 L4，反向依赖禁止
- **唯一 IO 例外**：`fin004_rate` 含本地文件缓存（TTL 24h），是唯一允许 IO 的模块
- **独立模块**：每个 fin00x 模块独立封装，可单独使用

## 模块划分

```
finance-engine/
├── fin001_account/             # 复式记账引擎
│   └── AccountingEngine       # 借贷记账、科目余额、试算平衡
├── fin002_loan/                # 贷款/借款核算
│   └── LoanEngine             # 4 种还款方式 + 提前还款模拟
├── fin003_insurance/           # 保险产品核算
│   └── InsuranceEngine        # 现金价值/IRR/红利演示
├── fin004_rate/                # 利率服务
│   └── RateEngine             # LPR/基准利率/利率转换/本地缓存
├── fin005_portfolio/           # 投资持仓核算
│   └── PortfolioEngine        # 收益/配置/再平衡
├── fin006_advisor/             # 理财建议引擎
│   └── AdvisorEngine          # KPI 诊断/资产配置/债务优化
├── core/                       # 内部基础设施
│   ├── db/repositories.py      # 数据仓储（供 L4 层注入数据）
│   ├── external/fx_source.py   # 外汇数据源
│   ├── external/base.py        # 外部数据源基类
│   └── security/               # 安全模块
├── web/                        # 独立 Web 演示
│   ├── main.py                 # Flask 入口
│   ├── api.py                  # REST API
│   └── templates/              # Jinja2 模板（12 页面）
├── integration/                # L4 集成
│   └── links.py                # L4 → L3 链接管理
├── config.py                   # 全局配置
├── load_demo_data.py           # 演示数据加载
└── tests/                      # 单元测试
```

## 关键接口/数据结构

- `AccountingEngine`：复式记账，`record_entry(debit, credit, amount)` / `trial_balance()`
- `LoanEngine`：贷款计算，`calculate_schedule(principal, rate, term, method)` / `prepay()`
- `InsuranceEngine`：保险测算，`cash_value()` / `irr()` / `dividend_demo()`
- `RateEngine`：利率服务，`get_lpr()` / `convert_rate()` / `cache_get()`
- `PortfolioEngine`：投资核算，`returns()` / `allocation()` / `rebalance()`
- `AdvisorEngine`：理财建议，`kpi_diagnosis()` / `asset_advice()` / `debt_optimize()`

## 依赖关系

- **依赖**：Python 3.10+、decimal（精度计算）
- **被依赖**：`fin-l4`（L4 层，通过 sys.path 注入方式 import 本组件）

## 演进方向

1. **新增模块**：税务引擎（fin007）、退休规划（fin008）
2. **精度提升**：引入更多金融数学模型（Monte Carlo 模拟）
3. **性能优化**：计算结果缓存、批量计算接口
4. **标准化**：发布为独立 PyPI 包，供外部项目使用
