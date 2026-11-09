# DESIGN-OUTLINE — 确收分析报告（Revenue Analysis）v1.0

| 项 | 值 |
|---|---|
| 所属系统 | BDMS（Bangcle 专属概念） |
| 模块 | revenue_analysis（确收分析报告自动生成） |
| 版本 | v1.0（整合稿） |
| 作者 | Jerry |
| 日期 | 2026-11-09 |
| 前置 | PRD-v2.1 §4.2 / DESIGN-OUTLINE-v2.1 §3.4 / DESIGN-DETAIL-REVENUE-v2.1 / DESIGN-DETAIL-REVENUE-FORECAST-v1.0 §11 |
| 状态 | **待 Rex 评审** |

---

## 0. 版本定位

| 维度 | v2.1（既有） | v1.0（本次整合） |
|---|---|---|
| 模块名 | `revenue`（确收分析） | `revenue_analysis`（确收分析报告） |
| 报表 Sheet 数 | 10 | **10（对齐 202606 基线）** |
| 计算列 | 手工填报（AW/BQ/BU/BV） | **自动生成（对齐 202606 公式）** |
| 金额取数 | 宽表 JSON | **按表头名对齐权威列** |
| 双口径 | 无 | **锁定口径 + 动态口径** |
| 自动化 | 导入 + 导出 | **导入 + 计算 + 生成 + 导出 全链路** |
| 黄金基准 | 202606 | **202606（含预算趋势分析 19×17）** |

---

## 1. 设计目标与范围边界

### 1.1 核心目标

**按照手工报表解析后的原始数据、公式计算数据、统计汇总数据，实现确收分析报告的完整自动化生产。**

### 1.2 范围边界

| 在范围内 | 不在范围内 |
|---|---|
| 10 Sheet 报表自动生成（对齐 202606） | ONES 实时数据接入（Part B，后续立项） |
| 预算执行表 + 计划确收底稿 导入 | 交付月报数据（依赖外部） |
| 预算趋势分析 19 行交叉表 | 项目利润计算（独立模块） |
| 双口径（锁定/动态）计算 | OA 写回（独立立项） |
| 计算列自动生成（AW/BQ/BU/BV） | 人工补填工作流（本版仅留空） |
| 导出格式化 Excel | Web UI（后续 Phase） |

### 1.3 铁律约束

- **金额红线**：唯一权威金额为财报已切分列；预算趋势分析按 BQ 状态分别取 O/AG/N/Q，不是统一取 O；禁用推算列，不得硬摊或造假
- **列对齐**：跨年物理列错位必须按**表头名称**对齐，禁止按字母硬套
- **纯计算优先**：engine 纯函数，无副作用；exporter 只做 IO
- **幂等可重入**：同输入多次执行结果一致
- **不破坏基线**：不破坏现有 367 passed

---

## 2. 总体架构

### 2.1 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                      CLI / Web API 层                        │
│   bdms revenue-analysis import 202609 --source ./报表.xlsx    │
│   bdms revenue-analysis generate 202609 --mode auto          │
│   bdms revenue-analysis export 202609 --out report.xlsx      │
├─────────────────────────────────────────────────────────────┤
│                      Service 层                              │
│   RevenueAnalysisService                                     │
│     import_source() → generate() → summary() → export()      │
│     幂等三模式：auto / read / regenerate                      │
├─────────────────────────────────────────────────────────────┤
│                      Engine 层                               │
│   RevenueAnalysisEngine                                      │
│     compute() → 10 Sheet 结构化数据                          │
│     compute_budget_trend() → 19 行交叉表                     │
│     compute_dual_caliber() → 锁定/动态双口径                 │
├─────────────────────────────────────────────────────────────┤
│                      Builder 层                              │
│   stats_builders.py — 7 个统计 Sheet 构建器                  │
│   trend_builder.py — 预算趋势分析构建器                      │
│   caliber_builder.py — 双口径构建器                          │
├─────────────────────────────────────────────────────────────┤
│                      Storage 层                              │
│   ra_sheet_row（宽表）+ ra_sheet_meta（元数据）               │
│   ra_period（账期登记）+ ra_caliber（双口径快照）             │
│   ra_trend_row（预算趋势分析行）                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 模块文件结构

```
modules/revenue_analysis/
├── __init__.py
├── engine.py              # RevenueAnalysisEngine — 核心计算
├── service.py             # RevenueAnalysisService — 幂等编排
├── importer.py            # RevenueAnalysisImporter — xlsx → 宽表
├── validator.py           # RevenueAnalysisValidator — 数据校验
├── exporter.py            # RevenueAnalysisExporter — 宽表 → Excel
├── stats_builders.py      # 7 个统计 Sheet 构建器
├── trend_builder.py       # 预算趋势分析构建器（19 行）
├── caliber_builder.py     # 双口径构建器（锁定/动态）
├── trend_columns.py       # 计算列生成器（AW/BQ/BU/BV）
└── config.py              # 配置常量（列映射/状态枚举/图例）
```

### 2.3 数据流

```
手工 Excel（202609 报表）
   │ import (校验 + 宽表落盘)
   ▼
ra_sheet_row（预算执行表 + 计划确收底稿）
   │ compute (纯函数)
   ▼
10 Sheet 结构化数据
   ├── 预算执行表（原始 + 计算列 AT-AX）
   ├── 计划确收底稿（原始）
   ├── 汇总（31 行）
   ├── 汇总分析（64 行）
   ├── 预算趋势分析（19 行 ← 核心新增）
   ├── 确收差异分析（16 行）
   ├── 重拆履约（9 行）
   ├── 图例（506 行）
   ├── 月度汇总记录（266 行）
   └── 履约汇总记录（126 行）
   │ export (格式化)
   ▼
output/确认收入分析_{period}.xlsx
```

---

## 3. 核心设计

### 3.1 计算列自动生成（AW/BQ/BU/BV）

> 详见 `DESIGN-DETAIL-REVENUE-FORECAST-v1.0.md` §11

| 列 | 202606 公式 | 202609 实现 |
|---|---|---|
| `AT` 合同数量统计唯一值 | `=C{r}&"-"&BQ{r}` | `=B{r}&"-"&AV{r}` |
| `AU` 统计位 | `=IF(COUNTIF(AT$3:AT{r-1},AT{r})>0,"","统计")` | 按 AT 去重首现标"统计" |
| `AV` 预算填报 | `VLOOKUP(J,[3]!$J:$BQ,60,FALSE)` | 匹配 202606 → M/O 日期判断 → 留空 |
| `AW` 预算趋势 | `VLOOKUP(J,[3]!$J:$BU,64,FALSE)` | 匹配 202606 → O 日期判断 → 留空 |
| `AX` 预算趋势类别 | `VLOOKUP(BU,图例!L:M,2,FALSE)` | Python 直查图例映射 |

### 3.2 预算趋势分析（19 行交叉表）

**结构**（对齐 202606）：

| 行 | 内容 |
|---|---|
| R1-R3 | 表头（3 层合并） |
| R4-R9 | 递延合同（6 种状态） |
| R10 | 递延合计 |
| R11 | 新签表头 |
| R12-R16 | 新签合同（5 种状态） |
| R17 | 新签合计 |
| R18 | 递延+新签共计 |
| R19 | 新签预计确收率 |

**列定义**（17 列）：

| 列 | 含义 |
|---|---|
| A | 期间（递延/新签） |
| B | 类型（状态描述） |
| C-D | 期初-合同数量/涉及金额（万） |
| E-F | 本年正常交付-合同数量/涉及金额（万） |
| G-H | 异常中-合同数量/涉及金额（万） |
| I-J | 合同消失-合同数量/涉及金额（万） |
| K-L | 未来交付-合同数量/涉及金额（万） |
| M-N | 校验-数量/金额 |
| O-P | 异常说明-未立项/已立项 |
| Q | （空） |

**金额取数规则**（按 BQ 状态分别取权威列）：

| 报表行 | BQ 状态 | 期初金额列 | 累计金额列 |
|---|---|---|---|
| R4 | 已归档但未下单 | `O` | `O` |
| R5 | 已下单但无法交付 | `O` | `O` |
| R6 | 已交付但无法确收 | `O` | `O` |
| R7 | 本年度正常可确收 | `AG` | `AG` |
| R8 | 未来可确收 | `N`+(N7−AG7) | `N` |
| R9 | 之前年度已确收 | `AG` | `Q` |
| R12 | 已归档但未下单 | `Q` | `Q` |
| R13 | 已下单但无法交付 | `Q` | `Q` |
| R14 | 已交付但无法确收 | `Q` | `Q` |
| R15 | 本年度正常可确收 | `AG` | `AG` |
| R16 | 未来可确收 | `Q`+(Q15−AG15) | `Q` |

**筛选条件**：`AU="统计"` + `A=递延/新签` + `AV=状态` + `AX=交付分类`

### 3.3 双口径（锁定/动态）

> 详见 `DESIGN-DETAIL-REVENUE-FORECAST-v1.0.md` §2

| 口径 | 定义 | 取数列 | 202609 锚点 |
|---|---|---|---|
| **锁定** | 已提交公司/财务，本年不可调 | `year_est`（col27） | 138,420,136.78 |
| **动态** | 经理按交付进度全权动态调整 | `rev_future`（col10）+ pipeline | 171,048,611.81 |

**口径差异**：动态 − 锁定 = +32,628,475.03（经理把原排在 2027+ 的项目提前到 2026）

### 3.4 10 Sheet 报表结构

| # | Sheet | 行数 | 列数 | 类型 | 数据源 |
|---|---|---|---|---|---|
| 1 | 预算执行表 | 10,477 | 50（45+5 计算列） | 核心数据 | 导入 + 计算列 |
| 2 | 计划确收底稿 | 38,052 | 45 | 核心数据 | 导入 |
| 3 | 汇总 | 31 | 13 | 汇总表 | 聚合 |
| 4 | 汇总分析 | 64 | 50 | 透视表 | 聚合 |
| 5 | 预算趋势分析 | 19 | 17 | 趋势表 | 计算列 + 状态 |
| 6 | 确收差异分析 | 16 | 4 | 透视表 | 聚合 |
| 7 | 重拆履约 | 9 | 3 | 透视表 | 聚合 |
| 8 | 图例 | 506 | 16 | 静态表 | md_reference |
| 9 | 月度汇总记录 | 266 | 11 | 汇总表 | 聚合 |
| 10 | 履约汇总记录 | 126 | 6 | 汇总表 | 聚合 |

---

## 4. 数据模型

### 4.1 表清单

| 表 | 用途 | 关键字段 |
|---|---|---|
| `ra_sheet_row` | 宽表数据 | period, sheet, row_index, contract_no, category, data(JSON) |
| `ra_sheet_meta` | Sheet 元数据 | period, sheet, columns(JSON), row_count |
| `ra_period` | 账期登记 | period, source_path, generated_at, row_counts(JSON) |
| `ra_caliber` | 双口径快照 | period, caliber(locked/dynamic), total, by_group(JSON) |
| `ra_trend_row` | 预算趋势分析行 | period, row_index, category_group, status, count, amount_wan |
| `ra_trend_cell` | 预算趋势分析单元格 | period, row_index, col_index, value |

### 4.2 索引策略

```sql
CREATE INDEX idx_ra_sheet ON ra_sheet_row(period, sheet);
CREATE INDEX idx_ra_contract ON ra_sheet_row(contract_no);
CREATE INDEX idx_ra_category ON ra_sheet_row(category);
CREATE INDEX idx_ra_trend_period ON ra_trend_row(period);
```

---

## 5. 接口契约

### 5.1 CLI

```bash
bdms revenue-analysis import 202609 --source ./202609报表.xlsx
bdms revenue-analysis generate 202609 --mode auto
bdms revenue-analysis export 202609 --out ./output/确认收入分析_202609.xlsx
bdms revenue-analysis caliber 202609          # 双口径汇总
bdms revenue-analysis trend 202609            # 预算趋势分析
```

### 5.2 Python API

```python
from bdms.modules.revenue_analysis.service import RevenueAnalysisService
svc = RevenueAnalysisService()
svc.import_source("202609", Path("./202609报表.xlsx"))
svc.generate("202609", mode="auto")
svc.export("202609", Path("./output/确认收入分析_202609.xlsx"))
```

### 5.3 Web API（预留）

| 方法/路径 | 作用 |
|---|---|
| `POST /api/revenue-analysis/upload` | 上传报表，启动异步 job |
| `GET /api/revenue-analysis/progress/{job_id}` | 轮询进度 |
| `GET /api/revenue-analysis/periods` | 账期列表 |
| `GET /api/revenue-analysis/overview?period=` | 双口径汇总 |
| `GET /api/revenue-analysis/trend?period=` | 预算趋势分析 |
| `GET /api/revenue-analysis/export?period=` | 导出 Excel |

---

## 6. 验收对齐

| 验收项 | 标准 |
|---|---|
| 10 Sheet 完整性 | 全部存在，行数误差 ≤ 1 |
| 列名一致性 | 100% 对齐 202606 基线 |
| 预算趋势分析 | 19 行 × 17 列，数量/金额与 202606 公式一致 |
| 计算列 | AT-AX 五列，统计位 0 重复 |
| 双口径 | 锁定 138,420,136.78 / 动态 171,048,611.81 |
| 幂等 | 同输入 3 次，全部数字逐分相等 |
| 回归 | 不破坏现有 367 passed |

---

## 7. 开发 Phase

| Phase | 内容 | 门 |
|---|---|---|
| P1 | importer + validator + 宽表落盘 | 自测 |
| P2 | engine.compute + 10 Sheet 构建 | 自测 |
| P3 | trend_builder + caliber_builder | 自测 |
| P4 | exporter + 格式化 | 自测 |
| P5 | service + CLI + 全量回归 | Rex 验收 |

---

## 8. 待 Rex 评审确认

1. 模块边界与文件划分（§2.2）；
2. 计算列 5 列设计（§3.1）；
3. 预算趋势分析 19 行公式（§3.2）；
4. 双口径定义与取数列（§3.3）；
5. 10 Sheet 报表结构（§3.4）；
6. 数据模型 5 张表（§4.1）；
7. Phase 拆分（§7）。

**通过后进入 DESIGN-DETAIL。**

---

## 变更历史

- 2026-11-09: v1.0 初版 — 整合 202606 基线 + 既有 v2.1 设计 + 双口径设计，形成完整确收分析报告概要设计
