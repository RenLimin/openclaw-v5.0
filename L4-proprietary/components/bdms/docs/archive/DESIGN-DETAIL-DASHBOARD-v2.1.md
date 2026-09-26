# BDMS v2.1 Dashboard 模块详细设计

> 版本：v2.1 Detail（2026-09-19）
> 层级：L4 专有业务层 — 横切模块
> 继承：L3 `delivery-management-framework`（整体框架）
> 状态：设计阶段，待 Rex 审核

---

## 1. 模块概述

Dashboard 是 BDMS v2.1 的数据聚合与可视化入口，横跨全部业务模块，提供总览指标、趋势分析、下钻穿透和对比分析能力。

**核心定位**：只读聚合层 — 不持有业务数据，不写入业务表，所有数据来自各业务模块的 DB 视图/快照，聚合计算在本模块内完成。

**L3 域归属**：横切（cross-cutting）

**服务的业务阶段**：全阶段（立项 → 实施 → 交付 → 验收 → 确收 → 售后 → 结项 → 风控 → 成本）

---

## 2. 技术方案

### 2.1 技术选型

| 维度 | 选型 | 依据 |
|---|---|---|
| 语言 | Python 3.10+ | 与 BDMS 全栈一致 |
| Web 渲染 | Jinja2 + ECharts（现有前端模板） | 沿用 v1.0 dashboard.html，增量扩展 |
| 数据聚合 | 纯 Python 函数 + pandas 辅助计算 | 轻量、可测试、不引入额外依赖 |
| 缓存机制 | SQLite `dash_snapshot` 表 + TTL | 避免每次看板请求都全表扫描 |
| 下钻实现 | URL 参数驱动的模块路由 | 与 Web 层路由解耦 |
| 自定义配置 | SQLite `dash_user_config` 表 | 用户级看板布局持久化 |

### 2.2 依赖的 L2/L3/L4 资产

| 资产 | 层级 | 复用方式 |
|---|---|---|
| L2 Persistence-006 | L2 | SQLite + Repository 模式（通过 bdms.core.db） |
| L3 DMS Framework | L3 | 事件总线（数据变更时触发缓存失效） |
| bdms.core.db | L4 Core | 统一 DB 连接与事务管理 |
| bdms.core.schemas | L4 Core | DASHBOARD_SCHEMA（指标定义） |
| contract_management 模块 | L4 Module | 合同指标数据源（只读） |
| project_management 模块 | L4 Module | 项目/交付/验收/成本/风险指标数据源（只读） |
| delivery_report 子引擎 | L4 Sub-engine | 交付月报指标数据源（只读） |
| revenue 子引擎 | L4 Sub-engine | 确收金额指标数据源（只读） |
| after_sales 模块 | L4 Module | 售后工单指标数据源（只读） |

### 2.3 与现有代码的复用/重构关系

现有 `modules/dashboard/` 包含：
- `service.py` — DashboardService（summary / trend / drill_down / compare 四接口）
- `web/routes.py` — Web 路由
- `templates/dashboard.html` — ECharts 看板页面

v2.1 变更：
1. **数据源扩展**：从 v1.0 的 4 个指标扩展为 12 个核心指标（覆盖 16 个流程阶段）
2. **快照机制优化**：`dash_snapshot` 表增加 `snapshot_type` 和 `metric_key` 字段
3. **下钻穿透增强**：从"指标 → 列表"扩展为"指标 → 模块明细 → 单条记录"三级下钻
4. **对比分析增强**：新增环比（MoM）/ 同比（YoY）/ 基线对比三种模式
5. **自定义看板**：新增用户级配置，支持自定义数据集合和展示方式

---

## 3. 接口契约

### 3.1 DashboardService（看板服务）

```python
class DashboardService:
    """看板数据聚合服务 — 纯只读，无副作用"""

    # ---------- 总览 ----------
    def summary(self, month: str = None, range_months: int = 12,
                user_id: str = None) -> dict:
        """
        获取指定月份的总览指标卡 + 趋势概览
        支持用户自定义：如果 user_id 有自定义配置，按配置返回
        返回：{
            "month": "2026-08",
            "kpis": [
                {"key": "contract_count", "label": "合同数量", "value": 42,
                 "mom": 0.08, "yoy": 0.15, "trend": "up"},
                ...
            ],
            "trend_preview": {...},
            "alerts": [...]
        }
        """

    # ---------- 趋势 ----------
    def trend(self, metric_key: str, range_months: int = 12,
              granularity: str = "month") -> list[dict]:
        """获取单个指标的时间序列趋势"""

    # ---------- 下钻 ----------
    def drill_down(self, metric_key: str, month: str,
                   level: int = 1, filters: dict = None) -> dict:
        """指标下钻穿透（level=1 维度分组 / level=2 明细 / level=3 单条详情）"""

    # ---------- 对比 ----------
    def compare(self, metric_key: str, baseline_month: str,
                compare_month: str = None, mode: str = "mom") -> dict:
        """指标对比分析（mom / yoy / custom）"""

    # ---------- 缓存管理 ----------
    def refresh_snapshot(self, metric_key: str = None) -> int:
        """刷新指标快照"""

    def invalidate_cache(self, source_module: str, event_type: str) -> None:
        """事件驱动的缓存失效"""
```

### 3.2 DashboardCustomizationService（自定义看板服务）

```python
class DashboardCustomizationService:
    """
    自定义看板服务：用户自行配置看板显示的数据集合和展示方式。
    
    参考 ONES 自定义看板能力：
    - 用户可选择要展示的 KPI 卡片（从 12 个核心指标中自选）
    - 用户可选择图表类型（柱状图 / 折线图 / 饼图 / 表格）
    - 用户可拖拽调整布局（卡片位置 / 大小）
    - 用户可保存多个视图（如"管理视图" / "财务视图" / "交付视图"）
    """

    # ---------- 视图管理 ----------
    def create_view(self, user_id: str, view_name: str,
                    config: dict) -> str:
        """
        创建自定义视图。
        
        config 格式：
        {
            "widgets": [
                {
                    "id": "widget_001",
                    "type": "kpi_card",           # kpi_card / chart / table
                    "metric_key": "contract_count",
                    "title": "合同数量",
                    "chart_type": "card",          # card / bar / line / pie
                    "position": {"x": 0, "y": 0, "w": 2, "h": 1},
                    "filters": {"range_months": 12}
                },
                {
                    "id": "widget_002",
                    "type": "chart",
                    "metric_key": "delivery_amount",
                    "title": "交付金额趋势",
                    "chart_type": "line",           # bar / line / pie
                    "position": {"x": 2, "y": 0, "w": 4, "h": 2},
                    "filters": {"range_months": 6, "granularity": "month"}
                }
            ]
        }
        
        返回 view_id
        """
        ...

    def update_view(self, view_id: str, config: dict) -> None:
        """更新视图配置"""

    def delete_view(self, view_id: str) -> None:
        """删除视图"""

    def get_view(self, view_id: str) -> dict:
        """获取视图配置"""

    def list_views(self, user_id: str) -> list[dict]:
        """列出用户的所有视图"""

    def set_default_view(self, user_id: str, view_id: str) -> None:
        """设置默认视图"""

    def get_default_view(self, user_id: str) -> dict:
        """获取用户默认视图"""

    # ---------- 可用指标/图表清单 ----------
    def list_available_metrics(self) -> list[dict]:
        """
        返回所有可用指标：
        [
            {"key": "contract_count", "label": "合同数量", "unit": "个",
             "chart_types": ["card", "bar", "line"], "category": "合同"},
            ...
        ]
        """
        ...

    def list_available_chart_types(self) -> list[dict]:
        """
        返回所有可用图表类型：
        [
            {"type": "card", "label": "指标卡", "description": "单值 + 环比"},
            {"type": "bar", "label": "柱状图", "description": "分类对比"},
            {"type": "line", "label": "折线图", "description": "时间趋势"},
            {"type": "pie", "label": "饼图", "description": "占比分布"},
            {"type": "table", "label": "表格", "description": "明细列表"},
        ]
        """
        ...
```

### 3.3 SnapshotRepository（快照仓储）

```python
class SnapshotRepository:
    """指标快照持久化 — 避免每次看板请求都做全表聚合"""

    def save(self, metric_key: str, period: str, value: float,
             dimension: str = None, dimension_value: str = None) -> None:
        """写入/更新单条快照记录"""

    def batch_save(self, records: list[dict]) -> int:
        """批量写入，幂等（metric_key + period + dimension 唯一）"""

    def get_latest(self, metric_key: str, period: str = None) -> dict | None:
        """获取最新快照"""

    def get_range(self, metric_key: str, start_period: str,
                  end_period: str) -> list[dict]:
        """获取时间范围内的快照序列"""

    def stale_since(self, metric_key: str) -> datetime | None:
        """返回快照最后更新时间，用于判断是否需要刷新"""
```

### 3.4 指标字典（12 个核心 KPI）

| metric_key | 标签 | 单位 | 数据源模块 | 下钻维度 |
|---|---|---|---|---|
| `contract_count` | 合同数量 | 个 | contract_management | 部门 / 产品线 / 销售 |
| `contract_amount` | 合同金额 | 元 | contract_management | 部门 / 产品线 / 客户类型 |
| `project_count` | 在建项目数 | 个 | project_management | 部门 / 类型 / 阶段 |
| `delivery_count` | 交付项目数 | 个 | delivery_report | 部门 / 产品线 / 区域 |
| `delivery_rate` | 交付及时率 | % | delivery_report | 部门 / 项目经理 |
| `acceptance_count` | 验收项目数 | 个 | project_management | 部门 / 类型 |
| `revenue_amount` | 确收金额 | 元 | revenue 子引擎 | 部门 / 产品线 / 区域 |
| `revenue_recognition_rate` | 确收率 | % | revenue 子引擎 | 部门 / 产品线 |
| `after_sales_ticket_count` | 售后工单数 | 个 | after_sales | 产品 / 严重级别 / SLA 状态 |
| `cost_amount` | 项目成本 | 元 | cost 子引擎 | 部门 / 项目类型 |
| `risk_count` | 风险项目数 | 个 | risk 子引擎 | 风险等级 / 部门 |
| `profit_margin` | 毛利率 | % | cost + revenue | 部门 / 产品线 |

### 3.5 Web 路由契约

| 路由 | 方法 | 说明 |
|---|---|---|
| `/dashboard` | GET | 看板主页面 |
| `/api/dashboard/summary?month=2026-08` | GET | 总览指标 JSON |
| `/api/dashboard/trend/{metric_key}?range=12` | GET | 趋势数据 JSON |
| `/api/dashboard/drill/{metric_key}/{month}` | GET | 下钻数据 JSON |
| `/api/dashboard/compare/{metric_key}` | GET | 对比数据 JSON |
| `/api/dashboard/refresh` | POST | 手动刷新缓存（需鉴权） |
| **自定义看板路由** | | |
| `/api/dashboard/views` | GET | 列出用户视图 |
| `/api/dashboard/views` | POST | 创建视图 |
| `/api/dashboard/views/{view_id}` | GET | 获取视图配置 |
| `/api/dashboard/views/{view_id}` | PUT | 更新视图配置 |
| `/api/dashboard/views/{view_id}` | DELETE | 删除视图 |
| `/api/dashboard/views/{view_id}/default` | POST | 设为默认视图 |
| `/api/dashboard/metrics` | GET | 可用指标清单 |
| `/api/dashboard/chart-types` | GET | 可用图表类型清单 |

---

## 4. 数据模型

### 4.1 新增表

dashboard 模块新增 2 张表：

| 表名 | 用途 | 关键字段 |
|---|---|---|
| `dash_snapshot` | 指标快照缓存 | id, metric_key, period, dimension, dim_value, value, updated_at |
| `dash_user_config` | 用户自定义看板配置 | id, user_id, view_id, view_name, config, is_default, updated_at |

### 4.2 dash_snapshot 表结构

```sql
CREATE TABLE dash_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_key TEXT NOT NULL,
    period TEXT NOT NULL,
    dimension TEXT DEFAULT 'total',
    dim_value TEXT DEFAULT 'all',
    value REAL NOT NULL,
    source_module TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    UNIQUE(metric_key, period, dimension, dim_value)
);

CREATE INDEX idx_dash_snapshot_lookup
    ON dash_snapshot(metric_key, period, dimension);
```

### 4.3 dash_user_config 表结构

```sql
CREATE TABLE dash_user_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    view_id TEXT NOT NULL UNIQUE,
    view_name TEXT NOT NULL,
    config TEXT NOT NULL,              -- JSON：widgets 布局配置
    is_default INTEGER DEFAULT 0,     -- 0 / 1
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX idx_dash_user_config_user
    ON dash_user_config(user_id);
```

### 4.4 数据来源映射

每个指标从对应模块的表中聚合：

| metric_key | 源表 | 聚合方式 |
|---|---|---|
| contract_count | `cr_contracts` | COUNT(*) WHERE sign_month = period |
| contract_amount | `cr_contracts` | SUM(amount) WHERE sign_month = period |
| project_count | `pm_projects` | COUNT(*) WHERE status IN ('executing','delivering') |
| delivery_count | `dr_delivery_item` | COUNT(*) WHERE delivery_month = period |
| delivery_rate | `dr_delivery_item` | is_timely_count / total_count |
| acceptance_count | `pm_projects` | COUNT(*) WHERE acceptance_month = period |
| revenue_amount | `rr_sheet_row` | SUM(amount) WHERE period = period |
| after_sales_ticket_count | `as_tickets` | COUNT(*) WHERE create_month = period |
| cost_amount | `ct_timesheet` | SUM(hours * rate) WHERE month = period |
| risk_count | `rk_risks` | COUNT(*) WHERE status = 'open' |

---

## 5. 核心流程

### 5.1 总览指标加载流程

```
用户请求 /dashboard
    │
    ▼
DashboardService.summary(month, user_id)
    │
    ├─► 检查用户是否有自定义视图（dash_user_config）
    │       │
    │       ├─ 有 ─► 按用户配置返回自选指标
    │       └─ 无 ─► 返回默认 12 个核心 KPI
    │
    ├─► 检查 dash_snapshot 缓存是否新鲜
    │       │
    │       ├─ 命中 ─► 直接返回缓存数据
    │       └─ 未命中 ─► 继续
    │
    ├─► 并行查询各指标（线程池，各模块独立查询）
    │
    ├─► 计算 MoM / YoY（查上月/去年同月快照）
    │
    ├─► 写入 dash_snapshot（异步，不阻塞响应）
    │
    └─► 返回组装好的 KPI 列表 + 告警
```

**性能目标**：首次加载 < 3s（12 指标并行查询），缓存命中 < 200ms。

### 5.2 下钻穿透流程

```
用户点击 KPI 卡片
    │
    ▼
drill_down(metric_key, month, level=1)
    │
    ├─ level=1: 按维度分组（SQL GROUP BY）
    │
    └─ 用户点击某维度 ─► level=2: 明细列表
            │
            └─ 用户点击某行 ─► level=3: 委托对应模块 get_detail()
```

### 5.3 缓存刷新机制

| 触发方式 | 时机 | 刷新范围 |
|---|---|---|
| 定时刷新 | 每小时整点 | 全部指标 |
| 事件驱动 | 订阅 L3 事件总线 | 相关指标增量刷新 |
| 手动刷新 | 用户点击 | 全部指标 |

**事件订阅清单**：

| 事件 | 触发模块 | 失效指标 |
|---|---|---|
| contract.created / updated | contract_management | contract_count, contract_amount |
| project.created / updated | project_management | project_count, acceptance_count |
| delivery.completed | delivery_report | delivery_count, delivery_rate |
| revenue.recognized | revenue | revenue_amount, revenue_recognition_rate |
| ticket.created / resolved | after_sales | after_sales_ticket_count |
| cost.recorded | cost | cost_amount, profit_margin |
| risk.opened / closed | risk | risk_count |

### 5.4 自定义看板流程

```
用户进入看板配置模式
    │
    ▼
DashboardCustomizationService.list_available_metrics()
    │ 返回 12 个可用指标 + 支持的图表类型
    │
    ▼
用户拖拽添加 widget → 选择指标 + 图表类型 + 位置
    │
    ▼
DashboardCustomizationService.create_view(user_id, view_name, config)
    │ 保存到 dash_user_config 表
    │
    ▼
用户下次访问 /dashboard → 自动加载自定义视图
```

---

## 6. 前端实现

### 6.1 页面布局

```
┌─────────────────────────────────────────────────────────────────┐
│  月份选择器: [2026-08 ▼]    范围: [近12月 ▼]    [🔄 刷新]       │
│  [⚙️ 配置] [📊 管理视图 ▼]                                      │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐        │
│  │合同数 │ │合同金│ │项目数│ │交付数│ │确收金│ │毛利率│        │
│  │  42  │ │540万 │ │  38  │ │  15  │ │320万 │ │ 28% │        │
│  │ ↑8%  │ │↑12%  │ │↓3%   │ │↑15%  │ │↑9%   │ │↑2%  │        │
│  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘        │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐        │
│  │交付及│ │验收数│ │确收率│ │工单数│ │成本金│ │风险数│        │
│  │  92%  │ │  12  │ │ 68%  │ │  23  │ │380万 │ │  5  │        │
│  │ ↑2%  │ │↑20%  │ │↑5%   │ │↓10%  │ │↑7%   │ │↓3   │        │
│  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘        │
├─────────────────────────────────────────────────────────────────┤
│  趋势图（折线/柱状切换）                                        │
│  [合同金额] [交付数] [确收金额] [成本]    近12个月              │
│  ~ 图表区域 ~                                                   │
├─────────────────────────────────────────────────────────────────┤
│  对比分析                                                       │
│  环比 [2026-07 vs 2026-08]   同比 [2025-08 vs 2026-08]        │
│  ~ 瀑布图 / 堆叠柱 ~                                            │
├─────────────────────────────────────────────────────────────────┤
│  异常告警（来自 risk 子引擎，按严重程度排序）                    │
│  🔴 P0: 某项目逾期超 30 天                                        │
│  🟡 P1: 3 个项目毛利率低于 10%                                    │
│  🟢 P2: 5 张工单接近 SLA 截止                                     │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 自定义看板配置界面

```
┌─────────────────────────────────────────────────────────────────┐
│  ⚙️ 配置看板                                      [保存] [取消]  │
├───────────────────────┬─────────────────────────────────────────┤
│  可用指标              │  画布区域                                │
│  ───────────────────  │  ┌──────┐ ┌──────┐ ┌──────────────┐    │
│  ☑ 合同数量            │  │合同数 │ │合同金│ │  交付金额趋势  │    │
│  ☑ 合同金额            │  │  42  │ │540万 │ │  ╱╲╱╲╱╲╱╲   │    │
│  ☑ 在建项目数          │  └──────┘ └──────┘ └──────────────┘    │
│  ☑ 交付项目数          │  ┌──────────────┐ ┌──────┐              │
│  ☑ 交付及时率          │  │ 确收金额趋势  │ │毛利率│              │
│  ☑ 验收项目数          │  │  ╱╲╱╲╱╲╱╲   │ │ 28% │              │
│  ☑ 确收金额            │  └──────────────┘ └──────┘              │
│  ☑ 确收率              │                                         │
│  ☑ 售后工单数          │                                         │
│  ☑ 项目成本            │                                         │
│  ☑ 风险项目数          │                                         │
│  ☑ 毛利率              │                                         │
│                       │                                         │
│  图表类型              │                                         │
│  ───────────────────  │                                         │
│  ● 指标卡 (card)       │                                         │
│  ○ 柱状图 (bar)        │                                         │
│  ○ 折线图 (line)       │                                         │
│  ○ 饼图 (pie)          │                                         │
│  ○ 表格 (table)        │                                         │
│                       │                                         │
│  预设视图              │                                         │
│  ───────────────────  │                                         │
│  + 管理视图（默认全部）│                                         │
│  + 财务视图（收入/成本）│                                         │
│  + 交付视图（交付/验收）│                                         │
│  + 售后视图（工单/SLA）│                                         │
└───────┘

### 6.3 交互设计

| 交互 | 行为 |
|---|---|
| 点击 KPI 卡片 | 弹出下钻面板（level=1 维度分组） |
| 点击维度分组项 | 展开明细列表（level=2） |
| 点击明细行 | 跳转对应模块详情页（level=3） |
| 悬停趋势图数据点 | 显示 tooltip + 环比标记 |
| 切换月份 | 全页面数据刷新（优先读缓存） |
| 点击刷新按钮 | 强制刷新所有指标缓存 |
| 点击配置按钮 | 进入自定义模式 |
| 拖拽 widget | 调整位置和大小 |
| 切换预设视图 | 加载对应预设配置 |

---

## 7. CLI 接口

```bash
# 总览
bdms dashboard summary 2026-08

# 趋势
bdms dashboard trend contract_amount --range 12
bdms dashboard trend revenue_amount --range 24 --granularity quarter

# 下钻
bdms dashboard drill contract_amount 2026-08 --level 1 --dimension department

# 对比
bdms dashboard compare revenue_amount 2026-07 2026-08
bdms dashboard compare profit_margin --mode yoy --baseline 2025-08

# 缓存管理
bdms dashboard refresh              # 刷新全部指标缓存
bdms dashboard refresh --metric contract_amount  # 刷新单个指标
bdms dashboard cache status         # 查看缓存新鲜度

# 自定义视图
bdms dashboard views list                          # 列出用户视图
bdms dashboard views create --name "财务视图" --config view.json
bdms dashboard views show <view_id>
bdms dashboard views update <view_id> --config view.json
bdms dashboard views delete <view_id>
bdms dashboard views set-default <view_id>

# 可用配置
bdms dashboard metrics                             # 可用指标清单
bdms dashboard chart-types                         # 可用图表类型
```

---

## 8. 非功能设计

### 8.1 性能

| 场景 | 目标 | 手段 |
|---|---|---|---|
| 首次加载（冷缓存） | < 3s | 12 指标并行查询 + SQLite 索引 |
| 缓存命中 | < 200ms | dash_snapshot 表直接读 |
| 单指标刷新 | < 500ms | 增量计算，只算变更数据 |
| 全量刷新 | < 10s | 多线程 + 批量写入 |
| 自定义视图加载 | < 500ms | dash_user_config 表 + JSON 解析 |

### 8.2 可靠性

- **快照 TTL 兜底**：即使上游模块数据变更事件丢失，最多 1 小时自动刷新
- **降级策略**：某模块查询失败时，该指标显示"--"并标记告警，不影响其他指标展示
- **历史数据不变性**：已关账月份的快照只读，不被后续刷新覆盖
- **自定义配置校验**：保存时校验 config JSON 合法性，拒绝无效配置

### 8.3 安全

- dashboard 本身只读，无写操作
- 下钻到明细页时走各模块自己的权限控制
- 手动刷新接口需 admin 权限
- 用户只能查看/修改自己的自定义视图（user_id 隔离）

---

## 9. 业界最佳实践对比与优化

### 9.1 对标标准

| 业界实践 | 核心思想 | BDMS 当前做法 | 差距 | 优化建议 |
|---|---|---|---|---|
| **ONES 自定义看板** | 用户自选指标 + 拖拽布局 + 多视图 | 固定 12 个指标 + 单一视图 | 缺自定义 | 已实现（§3.2 + §5.4 + §6.2） |
| **Grafana** | 数据源插件 + 面板模板 + 告警 | ECharts 固定图表 | 缺面板模板库 | 增加预设面板模板（管理/财务/交付/售后视图） |
| **Tableau** | 拖拽式探索 + 计算字段 | 预定义指标 + 下钻 | 缺即席探索 | 增加即席查询：用户自定义维度和指标组合 |
| **Power BI** | DAX 计算 + 交互式筛选 | SQL 聚合 + 简单过滤 | 缺计算引擎 | 增加计算字段：用户自定义公式（如：利润 = 收入 - 成本） |
| **Metabase** | 自然语言查询 + 可视化 | 预定义查询 | 缺 NL2SQL | 未来可选：LLM 驱动的问答式数据查询（OPTIONAL_TOKEN） |
| **Apache Superset** | 可视化探索 + SQL Lab | ECharts 固定渲染 | 缺 SQL 编辑器 | 高级用户可直接写 SQL 探索 |
| **数据大屏（DataV）** | 全屏展示 + 实时刷新 | 普通 Web 页面 | 缺大屏模式 | 增加全屏大屏模式（适用于会议室/展厅展示） |

### 9.2 建议的优化项

**P0（v2.1 必须做）**：

1. **自定义看板**
   - 问题：固定指标集合，不同角色关注点不同
   - 方案：用户自选指标 + 拖拽布局 + 多视图 + 预设模板
   - 成本：中（前端拖拽 + 后端配置持久化）
   - 收益：高（各角色按需配置，提升使用效率）

2. **预设视图模板**
   - 问题：新用户不知道如何配置
   - 方案：提供管理视图/财务视图/交付视图/售后视图 4 个预设
   - 成本：低（4 个 JSON 配置文件）
   - 收益：中（降低使用门槛）

**P1（v2.2 可做）**：

3. **即席查询**
   - 问题：预定义指标无法满足个性化分析需求
   - 方案：用户自定义维度组合 + 图表类型
   - 成本：中（前端探索界面 + 后端动态 SQL 生成）
   - 收益：中（高级用户自定义分析）

4. **计算字段**
   - 问题：派生指标（如毛利率）需要预计算
   - 方案：用户自定义公式（利润 = 收入 - 成本）
   - 成本：中（公式解析器 + 计算引擎）
   - 收益：中（灵活派生指标）

**P2（远期）**：

5. **全屏大屏模式**
   - 问题：缺会议室/展厅展示模式
   - 方案：全屏 + 自动轮播 + 实时刷新
   - 成本：低（CSS + 定时刷新）
   - 收益：低（非核心场景）

6. **NL2SQL 自然语言查询**
   - 问题：非技术人员难以自定义查询
   - 方案：LLM 驱动的自然语言转 SQL
   - 成本高 | 收益：中（OPTIONAL_TOKEN）

---

## 10. 实施计划

| 阶段 | 内容 | 预估工时 | 依赖 |
|---|---|---|---|
| P1 | dash_snapshot 表 + SnapshotRepository | 0.5d | — |
| P2 | 12 个指标的聚合查询实现（按模块分包） | 2d | 各模块表结构就绪 |
| P3 | DashboardService 四接口 | 1d | P2 完成 |
| P4 | 前端页面扩展（12 KPI + 告警区） | 1d | P3 完成 |
| P5 | 事件总线订阅 + 缓存失效 | 0.5d | L3 事件总线就绪 |
| P6 | CLI 命令实现 | 0.5d | P3 完成 |
| P7 | **自定义看板**（配置界面 + 多视图 + 预设模板） | 2d | P4 完成 |
| P8 | 单测 + 集成测试 | 1d | — |
| **合计** | | **8.5d** | |

### 10.1 与 v1.0 的兼容性

- `dashboard.html` 模板向后兼容
- API 路径不变，新增自定义视图 API 为纯增量
- `db_snapshot` 表（v1.0）迁移到 `dash_snapshot`（v2.1），数据一次性迁移

---

## 11. 功能完整性矩阵

### 11.1 12 个核心 KPI

| # | metric_key | 标签 | 单位 | 数据源 | 状态 |
|---|---|---|---|---|---|
| 1 | contract_count | 合同数量 | 个 | cr_contracts | ✅ |
| 2 | contract_amount | 合同金额 | 元 | cr_contracts | ✅ |
| 3 | project_count | 在建项目数 | 个 | pm_projects | ✅ |
| 4 | delivery_count | 交付项目数 | 个 | dr_sheet_row | ✅ |
| 5 | delivery_rate | 交付及时率 | % | dr_sheet_row | ✅ |
| 6 | acceptance_count | 验收项目数 | 个 | pm_projects | ✅ |
| 7 | revenue_amount | 确收金额 | 元 | rr_sheet_row | ❌ 未实现 |
| 8 | revenue_recognition_rate | 确收率 | % | rr_sheet_row | ❌ 未实现 |
| 9 | after_sales_ticket_count | 售后工单数 | 个 | as_tickets | ❌ 无数据 |
| 10 | cost_amount | 项目成本 | 元 | ct_timesheet | ❌ 未实现 |
| 11 | risk_count | 风险项目数 | 个 | rk_risks | ✅ |
| 12 | profit_margin | 毛利率 | % | cost + revenue | ❌ 未实现 |

### 11.2 自定义看板（8 API + 7 Service 方法）

| # | 功能 | API | 状态 |
|---|---|---|---|
| 1 | 列出用户视图 | GET /api/dashboard/views | ✅ |
| 2 | 创建视图 | POST /api/dashboard/views | ✅ |
| 3 | 获取视图配置 | GET /api/dashboard/views/{view_id} | ✅ |
| 4 | 更新视图配置 | PUT /api/dashboard/views/{view_id} | ✅ |
| 5 | 删除视图 | DELETE /api/dashboard/views/{view_id} | ✅ |
| 6 | 设为默认视图 | POST /api/dashboard/views/{view_id}/default | ✅ |
| 7 | 可用指标清单 | GET /api/dashboard/metrics | ✅ |
| 8 | 可用图表类型 | GET /api/dashboard/chart-types | ✅ |
| 9 | DashboardCustomizationService.create_view() | — | ✅ |
| 10 | DashboardCustomizationService.update_view() | — | ✅ |
| 11 | DashboardCustomizationService.delete_view() | — | ✅ |
| 12 | DashboardCustomizationService.get_view() | — | ✅ |
| 13 | DashboardCustomizationService.list_views() | — | ✅ |
| 14 | DashboardCustomizationService.set_default_view() | — | ✅ |
| 15 | DashboardCustomizationService.get_default_view() | — | ✅ |

### 11.3 缺失功能

| # | 功能 | 影响 | 修复优先级 |
|---|---|---|---|
| 1 | revenue_amount KPI | Dashboard 无法展示确收金额 | 🔴 高 |
| 2 | cost_amount KPI | Dashboard 无法展示成本 | 🔴 高 |
| 3 | profit_margin KPI | Dashboard 无法展示毛利率 | 🔴 高 |
| 4 | revenue/cost 趋势数据 | trend/compare API 无法返回财务数据 | 🔴 高 |

---

## 12. 风险与权衡

| 风险 | 影响 | 缓解措施 |
|---|---|---|---|
| 指标计算口径不一致 | 各模块聚合逻辑差异导致数据打架 | 统一在 schemas 中定义指标口径 + 跨模块对账脚本 |
| 快照延迟导致数据陈旧 | 用户看到的数据不是最新的 | TTL + 事件驱动双保险 + 手动刷新按钮 |
| 下钻跳转链路复杂 | 跨模块跳转容易 404 | 统一路由注册表 + 启动时校验 |
| 12 指标并行查询 DB 压力 | 瞬时连接数飙升 | 连接池上限 + 串行降级策略 |
| 自定义配置膨胀 | 用户创建大量视图占用存储 | 限制每用户最多 10 个视图 |
| 即席查询性能 | 动态 SQL 可能很慢 | 查询超时限制 + 只读权限 |
| 图表渲染性能 | 大数据量图表卡顿 | 数据分页 + 前端虚拟滚动 |