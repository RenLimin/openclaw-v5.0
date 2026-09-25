# BDMS v2.1 详细设计 — 驾驶舱管理（Dashboard）

| 项 | 值 |
|---|---|
| 文档编号 | DESIGN-DETAIL-DASHBOARD-v2.1 |
| 版本 | v2.1 r3（2026-09-24） |
| 层级 | L4 专有业务层（BDMS）模块详细设计 |
| 模块编码 | `dashboard` |
| 对应 PRD | PRD-v2.1.md §3.2 模块 6（F-DB-01~06 / F-DD-01~05 / F-DE-01~05） |
| 上游文档 | DESIGN-OUTLINE-v2.1.md §3.6 |
| 下游文档 | IMPLEMENTATION-PLAN（Phase 拆分）、VERIFICATION（验收报告） |
| 状态 | 待 Rex 审核 |
| 编制日期 | 2026-09-22 |

---


## 目录

0. [版本记录](#0-版本记录)
1. [模块概述](#1-模块概述)
2. [业务核心](#2-业务核心)
3. [业界最佳实践参考](#3-业界最佳实践参考)
4. [与其他模块交互](#4-与其他模块交互)
5. [OS 依赖与限制](#5-os-依赖与限制)
6. [技术方案](#6-技术方案)
7. [接口设计](#7-接口设计)
8. [数据模型](#8-数据模型)
9. [默认驾驶舱布局](#9-默认驾驶舱布局)
10. [KPI 卡片设计](#10-kpi-卡片设计)
11. [图表类型设计](#11-图表类型设计)
12. [下钻功能设计](#12-下钻功能设计)
13. [明细编辑设计](#13-明细编辑设计)
14. [视图管理设计（多看板/多驾驶舱）](#14-视图管理设计多看板多驾驶舱)
15. [前端实现方案](#15-前端实现方案)
16. [错误处理](#16-错误处理)
17. [CLI 命令 + Web API](#17-cli-命令--web-api)
18. [测试策略](#18-测试策略)
附录 B：[复用资产清单与使用方式](#附录-b复用资产清单与使用方式)
审核记录与变更历史

---

## 0. 版本记录

| 版本 | 日期 | 变更说明 |
|---|---|---|
| v2.1 Detail r1 | 2026-09-22 | 初版：14 章节完整设计 |
| v2.1 Detail r2 | 2026-09-22 | Rex 审核反馈 3 条：全系统数据覆盖 + 业务核心（默认月报汇总 + 多看板）+ 业界最佳实践深化 |
| v2.1 Detail r3 | 2026-09-22 | Rex 审核反馈：数据源注册辅助操作（SQL 提示/校验/说明/试运行/字段映射/性能评估） |

---

## 1 模块概述

### 1.1 业务域

驾驶舱管理模块是 BDMS 的**数据消费与可视化层**，负责：

- **全系统数据覆盖**：聚合查询、汇总、显示所有业务模块数据（当前 7 模块 + 预留新业务数据接口）
- **默认驾驶舱**：按交付月报 + 确收分析月报的统计汇总展示
- **可配置看板**：支持人工单独配置多看板/多驾驶舱，设置默认看板
- **下钻分析**：从汇总数据穿透到明细记录
- **明细编辑**：在驾驶舱内直接编辑特定字段

```
全系统数据（7 模块 + 预留新业务接口）
    ↓ 聚合计算
默认驾驶舱（交付月报 + 确收分析统计汇总）
    ↓
KPI 卡片区 + 图表区（5 种图表类型）
    ↓
下钻（KPI → 明细 → 单条记录，三级穿透）
    ↓
明细编辑（字段编辑 + 权限控制 + 编辑历史）
```

### 1.2 数据覆盖范围

| 数据域 | 当前模块 | 预留扩展 |
|---|---|---|
| 合同数据 | contract_management | — |
| 项目数据 | project_management | — |
| 交付月报 | delivery_report | — |
| 确收分析 | revenue | — |
| 项目利润 | profit_management | — |
| 风险数据 | project_management.risk | — |
| 售后数据 | project_management.after_sales | — |
| 知识库 | knowledge_base | v2.2 |
| 数据集成 | integration | v2.2 |
| 新业务 | — | **预留接口**（数据源注册机制，新模块接入无需改驾驶舱代码） |

> **预留机制**：通过 `dashboard_data_source` 注册表实现新模块数据源即插即用。新模块只需注册数据源 key + 聚合 SQL，驾驶舱自动纳入 KPI 候选池。

---

## 2 业务核心

### 2.1 核心定位

驾驶舱的业务核心是：

1. **默认展示交付月报 + 确收分析月报的统计汇总数据**
   - 顶部 KPI 区：12 个核心指标（合同数/金额、交付数/及时率、确收金额/率、成本/利润/风险等）
   - 交付月报区：签约数、交付项目数、交付及时率、异常项目数（来自 delivery_report 统计 Sheet）
   - 确收分析区：确收金额、确收率、预算完成率、差异分析（来自 revenue 汇总 Sheet）
   - 项目利润区：收入、成本、利润、毛利率（来自 profit_management）
   - 风险区：风险项目数、异常处置状态（来自 project_management）

2. **支持人工单独配置多看板/多驾驶舱**
   - 用户可创建多个视图（管理视图、交付视图、财务视图、自定义视图等）
   - 每个视图可配置显示的 KPI 卡片、图表类型、布局
   - 可设置任意视图为默认看板（首次访问自动加载）
   - 支持视图的 CRUD（创建/读取/更新/删除）

### 2.2 驾驶舱 vs 看板 概念区分

| 概念 | 说明 | 示例 |
|---|---|---|
| 驾驶舱（Cockpit） | 全局数据视图，覆盖全系统数据 | 默认驾驶舱 |
| 看板（Dashboard） | 用户自定义的专题视图 | 管理视图、交付视图 |
| 视图（View） | 一个具体的配置实例 | "我的交付看板" |
| 卡片（Card） | 视图中的最小展示单元 | KPI 卡片、图表卡片 |

> 本系统支持**多驾驶舱**（多个全局视图）和**多看板**（多个专题视图），统一由视图管理模块管理。

---

## 3 业界最佳实践参考

### 3.1 最佳实践对标

| 产品 | 核心能力 | 借鉴点 | 本系统落地 |
|---|---|---|---|
| **ONES 自定义看板** | KPI 卡片 + 图表 + 筛选 | 指标卡 + 图表类型选择 + 筛选器联动 | 12 KPI + 5 种图表 + 多维筛选 |
| **Grafana** | 面板 + 数据源 + 告警 | 数据源注册机制 + 面板布局 + 阈值告警 | dashboard_data_source 注册表 + CSS Grid + KPI 颜色阈值 |
| **Tableau** | 维度下钻 + 交互式分析 | 三级下钻 + 路径回溯 + 交叉筛选 | 部门→项目→记录 + Breadcrumb + 多维筛选 |
| **Power BI** | 书签 + 视图切换 | 多视图管理 + 默认视图 + 个人书签 | 视图 CRUD + 默认视图 + 用户配置 |
| **Metabase** | 快照缓存 + 实时刷新 | 查询缓存 + 手动刷新 + 快照表 | dash_snapshot + 刷新按钮 |
| **DataV** | 数据大屏 | 深色主题 + 大数字 + 实时动画 | 可选深色主题 + 大数字 KPI |
| **Kibana** | 时间序列 + 聚合 | 时间范围选择器 + 自动聚合 | 月/季/年/自定义 + 联动所有卡片 |

### 3.2 设计原则

| 原则 | 说明 | 落地 |
|---|---|---|
| **数据源可插拔** | 新模块数据源注册即可接入驾驶舱 | dashboard_data_source 注册表 |
| **默认即最佳** | 默认驾驶舱覆盖 80% 用户需求 | 交付月报 + 确收分析统计汇总 |
| **配置零代码** | 用户通过 UI 配置，无需写代码 | 视图编辑器（选择 KPI + 图表 + 布局） |
| **性能优先** | 大数据量用快照缓存 + 分页 | dash_snapshot + 分页查询 |
| **权限隔离** | 按角色 + 项目双重控制可见数据 | 数据权限过滤（查询时注入） |

---

## 4 与其他模块交互

### 4.1 数据源（只读消费）

| 模块 | 数据表 | 驾驶舱用途 | 数据新鲜度 |
|---|---|---|---|
| contract_management | cr_contracts | 合同数/金额 KPI | 实时 |
| project_management | pm_projects | 在建/交付/验收项目数 | 实时 |
| project_management | pm_risk_record | 风险项目数/处置状态 | 实时 |
| project_management | pm_after_sales | 售后工单数 | 实时 |
| delivery_report | dr_sheet_row + 统计 Sheet | 交付月报区数据 | 月报生成后 |
| revenue | rr_sheet_row + 汇总 Sheet | 确收分析区数据 | 月报生成后 |
| profit_management | pf_timesheet / pf_cost_item / pf_profit_snapshot | 项目利润区数据 | 实时 |
| **预留：新业务模块** | **dashboard_data_source 注册** | **即插即用** | — |

### 4.2 数据源注册机制（预留扩展）

```sql
CREATE TABLE IF NOT EXISTS dashboard_data_source (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key  TEXT UNIQUE NOT NULL,       -- 数据源标识（如 "contract_count"）
    module      TEXT NOT NULL,              -- 来源模块
    title       TEXT NOT NULL,              -- 显示名称
    description TEXT,
    category    TEXT NOT NULL,              -- kpi / chart / table
    aggregate_sql TEXT NOT NULL,            -- 聚合查询 SQL
    refresh_mode TEXT DEFAULT 'realtime',  -- realtime / daily / manual
    enabled     INTEGER DEFAULT 1,
    created_at  TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT DEFAULT (datetime('now', 'localtime'))
);
```

> 新模块接入驾驶舱只需：① 注册 dashboard_data_source ② 提供聚合 SQL ③ 驾驶舱自动纳入 KPI 候选池。无需修改驾驶舱代码。

#### 4.2.1 数据源注册辅助操作

为降低新模块接入门槛，提供以下辅助操作：

| 辅助功能 | 说明 | 触发时机 |
|---|---|---|---|
| **SQL 编写提示** | 根据数据源 category 自动生成 SQL 模板（KPI 类提供 COUNT/SUM/AVG 模板，Chart 类提供 GROUP BY 模板，Table 类提供 SELECT 模板） | 创建/编辑数据源时 |
| **SQL 语法校验** | 执行 `EXPLAIN QUERY PLAN <sql>` 验证 SQL 合法性，返回错误位置和原因 | 保存前自动校验 |
| **SQL 语义校验** | 检查 SQL 是否包含危险的写操作（INSERT/UPDATE/DELETE/DROP），只允许 SELECT 查询 | 保存前自动校验 |
| **SQL 说明生成** | 自动解析 SQL 语义，生成人类可读的说明（如「统计合同表中状态为 signed 的合同数量」） | 保存后自动生成 |
| **SQL 试运行** | 执行 SQL 并返回样例数据（LIMIT 10），验证结果格式符合预期 | 手动触发 |
| **字段映射提示** | 根据 SQL 返回的列名，自动映射到 KPI 字段（value / label / unit） | 试运行后自动提示 |
| **性能评估** | 执行 `EXPLAIN QUERY PLAN` 评估查询复杂度，标记全表扫描等低效查询 | 保存前自动评估 |

**SQL 编写提示模板**：

| category | 模板 | 变量 |
|---|---|---|---|
| kpi（计数） | `SELECT COUNT(*) AS value FROM {table} WHERE {conditions}` | table, conditions |
| kpi（求和） | `SELECT SUM({field}) AS value FROM {table} WHERE {conditions}` | table, field, conditions |
| kpi（比率） | `SELECT ROUND(SUM(CASE WHEN {cond} THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS value FROM {table}` | table, cond |
| chart（趋势） | `SELECT {time_field} AS month, COUNT(*) AS value FROM {table} GROUP BY {time_field} ORDER BY {time_field}` | table, time_field |
| chart（分布） | `SELECT {dim} AS label, COUNT(*) AS value FROM {table} GROUP BY {dim} ORDER BY value DESC` | table, dim |
| table（明细） | `SELECT {fields} FROM {table} WHERE {conditions} ORDER BY {sort_field} LIMIT 100` | table, fields, conditions, sort_field |

**SQL 校验规则**：

| 校验项 | 规则 | 错误提示 |
|---|---|---|---|
| 语法合法性 | `EXPLAIN QUERY PLAN <sql>` 不报错 | 「SQL 语法错误：{error_msg}，位置：{pos}」 |
| 只读检查 | SQL 必须以 SELECT 开头（允许 WITH ... SELECT） | 「仅允许 SELECT 查询，禁止写操作」 |
| 表存在性 | SQL 中引用的表必须在 bdms.db 中存在 | 「表 {table_name} 不存在」 |
| 字段存在性 | SQL 中引用的字段必须在对应表中存在 | 「字段 {field_name} 不存在于表 {table_name}」 |
| 别名要求 | 聚合查询必须有 AS value 别名 | 「聚合查询必须包含 AS value 别名」 |
| 性能警告 | EXPLAIN 出现 SCAN TABLE（全表扫描）时警告 | 「警告：查询使用全表扫描，建议添加索引」 |

**SQL 说明生成规则**：

```python
class SqlDescriber:
    """SQL 语义说明生成器。"""

    def describe(self, sql: str) -> str:
        """解析 SQL → 人类可读说明。

        示例：
        - SELECT COUNT(*) FROM cr_contracts WHERE status='signed'
          → "统计合同表中状态为已签署的合同数量"
        - SELECT SUM(amount) FROM cr_contracts WHERE substr(created_at,1,7)='2026-09'
          → "统计合同表中 2026-09 月的合同金额总和"
        - SELECT dept, COUNT(*) as value FROM pm_projects GROUP BY dept
          → "按部门分组统计项目数量"
        """
```

### 4.3 写入（驾驶舱自有）

| 表 | 用途 |
|---|---|
| `db_view_config` | 视图配置（布局 + KPI + 图表 + 筛选条件） |
| `db_edit_history` | 编辑历史记录 |
| `dash_snapshot` | KPI 快照缓存 |
| `dashboard_data_source` | 数据源注册表（预留扩展） |
| `dash_user_config` | 用户级配置（默认视图、主题偏好） |

---

## 5. OS 依赖与限制

> 驾驶舱是数据消费层，自身逻辑 OS 无关，但依赖前端浏览器和后端数据源。

| 功能 | OS 依赖 | macOS | Windows | Linux | 说明 |
|---|---|---|---|---|---|
| 前端渲染 | 浏览器（HTML/JS/Chart.js） | ✅ Chrome/Safari | ✅ Chrome/Edge | ✅ Chrome/Firefox | 响应式布局 |
| KPI 聚合查询 | SQLite SQL | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 SQL，OS 无关 |
| 下钻明细查询 | SQLite SQL | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 SQL，OS 无关 |
| 明细编辑 | SQLite UPDATE | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 SQL，OS 无关 |
| 视图配置存储 | SQLite | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 SQL，OS 无关 |
| 数据源（间接） | integration 浏览器自动化 | ✅ osascript（已验证） | 🔶 Playwright（待适配） | 🔶 Playwright（待适配） | 间接依赖各模块数据 |
| Web 服务 (FastAPI) | uvicorn | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 Python |
| CLI (Click) | click | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 Python |

**间接依赖链**：
```
dashboard
├── 前端 → 浏览器（跨平台，响应式）
├── KPI/下钻/编辑 → SQLite SQL（OS 无关）
├── 数据源 → 各业务模块 → integration → 浏览器自动化
│   ├── macOS: osascript + Chrome（已验证）
│   ├── Linux: Playwright Headless（待验证）
│   └── Windows: Playwright Headless（待开发）
└── Web/CLI → 纯 Python（全平台）
```

## 6. 技术方案

### 5.1 架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                         前端层（Browser）                             │
│                                                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ dashboard.html│  │ dashboard.js │  │ Chart.js     │              │
│  │ (Jinja2 模板) │  │ (交互逻辑)    │  │ (图表渲染)    │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
│         └─────────────────┼─────────────────┘                       │
│                           │ fetch /api/dashboard/*                   │
├───────────────────────────┼─────────────────────────────────────────┤
│                      API 路由层                                      │
│  web/dashboard.py                                                     │
│    /api/dashboard/summary       → KPI 汇总                           │
│    /api/dashboard/trend         → 趋势数据                           │
│    /api/dashboard/drilldown     → 下钻明细                           │
│    /api/dashboard/views         → 视图 CRUD                          │
│    /api/dashboard/edit          → 字段编辑                           │
│    /api/dashboard/data-sources  → 数据源注册（预留）                  │
├───────────────────────────┼─────────────────────────────────────────┤
│                      服务层                                          │
│  DashboardService          → 驾驶舱核心（汇总 + 下钻）               │
│  DashboardCustomizationService → 视图管理（多看板/多驾驶舱）         │
│  DashboardEditService      → 明细编辑                                │
│  DashboardDataSourceService → 数据源注册（预留）                     │
├───────────────────────────┼─────────────────────────────────────────┤
│                      引擎层                                          │
│  DashboardEngine                                                     │
│    - compute_kpis()         → 12 个 KPI 计算                         │
│    - compute_trend()        → 趋势序列                               │
│    - compute_drilldown()    → 下钻明细                               │
│    - compute_snapshot()     → 快照聚合                               │
│    - compute_custom_metric() → 自定义指标（预留）                    │
├───────────────────────────┼─────────────────────────────────────────┤
│                      数据层                                          │
│  bdms.db（业务表，只读） + 驾驶舱自有表（视图配置 + 编辑历史 + 快照） │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.2 文件结构

```
modules/dashboard/
├── __init__.py              # 模块导出
├── engine.py                # 聚合查询引擎
├── service.py               # 驾驶舱核心服务
├── edit_service.py          # 明细编辑服务
├── views_service.py         # 视图管理服务（多看板/多驾驶舱）
├── data_source_service.py   # 数据源注册服务（预留扩展）
└── cli.py                   # CLI 命令

web/
├── dashboard.py             # 驾驶舱 API 路由
├── dashboard_mvp.py         # MVP 看板路由（已有，保留兼容）
├── templates/
│   ├── dashboard.html       # 驾驶舱主页面
│   ├── dashboard_mvp.html   # MVP 看板页面（已有）
│   └── dashboard_view.html  # 视图编辑页面
└── static/js/
    ├── dashboard.js         # 驾驶舱交互逻辑
    └── dashboard_mvp.js     # MVP 看板 JS（已有）

tests/
├── test_dashboard.py        # 引擎层测试
├── test_dashboard_api.py    # API 层测试
├── test_dashboard_edit.py   # 编辑功能测试
└── test_dashboard_views.py  # 视图管理测试
```

---

## 7. 接口设计

### 6.1 DashboardService（驾驶舱核心）

```python
class DashboardService:
    """驾驶舱核心服务 — 默认视图 + 汇总 + 下钻。"""

    def get_default_view(self) -> dict:
        """获取默认驾驶舱配置。

        默认驾驶舱 = 交付月报 + 确收分析月报统计汇总。
        5 个区域：KPI 区 + 交付月报区 + 确收分析区 + 项目利润区 + 风险区。
        """

    def summary(self, month: str | None = None,
                view_id: str | None = None) -> dict:
        """KPI 汇总。view_id 指定自定义视图，None 用默认驾驶舱。"""

    def trend(self, metric: str, range_months: int = 12) -> list:
        """单指标时间序列趋势。"""

    def drill_down(self, metric: str, month: str,
                   dimension: str | None = None,
                   value: str | None = None,
                   page: int = 1, page_size: int = 50,
                   sort_by: str | None = None,
                   sort_order: str = "desc",
                   filters: dict | None = None) -> dict:
        """下钻明细查询（三级穿透 + 分页/排序/筛选）。"""

    def refresh_snapshot(self, month: str | None = None) -> dict:
        """手动刷新快照缓存。"""
```

### 6.2 DashboardCustomizationService（视图管理 — 多看板/多驾驶舱）

```python
class DashboardCustomizationService:
    """视图管理服务 — 支持多看板/多驾驶舱配置。"""

    # 预置视图模板
    PRESET_VIEWS = {
        "default": "默认驾驶舱（交付月报+确收分析）",
        "management": "管理视图（全量 KPI + 风险）",
        "delivery": "交付视图（交付月报为主）",
        "revenue": "确收视图（确收分析为主）",
        "profit": "利润视图（成本/利润/毛利率）",
    }

    AVAILABLE_METRICS = [...]      # 12 个核心指标 + 自定义指标 + EVM 预留指标
    # EVM 预留（v2.2，见 PROFIT-MANAGEMENT §1.3.2）：
    #   spi (进度绩效指数) / cpi (成本绩效指数) / eac (完工估算) / vac (完工偏差)
    AVAILABLE_CHART_TYPES = [...]  # 5 种图表类型

    def create_view(self, user_id: str, view_name: str,
                    config: dict, set_default: bool = False) -> dict:
        """创建新视图（看板/驾驶舱）。"""

    def update_view(self, view_id: str, config: dict) -> dict:
        """更新视图配置。"""

    def delete_view(self, view_id: str) -> dict:
        """删除视图。"""

    def get_view(self, view_id: str) -> dict:
        """获取视图配置。"""

    def list_views(self, user_id: str) -> list[dict]:
        """列出用户所有视图。"""

    def set_default_view(self, view_id: str, user_id: str) -> dict:
        """设置默认视图（首次访问自动加载）。"""

    def get_default_view(self, user_id: str) -> dict:
        """获取用户的默认视图配置。"""

    def apply_preset(self, preset_key: str, user_id: str) -> dict:
        """应用预置视图模板。"""
```

### 6.3 DashboardEditService（明细编辑）

```python
class DashboardEditService:
    """明细编辑服务 — 字段编辑 + 权限控制 + 编辑历史。"""

    # 可编辑字段配置（按角色 + 项目双重控制）
    EDITABLE_FIELDS = {
        "cr_contracts": {
            "remark": {"label": "备注", "type": "text",
                       "roles": ["admin", "pmo", "sales", "super_admin"]},
            "status": {"label": "状态", "type": "select",
                       "roles": ["admin", "pmo", "super_admin"]},
        },
        "pm_projects": {
            "remark": {"label": "备注", "type": "text",
                       "roles": ["admin", "pmo", "pm", "super_admin"]},
            "pm": {"label": "项目经理", "type": "text",
                    "roles": ["admin", "pmo", "super_admin"]},
        },
        "pm_risk_record": {
            "remark": {"label": "备注", "type": "text",
                       "roles": ["admin", "pmo", "pm", "super_admin"]},
            "status": {"label": "状态", "type": "select",
                       "roles": ["admin", "pmo", "pm", "super_admin"]},
            "resolution": {"label": "处置方案", "type": "textarea",
                           "roles": ["admin", "pmo", "pm", "super_admin"]},
        },
        "pm_after_sales": {
            "remark": {"label": "备注", "type": "text",
                       "roles": ["admin", "pmo", "tech", "super_admin"]},
            "status": {"label": "状态", "type": "select",
                       "roles": ["admin", "pmo", "tech", "super_admin"]},
        },
    }

    def check_permission(self, user_id: str, table: str, field: str,
                         record_id: int | None = None) -> bool:
        """权限检查：角色控制字段范围 + 项目控制数据范围。"""

    def edit_field(self, record_id: int, field: str, value: any,
                   table: str, user_id: str) -> dict:
        """单字段编辑（权限检查 + 历史记录 + 即时保存）。"""

    def batch_edit(self, record_ids: list[int], field: str, value: any,
                   table: str, user_id: str) -> dict:
        """批量编辑。"""

    def get_edit_history(self, record_id: int, table: str) -> list:
        """获取编辑历史。"""

    def undo_edit(self, edit_id: int, user_id: str) -> dict:
        """撤销单次编辑（会话内）。"""
```

### 6.4 DashboardDataSourceService（数据源注册 + 辅助操作 — 预留）

```python
class DashboardDataSourceService:
    """数据源注册服务 — 新模块即插即用 + SQL 辅助操作。"""

    # ─── 数据源 CRUD ───

    def register_source(self, source_key: str, module: str, title: str,
                        category: str, aggregate_sql: str,
                        refresh_mode: str = "realtime",
                        description: str = "") -> dict:
        """注册新数据源（自动执行 SQL 校验 + 说明生成）。

        Returns: {"source_key": "...", "description_auto": "统计...", "warnings": []}

        Raises:
            SqlValidationError: SQL 语法/语义校验失败
        """

    def list_sources(self, enabled_only: bool = True) -> list[dict]:
        """列出所有已注册数据源。"""

    def compute_metric(self, source_key: str, month: str | None = None) -> dict:
        """计算指定数据源的指标值。"""

    # ─── SQL 辅助操作 ───

    def generate_sql_template(self, category: str, table: str,
                              **kwargs) -> str:
        """根据 category + 表名生成 SQL 模板。

        Args:
            category: kpi_count / kpi_sum / kpi_ratio / chart_trend / chart_dist / table_detail
            table: 目标表名
            **kwargs: 模板变量（field, conditions, time_field, dim 等）

        Returns:
            生成的 SQL 模板字符串
        """

    def validate_sql(self, sql: str) -> dict:
        """SQL 语法 + 语义 + 性能校验。

        Returns: {
            "valid": bool,
            "errors": [{"type": "syntax"|"readonly"|"table_not_found"|"field_not_found"|"alias_missing", "message": str}],
            "warnings": [{"type": "full_scan", "message": str}],
            "plan": str  -- EXPLAIN QUERY PLAN 输出
        }
        """

    def describe_sql(self, sql: str) -> str:
        """SQL → 人类可读说明。

        示例:
            SELECT COUNT(*) FROM cr_contracts WHERE status='signed'
            → "统计合同表中状态为已签署的合同数量"
        """

    def dry_run_sql(self, sql: str, limit: int = 10) -> dict:
        """试运行 SQL，返回样例数据。

        Returns: {
            "columns": ["value"],
            "rows": [[123]],
            "row_count": 1,
            "elapsed_ms": 12
        }
        """

    def suggest_field_mapping(self, sql: str) -> dict:
        """根据 SQL 返回列名，自动建议 KPI 字段映射。

        Returns: {
            "value_col": "value",   -- 数值列
            "label_col": null,        -- 标签列（chart/table 类型）
            "unit": "个"              -- 自动推断单位
        }
        """

    def estimate_performance(self, sql: str) -> dict:
        """性能评估（EXPLAIN QUERY PLAN）。

        Returns: {
            "complexity": "low"|"medium"|"high",
            "has_full_scan": true,
            "suggestions": ["建议为 status 字段添加索引"]
        }
        """
```

### 6.5 Web API 路由

```
/api/dashboard/summary          → KPI 汇总（支持 view_id 参数）
/api/dashboard/trend/{metric}   → 趋势数据
/api/dashboard/drilldown/{metric} → 下钻明细
/api/dashboard/views            → 视图 CRUD
/api/dashboard/views/{id}       → 单个视图
/api/dashboard/views/{id}/default → 设为默认
/api/dashboard/presets         → 预置视图模板
/api/dashboard/edit             → 字段编辑
/api/dashboard/edit-history     → 编辑历史
/api/dashboard/undo             → 撤销
/api/dashboard/refresh          → 刷新快照
/api/dashboard/data-sources     → 数据源注册（预留）
```

---

## 8. 数据模型

### 7.1 db_view_config（视图配置表）

```sql
CREATE TABLE IF NOT EXISTS db_view_config (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    view_id     TEXT UNIQUE NOT NULL,           -- 视图唯一标识
    view_name   TEXT NOT NULL,                  -- 视图名称
    user_id     TEXT,                           -- 创建人（NULL = 系统预置）
    is_default  INTEGER DEFAULT 0,              -- 是否为该用户默认视图
    is_system   INTEGER DEFAULT 0,              -- 系统预置视图（不可删除）
    layout      TEXT NOT NULL DEFAULT '{}',     -- 布局 JSON（KPI 位置 + 图表配置）
    filters     TEXT DEFAULT '{}',              -- 默认筛选条件
    chart_types TEXT DEFAULT '{}',              -- 图表类型配置
    created_at  TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT DEFAULT (datetime('now', 'localtime')),
    deleted_at  TEXT DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS idx_db_view_user ON db_view_config(user_id);
CREATE INDEX IF NOT EXISTS idx_db_view_default ON db_view_config(user_id, is_default);
```

### 7.2 db_edit_history（编辑历史表）

```sql
CREATE TABLE IF NOT EXISTS db_edit_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id   INTEGER NOT NULL,
    table_name  TEXT NOT NULL,
    field       TEXT NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    operator    TEXT NOT NULL,
    is_undo     INTEGER DEFAULT 0,              -- 是否为撤销操作
    batch_id    TEXT,                           -- 批量编辑批次号
    created_at  TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_db_edit_record ON db_edit_history(record_id, table_name);
```

### 7.3 dashboard_data_source（数据源注册表 — 预留）

```sql
CREATE TABLE IF NOT EXISTS dashboard_data_source (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key    TEXT UNIQUE NOT NULL,
    module        TEXT NOT NULL,
    title         TEXT NOT NULL,
    description   TEXT,
    category      TEXT NOT NULL,                -- kpi / chart / table
    aggregate_sql TEXT NOT NULL,
    refresh_mode  TEXT DEFAULT 'realtime',      -- realtime / daily / manual
    enabled       INTEGER DEFAULT 1,
    created_at    TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at    TEXT DEFAULT (datetime('now', 'localtime'))
);
```

### 7.4 dash_user_config（用户配置表）

```sql
CREATE TABLE IF NOT EXISTS dash_user_config (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT UNIQUE NOT NULL,
    default_view_id TEXT,                       -- 默认视图 ID
    theme           TEXT DEFAULT 'light',       -- light / dark
    page_size       INTEGER DEFAULT 50,
    updated_at      TEXT DEFAULT (datetime('now', 'localtime'))
);
```

---

## 9. 默认驾驶舱布局

### 8.1 布局结构

默认驾驶舱按 5 区域布局，数据源 = 交付月报 + 确收分析月报统计汇总：

```
┌─────────────────────────────────────────────────────────────────┐
│  Header：标题 | 月份选择器 | 视图切换 | 刷新 | 配置视图          │
├─────────────────────────────────────────────────────────────────┤
│                    顶部 KPI 区（12 个指标卡）                      │
│  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐              │
│  │合同数│ │合同额│ │在建 │ │交付数│ │及时率│ │验收数│              │
│  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘              │
│  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐              │
│  │确收额│ │确收率│ │成本 │ │工单数│ │风险数│ │毛利率│              │
│  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘              │
├─────────────────────────────────────────────────────────────────┤
│ 交付月报区（左）              │ 确收分析区（右）                  │
│ ┌─────────────────────────┐ │ ┌─────────────────────────┐      │
│ │ 签约数 / 交付项目数       │ │ │ 确收金额 / 确收率         │      │
│ │ 交付及时率 / 异常项目数   │ │ │ 预算完成率 / 差异分析     │      │
│ │ [柱状图: 月度交付趋势]    │ │ │ [折线图: 确收趋势]        │      │
│ └─────────────────────────┘ │ └─────────────────────────┘      │
├─────────────────────────────────────────────────────────────────┤
│ 项目利润区（左）              │ 风险区（右）                      │
│ ┌─────────────────────────┐ │ ┌─────────────────────────┐      │
│ │ 收入 / 成本 / 利润        │ │ │ 风险项目数                │      │
│ │ [饼图: 成本构成]          │ │ │ 异常处置状态              │      │
│ │ 毛利率                    │ │ │ [表格: TOP10 风险项目]    │      │
│ └─────────────────────────┘ │ └─────────────────────────┘      │
├─────────────────────────────────────────────────────────────────┤
│ 明细列表区（可折叠）                                              │
│ [下钻明细表格：支持筛选/排序/分页/编辑]                           │
└─────────────────────────────────────────────────────────────────┘
```

### 8.2 5 区域数据源映射

| 区域 | 数据项 | 来源 | 聚合方式 |
|---|---|---|---|
| 顶部 KPI | 12 个核心指标 | 各模块实时数据 | COUNT/SUM/AVG |
| 交付月报区 | 签约数/交付数/及时率/异常数 | delivery_report 统计 Sheet（Sheet 6-14） | 月报生成后落盘 |
| 确收分析区 | 确收金额/确收率/预算完成/差异 | revenue 汇总 Sheet（Sheet 3） | 月报生成后落盘 |
| 项目利润区 | 收入/成本/利润/毛利率 | profit_management 实时聚合 | SUM/AVG |
| 风险区 | 风险项目数/处置状态 | project_management 实时聚合 | COUNT/GROUP BY |

---

## 10. KPI 卡片设计

### 9.1 12 个核心指标

| # | KPI | 数据源表 | 计算 SQL | 刷新频率 | 颜色阈值 |
|---|---|---|---|---|---|
| 1 | 合同数量 | cr_contracts | COUNT(*) | 实时 | — |
| 2 | 合同金额 | cr_contracts | SUM(amount) | 实时 | — |
| 3 | 在建项目数 | pm_projects | COUNT(status='executing') | 实时 | — |
| 4 | 交付项目数 | dr_sheet_row | COUNT(DISTINCT contract_no) | 月报后 | — |
| 5 | 交付及时率 | dr 统计 Sheet | is_timely / total | 月报后 | <80% 红 / <90% 橙 / ≥90% 绿 |
| 6 | 验收项目数 | pm_projects | COUNT(acceptance_month=current) | 实时 | — |
| 7 | 确收金额 | rr_sheet_row | SUM(actual_amount) | 月报后 | — |
| 8 | 确收率 | rr 汇总 Sheet | SUM(actual) / SUM(plan) | 月报后 | <80% 红 / <90% 橙 / ≥90% 绿 |
| 9 | 售后工单数 | pm_after_sales | COUNT(*) | 实时 | >10 红 / >5 橙 / ≤5 绿 |
| 10 | 项目成本 | pf_cost_item | SUM(cost) | 实时 | — |
| 11 | 风险项目数 | pm_risk_record | COUNT(status='open') | 实时 | >5 红 / >2 橙 / ≤2 绿 |
| 12 | 毛利率 | pf_profit_snapshot | (revenue-cost)/revenue | 实时 | <10% 红 / <20% 橙 / ≥20% 绿 |

---

## 11. 图表类型设计

> 5 种类型：指标卡 / 柱状图 / 折线图 / 饼图 / 表格

## 12. 下钻功能设计

> 三级下钻：部门 → 项目 → 单条记录 + 路径回溯

## 13. 明细编辑设计

新增超级管理员权限：

| 角色 | 可编辑字段 | 数据范围 |
|---|---|---|
| 项目经理 | 备注、状态 | 自己负责的项目 |
| PMO | 备注、状态、金额（±10%内） | 全部项目 |
| 管理员 | 全部字段 | 全部项目 |
| **超级管理员** | **全部字段 + 系统级** | **全部** |

## 14. 视图管理设计（多看板/多驾驶舱）

新增能力：

| 功能 | 说明 |
|---|---|
| 多驾驶舱 | 可创建多个全局视图（不止默认一个） |
| 多看板 | 可创建多个专题视图 |
| 默认看板设置 | 任意视图可设为默认（首次访问自动加载） |
| 预置模板 | 5 种预置视图（默认/管理/交付/确收/利润） |
| 数据源注册 | 新模块数据源即插即用（预留） |

## 15. 前端实现方案

> 详细设计见旧版（archive/DESIGN-DETAIL-DASHBOARD-v2.1.md §11），要点：
- Jinja2 模板 + 原生 JS + Chart.js（无 React/Vue）
- CSS Grid 布局 + HTML5 draggable 拖拽
- fetch API 调用 /api/dashboard/*
- 响应式布局（桌面/移动端）

## 16. 错误处理

> 详细设计见旧版 §12，要点：
| 错误码 | 说明 |
|---|---|
| DB-4001 | 视图不存在 |
| DB-4002 | 视图配置非法（JSON 解析失败） |
| DB-4003 | 无编辑权限 |
| DB-4004 | 字段不可编辑 |
| DB-5001 | KPI 计算异常（除零等） |
| DB-5002 | 数据源 SQL 执行失败 |

## 17. CLI 命令 + Web API

> 详细设计见旧版 §13，要点：

CLI：`bdms dashboard summary / trend / drilldown / views / set-default`
Web API：15 个路由（summary/trend/drilldown/views CRUD/edit/undo/refresh/data-sources）

## 18. 测试策略

> 详细设计见旧版 §14，要点：
| 层 | 工具 | 覆盖 |
|---|---|---|
| 单元 | pytest | KPI 计算 / 视图 CRUD / 权限检查 |
| 集成 | pytest + 临时 DB | 下钻三级 / 编辑留痕 / 数据源注册 |
| E2E | 真实 HTTP | 登录→Cookie→看板操作（禁 TestClient） |
| 性能 | 计时断言 | KPI 汇总 <3s / 下钻 <2s |

## 附录 B：复用资产清单与使用方式

> **原则**：所有复用资产通过 **import 引用 / 继承 / 组合** 方式使用，**禁止复制粘贴**。

| 资产 | 来源文件 | 使用方式 | 重构操作 | 本模块调用代码 |
|---|---|---|---|---|
| `DashboardEngine` | `modules/dashboard/engine.py` | **import 引用** | 无（直接调用） | `from bdms.modules.dashboard.engine import DashboardEngine` |
| `DashboardService` | `modules/dashboard/service.py` | **import 引用** | 无（直接调用） | `from bdms.modules.dashboard.service import DashboardService` |
| `DashboardCustomizationService` | `modules/dashboard/service.py` | **import 引用** | 无（直接调用） | `from bdms.modules.dashboard.service import DashboardCustomizationService` |
| `dr_sheet_row` | `core/schemas_v21.py` | **DB 共享** | 只读 | `SELECT data FROM dr_sheet_row WHERE month=? AND sheet=?` |
| `rr_sheet_row` | `core/schemas_v21.py` | **DB 共享** | 只读 | `SELECT data FROM rr_sheet_row WHERE month=?` |
| `cr_contracts` | `core/schemas_v21.py` | **DB 共享** | 只读 | `SELECT COUNT(*), SUM(amount) FROM cr_contracts` |
| `pm_projects` | `core/schemas_v21.py` | **DB 共享** | 只读 | `SELECT COUNT(*) FROM pm_projects WHERE status='executing'` |
| `pm_risk_record` | `core/schemas_v21.py` | **DB 共享** | 只读 | `SELECT COUNT(*) FROM pm_risk_record WHERE status='open'` |
| `pf_profit_snapshot` | `core/schemas_v21.py` | **DB 共享** | 只读 | `SELECT revenue, cost FROM pf_profit_snapshot WHERE period=?` |
| `Chart.js` | `web/static/js/chart.umd.min.js` | **前端引用** | 无（CDN/本地静态文件） | `<script src="/static/js/chart.umd.min.js">` |
| `Jinja2 模板` | `web/templates/` | **模板继承** | base.html 继承 | `{% extends "base.html" %}` |

**重构检查清单**：
- [ ] 所有 import 路径指向源文件（非副本）
- [ ] 数据聚合通过 SQL 查询（非内存计算）
- [ ] 统计汇总复用 DashboardService（非重复实现）
- [ ] 前端通过 Chart.js API 渲染（非重复造轮子）
- [ ] 无复制粘贴代码块

---

## 审核记录与变更历史

### 审核

| 轮次 | 日期 | 审核人 | 结论 | 意见 |
|---|---|---|---|---|
| 1 | 2026-09-22 | Rex | ⏳ 待审 | — |

### 变更历史

| 版本 | 日期 | 变更 |
|---|---|---|
| v2.1 r3 | 2026-09-22 | Rex 审核反馈：<br>⑦ 数据源注册增加辅助操作（SQL 编写提示 + 语法校验 + 语义校验 + 说明生成 + 试运行 + 字段映射 + 性能评估） |
| v2.1 r2 | 2026-09-22 | Rex 审核反馈 3 条修改：<br>① 扩展数据覆盖范围（全系统 + 预留新业务数据接口）<br>② 明确业务核心（默认=交付月报+确收分析汇总；支持多看板/多驾驶舱配置）<br>③ 深化业界最佳实践参考（ONES/Grafana/Tableau/Power BI/Metabase/DataV/Kibana）<br>④ 新增 dashboard_data_source 注册表（新模块即插即用）<br>⑤ 新增 DashboardDataSourceService（预留）<br>⑥ 新增超级管理员角色 |
| v2.1 | 2026-09-22 | 初版 |
