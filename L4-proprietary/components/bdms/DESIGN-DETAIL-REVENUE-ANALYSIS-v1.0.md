# DESIGN-DETAIL — 确收分析报告（Revenue Analysis）v1.0

| 项 | 值 |
|---|---|
| 所属系统 | BDMS（Bangcle 专属概念） |
| 模块 | revenue_analysis（确收分析报告自动生成） |
| 版本 | v1.0（整合稿） |
| 作者 | Jerry |
| 日期 | 2026-11-09 |
| 前置 | DESIGN-OUTLINE-REVENUE-ANALYSIS-v1.0（待评审）/ DESIGN-DETAIL-REVENUE-v2.1 / DESIGN-DETAIL-REVENUE-FORECAST-v1.0 §11 |
| 状态 | **待 Rex 终审** |

---

## 目录

0. [版本记录](#0-版本记录)
1. [模块概述](#1-模块概述)
2. [总体架构](#2-总体架构)
3. [计算列设计（AT-AX）](#3-计算列设计atax)
4. [逐 Sheet 详细定义](#4-逐-sheet-详细定义)
5. [预算趋势分析公式（19 行）](#5-预算趋势分析公式19-行)
6. [双口径计算（锁定/动态）](#6-双口径计算锁定动态)
7. [计算公式字典](#7-计算公式字典)
8. [数据模型](#8-数据模型)
9. [接口契约](#9-接口契约)
10. [Excel 导出样式规范](#10-excel-导出样式规范)
11. [错误处理](#11-错误处理)
12. [测试策略](#12-测试策略)
13. [风险与限制](#13-风险与限制)
14. [复用资产清单](#14-复用资产清单)
15. [变更历史](#15-变更历史)

---

## 0. 版本记录

| 版本 | 日期 | 变更说明 |
|---|---|---|
| v1.0 Detail r1 | 2026-11-09 | 初始版本：整合 202606 基线 10 Sheet + v2.1 既有设计 + 双口径 + 计算列，形成完整详细设计 |

---

## 1. 模块概述

### 1.1 模块定位

确收分析模块（revenue_analysis）负责：
1. 导入手工确收对比表（Excel）→ 校验 → 落盘到统一宽表
2. 从宽表聚合计算 → 生成 10 Sheet 结构化数据
3. 生成计算列（AT-AX）→ 预算趋势分析 19 行交叉表
4. 计算双口径（锁定/动态）→ 差异分析
5. 导出格式化 Excel → 对齐 202606 黄金基准

### 1.2 黄金基准

```
~/Bangcle Workspace/01. Management/2026/2026团队报告/202606/
  2026年计划确收&实际确收对比表202601-06-0724 - 差异分析.xlsx
```

**基线结构**（实测）：

| Sheet | 行数 | 列数 |
|---|---|---|
| 汇总 | 31 | 13 |
| 汇总分析 | 64 | 50 |
| 预算趋势分析 | 19 | 17 |
| 确收差异分析 | 16 | 4 |
| 预算执行表 | 8,988 | 93 |
| 计划确收底稿 | 36,400 | 45 |
| 重拆履约 | 9 | 3 |
| 图例 | 506 | 16 |
| 月度汇总记录 | 266 | 11 |
| 履约汇总记录 | 126 | 6 |

### 1.3 模块依赖

```
┌───────────────────────────────────────────────────────────────┐
│ 确收分析模块（revenue_analysis）                                │
│                                                                 │
│ 依赖（向下）：                                                    │
│   ├── bdms.core.db（统一 SQLite 层）                              │
│   ├── bdms.core.paths（路径解析）                                 │
│   ├── bdms.core.header_mapper（表头探测）                         │
│   ├── bdms.modules.base（BaseEngine/BaseService）                 │
│   ├── 交付月报模块 dr_sheet_row（共享宽表结构）                    │
│   ├── 数据集成模块 weekly_signing（周报产线数据）                  │
│   ├── 合同管理模块 cr_contracts（合同信息）                        │
│   └── 产品/服务知识库 kb_item（标准产品目录）                      │
│                                                                 │
│ 被依赖（向上）：                                                  │
│   ├── 项目利润模块（pf_profit_snapshot 收入数据源）                 │
│   ├── 驾驶舱模块（db_snapshot 引用汇总数据）                       │
│   └── CLI / Web API（generate/export 命令）                       │
└───────────────────────────────────────────────────────────────┘
```

### 1.4 文件结构

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
├── trend_columns.py       # 计算列生成器（AT-AX）
└── config.py              # 配置常量（列映射/状态枚举/图例）
```

---

## 2. 总体架构

### 2.1 分层架构

```
┌──────────────────────────────────────────────────────────┐
│ CLI / Web API 层                                          │
│   bdms revenue-analysis import 202609 --source ./报表.xlsx │
│   bdms revenue-analysis generate 202609 --mode auto       │
│   bdms revenue-analysis export 202609 --out report.xlsx   │
├──────────────────────────────────────────────────────────┤
│ Service 层（RevenueAnalysisService）                       │
│   import_source() → generate() → summary() → export()     │
│   幂等三模式：auto / read / regenerate                     │
├──────────────────────────────────────────────────────────┤
│ Engine 层（RevenueAnalysisEngine）                         │
│   compute() → 10 Sheet 结构化数据                         │
│   compute_budget_trend() → 19 行交叉表                    │
│   compute_dual_caliber() → 锁定/动态双口径                │
├──────────────────────────────────────────────────────────┤
│ Builder 层                                                │
│   stats_builders.py → 7 个统计 Sheet                     │
│   trend_builder.py → 预算趋势分析                        │
│   caliber_builder.py → 双口径                            │
├──────────────────────────────────────────────────────────┤
│ Storage 层（bdms.core.db）                                │
│   ra_sheet_row + ra_sheet_meta                            │
│   ra_period + ra_caliber + ra_trend_row + ra_trend_cell   │
└──────────────────────────────────────────────────────────┘
```

### 2.2 数据流转

```
手工 Excel 导入 xlsx
       │
       ▼
┌──────────────────┐
│ RevenueAnalysis  │ ──→ ra_sheet_row (sheet='预算执行表')
│ Importer         │ ──→ ra_sheet_row (sheet='计划确收底稿')
│ .import_all()    │ ──→ ra_sheet_row (sheet='汇总')
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ RevenueAnalysis  │ ──→ 幂等判断（auto/read/regenerate）
│ Service          │ ──→ 调用 Engine.compute()
│ .generate()      │ ──→ 缓存到 ra_period.extra
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ RevenueAnalysis  │ ──→ 读缓存/宽表
│ Exporter         │ ──→ 渲染 10 Sheet 格式化 Excel
│ .export()        │ ──→ 输出到 output/确认收入分析_{period}.xlsx
└──────────────────┘
```

### 2.3 幂等设计

| 模式 | 行为 | 适用场景 |
|---|---|---|
| `auto`（默认） | 有缓存读缓存，无缓存重新计算 | 日常使用 |
| `read` | 只读已有数据，无数据报错 | 快速查询 |
| `regenerate` | 强制重新计算，覆盖缓存 | 数据修正后 |

### 2.4 缓存策略

- **generate 阶段**：`Engine.compute()` 结果写入 `ra_period.extra`（JSON）
- **export 阶段**：只读 `ra_period.extra` 缓存，不实时计算
- **缓存失效**：`regenerate` 模式或 `import_source` 后自动失效

---

## 3. 计算列设计（AT-AX）

> 详见 `DESIGN-DETAIL-REVENUE-FORECAST-v1.0.md` §11

### 3.1 202606 权威公式

| 202606 列 | 公式 | 作用 |
|---|---|---|
| `AV` | `=C{r}&"-"&BQ{r}` | 合同数量统计唯一值（**合同编号** + 预算填报） |
| `AW` | `=IF(COUNTIF(AV$3:AV{r-1},AV{r})>0,"","统计")` | 统计位（按 AV 去重） |
| `BQ` | `=VLOOKUP(J{r},[3]预算执行表!$J:$BQ,60,FALSE)` | 预算填报 |
| `BU` | `=VLOOKUP(J{r},[3]预算执行表!$J:$BU,64,FALSE)` | 预算趋势 |
| `BV` | `=VLOOKUP(BU{r},图例!L:M,2,FALSE)` | 预算趋势类别 |

### 3.2 202609 列映射

202609「预算执行表」原有 45 列（A–AS），新增 5 列（AT–AX）：

| 202609 列 | 对应 202606 | 表头 | 来源/公式 |
|---|---|---|---|
| `AT` (col46) | `AV` | 合同数量统计唯一值 | `=B{r}&"-"&AV{r}`（B=合同编号） |
| `AU` (col47) | `AW` | 统计位 | 按 AT 去重，首现标"统计" |
| `AV` (col48) | `BQ` | 预算填报 | 匹配 202606 → M/O 日期判断 → 留空 |
| `AW` (col49) | `BU` | 预算趋势 | 匹配 202606 → O 日期判断 → 留空 |
| `AX` (col50) | `BV` | 预算趋势类别 | BU → 图例映射 |

### 3.3 Rex 规则（2026-11-09 指令）

| # | 规则 | 实现 |
|---|---|---|
| 1 | **AW 列**按 202606 计算公式自动生成 | `AT = B & "-" & AV(填报)`；`AU` 按 AT 去重首现标"统计" |
| 2 | **BQ 列**下拉列表，按履约ID匹配 202606 自动带入；无法匹配的按「计划开始时间」/「计划完成时间」是否在本年度判断「本年度正常可确收」；剩余留空人工 | 匹配 8855 行；M/O 日期判断 881 行；留空 738 行 |
| 3 | **BV 列**按 202606 计算公式自动生成（依赖 BU 列） | Python 直查图例映射 |
| 4 | **BU 列**下拉列表，按履约ID匹配 202606 自动带入；无法匹配的按「预估交付完成日期（周报）」是否在本年度判断；剩余留空人工 | 匹配 8855 行；O 日期判断 385 行；留空 1234 行 |

### 3.4 图例映射（BU → BV）

| BU（预算趋势） | BV（预算趋势类别） |
|---|---|
| 已归档但未下单 | 异常中 |
| 已下单但无法交付 | 异常中 |
| 已交付但无法确收 | 异常中 |
| 之前年度已确收 | 异常中 |
| 本年度正常可确收 | 本年正常交付 |
| 未来可确收 | 未来交付 |
| 合同消失 | 合同消失 |

---

## 4. 逐 Sheet 详细定义

### 4.1 Sheet 1：预算执行表

**类型**：核心数据（原始明细 + 计算列）
**数据源**：手工 Excel 导入 + 计算列生成
**行数**：~10,477 行（202609 实测）
**列数**：50 列（45 原始 + 5 计算列）

**行结构**：

| 行 | 内容 |
|---|---|
| row 1 | 空行 |
| row 2 | 分组标题行 |
| row 3 | 表头行（50 列） |
| row 4+ | 数据行 |

**列定义（45 原始列，A–AS）**：

| 列 | 列名 | 字段名 | 类型 | 说明 |
|---|---|---|---|---|
| A | 分类 | category | TEXT | 递延 / 新签 |
| B | 合同编号 | contract_no | TEXT | 索引列 |
| C | 合同编号（校准） | contract_no_cal | TEXT | 校准用 |
| D | 客户名称 | customer | TEXT | |
| E | 最终用户名称 | end_user | TEXT | |
| F | 签约主体 | sign_subject | TEXT | |
| G | 合同归档月份 | archive_month | TEXT | YYYYMM |
| H | 履约ID（预算） | perf_id_budget | TEXT | 带 YS 后缀 |
| I | 履约明细(预算） | perf_detail_budget | TEXT | |
| J | 履约ID | perf_id | TEXT | 索引列 |
| K | 收入确认方法 | rev_method | TEXT | 时点法 / 时段法 |
| L | 单项履约义务金额 | perf_amount | NUMERIC | 核心金额 |
| M | 截止20251231已确收金额 | rev_prior | NUMERIC | |
| N | 2026年及以后计划确收 | rev_future | NUMERIC | |
| O | 年初-未立项&项目异常未计划确收 | no_plan | NUMERIC | |
| P | 截止20251231未确收金额 | unrev_prior | NUMERIC | |
| Q | 截止20251231未确收金额（调整） | unrev_adj | NUMERIC | |
| R | 计划开始时间 | plan_start | TEXT | |
| S | 计划结束时间 | plan_end | TEXT | |
| T | 计划完成时间 | plan_done | TEXT | |
| U-AF | 202601 ~ 202612 | m202601~m202612 | NUMERIC | 各月**计划**确收 |
| AG | 2026年预计 | year_est | NUMERIC | SUM(U:AF) |
| AH | 202601-09预计 | h1_plan | NUMERIC | SUM(U:Z) |
| AI | 202601-09确收 | h1_actual | NUMERIC | SUM(AL:AQ) |
| AJ | 202601-09提前完成 | h1_ahead | NUMERIC | |
| AK | 202601-09滞后未完成 | h1_behind | NUMERIC | |
| AL-AQ | 202601 ~ 202609 | a202601~a202609 | NUMERIC | 各月**实际**确收 |
| AR | 2026消失金额 | disappear_2026 | NUMERIC | |
| AS | 2026年及以后消失金额 | disappear_future | NUMERIC | |

**新增计算列（AT–AX）**：

| 列 | 列名 | 字段名 | 类型 | 说明 |
|---|---|---|---|---|
| AT | 合同数量统计唯一值 | stat_unique | TEXT | `=B{r}&"-"&AV{r}` |
| AU | 统计位 | stat_flag | TEXT | 按 AT 去重首现标"统计" |
| AV | 预算填报 | budget_fill | TEXT | 匹配 202606 → 日期判断 → 留空 |
| AW | 预算趋势 | budget_trend | TEXT | 匹配 202606 → 日期判断 → 留空 |
| AX | 预算趋势类别 | budget_trend_cat | TEXT | BU → 图例映射 |

**恒等式**：
```
AG「2026年预计」 = Σ(U..AF)                    ……(E1)
N「2026及以后」 = AG + (N − AG)                ……(E2)
```

### 4.2 Sheet 2：计划确收底稿

**类型**：核心数据（原始明细）
**数据源**：手工 Excel 导入
**行数**：~38,052 行（202609 实测）
**列数**：45 列

**列定义（45 列）**：

| 列 | 列名 | 字段名 | 类型 | 说明 |
|---|---|---|---|---|
| A | 年初-填写说明 | note | TEXT | |
| B | 年初-交付预计完成时间 | init_est_date | TEXT | |
| C | 交付预计完成时间 | est_date | TEXT | **动态口径分类主依据** |
| D | 合同编号 | contract_no | TEXT | |
| E | 合同归档月份 | archive_month | TEXT | |
| F | 合同编号 | contract_no2 | TEXT | |
| G | 标准产品服务名称序号 | prod_seq | TEXT | |
| H | 履约ID | perf_id | TEXT | 索引列 |
| I | 对应预算履约ID | budget_perf_id | TEXT | |
| J | 现行部门 | dept | TEXT | |
| K | 合同名称 | contract_name | TEXT | |
| L | 客户名称 | customer | TEXT | |
| M | 最终用户名称 | end_user | TEXT | |
| N | 合同备注 | contract_note | TEXT | |
| O | 合同操作备注 | ops_note | TEXT | |
| P | 产品服务税率 | tax_rate | NUMERIC | |
| Q | 合同签订日期 | sign_date | TEXT | |
| R | 合同起始时间 | contract_start | TEXT | |
| S | 合同结束时间 | contract_end | TEXT | |
| T | 服务期限（月） | service_months | INTEGER | |
| U | 合同类型 | contract_type | TEXT | |
| V | 合同版本类型 | version_type | TEXT | |
| W | 是否赠送项项目 | gift | TEXT | |
| X | 标准产品类别 | prod_category | TEXT | |
| Y | 合同产品服务名称 | prod_name | TEXT | |
| Z | 履约义务明细 | perf_detail | TEXT | |
| AA | 标准产品服务名称 | std_prod_name | TEXT | |
| AB | 收入对应科目 | rev_subject | TEXT | |
| AC | 末级税金科目名称 | tax_subject | TEXT | |
| AD | 价格拆分依据 | price_basis | TEXT | |
| AE | 验收文件类型 | accept_type | TEXT | |
| AF | 合同约定的验收条款 | accept_term | TEXT | |
| AG | 合同约定的收款节奏 | payment_term | TEXT | |
| AH | 收入确认方法 | rev_method | TEXT | |
| AI | 履约不执行原因 | no_exec_reason | TEXT | |
| AJ | 数量单位 | qty_unit | TEXT | |
| AK | 数量 | qty | NUMERIC | |
| AL | 合同金额 | contract_amount | NUMERIC | |
| AM | 确认合同额 | confirm_amount | NUMERIC | |
| AN | 单项履约义务金额 | perf_amount | NUMERIC | |
| AO | 计划履约金额 | plan_perf_amount | NUMERIC | |
| AP | 截止20251231已确收 | rev_before_2025 | NUMERIC | |
| AQ | 2026年及以后计划确收 | rev_2026_future | NUMERIC | **动态金额取此列** |
| AR | 计划-消失金额 | plan_disappear | NUMERIC | |
| AS | 消失原因 | disappear_reason | TEXT | |

**恒等式**：
```
AN「单项履约义务金额」 = AP「截止2025已确收」 + AQ「2026及以后计划确收」   ……(E3)
```

### 4.3 Sheet 3：汇总

**类型**：汇总表（计算 + 缓存）
**数据源**：预算执行表聚合
**行数**：31 行（固定结构）
**列数**：13 列

**列定义（13 列）**：

| 列 | 列名 | 类型 | 公式 |
|---|---|---|---|
| A | （空） | — | — |
| B | 期间 | TEXT | "202601" ~ "202612" |
| C | 新签合同额 | NUMERIC | SUMIF(category="新签", archive_month=B, perf_amount) |
| D | 新签-预计确收合同额 | NUMERIC | SUMIF(category="新签", SUM(m2026xx)) |
| E | 新签-实际确收合同额 | NUMERIC | SUMIF(category="新签", SUM(a2026xx)) |
| F | 新签-完成率 | NUMERIC | E / D |
| G | 递延-预计确收合同额 | NUMERIC | SUMIF(category="递延", SUM(m2026xx)) |
| H | 递延-实际确收合同额 | NUMERIC | SUMIF(category="递延", SUM(a2026xx)) |
| I | 递延-完成率 | NUMERIC | H / G |
| J | 合计-预计确收合同额 | NUMERIC | D + G |
| K | 合计-实际确收合同额 | NUMERIC | E + H |
| L | 合计-完成率 | NUMERIC | K / J |
| M | 校验 | NUMERIC | 恒等式校验 |

**31 行结构**：

| 行号 | B 列 | C-M 列内容 | 说明 |
|---|---|---|---|
| 1 | （空） | （空） | 留空 |
| 2 | 期间 | 新签合同/（合并）/ 递延合同/（合并）/ 合计/（合并） | 分组标题 |
| 3 | （空） | 新签合同额/预计确收合同额/实际确收合同额/完成率 × 3组 | 子表头 |
| 4-15 | 202601~202612 | 各月数据 | 12 月 |
| 16 | 1-6月小计 | SUM(row4:row9) | 上半年小计 |
| 17 | 合计 | SUM(全年) | 全年合计 |
| 18 | 说明1 | 递延说明文本 | |
| 19 | 说明2 | 新签说明文本 | |
| 20 | 履约维度： | | 标题 |
| 21 | 类别/新签/递延/合计 | | 表头 |
| 22 | 预算完成 | 值 | |
| 23 | 实际完成 | 值 | |
| 24 | 预算-实际 | 值 | |
| 25 | 其中：提前完成 | 值 | |
| 26 | 滞后未完成 | 值 | |
| 27 | 消失 | 值 | |
| 28 | 校验 | 值 | 应为 0 |
| 29-31 | （空） | | |

### 4.4 Sheet 4：汇总分析

**类型**：透视表
**数据源**：按团队/产线聚合
**行数**：~64 行
**列数**：50 列

**行结构**：

| 行 | 内容 |
|---|---|
| row 1-3 | 筛选条件行（团队/产线/项目经理） |
| row 4 | 分组标题行 |
| row 5 | 子表头行 |
| row 6-17 | 各月数据（202601 ~ 202612） |
| row 18 | 1-6月小计 |
| row 19 | 合计 |
| row 20-28 | 同比分析区 |
| row 29-64 | 扩展分析区 |

**列定义（50 列）**：

| 列 | 列名 | 分组 | 类型 |
|---|---|---|---|
| A | （空） | — | — |
| B | 期间 | — | TEXT |
| C-F | 新签合同额/预计/实际/完成率 | 新签 | NUMERIC |
| G-I | 递延-预计/实际/完成率 | 递延 | NUMERIC |
| J-L | 合计-预计/实际/完成率 | 新签+递延 | NUMERIC |
| M-N | （空/分隔） | — | — |
| O | 同比分析标题 | 同比 | TEXT |
| P | Y26 1~6 合同类别 | 同比 | TEXT |
| Q | 销售合同额 | 同比 | NUMERIC |
| R | 确收合同额 | 同比 | NUMERIC |
| S | 确收度 | 同比 | NUMERIC |
| T | 比重 | 同比 | NUMERIC |
| U | 预计确收合同额 | 同比 | NUMERIC |
| V-AX | 扩展列（团队/产线展开） | 多维 | MIXED |

### 4.5 Sheet 5：预算趋势分析

**类型**：趋势表
**数据源**：计算列 + 状态分类
**行数**：19 行
**列数**：17 列

> 公式详见 §5

### 4.6 Sheet 6：确收差异分析

**类型**：透视表
**数据源**：项目经理维度差异
**行数**：~16 行
**列数**：4 列

**行结构**：

| 行 | 内容 |
|---|---|
| row 1-4 | 筛选条件行（项目经理/团队/消失备注/重拆履约） |
| row 5 | 空行 |
| row 6 | 透视表标题（"求和项:202601-06滞后未完成"） |
| row 7 | 表头（行标签 / 递延 / 新签 / 总计） |
| row 8-15 | 差异原因类别 |
| row 16 | 总计 |

**列定义（4 列）**：

| 列 | 列名 | 类型 |
|---|---|---|
| A | 行标签（差异原因类别） | TEXT |
| B | 递延 | NUMERIC |
| C | 新签 | NUMERIC |
| D | 总计 | NUMERIC |

**差异原因类别**（202606 实测）：

| 类别 | 递延 | 新签 | 总计 |
|---|---|---|---|
| 交付原因-延期 | 674,266.18 | 176,923.30 | 851,189.48 |
| 客户原因-延期 | 57,625.01 | 287,108.33 | 344,733.34 |
| 客户原因-终止 | 316,379.59 | — | 316,379.59 |
| 综合原因-分项金额调整 | 70,453.97 | 14,371.56 | 84,825.53 |
| 综合原因-核算差异 | 0 | — | 0 |
| 综合原因-考核扣款 | 83,686.90 | — | 83,686.90 |
| 综合原因-项目异常 | 25,000 | — | 25,000 |
| （空白） | 0 | 0 | 0 |
| **总计** | **1,227,411.65** | **478,403.19** | **1,705,814.84** |

### 4.7 Sheet 7：重拆履约

**类型**：透视表
**数据源**：合同 × 提前/滞后
**行数**：~9 行
**列数**：3 列

**行结构**：

| 行 | 内容 |
|---|---|
| row 1 | 空行 |
| row 2 | 表头（合同编号 / 提前完成 / 滞后未完成） |
| row 3-8 | 数据行（有差异的合同） |
| row 9 | 总计 |

**列定义（3 列）**：

| 列 | 列名 | 类型 |
|---|---|---|
| A | 合同编号 | TEXT |
| B | 求和项:202601-06提前完成 | NUMERIC |
| C | 求和项:202601-06滞后未完成 | NUMERIC |

### 4.8 Sheet 8：图例

**类型**：静态表（参考数据）
**数据源**：md_reference 表 + 计划确收底稿
**行数**：~506 行
**列数**：16 列

**列定义（16 列）**：

| 列 | 列名 | 分组 | 类型 | 说明 |
|---|---|---|---|---|
| A | 项目经理 | 项目经理映射 | TEXT | |
| B | 部门 | 项目经理映射 | TEXT | |
| C | 备注 | 项目经理映射 | TEXT | 在职/离职状态 |
| D | （空） | — | — | 分隔 |
| E | 偏差-状态/趋势 | 偏差分类 | TEXT | |
| F | 偏差-原因类别 | 偏差分类 | TEXT | |
| G | 偏差-原因类别说明 | 偏差分类 | TEXT | |
| H | （空） | — | — | 分隔 |
| I | 滞后验收原因 | 验收分类 | TEXT | |
| J | 滞后验收处置措施 | 验收分类 | TEXT | |
| K | （空） | — | — | 分隔 |
| L | 预算执行进度 | 执行进度 | TEXT | |
| M | 预算执行进度类别 | 执行进度 | TEXT | |
| N | （空） | — | — | 分隔 |
| O | 团队 | 团队/产线 | TEXT | |
| P | 产线 | 团队/产线 | TEXT | |

### 4.9 Sheet 9：月度汇总记录

**类型**：汇总表（历史累积）
**数据源**：按月份聚合
**行数**：~266 行（多月份累积）
**列数**：11 列

**行结构**：

| 行 | 内容 |
|---|---|
| row 1 | 分组标题行 |
| row 2 | 表头行 |
| row 3+ | 数据行（统计期间 × 合同期间 交叉） |

**列定义（11 列）**：

| 列 | 列名 | 类型 | 公式 |
|---|---|---|---|
| A | 统计期间 | TEXT | YYYYMM |
| B | 合同期间 | TEXT | YYYYMM（归档月份） |
| C | 新签合同额（万） | NUMERIC | SUM(perf_amount) WHERE category="新签" AND archive_month=B |
| D | 新签-预计确收合同额（万） | NUMERIC | SUM(m2026xx) WHERE category="新签" AND archive_month=B |
| E | 新签-实际确收合同额（万） | NUMERIC | SUM(a2026xx) WHERE category="新签" AND archive_month=B |
| F | 递延-预计确收合同额（万） | NUMERIC | SUM(m2026xx) WHERE category="递延" AND archive_month=B |
| G | 递延-实际确收合同额（万） | NUMERIC | SUM(a2026xx) WHERE category="递延" AND archive_month=B |
| H | 合计-预计确收合同额（万） | NUMERIC | D + F |
| I | 合计-实际确收合同额（万） | NUMERIC | E + G |
| J | 合计校准（预计） | NUMERIC | 校验列（应为 0） |
| K | 合计校准（实际） | NUMERIC | 校验列（应为 0） |

### 4.10 Sheet 10：履约汇总记录

**类型**：汇总表（历史累积）
**数据源**：按履约维度聚合
**行数**：~126 行（多月份累积）
**列数**：6 列

**每月子结构（7 行）**：

| 行 | 类别 | 说明 |
|---|---|---|
| 1 | 预算完成 | 截止到当月的全年累计计划 |
| 2 | 实际完成 | 截止到当月的全年累计实际 |
| 3 | 预算-实际 | 差异（实际 - 预算） |
| 4 | 其中：提前完成 | 不含分项金额调整 |
| 5 | 滞后未完成 | 不含分项金额调整 |
| 6 | 消失 | 消失金额 |

**列定义（6 列）**：

| 列 | 列名 | 类型 |
|---|---|---|
| A | 统计期间 | TEXT |
| B | 类别 | TEXT |
| C | 新签 | NUMERIC |
| D | 递延 | NUMERIC |
| E | 合计 | NUMERIC |
| F | 备注 | TEXT |

---

## 5. 预算趋势分析公式（19 行）

### 5.1 结构

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

### 5.2 列定义（17 列）

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

### 5.3 金额取数规则（按 BQ 状态分别取权威列）

**筛选条件**：`AU="统计"` + `A=递延/新签` + `AV=状态` + `AX=交付分类`

> **Q 列等价说明**（2026-11-09 实测确认）：202606 的 `Q` 列（截止20251231未确收金额（调整））= `L − M`（单项履约义务金额 − 截止20251231已确收金额），8985 行 0 不匹配，且 Q = P（0 差异）。202609 无独立 Q 列，按 202606 逻辑用 `I − J` 计算等价值（推算值，非权威列）。

**递延合同**（R4–R9）：

| 行 | BQ 状态 | 期初金额列 | 累计金额列 |
|---|---|---|---|
| R4 | 已归档但未下单 | `O` | `O` |
| R5 | 已下单但无法交付 | `O` | `O` |
| R6 | 已交付但无法确收 | `O` | `O` |
| R7 | 本年度正常可确收 | `AG` | `AG` |
| R8 | 未来可确收 | `N`+(N7−AG7) | `N` |
| R9 | 之前年度已确收 | `AG` | `Q`（202609 = `I−J`） |

**新签合同**（R12–R16）：

| 行 | BQ 状态 | 期初金额列 | 累计金额列 |
|---|---|---|---|
| R12 | 已归档但未下单 | `Q`（202609 = `I−J`） | `Q`（202609 = `I−J`） |
| R13 | 已下单但无法交付 | `Q`（202609 = `I−J`） | `Q`（202609 = `I−J`） |
| R14 | 已交付但无法确收 | `Q`（202609 = `I−J`） | `Q`（202609 = `I−J`） |
| R15 | 本年度正常可确收 | `AG` | `AG` |
| R16 | 未来可确收 | `Q`+(Q15−AG15)（202609 = `I−J`） | `Q`（202609 = `I−J`） |

### 5.4 202606 基线值（黄金锚点）

**递延合同**：

| 行 | 状态 | 期初数量 | 期初金额（万） | 正常交付数量 | 正常交付金额（万） | 异常中数量 | 异常中金额（万） | 消失数量 | 消失金额（万） |
|---|---|---|---|---|---|---|---|---|---|
| R4 | 已归档但未下单 | 6 | 99.9886 | 0 | 0 | 6 | 99.9886 | 0 | 0 |
| R5 | 已下单但无法交付 | 53 | 218.0318 | 0 | 0 | 53 | 218.0318 | 0 | 0 |
| R6 | 已交付但无法确收 | 6 | 208.7500 | 0 | 0 | 6 | 208.7500 | 0 | 0 |
| R7 | 本年度正常可确收 | 1248 | 7190.0003 | 1245 | 7179.5403 | 1 | 2.5 | 2 | — |
| R8 | 未来可确收 | 118 | 3681.9536 | 9 | 41.8470 | 0 | 0 | 1 | — |
| R9 | 之前年度已确收 | 6 | 0 | 2 | 3.9724 | 2 | 0.000008 | 2 | — |
| R10 | 合计 | 1437 | 11398.7243 | 1256 | 7225.3597 | 68 | 529.2704 | 5 | — |

**新签合同**：

| 行 | 状态 | 期初数量 | 期初金额（万） | 正常交付数量 | 正常交付金额（万） | 异常中数量 | 异常中金额（万） | 消失数量 | 消失金额（万） |
|---|---|---|---|---|---|---|---|---|---|
| R12 | 已归档但未下单 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| R13 | 已下单但无法交付 | 8 | 170.2820 | 0 | 0 | 8 | 170.2820 | 0 | 0 |
| R14 | 已交付但无法确收 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| R15 | 本年度正常可确收 | 513 | 4718.5301 | 510 | 4685.5135 | 1 | 6.2667 | 0 | 0 |
| R16 | 未来可确收 | 117 | 2835.0329 | 1 | 6.1125 | 0 | 0 | 0 | 0 |
| R17 | 合计 | 638 | 7723.8450 | 511 | 4691.6260 | 9 | 176.5487 | 0 | 0 |

**共计**：

| 行 | 期初数量 | 期初金额（万） | 正常交付数量 | 正常交付金额（万） | 异常中数量 | 异常中金额（万） | 消失数量 |
|---|---|---|---|---|---|---|---|
| R18 | 2075 | 19122.5693 | 1767 | 11916.9857 | 77 | 705.8191 | 5 |

**R19**：新签预计确收率 = 0.607421038492957

### 5.5 微观计数差异复现与解释（2026-11-09 实测）

**问题**：202606「预算执行表」AW="统计" 共 **2078 行**，但「预算趋势分析」递延 1437 + 新签 638 = **2075 个**，差异 **3 行**。

**实测对账**（AW=统计 按 BQ 状态 vs 预算趋势分析 C 列）：

| BQ 状态 | 分类 | AW=统计 行数 | 预算趋势分析 C | 差异 |
|---|---|---|---|---|
| 已归档但未下单 | 递延 | 6 | 6 | 0 |
| 已下单但无法交付 | 递延 | 53 | 53 | 0 |
| 已交付但无法确收 | 递延 | 6 | 6 | 0 |
| 本年度正常可确收 | 递延 | 1248 | 1248 | 0 |
| 未来可确收 | 递延 | 118 | 118 | 0 |
| 之前年度已确收 | 递延 | **4** | **6** | **+2** |
| 合同消失 | 递延 | **5** | **0** | **−5** |
| **递延合计** | | **1440** | **1437** | **−3** |
| 已归档但未下单 | 新签 | 0 | 0 | 0 |
| 已下单但无法交付 | 新签 | 8 | 8 | 0 |
| 已交付但无法确收 | 新签 | 0 | 0 | 0 |
| 本年度正常可确收 | 新签 | 513 | 513 | 0 |
| 未来可确收 | 新签 | 117 | 117 | 0 |
| **新签合计** | | **638** | **638** | **0** |
| **共计** | | **2078** | **2075** | **−3** |

**根因（已实测确认）**：

1. **「合同消失」不独立成行**：AW=统计 中 BQ="合同消失" 的 5 行，在预算趋势分析中**没有独立行**，而是按原 BQ 状态归入对应行的 **I 列「合同消失」**：
   - R7（本年度正常可确收）I 列 = 2
   - R8（未来可确收）I 列 = 1
   - R9（之前年度已确收）I 列 = 2
   - **合计 = 5**，与 AW=统计 的「合同消失」5 行完全一致。

2. **「之前年度已确收」R9 的 6 ≠ AW=统计 的 4**：R9 的 C 列=6，其中 4 行来自 AW=统计 的 BQ="之前年度已确收"，另 **2 行来自其他状态转入**（AW=统计 中 BQ 为其他状态但 BV="异常中" 的行，被归入 R9）。

3. **恒等式成立**：每行 `C（期初数量）= E+G+I+K（正常+异常+消失+未来）`，11 行全部 ✅。

**结论**：
- 预算趋势分析的行口径 = **BQ 状态分组**（递延 6 行 + 新签 5 行）
- 每行内部 = **BV 交付分类拆分**（本年正常交付/异常中/合同消失/未来交付）
- **「合同消失」是 BV 维度，不是 BQ 维度**，故不独立成行
- 2078 vs 2075 的 3 行差异 = 递延「合同消失」5 行（−5）+「之前年度已确收」转入 2 行（+2）

**对 202609 的落地影响**：
- 202609 生成预算趋势分析时，**BQ 状态分组**必须与 202606 一致（递延 6 行 + 新签 5 行）
- **合同消失**不独立成行，按 BV="合同消失" 归入对应 BQ 行的 I 列
- 数量校验：每行 C = E+G+I+K，合计 C = Σ(各行 C)

---

## 6. 双口径计算（锁定/动态）

> 详见 `DESIGN-DETAIL-REVENUE-FORECAST-v1.0.md` §2

### 6.1 锁定口径（Locked）

```
对预算执行表每行：
  locked_year_2026      = AG「2026年预计」 = Σ(U..AF)
  actual_2026_01_09     = Σ(AL..AQ)
  按 A「分类」拆 新签/递延；按 U..AF 拆月
```

**202609 锚点**：

| | 新签 | 递延 | 合计 |
|---|---|---|---|
| 锁定 2026 | 66,520,133.50 | 71,900,003.28 | **138,420,136.78** |
| 实际 1–9 月 | — | — | **94,457,828.53** |

### 6.2 动态口径（Dynamic）

底稿 C「交付预计完成时间」按优先级分类（互斥穷尽），金额取 **AQ「2026年及以后计划确收」**：

| 优先级 | category | 判定 | 计入 | 归月 |
|---|---|---|---|---|
| 1 | DUE_2026 | 日期 year=2026 | ✅ AQ | 按 C 月份 |
| 2 | FUTURE_YEAR | 日期 year≥2027 | ❌ | 跨年清单 |
| 3 | IN_PIPELINE | 文本含「已提交资料」 | ✅ AQ | pipeline 桶 |
| 4 | ALREADY_DONE | 文本含「100%确收」 | ❌ | — |
| 5 | EXCEPTION | 含「异常」 | ❌ | 风险清单 |
| 6 | TERMINATED | 含「终止」 | ❌ | 排除清单 |
| 7 | ADJUSTED | 含「调整」 | ❌ | — |
| 8 | NOT_STARTED | 含「未立项」「未预计」 | ❌ | 风险清单 |
| 9 | ZERO_AMOUNT | 含「金额为0」 | ❌ | 零额清单 |
| 兜底 | MISSING_DATE | 空/不可解析 | ❌ | 风险清单 |

**202609 锚点**：

| 子类 | 新签 | 递延 | 小计 |
|---|---|---|---|
| DUE_2026 | — | — | 86,936,513.95 |
| IN_PIPELINE | — | — | 84,112,097.86 |
| **合计** | **85,065,322.34** | **85,983,289.47** | **171,048,611.81** |

### 6.3 口径差异

```
动态 171,048,611.81 − 锁定 138,420,136.78 = +32,628,475.03
含义：经理把原排在 2027 及以后的部分项目，用"预估交付完成日期"提前到 2026。
```

---

## 7. 计算公式字典

### 7.1 核心公式

| 编号 | 公式名称 | 表达式 | 说明 |
|---|---|---|---|
| F01 | 完成率 | `实际确收 / 预计确收` | 单月/累计完成率 |
| F02 | 新签合同额 | `SUM(perf_amount) WHERE category="新签" AND archive_month = 当前月` | 当月归档的新签合同金额 |
| F03 | 预计确收合同额 | `SUM(m2026xx) WHERE category=指定分类` | 某月计划确收 |
| F04 | 实际确收合同额 | `SUM(a2026xx) WHERE category=指定分类` | 某月实际确收 |
| F05 | 差异 | `实际完成 - 预算完成` | 正=超额，负=未完成 |
| F06 | 提前完成 | `SUM(MAX(actual - plan, 0))` 按合同 | 实际>计划的累计差 |
| F07 | 滞后未完成 | `SUM(MAX(plan - actual, 0))` 按合同 | 计划>实际的累计差 |
| F08 | 校验 | `滞后未完成 - 提前完成 - (预算 - 实际)` | 应≈0 |
| F09 | 合计预计确收 | `新签预计 + 递延预计` | 分组合计 |
| F10 | 合计实际确收 | `新签实际 + 递延实际` | 分组合计 |
| F11 | 合计完成率 | `合计实际 / 合计预计` | 综合完成率 |
| F12 | 1-6月小计 | `SUM(m202601:m202606)` | 上半年累计 |
| F13 | 全年合计 | `SUM(m202601:m202612)` | 全年累计 |
| F14 | 确收度 | `确收合同额 / 销售合同额` | 同比分析用 |
| F15 | 比重 | `单类合同额 / 总合同额` | 结构分析 |

### 7.2 汇总 Sheet 行 18-19 说明文本模板

```
row18: "{递延/新签}合同截止{year}年{month}月实际比预计完成{减少/增加}{abs(diff):.0f}万元。"
```

### 7.3 预算趋势分析公式

| 编号 | 公式 | 说明 |
|---|---|---|
| T01 | 本年正常交付: `disappear_2026 in (None, "", "0") AND rebuild_perf in (None, "", "0")` | 正常履约 |
| T02 | 异常中: `disappear_2026 not in (None, "", "0")` | 有消失金额 |
| T03 | 上年结转: `rev_prior > 0` | 有前期已确收 |
| T04 | 校验: `期初数量 = Σ(各状态数量)` | 恒等校验 |

---

## 8. 数据模型

### 8.1 表清单

```sql
-- 宽表数据
CREATE TABLE IF NOT EXISTS ra_sheet_row (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,              -- YYYYMM
    sheet TEXT NOT NULL,              -- Sheet 名称
    row_index INTEGER NOT NULL,       -- 行序号
    contract_no TEXT,                 -- 索引列：合同编号
    category TEXT,                    -- 索引列：分类（递延/新签）
    archive_month TEXT,               -- 索引列：归档月份
    perf_id TEXT,                     -- 索引列：履约ID
    data TEXT NOT NULL,               -- JSON：完整行数据
    UNIQUE(period, sheet, row_index)
);
CREATE INDEX IF NOT EXISTS idx_ra_sheet ON ra_sheet_row(period, sheet);
CREATE INDEX IF NOT EXISTS idx_ra_contract ON ra_sheet_row(contract_no);
CREATE INDEX IF NOT EXISTS idx_ra_category ON ra_sheet_row(category);
CREATE INDEX IF NOT EXISTS idx_ra_archive ON ra_sheet_row(archive_month);

-- Sheet 元数据
CREATE TABLE IF NOT EXISTS ra_sheet_meta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    sheet TEXT NOT NULL,
    columns TEXT NOT NULL,            -- JSON 数组：列名列表
    row_count INTEGER DEFAULT 0,
    UNIQUE(period, sheet)
);

-- 账期登记
CREATE TABLE IF NOT EXISTS ra_period (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    source_path TEXT,
    generated_at TEXT,
    row_counts TEXT,                  -- JSON: {sheet: count}
    extra TEXT,                       -- JSON: Engine 计算结果缓存
    UNIQUE(period)
);

-- 双口径快照
CREATE TABLE IF NOT EXISTS ra_caliber (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    caliber TEXT NOT NULL,            -- locked / dynamic
    total REAL NOT NULL,
    by_group TEXT,                    -- JSON: {新签: x, 递延: y}
    by_month TEXT,                    -- JSON: {202601: x, ...}
    created_at TEXT,
    UNIQUE(period, caliber)
);

-- 预算趋势分析行
CREATE TABLE IF NOT EXISTS ra_trend_row (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    row_index INTEGER NOT NULL,       -- 4-19
    category_group TEXT,              -- 递延 / 新签
    status TEXT,                      -- 状态描述
    init_count INTEGER,
    init_amount_wan REAL,
    normal_count INTEGER,
    normal_amount_wan REAL,
    exception_count INTEGER,
    exception_amount_wan REAL,
    disappear_count INTEGER,
    disappear_amount_wan REAL,
    future_count INTEGER,
    future_amount_wan REAL,
    check_count INTEGER,
    check_amount REAL,
    UNIQUE(period, row_index)
);
CREATE INDEX IF NOT EXISTS idx_ra_trend_period ON ra_trend_row(period);

-- 预算趋势分析单元格（R19 等特殊单元格）
CREATE TABLE IF NOT EXISTS ra_trend_cell (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    row_index INTEGER NOT NULL,
    col_index INTEGER NOT NULL,
    value TEXT,
    UNIQUE(period, row_index, col_index)
);
```

### 8.2 索引策略

- 宽表：period + sheet 联合索引（查询主路径）
- 合同/分类/归档月份：单列索引（筛选）
- 趋势行：period 索引

---

## 9. 接口契约

### 9.1 RevenueAnalysisEngine

```python
class RevenueAnalysisEngine(BaseEngine):
    """确收分析引擎。"""

    def __init__(self, db_path: Optional[Path] = None): ...
    def check_sources(self, period: str) -> dict: ...
    def sources_available(self, period: str) -> bool: ...
    def import_source(self, period: str, excel_path: Optional[Path] = None) -> dict: ...
    def compute(self, period: str) -> dict: ...
    def compute_budget_trend(self, period: str) -> list[dict]: ...
    def compute_dual_caliber(self, period: str) -> dict: ...
    def load(self, period: str) -> dict: ...
    def persist(self, period: str, data: dict, overwrite: bool = True) -> dict: ...
    def has_data(self, period: str) -> bool: ...
```

### 9.2 RevenueAnalysisService

```python
class RevenueAnalysisService(BaseService):
    """确收分析服务层。"""
    module_name: str = "revenue_analysis"

    def __init__(self, db_path: Optional[Path] = None): ...
    def generate(self, period: str, mode: str = "auto") -> dict: ...
    def import_source(self, period: str, excel_path: Optional[Path] = None) -> dict: ...
    def summary(self, period: str) -> dict: ...
    def caliber(self, period: str) -> dict: ...
    def trend(self, period: str) -> list[dict]: ...
    def sources_available(self, period: str) -> bool: ...
    def list_periods(self) -> list[str]: ...
```

### 9.3 RevenueAnalysisExporter

```python
class RevenueAnalysisExporter:
    """确收分析 Excel 导出器。"""

    def __init__(self, db_path: Optional[Path] = None): ...
    def export(self, period: str, out_path: Optional[Path] = None) -> Path: ...
```

### 9.4 RevenueAnalysisImporter

```python
class RevenueAnalysisImporter:
    """统一确收分析导入器：xlsx → ra_sheet_row 宽表。"""

    def __init__(self, db_path: Optional[Path] = None): ...
    def import_budget_exec(self, excel_path: Path, period: str) -> dict: ...
    def import_plan_draft(self, excel_path: Path, period: str) -> dict: ...
    def import_summary(self, excel_path: Path, period: str) -> dict: ...
    def import_all(self, excel_path: Path, period: str) -> dict: ...
```

### 9.5 RevenueAnalysisValidator

```python
class RevenueAnalysisValidator:
    """确收分析数据导入有效性/合法性校验器。"""

    def validate_row(self, sheet: str, row: dict, row_index: int) -> list[dict]: ...
    def validate_batch(self, sheet: str, rows: list[dict], period: str) -> dict: ...
    def persist_validation_results(self, period: str, results: dict) -> int: ...
    def list_pending(self, period: str) -> list[dict]: ...
```

### 9.6 CLI

```bash
bdms revenue-analysis import 202609 --source ./202609报表.xlsx
bdms revenue-analysis generate 202609 --mode auto
bdms revenue-analysis export 202609 --out ./output/确认收入分析_202609.xlsx
bdms revenue-analysis caliber 202609
bdms revenue-analysis trend 202609
```

### 9.7 Web API（预留）

| 方法/路径 | 作用 |
|---|---|
| `POST /api/revenue-analysis/upload` | 上传报表，启动异步 job |
| `GET /api/revenue-analysis/progress/{job_id}` | 轮询进度 |
| `GET /api/revenue-analysis/periods` | 账期列表 |
| `GET /api/revenue-analysis/overview?period=` | 双口径汇总 |
| `GET /api/revenue-analysis/trend?period=` | 预算趋势分析 |
| `GET /api/revenue-analysis/export?period=` | 导出 Excel |

---

## 10. Excel 导出样式规范

### 10.1 字体

| 用途 | 字体 | 大小 | 样式 | 颜色 |
|---|---|---|---|---|
| 表头 | 微软雅黑 | 10pt | bold | 白色 (FFFFFFFF) |
| 子表头 | 微软雅黑 | 10pt | bold | 黑色 |
| 数据 | 微软雅黑 | 10pt | normal | 黑色 |
| 小计/合计 | 微软雅黑 | 10pt | bold | 黑色 |

### 10.2 填充色

| 用途 | 前景色 | 背景色 |
|---|---|---|
| 主表头 | FF4472C4（蓝） | solid |
| 子表头/小计 | FFD9E1F2（浅蓝） | solid |
| 数据行 | 无 | 无 |

### 10.3 对齐

| 类型 | 水平 | 垂直 |
|---|---|---|
| 期间列 | center | center |
| 文本列 | left | center |
| 金额列 | right | center |
| 完成率列 | right | center |

### 10.4 边框

所有数据单元格：四边薄线，颜色 FFD9D9D9（浅灰）。

### 10.5 数值格式

| 类型 | 格式代码 |
|---|---|
| 金额 | `#,##0.00` |
| 完成率 | `0.0000` |
| 整数 | `#,##0` |
| 万元金额 | `#,##0.00` |

### 10.6 列宽

| Sheet | 列宽策略 |
|---|---|
| 汇总 | 固定：A=10, B=14, C-K=14/10 交替 |
| 预算执行表 | 自动（采样前 200 行，最大 40） |
| 计划确收底稿 | 自动（采样前 200 行，最大 40） |
| 其他 | 自动（采样前 200 行，最大 40） |

### 10.7 冻结窗格

| Sheet | 冻结位置 |
|---|---|
| 汇总 | B4（冻结前 3 行 + A 列） |
| 预算执行表 | D4（冻结前 3 行 + A-C 列） |
| 计划确收底稿 | D4 |
| 其他 | A2（冻结表头） |

### 10.8 行高

- 表头行：20pt（自动换行）

---

## 11. 错误处理

| 情况 | 行为 |
|---|---|
| 缺 Sheet / 格式错 | job error，保留上版 |
| E1/E2/E3 恒等式不符 | 记差异行入校验报告，不静默 |
| 日期不可解析 | MISSING_DATE 入风险清单 |
| 金额列缺失 | 报错，不推算 |
| 计算列匹配失败 | 留空，标记人工补填 |
| 双口径差异异常 | 记录差异，不阻断 |

---

## 12. 测试策略

### 12.1 单元测试

| 测试项 | 覆盖 |
|---|---|
| importer | 10 Sheet 导入、行数、列名 |
| validator | 12 条校验规则 |
| engine.compute | 10 Sheet 结构、恒等式 |
| trend_builder | 19 行公式、202606 基线值 |
| caliber_builder | 双口径、202609 锚点 |
| trend_columns | 5 列生成、统计位去重 |

### 12.2 黄金基准测试

| 锚点 | 202606 基线 | 202609 实测 |
|---|---|---|
| 预算执行表行数 | 8,988 | 10,477 |
| 计划确收底稿行数 | 36,400 | 38,052 |
| 汇总行数 | 31 | 31 |
| 预算趋势分析行数 | 19 | 19 |
| 递延期初数量 | 1437 | — |
| 新签期初数量 | 638 | — |
| 锁定 2026 | — | 138,420,136.78 |
| 动态 2026 | — | 171,048,611.81 |

### 12.3 幂等测试

- 同输入 3 次，全部数字逐分相等
- 缓存读写一致

### 12.4 回归测试

- 不破坏现有 367 passed
- 新增测试数 ≥ 新增分支数

---

## 13. 风险与限制

| 风险/限制 | 影响 | 缓解 |
|---|---|---|
| 202609 无独立 Q 列 | 新签 R12-R14/R16 口径需推算 | ✅ 已确认：Q = `I − J`（202606 实测 Q=L−M 8985 行 0 不匹配） |
| 202609 无图例 sheet | BV 映射需 Python 直查 | ✅ 已用配置常量（语义一致） |
| 202609 无「预估交付完成日期（周报）」 | BU 日期判断用 O 列替代 | ✅ 已标注口径差异 |
| BQ/BU 留空行 | 需人工补填 | 本版仅留空，不造假 |
| 202606 微观计数差异（2078 vs 2075） | ✅ 已复现解释（见 §5.5） | 合同消失 5 行归入 I 列 + 之前年度已确收转入 2 行 |
| ONES 实时数据 | Part B 未接入 | 后续立项 |

---

## 14. 复用资产清单

| 资产 | 来源 | 复用方式 | 价值 |
|---|---|---|---|
| 确收引擎 | `modules/revenue/engine.py` | 保留，接入 Base | ⭐⭐⭐⭐⭐ |
| 确收服务 | `modules/revenue/service.py` | 保留，接入 BaseService | ⭐⭐⭐⭐⭐ |
| 确收导出 | `modules/revenue/exporter.py` | 保留，接入 BaseExporter | ⭐⭐⭐⭐⭐ |
| 确收导入 | `modules/revenue/importer.py` | 直接复用 | ⭐⭐⭐⭐⭐ |
| 确收统计构建器 | `modules/revenue/stats_builders.py` | 保留，融入 engine | ⭐⭐⭐⭐⭐ |
| 汇总引擎 | `modules/revenue/summary_engine.py` | 保留并扩展 | ⭐⭐⭐⭐⭐ |
| 周数据导入 | `modules/revenue/weekly_importer.py` | 重构为 integration | ⭐⭐⭐⭐ |
| 双口径引擎 | `modules/revenue_forecast/engine.py` | 保留，扩展 | ⭐⭐⭐⭐⭐ |
| 计算列生成 | `modules/revenue_forecast/trend_columns.py` | 新增 | ⭐⭐⭐⭐⭐ |
| Base 层 | `modules/base.py` | 保留并扩展 | ⭐⭐⭐⭐⭐ |
| Core 层 | `core/db.py` / `core/paths.py` | 保留并加固 | ⭐⭐⭐⭐⭐ |
| L2 Office-011 | `L2-infra/components/office-generation/` | Excel 样式模板 | ⭐⭐⭐⭐ |
| L2 Persistence-006 | `L2-infra/components/persistence/` | SQLite + Repository | ⭐⭐⭐⭐ |

---

## 15. 变更历史

- 2026-11-09: v1.0 Detail r1 — 初始版本：整合 202606 基线 10 Sheet + v2.1 既有设计 + 双口径 + 计算列，形成完整详细设计
