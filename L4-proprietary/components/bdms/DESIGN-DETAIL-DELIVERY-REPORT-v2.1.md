# BDMS v2.1 — 交付月报模块详细设计文档

> **Bangcle Delivery Management System — Delivery Report Module**
> 版本：v2.1 Detail r2（2026-09-22）
> 层级：L4 专有业务层 — 模块 #3
> 依据：`PRD-v2.1.md` §模块 3 + `DESIGN-OUTLINE-v2.1.md` §模块 3
> 前置：`DR_SCHEMA`（宽表 JSON 行存储）已就绪
> 状态：待 Rex 审核

## 目录

1. [模块概述](#1-模块概述)
2. [OS 依赖与限制](#2-os-依赖与限制)
3. [技术方案](#3-技术方案)
4. [接口设计](#4-接口设计)
5. [数据模型](#5-数据模型)
6. [逐 Sheet 详细定义](#6-逐-sheet-详细定义)
7. [开发自检项](#7-开发自检项)
8. [复用资产清单与使用方式](#8-复用资产清单与使用方式)
9. [验收标准](#9-验收标准)
10. [审核记录与变更历史](#10-审核记录与变更历史)

## 0. 版本记录

| 版本 | 日期 | 变更说明 |
|---|---|---|
| v2.1 Detail r1 | 2026-09-22 | 初版：15 Sheet 定义 + 分步流程 |
| v2.1 Detail r2 | 2026-09-22 | Rex 审核反馈 6 条：数据来源细化 + 图例预落盘 + 分步执行 + DASHBOARD 统计 + Validator + 业界最佳实践 + dr_import_validation |
| v2.1 Detail r3 | 2026-10-14 | Web UI 重构：左侧月份导航 + 右侧三 Tab 布局，生成操作移入左侧栏，移除顶部冗余生成卡片，统一操作上下文 |
| v2.1 Detail r4 | 2026-10-15 | UI 组件规范化：原生 alert/confirm/prompt 全部替换为正式组件（Modal + Toast），统一交互体验 |
| v2.1 Detail r5 | 2026-10-15 | 对齐 L2 通用 Web UI 设计规范：新增视觉规范（色彩/字体/间距/圆角）、状态视觉映射、交互细节对齐（Tab/卡片/导航）、明确重构范围与后端零改动约束 |
| v2.1 Detail r6 | 2026-10-15 | 新增 2.4.13 Bangcle 品牌元素规范：Logo 使用规范（真实 logo.png 替换 emoji）、VI 标准色→CSS 变量映射（梆梆蓝 #2D74BB 系列）、品牌图例与图形元素、字体规范（思源黑体）、品牌元素验收项 |

---

## 1. 模块概述

### 1.1 业务目标

按照手工报表解析后的三类数据——**原始数据**、**公式计算数据**、**统计汇总数据**——实现 Bangcle 交付月报 Excel（15 Sheet）的自动生成，以 202606 黄金基准（`2026交付月报-20260630.xlsx`）为验收标准，达到逐格一致。

### 1.2 数据来源与获取方式

| # | 数据源 | 获取方式 | 数据量特征 | 导入频率 | 备注 |
|---|---|---|---|---|---|
| 1 | 签约合同导出 CSV | **ONES 浏览器自动化**导出 | ~15,682 行（同一年度逐月增加） | 月报生成时 | 主数据源 |
| 2 | POC&提前实施导出 CSV | **ONES 浏览器自动化**导出 | ~4,270 行（同一年度逐月增加） | 月报生成时 | 主数据源 |
| 3 | 异常项目导出 CSV | **ONES 浏览器自动化**导出 | ~352 行 | 月报生成时 | 主数据源 |
| 4 | 确收交接导出 CSV | **企业微信文档**（优先）/ 系统通用数据导入（备选） | ~514 行 | 月报生成时 | 如企微存在技术瓶颈，通过系统通用数据导入功能实现 |
| 5 | 验收交接导出 CSV | **企业微信文档**（优先）/ 系统通用数据导入（备选） | ~531 行 | 月报生成时 | 如企微存在技术瓶颈，通过系统通用数据导入功能实现 |
| 6 | 图例配置表 | **黄金基准 Sheet-15** 预提取 | ~502 行 × 48 列 | 一次性预落盘 | 为公式计算提供 VLOOKUP 映射 |

> **数据获取技术方案**：
> - ONES CSV：通过 integration 模块 I-01 连接器（浏览器自动化）导出
> - 企微文档：通过 integration 模块 I-04 连接器（API 接口）获取
> - 系统通用导入：如企微 API 存在技术瓶颈，通过 integration I-05（本机导入 Excel/CSV）实现
> - 图例配置：从黄金基准 Sheet-15 提取后预落盘到 `md_reference`（data_type='legend_config'）

#### 1.2.1 业界最佳实践参考

| 产品/方案 | 核心能力 | 借鉴点 | 本系统落地 |
|---|---|---|---|
| **Power BI Report Server** | 报表自动化 | 数据集 → 报表分层 + 定时刷新 | extract → compute → export 分步执行 |
| **SSRS (SQL Server Reporting)** | 企业报表 | 模板化报表 + 订阅分发 | 15 Sheet 模板 + 黄金基准对齐 |
| **Apache Superset** | 数据可视化 | SQL → 图表 + 下钻 | DASHBOARD 实时聚合统计 Sheet |
| **Airbyte/dbt** | 数据管道 | ELT 分层 + 数据质量测试 | Validator 12 条规则 + 存疑数据流程 |
| **Great Expectations** | 数据校验 | 数据质量断言 + 告警 | validate_not_null/type/enum/row_count |
| **Excel Power Query** | 数据转换 | M 语言管道 + 刷新 | _apply_computations 计算管线 |

### 1.3 设计原则

| 原则 | 落地方式 |
|---|---|
| **计算与输出分离** | `engine.compute()` 纯计算（无 DB 写入）；`engine.persist()` 负责落盘；`exporter.export()` 纯 IO 不做业务计算 |
| **公式计算落盘** | 公式计算在 compute 阶段完成，由 persist 写入 dr_sheet_row（以值写入，非 Excel 公式） |
| **统计汇总走 DASHBOARD** | 统计汇总数据通过 DASHBOARD 实时聚合生成，无需单独落盘；导出时直接通过 DASHBOARD 功能生成 |
| **幂等可重入** | auto / read / regenerate 三模式；`persist(overwrite=True)` 保证重复执行一致 |
| **宽表 JSON 行** | `dr_sheet_row(data JSON)` 避免 83 列硬编码 DDL |
| **黄金基准对齐** | `tools/compare_delivery_report.py` 逐格比对验证 |

> **关于 compute 纯计算 vs 公式落盘**：不冲突。compute() 方法是纯函数（输入→输出，不写 DB），但 persist() 负责将 compute 的结果落盘。公式计算在 compute 阶段完成计算逻辑，由 persist 阶段写入 DB。

### 1.4 月报生成分步流程

每次新生成月报时，分步执行：

```
Step 1: 提取原始数据并落盘
    ├── 1a. ONES 导出签约/POC/异常 CSV（浏览器自动化）
    ├── 1b. 企微/导入获取确收/验收 CSV
    ├── 1c. 解析 CSV → dr_sheet_row（原始数据 Sheet 1-5）
    └── 1d. 图例配置预落盘（md_reference）

Step 2: 校验原始数据有效性
    ├── 2a. 非空检查（必填字段：合同编号、项目名称等）
    ├── 2b. 数据类型检查（日期格式、金额数值等）
    ├── 2c. 枚举值检查（状态标志、类型编码等）
    ├── 2d. 行数合理性检查（与上月对比，偏差 >20% 警告）
    └── 2e. 存疑数据展示 → 人工调整（Web UI 标注 + 编辑）

Step 3: 公式计算数据计算并落盘
    ├── 3a. 状态桶计算（c56 IFS 状态桶 + c57-c65 九状态列）
    ├── 3b. 考核列计算（交付计划准确率/按时交付率 4 列组）
    ├── 3c. VLOOKUP 跨 sheet 列（项目经理→部门映射）
    ├── 3d. 校验列计算（c53/c66）
    └── 3e. 落盘 dr_sheet_row（formula 类型）

Step 4: 统计汇总数据生成（通过 DASHBOARD）
    ├── 4a. 10 个统计 Sheet 定义（结构 + 列名）
    ├── 4b. 数据通过 DASHBOARD 实时聚合生成（不单独落盘）
    └── 4c. 导出时直接读取 DASHBOARD 聚合结果

Step 5: Excel 导出
    ├── 5a. 核心数据 Sheet（1-5）：读 dr_sheet_row 原始数据 + 公式计算结果
    ├── 5b. 统计 Sheet（6-14）：读 DASHBOARD 实时聚合结果
    └── 5c. 图例 Sheet（15）：读 md_reference legend_config
```

### 1.5 文件结构

```
modules/delivery_report/
├── __init__.py          # 模块入口
├── engine.py            # 计算引擎（DeliveryReportEngine，包含统计 Sheet 结构定义（C组10个））
├── service.py           # 编排服务（DeliveryReportService）
├── validator.py         # 数据校验器（新增）
└── exporter.py          # Excel 导出（DeliveryReportExporter）

modules/dashboard/
└── delivery_report_connector.py  # DASHBOARD 聚合查询适配（新增）

docs/
├── DESIGN-DETAIL-DELIVERY-REPORT-v2.1.md  # 本文档
└── archive/

tools/
└── compare_delivery_report.py

tests/
└── test_delivery_report_export.py
```

---

> **实现状态说明**（2026-10-14 文档-代码一致性对齐）：四个核心类
> （DeliveryReportEngine / DeliveryReportService / DeliveryReportExporter / DeliveryReportValidator）
> 实际均**直接实现**，未继承 Base 基类；`stats_builders_c.py` 不存在，C 组统计结构定义已内联至 engine.py。

## 2. OS 依赖与限制

> 本模块通过 integration 模块间接依赖浏览器自动化（ONES 数据源），需对齐 INTEGRATION 模块的 OS 适配方案。

| 功能 | OS 依赖 | macOS | Windows | Linux | 说明 |
|---|---|---|---|---|---|
| ONES 数据导入（签约/POC/异常） | 浏览器自动化 | ✅ osascript（已验证） | 🔶 Playwright（待适配） | 🔶 Playwright（待适配） | 间接依赖 integration I-01 |
| 企微文档导入（确收/验收） | API/浏览器/本机导入 | ✅ 多方案降级 | ✅ 多方案降级 | ✅ 多方案降级 | 间接依赖 integration I-04 |
| 统计汇总生成 | DASHBOARD 实时聚合 | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 SQL 聚合，OS 无关 |
| Excel 导出 | openpyxl | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 Python |
| 数据校验 | pandas | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 Python |
| Web UI (FastAPI) | uvicorn + Jinja2 | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 Python |
| CLI (Click) | click | ✅ 支持 | ✅ 支持 | ✅ 支持 | 纯 Python |

**间接依赖链**：
```
delivery_report
├── ONES 数据源 → integration I-01 → 浏览器自动化
│   ├── macOS: osascript + Chrome（已验证）
│   ├── Linux: Playwright Headless（待验证）
│   └── Windows: Playwright Headless（待开发）
├── 企微文档 → integration I-04 → API/浏览器/本机导入（多方案降级）
├── 统计汇总 → DASHBOARD 实时聚合（OS 无关）
└── Excel/校验/Web/CLI → 纯 Python（全平台）
```

## 3. 技术方案

### 2.1 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                    CLI / Web API 入口                         │
│              bdms-cli report generate 2026-06                 │
│              bdms-cli report export 2026-06                   │
├─────────────────────────────────────────────────────────────┤
│                   Service 层（编排）                          │
│             DeliveryReportService.generate()                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Step 1: extract_raw_data()  → 原始数据落盘           │   │
│  │  Step 2: validate_raw_data() → 校验 + 存疑展示        │   │
│  │  Step 3: compute_formula()   → 公式计算落盘           │   │
│  │  Step 4: stats_via_dashboard() → DASHBOARD 实时聚合   │   │
│  │  Step 5: export()           → Excel 导出              │   │
│  └──────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│                   Engine 层（计算）                           │
│             DeliveryReportEngine.compute()                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  1. load_ones_sign_contracts()  → df_sign             │   │
│  │  2. load_ones_poc()             → df_poc              │   │
│  │  3. load_ones_exceptions()      → df_exc              │   │
│  │  4. load_handover_revenue()     → df_rev              │   │
│  │  5. load_handover_acceptance()  → df_acc              │   │
│  │  6. build_sign_sheet_df()       → 签约 83 列          │   │
│  │  7. build_poc_sheet_df()        → POC 84 列           │   │
│  │  8. build_exception_df()        → 异常 38 列          │   │
│  │  9. build_revenue_handover_df() → 确收 23 列          │   │
│  │ 10. build_acceptance_handover_df()→ 验收 27 列         │   │
│  │ 11. _apply_computations()       → VLOOKUP/公式/状态    │   │
│  └──────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│                   数据校验层（新增）                          │
│             DeliveryReportValidator                         │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  1. validate_not_null()      → 非空检查               │   │
│  │  2. validate_data_type()     → 类型检查               │   │
│  │  3. validate_enum()          → 枚举值检查             │   │
│  │  4. validate_row_count()     → 行数合理性             │   │
│  │  5. collect_suspicious()     → 存疑数据收集           │   │
│  └──────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│                   Persist 层（落盘）                          │
│             DeliveryReportEngine.persist()                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  dr_sheet_row:   month, sheet, row_index, data(JSON)  │   │
│  │  dr_sheet_meta:  month, sheet, columns(JSON), count   │   │
│  │  report_month:   module, month, row_counts            │   │
│  │  md_reference:   legend_config（图例预落盘）          │   │
│  └──────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│                   Export 层（输出）                           │
│             DeliveryReportExporter.export()                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  1. 核心数据 Sheet（1-5）：读 dr_sheet_row            │   │
│  │  2. 统计 Sheet（6-14）：读 DASHBOARD 实时聚合         │   │
│  │  3. 图例 Sheet（15）：读 md_reference                  │   │
│  │  4. openpyxl 样式 → 字体/颜色/列宽/冻结/筛选          │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 数据流

```
ONES CSV（签约/POC/异常）         企微文档/导入（确收/验收）
    ↓ 浏览器自动化/API              ↓ API/通用导入
原始 DataFrame                      原始 DataFrame
    ↓ build_*_sheet_df()            ↓ build_*_sheet_df()
基础 DataFrame（原始列）
    ↓ _apply_computations()
完整 DataFrame（公式计算列）
    ↓ persist()
dr_sheet_row（JSON 宽表）+ dr_sheet_meta + md_reference（图例）
    ↓ export()
交付月报_{YYYYMM}.xlsx（15 Sheet）
    ├── Sheet 1-5：核心数据（dr_sheet_row）
    ├── Sheet 6-14：统计（DASHBOARD 实时聚合）
    └── Sheet 15：图例（md_reference）
```

### 2.3 计算契约（核心约束）

| 约束 | 说明 |
|---|---|
| ❌ exporter 禁止任何业务计算 | export 只做读 DB + 写 Excel 格式 |
| ✅ 公式计算在 compute 阶段完成 | 结果由 persist 落盘到 dr_sheet_row |
| ✅ 公式结果以值写入 | 非 Excel 公式 |
| ✅ 统计 Sheet 通过 DASHBOARD 实时生成 | 无需单独落盘，导出时直接读取 |
| ✅ 图例配置预落盘 | 从黄金基准 Sheet-15 提取 → md_reference |

---

### 2.4 Web UI 交互设计（v2.1 r3 新增）

#### 2.4.1 设计目标（对齐 L2 通用设计原则）

- **单一入口原则**：月份相关操作统一在左侧栏，避免多处选月造成混乱
- **上下文一致**：右侧所有操作围绕「当前选中月份」展开，不需要重复选择月份
- **降低认知负担**：隐藏技术概念（auto / regenerate / read 模式），系统智能判断
- **符合业界惯例**：参考 Linear / Stripe / Notion 的「左侧列表 + 右侧详情」模式
- **视觉层次**：突出核心操作，弱化次要信息，降低用户认知负担
- **一致性**：整个页面元素、颜色、字体、交互对齐 L2 通用规范

#### 2.4.2 整体布局（对齐 L2 通用布局规范）

```
┌─────────────────────────────────────────────────────────┐
│  顶部导航（BDMS 全局）                                    │
├──────────┬──────────────────────────────────────────────┤
│          │  生成&审核 │ 数据浏览 │ 问题清单               │  ← Tab 栏（顶部）
│ 左侧月份栏 ├──────────────────────────────────────────────┤
│          │                                              │
│ [+ 新建]  │   状态卡片（当前月份状态 + 统计 + 操作按钮）      │
│          │                                              │
│ 202608 ✅ │   内容区（根据选中 Tab 切换内容）               │
│ 202607 ⚠️ │                                              │
│ 202606 🔄 │                                              │
│ ...      │                                              │
└──────────┴──────────────────────────────────────────────┘
```

**布局类型：** 侧边栏 + 主内容，符合后台管理系统布局最佳实践。

#### 2.4.3 左侧月份栏

| 元素 | 交互 | 说明 | 对齐 L2 规范 |
|---|---|---|---|
| 「+ 新建月份」按钮 | 点击 → 弹出输入 Modal → 输入月份 → 触发生成 | 新建 = 生成，一步到位 | 主按钮样式（主色背景） |
| 月份列表项 | 点击 → 切换当前月份 → 右侧内容联动 | 状态图标：✅ 已通过 / ⚠️ 待审核 / 🔄 生成中 | 当前项高亮，导航规范 |
| 空状态 | 显示引导文字 + 快捷新建入口 | 首次使用无数据时，友好提示 | 空状态规范 |

**状态图标定义：**
- ✅ `approved` — 已审核通过
- ⚠️ `validating` / `reviewing` — 待审核 / 审核中
- 🔄 `generating` — 生成中

#### 2.4.4 右侧三 Tab

**核心原则：月份上下文单一来源** — 月份选择只有左侧栏一个入口，右侧所有 Tab 自动跟随当前选中月份，不再重复出现月份选择器。

| Tab | 内容 | 对应操作场景 | 对齐规范 |
|---|---|---|---|
| **生成&审核** | 状态卡片 + 统计数据 + 操作按钮 + Sheet 明细折叠 | 月度生成 + 人工审核主流程 | 分组切换，当前 Tab 高亮 |
| **数据浏览** | Sheet 选择 + 搜索 + 数据表格 + 分页 + 导出当前筛选 | 查看原始数据、排查问题 | 表格对齐规范：文本左，数字右 |
| **问题清单** | 严重程度筛选 + 状态筛选 + 问题列表 + 分页 | 人工核验校验结果 | 筛选交互规范 |

**Tab 交互细节（对齐 L2 规范）：**
- URL hash 同步（`#tab=browse`），刷新保持当前 Tab
- 切换 Tab 不丢失当前选中月份上下文（从左侧栏继承）
- 数据浏览 Tab 不显示月份下拉框，月份以静态文字形式在工具栏左侧显示（如「当前月份：2026年06月」），明确上下文来源
- 空状态友好提示（无数据 / 无问题 / 无月份）
- 切到数据浏览/问题清单 Tab 时，如果已有选中月份，自动加载数据
- 超出宽度可横向滚动（响应式）

#### 2.4.5 状态卡片（生成&审核 Tab）

```
┌──────────────────────────────────────────────────────────┐
│ 2026年06月 交付月报              [重新生成] [审批通过] [导出] │
│ 状态：待审核                                         │
│ ┌──────┬──────┬──────┐                               │
│ │  错误  │  警告  │ 待处理 │                               │
│ │   1   │  159  │   2   │                               │
│ └──────┴──────┴──────┘                               │
└──────────────────────────────────────────────────────────┘
```

- **视觉层次**：标题 > 状态 > 统计卡片 > 操作按钮
- 状态圆点实时反映当前审核状态
- 3 个统计卡片（错误 / 警告 / 待处理），点击跳转到问题清单 Tab
- 操作按钮根据状态动态启用/禁用（如：未审批不能导出）
- 卡片有内边距，内容留白清晰，对齐卡片规范

#### 2.4.6 生成模式：系统智能判断（简化认知）

移除前端 `auto / regenerate / read` 三选一模式下拉框，改为后端自动判断：

| 场景 | 后端行为 | 说明 |
|---|---|---|
| 新月份（无数据） | 全新生成 | 用户不需要选，系统自动判断 |
| 已有月份，点「新建」 | 提示「已存在」，切换到该月份 | 避免重复生成 |
| 已有月份，点「重新生成」 | 强制重新生成（regenerate） | 刷新数据入口 |

**理由**：`auto / read / regenerate` 是技术概念，业务用户不需要理解。系统应该「做正确的事」而不是让用户选，简化用户认知负担。

#### 2.4.7 核心交互流（对齐用户体验）

**月度例行生成流：**
```
1. 点左侧「+ 新建月份」→ 弹出新建 Modal → 输入 YYYYMM → 确认生成
2. 系统开始生成 → 左侧月份状态变为「生成中」→ 完成后自动切换到该月份
3. 状态卡片显示校验结果（错误 / 警告 / 待处理）
4. 用户切到「问题清单」Tab 逐条人工核验
5. 核验完毕，点「审批通过」→ 弹出确认 Modal → 确认后状态更新
6. 状态变为「已通过」→ 导出按钮启用 → 用户点击下载 Excel
```

**历史月份查看流：**
```
1. 左侧点某个历史月份
2. 右侧自动显示该月份的状态 + 数据 + 问题
3. 用户可在「数据浏览」Tab 搜索、筛选、导出
```

#### 2.4.8 响应式设计（对齐 L2 响应式规范）

- 大屏（>1200px）：左侧栏固定宽度 200px，右侧自适应
- 中屏（768px - 1200px）：左侧栏压缩到 160px
- 小屏（< 768px）：左侧栏收起为顶部分段控件，Tab 变为横向滚动
- 断点对齐 L2 通用响应式断点规范

#### 2.4.9 UI 组件规范（对齐 L2 通用 Web UI 设计规范 v2.1 r4）

**核心原则（对齐 L2 通用规范）：禁止使用浏览器原生弹窗**（`alert()` / `confirm()` / `prompt()`），
全部替换为 L2 通用自定义组件，保持整个系统视觉一致性与专业交互体验。

| 原生 API | 替换为 | 组件来源 | 使用场景 |
|---|---|---|---|
| `alert()` | **Toast** 通知 | `L2-infra/web-common/macros/components.html` | 操作成功 / 失败 / 警告的轻量提示 |
| `confirm()` | **Modal** 对话框 | `L2-infra/web-common/macros/components.html` | 需要用户确认的危险操作（重新生成 / 审批 / 驳回） |
| `prompt()` | **Modal** 对话框（含输入框） | `L2-infra/web-common/macros/components.html` | 需要用户输入信息的操作（新建月份） |

**Toast 组件规范（对齐 L2 通用）：**
- 位置：右上角堆叠
- 动画：从右侧滑入，淡出消失（时长 300ms ease-out）
- 持续时间：默认 3s，成功/信息类可缩短到 2s
- 四种类型：`success`（绿色）/ `error`（红色）/ `warning`（橙色）/ `info`（默认灰色）
- 无阻塞：不中断用户操作，多条可堆叠显示

**Modal 组件规范（对齐 L2 通用）：**
- 位置：屏幕居中，半透明遮罩 + backdrop blur 虚化背景
- 动画：轻微缩放 + 淡入（150-200ms ease-out）
- 关闭方式：ESC 键关闭 / 点击遮罩关闭 / 取消按钮关闭 / JS 代码调用关闭
- 结构：标题栏 + 内容区 + 底部操作区（左取消按钮 / 右确认按钮）
- 输入型 Modal：标题 + 输入框 + 描述文字 + 操作区，支持回车确认
- 确认型 Modal：标题 + 确认描述文字 + 取消/确认按钮
- 危险操作：确认按钮使用 danger 颜色变体（红色）

**组件复用策略（对齐 L2 架构规范）：**
- Modal / Toast 作为基础通用组件，统一实现在 L2 `web-common/macros/components.html`
- 所有 L3/L4 业务模块统一 import 使用，禁止各模块重复自行实现
- 组件 API 稳定，主题色通过 CSS 变量自动适配各模块主题
- 组件自带无依赖实现（纯 CSS + 原生 JS），不引入第三方库

**BDMS 交付月报模块替换清单：**

| 原原生实现 | 替换为 L2 组件 | 使用场景 |
|---|---|---|
| `alert('月份格式不正确')` | `toast.warning()` | 新建月份输入校验失败 |
| `alert('请先选择月份')` | `toast.warning()` | 无选中月份时的操作提示 |
| `alert('✅ 审核通过')` | `toast.success()` | 操作成功提示 |
| `alert('审批失败: xxx')` | `toast.error()` | 操作失败提示 |
| `confirm('确认重新生成？')` | `showConfirm()` Modal | 重新生成操作前确认 |
| `confirm('确认审批通过？')` | `showConfirm()` Modal | 审批通过操作前确认 |
| `confirm('确认驳回？')` | `showConfirm()` Modal | 驳回操作前确认 |
| `prompt('请输入月份')` | 新建月份 Modal（内置输入框） | 新建月份输入 |

**交互设计对齐 L2 通用规范：**
- 色彩：使用 L2 主题色系统，功能色对应语义（成功绿/错误红/警告橙）
- 动效：动画时长 150-400ms，入场 ease-out，出场 ease-in
- 反馈：用户操作即时反馈，错误清晰提示，不阻塞流程
- 一致性：所有组件样式、交互行为和 L2 规范保持一致

#### 2.4.10 视觉规范（v2.1 r5 新增，对齐 L2 通用视觉规范）

**色彩系统（全部走 CSS 变量，适配亮/暗主题）：**

| 变量 | 用途 | 使用场景 |
|---|---|---|
| `--c-primary` | 主色 | 主按钮、「+ 新建月份」、Tab 激活态、选中高亮 |
| `--c-primary-soft` | 主色浅底 | 左侧栏激活月份背景 |
| `--c-success` | 成功绿 | 审批通过状态点、toast.success、导出按钮 |
| `--c-danger` | 错误红 | 驳回按钮、错误统计值、toast.error |
| `--c-warning` | 警告橙 | 待审核状态点、警告/待处理统计值 |
| `--c-muted` | 弱化文字 | 辅助说明、空状态提示、生成时间 |
| `--c-text` | 主文字 | 标题、正文 |
| `--c-surface` / `--c-surface-2` | 背景层 | 卡片、侧边栏、Tab 栏 |
| `--c-border` / `--c-border-2` | 边框 | 分割线、卡片描边 |
| `--c-hover` | 悬浮底 | 列表项、Tab 悬浮反馈 |

**字体系统（继承 L2 规范）：**

| 层级 | 字号 | 字重 | 场景 |
|---|---|---|---|
| 页面标题 | 20-24px | 600 | page_header 标题 |
| 卡片标题 | 16-18px | 600 | 状态卡片标题、Sheet 明细标题 |
| 正文 | 14-16px | 400 | 表格、说明文字 |
| 辅助 | 12-13px | 400 | 生成时间、空状态副文案 |
| 等宽（输入） | 14px mono | 500 | 新建月份输入框（月份编码） |

**间距系统：**
- 页面间距：1rem（16px）栅格，模块间 1.5rem
- 卡片内边距：1rem
- 列表项：0.6rem 垂直 + 1rem 水平
- 操作区：0.75rem 间距，1rem 上分隔

**圆角与阴影：**
- 卡片/侧边栏/Modal：`var(--radius)` 统一圆角
- 状态卡片：1px 边框 + 浅阴影，突出层次
- 按钮圆角 8-10px，输入框 8-10px

#### 2.4.11 状态视觉映射（对齐功能色语义）

| 状态 | 圆点颜色 | 文字标签 | 按钮联动 |
|---|---|---|---|
| not_started | 灰色 `--c-muted` | 未生成 | 审批/驳回/导出禁用，可重新生成 |
| generating | 主色 `--c-primary` | 生成中 | 全部禁用，进度条显示 |
| validating | 橙色 `--c-warning` | 待审核 | 审批/驳回启用 |
| reviewing | 橙色 `--c-warning` | 审核中 | 审批/驳回启用 |
| approved | 绿色 `--c-success` | 已通过 | 导出启用，审批/驳回禁用 |
| rejected | 红色 `--c-danger` | 已驳回 | 可重新生成/重新校验 |

#### 2.4.12 重构范围与约束（v2.1 r5 新增）

| 项 | 内容 |
|---|---|
| 重构范围 | 仅 `src/bdms/web/templates/report.html` + 必要时补充 web-common 组件 |
| 后端约束 | **零改动**：`api.py` / `service.py` / `engine.py` / `db.py` 一律不动 |
| 业务逻辑 | 不修改任何生成/校验/审批/导出逻辑 |
| 数据模型 | 不改 DB 表结构 |
| 组件约束 | 全部使用 L2 web-common 组件库（modal / toast / progress_bar / pagination / filter_bar / card） |
| 验收 | 浏览器自动化 E2E 全流程 + 0 JS 错误 + 0 原生弹窗 |

#### 2.4.13 Bangcle 品牌元素规范（v2.1 r6 新增）

> **依据**：`docs/architecture/components/bangcle-web-ui/DESIGN.md`（WEB-001 Bangcle Web UI 设计系统，基于官方 PPT VI 规范适配 Web）
> **原则**：品牌一致 — 所有视觉元素遵循 VI 规范，与公司官网、PPT、文档保持一致的品牌感

##### 2.4.13.1 Logo 使用规范

| 项 | 规范 |
|---|---|
| 资源文件 | `src/bdms/web/static/img/logo.png`（591×217 PNG，透明背景，已存在） |
| 使用位置 | ① 侧边栏品牌区（替换现有 `📦` emoji brand_icon）；② 页面头部 page_header 品牌区 |
| 横版 Logo | 宽 120px，安全间距四周 8px，适用白底/浅底导航栏 |
| 方形 Logo | 宽 32px，安全间距四周 4px，适用深色背景/移动端侧边栏 |
| 禁止 | 拉伸变形、改色、加阴影、压缩到无法辨识的尺寸 |

**落地方式（仅前端模板）**：
- 侧边栏品牌区：`<img src="/static/img/logo.png" alt="Bangcle BDMS" style="height:32px;width:auto;">` 替换 `brand_icon` emoji
- main.py 品牌配置不动（后端零改动约束），模板内直接用 `<img>` 引用静态资源
- 深色模式下 logo 保持原 PNG（透明底），若对比度不足，侧边栏背景使用 `--c-surface` 适配

##### 2.4.13.2 品牌配色映射（VI 标准色 → CSS 变量）

交付月报页面全部走 CSS 变量，主色由 L2 web-common 默认蓝 `#2563eb` 切换为 Bangcle 梆梆蓝 VI 系列：

| CSS 变量 | VI 色值 | 色名 | 用途（交付月报页面） |
|---|---|---|---|
| `--c-primary` | `#2D74BB` | 梆梆蓝（C-01） | 主按钮、Tab 激活态、选中月份高亮、链接 |
| `--c-primary-l` | `#3FA1DA` | 浅蓝（C-02） | 悬停态、进度条、二级强调 |
| `--c-primary-d` | `#1D4ED8` → VI 深蓝 `#00122B` 系 | 深藏青（C-06） | 深色模式背景、强调边框 |
| `--c-primary-soft` | `#BEE3FA` | 极浅蓝（辅助） | 选中月份背景、表头背景、标签背景 |
| `--c-success` | `#33ADA0` | 青绿（C-04） | 审批通过状态点、成功 toast、导出按钮 |
| `--c-warning` | `#EFBA20` | 金色（C-05） | 待审核状态点、警告/待处理统计值 |
| `--c-danger` | `#DC3545` | 功能红 | 驳回按钮、错误统计值、错误 toast |
| `--c-info` | `#3FA1DA` | 浅蓝（C-02） | 信息提示、中性状态 |
| `--c-bg` | `#F0F2F5` | 页面浅灰 | 页面底色 |
| `--c-surface` | `#FFFFFF` | 白 | 卡片、侧边栏、Tab 内容区 |
| `--c-border` | `#E7E6E6` | 浅灰 | 卡片边框、分割线 |
| `--c-muted` | `#595757` | 深灰（C-07） | 辅助文字、生成时间、空状态 |
| `--c-text` | `#333333` | 正文深灰 | 正文、表格数据 |

**主题色落地方式（不依赖后端）：**
- 在 `report.html` 的 `<style>` 块顶部覆盖 CSS 变量：
  ```css
  .report-page {  /* 或页面根容器作用域 */
    --c-primary: #2D74BB;
    --c-primary-l: #3FA1DA;
    --c-primary-soft: #BEE3FA;
    --c-success: #33ADA0;
    --c-warning: #EFBA20;
    --c-danger: #DC3545;
    --c-bg: #F0F2F5;
    --c-border: #E7E6E6;
    --c-muted: #595757;
  }
  ```
- 深色模式（`[data-theme="dark"]`）：背景 `#00122B`，卡片 `#1A2B48`，边框 `#BFBFBF`，辅助文字 `#BEE3FA`
- **约束**：不改 L2 web-common 全局 base.css（避免影响其他模块），页面级覆盖仅在交付月报模板生效

##### 2.4.13.3 品牌图例与图形元素

| 元素 | 规范 |
|---|---|
| 状态图例（页面内） | 状态圆点 + 文字标签成组展示（未生成灰/生成中蓝/待审核金/已通过青绿/已驳回红），圆点 12px 圆形 |
| 页面图标 | 线性图标为主，默认 `#595757`，可点击 `#2D74BB`；尺寸 16/20/24px |
| 装饰元素 | 克制使用：标题左侧可选 4px 梆梆蓝装饰条（`#0081FF`/`#2D74BB`） |
| 品牌签名区 | 页面底部可选「Powered by Bangcle」小字（12px `#A7A7A7`），增强品牌露出 |
| 数据表格表头 | 背景 `#F5F7FA`（浅色）/ `#2D74BB20`（深色），斑马纹行 |
| 统计卡片大数字 | 32px 梆梆蓝 `#2D74BB`，标题 14px 深灰 `#595757` |

##### 2.4.13.4 字体规范（对齐 WEB-001）

| 项 | 规范 |
|---|---|
| 字体家族 | 思源黑体（Source Han Sans CN）优先，fallback `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif` |
| 页面大标题 | 24px / 600-700 |
| 板块标题 | 18-20px / 600 |
| 卡片标题 | 16-18px / 500-600 |
| 正文 | 14px / 400 |
| 辅助文字 | 12-13px / 400 |
| 月份编码输入框 | 14px 等宽（mono），与编码输入场景匹配 |

##### 2.4.13.5 品牌元素验收项

| # | 验收项 | 方法 |
|---|---|---|
| 1 | 侧边栏显示真实 logo.png（非 emoji） | 浏览器截图目测 |
| 2 | 主色为梆梆蓝 `#2D74BB`（主按钮/激活态） | 浏览器 computed style 检查 |
| 3 | 功能色语义正确（成功青绿/警告金/错误红） | 状态点 + toast 实测 |
| 4 | 深色模式品牌适配（背景 `#00122B` 系） | 切换主题截图 |
| 5 | 页面无任何非品牌颜色残留（L2 默认蓝） | 截图目测 + CSS 变量检查 |

---

## 4. 接口设计

### 3.1 DeliveryReportEngine

```python
class DeliveryReportEngine:
    """交付月报计算引擎（无状态，方法可独立调用）。"""

    # ─── 数据源检查 ───
    def check_sources(self, month: str) -> dict:
        """检查某月数据源是否齐备。"""

    def sources_available(self, month: str) -> bool:
        """签约数据源是否可用（最低门槛）。"""

    # ─── 分步执行 ───
    def extract_raw_data(self, month: str) -> dict:
        """Step 1: 提取原始数据并落盘。
        调用 integration 连接器获取 ONES CSV + 企微文档。
        返回：{sheet_name: DataFrame}
        """

    def compute(self, month: str) -> dict[str, pd.DataFrame]:
        """Step 3: 公式计算（纯函数，无 DB 写入）。
        前置：原始数据已落盘。
        返回：{sheet_name: DataFrame}
        """

    def persist(self, month: str, data: dict[str, pd.DataFrame],
                overwrite: bool = True) -> dict[str, int]:
        """将公式计算结果落盘到 dr_sheet_row。"""

    # ─── 读取 ───
    def load(self, month: str) -> dict[str, pd.DataFrame]:
        """从 DB 读取某月全部 Sheet 数据。"""

    def has_data(self, month: str) -> bool:
        """DB 中是否已有该月数据。"""
```

### 3.2 DeliveryReportValidator（新增）

```python
class DeliveryReportValidator:
    """原始数据校验器。"""

    def validate_not_null(self, df: pd.DataFrame, required_cols: list[str]) -> list[dict]:
        """非空检查。返回：[{row: int, col: str, value: None}]"""

    def validate_data_type(self, df: pd.DataFrame, col_types: dict[str, str]) -> list[dict]:
        """数据类型检查（date/numeric/text）。"""

    def validate_enum(self, df: pd.DataFrame, col_enums: dict[str, list[str]]) -> list[dict]:
        """枚举值检查。"""

    def validate_row_count(self, sheet: str, current: int, previous: int,
                           threshold: float = 0.2) -> dict:
        """行数合理性检查（与上月对比）。
        偏差 >threshold 时返回警告。"""

    def collect_suspicious(self, month: str) -> dict:
        """收集所有存疑数据。
        Returns: {
            "errors": [{"sheet": str, "row": int, "col": str, "issue": str, "value": any}],
            "warnings": [{"sheet": str, "row": int, "col": str, "issue": str}],
            "summary": {"total_errors": int, "total_warnings": int}
        }
        """

    def apply_manual_fixes(self, month: str, fixes: list[dict]) -> dict:
        """应用人工调整。
        fixes: [{"sheet": str, "row_index": int, "col": str, "value": any}]
        """
```

### 3.3 DeliveryReportService

```python
class DeliveryReportService(BaseService):
    """交付月报编排服务（分步执行）。"""

    module_name: str = "delivery_report"

    def generate(self, month: str, mode: str = "auto") -> dict:
        """分步执行月报生成。
        Step 1: extract_raw_data → 落盘
        Step 2: validate → 返回存疑数据（如需人工调整，等待后继续）
        Step 3: compute → persist 落盘
        Step 4: 统计汇总通过 DASHBOARD 实时生成
        """

    def generate_with_validation(self, month: str,
                                  fixes: list[dict] = None) -> dict:
        """带校验的生成流程。
        如有存疑数据，应用 fixes 后继续。
        """

    def export(self, month: str, out_path: Path = None) -> Path:
        """导出 Excel。"""
```

### 3.4 DeliveryReportExporter

```python
class DeliveryReportExporter:
    """交付月报 Excel 导出器（只做 IO + 格式，不做计算）。"""

    SHEET_ORDER: list[str] = [
        "签约", "POC&提前实施", "异常项目", "确收交接", "验收交接",
        "异常台账", "交付效率统计", "签约统计", "产品-授权&维保统计",
        "POC&提前实施统计", "提前实施分事业部统计", "异常统计",
        "交付异常分事业部统计", "交接统计", "图例",
    ]

    def export(self, month: str, out_path: Path = None) -> Path:
        """导出某月数据为 Excel。
        核心数据（Sheet 1-5）：读 dr_sheet_row
        统计 Sheet（6-14）：读 DASHBOARD 实时聚合
        图例（Sheet 15）：读 md_reference legend_config
        """
```

---

## 5. 数据模型

### 4.1 dr_sheet_row（核心数据表）

> 与旧版一致。宽表 JSON 行模式。

### 4.2 dr_sheet_meta（Sheet 元信息表）

> 与旧版一致。

### 4.3 report_month（月度登记）

> 与旧版一致。

### 4.4 md_reference（字典表 — 扩展）

新增 data_type：

| data_type | 说明 | 预落盘来源 |
|---|---|---|
| `legend_config` | 图例配置（48 列 × ~502 行） | 黄金基准 Sheet-15 |
| `legend_pm_dept` | 项目经理→部门映射（核心 2 列） | 黄金基准 Sheet-15 A:B |
| `legend_team_stats` | 销售团队→统计团队映射 | 黄金基准 Sheet-15 AA:AB |
| `legend_baseline` | 基准列（预算-预估日期等） | 黄金基准 Sheet-15 F:K |
| `legend_pm_full` | 项目经理全量映射（含考核项） | 黄金基准 Sheet-15 M:Y |

**图例 48 列分组结构**（以 202606 基准为例）：

| 组 | 列范围 | 内容 | 列数 |
|---|---|---|---|
| 第一组 | A-D | 项目经理、部门、中心、备注 | 4 |
| 第二组 | F-K | 考核项、偏差类别、是否跨月等 | 6 |
| 第三组 | M-Y | 日期列映射（预估/预算/基线） | 13 |
| 第四组 | AA-AB | 销售团队→统计团队 | 2 |
| 第五组 | AD-AF | 其他映射（直签/代理等） | 3 |
| 空列 | E, L, Z, AC | 分隔空列 | 4 |
| **合计** | A-AF | | **48** |

> 空列（E/L/Z/AC）为分隔列，导出时保留空列位。

### 4.5 dr_import_validation（导入校验结果表，新增）

> 对齐 REVENUE 模块的 rr_import_validation 模式（存疑数据统一落盘 + 人工处置流程）。

```sql
CREATE TABLE IF NOT EXISTS dr_import_validation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    sheet TEXT NOT NULL,               -- 签约 / POC&提前实施 / 异常项目 / 确收交接 / 验收交接
    row_index INTEGER NOT NULL,
    column_name TEXT,
    rule_code TEXT NOT NULL,           -- V01 ~ V10（见 §3.2 DeliveryReportValidator）
    severity TEXT NOT NULL,            -- ERROR / WARNING
    message TEXT NOT NULL,
    original_value TEXT,
    corrected_value TEXT,              -- 人工校正后的值（NULL = 未处理）
    status TEXT DEFAULT 'pending',     -- pending / confirmed / rejected
    operator TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_dr_val_month ON dr_import_validation(month, status);
```


---

## 6. 逐 Sheet 详细定义

### 5.1 Sheet 1：签约

| 属性 | 值 |
|---|---|
| **类型** | 核心数据 |
| **数据源** | ONES 签约合同导出 CSV（浏览器自动化） |
| **行数基准** | ~15,682（202606 实测，同一年度逐月增加） |
| **列数** | 83 |

**关键公式列**：

| # | 列名 | 计算逻辑 |
|---|---|---|
| 53 | 履约项合计 | COUNTIF 当前合同编号在整列的出现次数 |
| 54 | 校验 | `c53 - SUM(c45:c52)` |
| 56 | 项目统计状态 | IFS 状态桶（基于 c45-c52 九状态标志） |
| 57-65 | 九状态列 | 每状态一列，值为 1/0 |
| 66 | 统计校验 | `SUM(c57:c65) - c53` |
| 67 | 履约项统计状态 | 财报-交付/确收状态 |
| 68-72 | 考核列（交付计划准确率） | 差异/提前延后/是否跨月/考核扣分 |
| 73-76 | 考核列（按时交付率） | 差异/提前延后/是否跨月/考核扣分 |
| 79 | 销售团队-统计 | `VLOOKUP(责任销售所属团队, 图例!AA:AB, 2, FALSE)` |

### 5.2 Sheet 2：POC&提前实施

| 属性 | 值 |
|---|---|
| **类型** | 核心数据 |
| **数据源** | ONES POC 导出 CSV（浏览器自动化） |
| **行数基准** | ~4,270（202606 实测，同一年度逐月增加） |
| **列数** | 84 |

**c80「统计所属项目」**：列 CE，逐行去重标记。
```python
# 计算逻辑：每行校验其上方行（同列）是否已存在相同的所属项目值
# - 如上方已出现 → 本单元格为空（去重）
# - 如上方未出现 → 本单元格为当前行的所属项目数值
# 实现：
seen = set()
for i, val in enumerate(df['所属项目']):
    if val in seen:
        c80[i] = None  # 已出现过，置空
    else:
        c80[i] = val   # 首次出现，显示值
        seen.add(val)
```

### 5.3 Sheet 3：异常项目

| 属性 | 值 |
|---|---|
| **类型** | 核心数据 |
| **数据源** | ONES 异常导出 CSV（浏览器自动化） |
| **行数基准** | ~352 |
| **列数** | 38 |

### 5.4 Sheet 4：确收交接

| 属性 | 值 |
|---|---|
| **类型** | 核心数据 |
| **数据源** | 企业微信文档（优先）/ 系统通用导入（备选） |
| **行数基准** | ~514 |
| **列数** | 23 |

### 5.5 Sheet 5：验收交接

| 属性 | 值 |
|---|---|
| **类型** | 核心数据 |
| **数据源** | 企业微信文档（优先）/ 系统通用导入（备选） |
| **行数基准** | ~531 |
| **列数** | 27 |

### 5.6 Sheet 6-14：统计汇总

| Sheet | 名称 | 数据生成方式 | 说明 |
|---|---|---|---|
| 6 | 交付效率统计 | **DASHBOARD 实时聚合** | 项目经理团队/部门/中心 3 组 |
| 7 | 签约统计 | **DASHBOARD 实时聚合** | 按统计项目编号/部门 |
| 8 | 产品-授权&维保统计 | **DASHBOARD 实时聚合** | 按产品分类 |
| 9 | POC&提前实施统计 | **DASHBOARD 实时聚合** | 多维度 |
| 10 | 提前实施分事业部统计 | **DASHBOARD 实时聚合** | 按事业部 |
| 11 | 异常统计 | **DASHBOARD 实时聚合** | 多维交叉（条件默认全部时应与手工一致） |
| 12 | 异常台账 | **DASHBOARD 实时聚合** | 36 行固定结构 |
| 13 | 交付异常分事业部统计 | **DASHBOARD 实时聚合** | 按事业部 |
| 14 | 交接统计 | **DASHBOARD 实时聚合** | 按区域 |

> **统计 Sheet 说明**：
> - 统计汇总数据通过 DASHBOARD 实时聚合生成，无需单独落盘
> - 导出时直接读取 DASHBOARD 聚合结果（耗时 < 3s）
> - 异常统计 54 列结构：条件默认全部时应与手工基准一致；当月自动生成报表与手工报表也应一致
> - 异常台账固定 36 行（2025 基准 12 行 + 2026 基准 13 行 + 3 空行 + 8 末尾空行）

### 5.7 Sheet 15：图例

| 属性 | 值 |
|---|---|
| **类型** | 静态配置 |
| **数据源** | md_reference（legend_config，从黄金基准预提取） |
| **行数** | ~502 |
| **列数** | 48 |
| **列分组** | A-D(4) + E(空) + F-K(6) + L(空) + M-Y(13) + Z(空) + AA-AB(2) + AC(空) + AD-AF(3) = 48 |

---

## 7. 开发自检项

> 以下条目为开发/验收时的自检项，无需人工确认，逐项对比 202606 黄金基准通过即可。

| # | 自检项 | 校验方法 | 影响范围 |
|---|---|---|---|
| 1 | 交付效率统计偏差率公式 | 公式计算数据中已处理 ABS，按参考手工基准计算 | Sheet 6 |
| 2 | 异常统计 54 列结构 | 对比 202606 基准 Sheet-11 逐列核实（列名 + 列序 + 值） | Sheet 11 |
| 3 | POC c80 统计所属项目 | 逐行去重标记：上方已出现则为空，否则显示值 | Sheet 2 |

---

## 8. 复用资产清单与使用方式

> **原则**：所有复用资产通过 **import 引用 / 继承 / 组合** 方式使用，**禁止复制粘贴**。

| 资产 | 来源文件 | 使用方式 | 重构操作 | 本模块调用代码 |
|---|---|---|---|---|
| `load_ones_sign_contracts` | `delivery-center/v2/` 或 `modules/revenue/weekly_importer.py` | **import 引用** | 重构为 integration I-01 连接器方法 | `from bdms.modules.integration.connectors.ones import OnesConnector` |
| `build_sign_sheet_df` | `delivery-center/v2/` | **import 引用** | 迁入本模块 engine.py | `from .legacy_adapter import build_sign_sheet_df` |
| `stats_builders_c` | 已内联至 `modules/delivery_report/engine.py` | **直接实现** | 无 | 无外部引用（已内联） |
| `BaseEngine` | `modules/base.py` | 实际未继承，直接实现 | 无 | `class DeliveryReportEngine: ...` |
| `BaseService` | `modules/base.py` | 实际未继承，直接实现 | 无 | `class DeliveryReportService: ...` |
| `BaseExporter` | `modules/base.py` | 实际未继承，直接实现 | 无 | `class DeliveryReportExporter: ...` |
| `DashboardService` | `modules/dashboard/service.py` | **组合** | 实例化调用（统计汇总） | `from bdms.modules.dashboard.service import DashboardService; dashboard = DashboardService()` |
| `md_reference` | `core/schemas_v21.py` | **DB 共享** | 读写字典 | `SELECT label FROM md_reference WHERE data_type='legend_config' AND code=?` |
| `dr_sheet_row` | `core/schemas_v21.py` | **DB 共享** | 读写宽表 | `INSERT INTO dr_sheet_row (month, sheet, row_index, data) VALUES (...)` |

**重构检查清单**：
- [ ] 所有 import 路径指向源文件（非副本）
- [ ] delivery-center v2 代码通过 import 引用（非复制到本模块）
- [ ] 统计汇总通过 DashboardService 调用（非本模块重复实现）
- [ ] 继承关系正确（子类 → BaseEngine/BaseService/BaseExporter）
- [ ] 无复制粘贴代码块
- [ ] 如需修改源文件功能，通过 PR 修改源文件（非本模块内重写）

---

## 9. 验收标准

| 维度 | 标准 |
|---|---|
| 15 Sheet 完整性 | 全部 15 Sheet 存在 |
| 行数误差 | 核心数据 Sheet ≤ 1；统计 Sheet 通过 DASHBOARD 实时生成 |
| 列名一致性 | 100%（含列序） |
| 公式计算 | 与手工报表值一致 |
| 原始数据 | 与 ONES/企微导出 CSV 一致 |
| 图例配置 | 与黄金基准 Sheet-15 一致 |

---

## 10. 审核记录与变更历史

### 8.1 审核

| 轮次 | 日期 | 审核人 | 结论 | 意见 |
|---|---|---|---|---|
| 1 | 2026-09-22 | Rex | ⏳ 待审 | — |

### 8.2 变更历史

| 版本      | 日期         | 变更                                                                                                                                                                                                                                                           |
| ------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| v2.1 r2 | 2026-09-22 | Rex 审核反馈 6 条修改：<br>① 明确公式计算落盘不冲突（compute 纯计算 + persist 落盘）<br>② 细化数据来源获取方式（ONES 浏览器自动化 + 企微文档/通用导入）<br>③ 新增图例配置预落盘（从黄金基准 Sheet-15 提取）<br>④ 新增分步执行流程（提取→校验→公式计算→统计汇总→导出）<br>⑤ 统计汇总走 DASHBOARD（不单独落盘）<br>⑥ 新增 DeliveryReportValidator 数据校验器<br>⑦ 图例 48 列分组结构定义 |
| v2.1 r1 | 2026-09-22 | 初版                                                                                                                                                                                                                                                           |

## 月份格式约定（2026-09-28 补充）

**约定：系统内月份统一使用 `YYYYMM` 格式（如 202606），不带分隔符。**

| 场景 | 格式 | 说明 |
|---|---|---|
| report_month 表 | YYYYMM | 登记月份，register_month 自动规范化 |
| dr_sheet_row.month | YYYYMM | 数据行月份 |
| API 路径参数 | YYYYMM | /api/report/export/{month}，自动规范化（兼容 YYYY-MM 输入） |
| API body 参数 | YYYYMM | {month: "202606"}，自动规范化 |
| 前端月份选择 | YYYYMM | 下拉框选项从 /api/report/months 加载 |
| 例外：profit 模块 period | YYYY-MM | 会计期间格式，设计约定保持不变 |

**实现**：`core/db.py normalize_month()` 统一规范化（YYYY-MM/YYYY/MM/YYYY.MM → YYYYMM），
`register_month()` 写入前规范化，`list_months()` 读取时去重 + 规范化，
`web/api.py` 全部 month 入口参数规范化。

**背景**：2026-09-27 人工审核发现月份列表重复显示（2026年06月 / 2026年-06月），
根因是 E2E 测试曾以 YYYY-MM 格式写入 report_month 和 dr_sheet_row，
历史脏数据已清理（备份 data/bdms.db.bak-month-fix）。

---

