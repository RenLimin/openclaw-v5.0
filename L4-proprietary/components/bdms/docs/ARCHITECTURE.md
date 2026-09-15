# BDMS 架构设计

> Bangcle Delivery Management System — 交付管理系统
> 版本：v1.0（2026-09-15）
> 层级：L4 专有业务
> 继承：L3 `delivery-management-framework`（DDD 骨架）

## 1. 设计目标

为交付团队提供**端到端自动化**的交付管理系统，覆盖：

1. **交付月度管理** — 交付月报端到端自动生成（可 AI Agent 独立执行）
2. **确认收入管理** — 确收差异分析报表端到端自动生成（可 AI Agent 独立执行）
3. **交付管理基础数据** — 图例等核心数据的 Web 维护
4. **交付统计看板** — 汇总数据的可视化 + 下钻穿透
5. **交付管理系统设定** — 全局时间筛选条件

## 2. 核心架构决策

### 2.1 单一实现路径（强制）

所有功能**只有一个实现路径**，禁止多版本共存。既有资产以**代码级复用**方式迁入，迁入后原实现归档。

### 2.2 数据流架构

```
原始数据源                     计算层                    持久层                输出层
┌──────────────┐          ┌──────────────┐        ┌─────────────┐      ┌────────────┐
│ ONES 导出 CSV │          │  月报引擎     │        │             │      │  Excel 导出 │
│  (签约/POC/异常)│ ────────>│  (83/84/38列) │───────>│  SQLite     │─────>│            │
├──────────────┤          ├──────────────┤        │  bdms.db    │      ├────────────┤
│ 确收对比表 xlsx│          │  确收引擎     │        │             │      │  Web UI    │
│  (计划/预算)  │ ────────>│  (21 计算)    │───────>│  (月报表 +   │─────>│  (看板/下钻) │
├──────────────┤          ├──────────────┤        │   确收表)    │      ├────────────┤
│ 图例/基础数据 │ ────────>│  基础数据引擎  │───────>│             │      │  JSON API  │
└──────────────┘          └──────────────┘        └─────────────┘      └────────────┘
```

### 2.3 三大核心原则

| 原则 | 落地方式 |
|---|---|
| **幂等生成** | 同一月份重复生成 → 检测已有数据 → 支持"读取现有"或"重新生成(覆盖)" |
| **AI Agent 可独立执行** | 每个核心功能暴露纯函数入口 + CLI 子命令，不依赖 Web |
| **计算与展示分离** | 引擎层纯计算无副作用；Web 层只读 DB 渲染 |

## 3. 模块划分

```
bdms/
├── src/bdms/
│   ├── core/                    # 核心层（跨模块）
│   │   ├── db.py                # SQLite 连接 + schema 管理 + 迁移
│   │   ├── models.py            # 领域模型（继承 L3 BaseModel）
│   │   ├── paths.py             # 路径解析（数据源/输出/DB）
│   │   ├── registry.py          # 模块注册（5 大功能模块）
│   │   └── events.py            # 事件总线（可选，复用 L3）
│   ├── modules/
│   │   ├── delivery_report/     # 【模块1】交付月度管理
│   │   │   ├── engine.py        #   计算引擎（复用 delivery-center v2）
│   │   │   ├── generator.py     #   Excel 生成
│   │   │   └── service.py       #   编排（幂等/覆盖/读取）
│   │   ├── revenue/             # 【模块2】确认收入管理
│   │   │   ├── engine.py        #   计算引擎（复用 revenue-recognition）
│   │   │   ├── generator.py     #   Excel 生成
│   │   │   └── service.py       #   编排
│   │   ├── master_data/         # 【模块3】交付管理基础数据
│   │   │   ├── engine.py        #   图例等基础数据 CRUD
│   │   │   └── service.py
│   │   ├── dashboard/           # 【模块4】交付统计看板
│   │   │   ├── engine.py        #   聚合查询
│   │   │   └── service.py       #   图表数据构造 + 下钻
│   │   └── settings/            # 【模块5】交付管理系统设定
│   │       ├── engine.py        #   系统设置读写
│   │       └── service.py
│   ├── web/                     # Web UI（FastAPI）
│   │   ├── main.py              #   应用入口 + 路由
│   │   ├── api.py               #   REST API
│   │   ├── views/               #   Jinja2 模板
│   │   └── static/              #   CSS/JS
│   └── cli/                     # CLI 入口（AI Agent 调用）
│       └── main.py              #   bdms <module> <command>
├── config/                      # 配置（Sheet 格式、列映射、图例定义）
├── data/                        # SQLite DB
├── output/                      # Excel 输出
└── tests/                       # 测试
```

## 4. 数据模型

### 4.1 统一 DB（`data/bdms.db`）

**元数据表**

| 表 | 用途 |
|---|---|
| `job` | 生成任务记录（月报/确收），含状态、进度、时间戳 |
| `report_month` | 月度数据登记（哪个月的数据已落盘、来源、生成时间） |

**月报模块表**（`dr_` 前缀）

| 表 | 对应 Sheet | 列数 |
|---|---|---|
| `dr_sign` | 签约 | 83 |
| `dr_poc` | POC&提前实施 | 84 |
| `dr_exception` | 异常项目 | 38 |
| `dr_revenue_handover` | 确收交接 | 23 |
| `dr_acceptance_handover` | 验收交接 | 27 |
| `dr_stat_*` | 各统计 Sheet | — |

**确收模块表**（`rr_` 前缀）

| 表 | 用途 |
|---|---|
| `rr_plan_draft` | 计划确收底稿 |
| `rr_budget_exec` | 预算执行表 |
| `rr_monthly_summary` | 月度汇总记录 |
| `rr_performance_summary` | 履约汇总记录 |
| `rr_reference_data` | 图例等参考数据 |

### 4.2 幂等与覆盖语义

```
generate(month, mode) →
  mode = "auto"     # 默认：DB 有数据 → 直接读取；无数据 → 全流程生成
  mode = "read"     # 强制从 DB 读取（不重新计算）
  mode = "regenerate" # 强制重新生成 + 覆盖 DB
```

## 5. 关键接口

### 5.1 引擎层（纯函数）

```python
# 交付月报引擎
DeliveryReportEngine(db_path).compute(month: str) -> dict[str, pd.DataFrame]
DeliveryReportEngine(db_path).persist(month, data, overwrite: bool) -> None
DeliveryReportEngine(db_path).load(month) -> dict[str, pd.DataFrame]

# 确收引擎
RevenueEngine(db_path).compute(period: str) -> dict[str, list[dict]]
RevenueEngine(db_path).persist(period, data, overwrite) -> None
RevenueEngine(db_path).load(period) -> dict[str, list[dict]]
```

### 5.2 服务层（编排）

```python
ReportService(db_path).generate_report(month, mode="auto") -> JobResult
RevenueService(db_path).generate_analysis(period, mode="auto") -> JobResult
```

### 5.3 CLI（AI Agent 入口）

```bash
bdms report generate 202608              # 生成交付月报
bdms report generate 202608 --mode regenerate
bdms report export 202608 --out ./x.xlsx
bdms revenue generate 202608 --mode auto
bdms revenue export 202608
bdms master-data legend list
bdms dashboard summary 202608
bdms settings get
bdms settings set --months-back 12
```

## 6. 复用映射

| 新模块 | 复用来源 | 复用方式 |
|---|---|---|
| `modules/delivery_report/engine.py` | `delivery-center/src/delivery_center/v2/delivery_report_generator.py` | 迁入核心函数，重构为类 |
| `modules/delivery_report/generator.py` | `delivery-center/src/delivery_center/v2/generators/build_stat_sheets.py` | 迁入统计 Sheet 构建 |
| `modules/revenue/engine.py` | `revenue-recognition/src/revenue_recognition/v1/engine.py` | 迁入 RevenueEngine |
| `config/sheet_formats.py` | `delivery-center/src/delivery_center/v2/config/sheet_formats.py` | 直接复制 |
| `core/db.py` | 两处 db.py 合并 | 统一 schema |

## 7. Web UI 页面

| 页面 | 路径 | 功能 |
|---|---|---|
| 总览 | `/` | 系统状态 + 快捷入口 |
| 交付月报 | `/delivery-report` | 生成/查看/导出月报 |
| 确认收入 | `/revenue` | 生成/查看/导出确收分析 |
| 基础数据 | `/master-data` | 图例等数据维护 |
| 统计看板 | `/dashboard` | 图表 + 筛选 + 下钻 |
| 系统设定 | `/settings` | 默认时间跨度等 |

## 8. 依赖关系

- **依赖**：Python 3.10+、pandas、openpyxl、FastAPI、uvicorn、Jinja2
- **继承**：L3 `delivery-management-framework`（DDD 骨架、事件总线）
- **数据源**：
  - ONES 导出：`~/.openclaw/data/ones_exports/*.csv`
  - 团队报告：`/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/{month}/`

## 9. 演进方向

1. **数据源 API 化** — 从手动导出改为 API 实时拉取
2. **AI 分析增强** — LLM 自动生成月报分析文字
3. **告警联动** — 异常数据触发通知
4. **多租户** — 支持多团队并行

## 变更历史

- 2026-09-15: v1.0 初版，5 大模块架构设计
