# DESIGN-OUTLINE — 实时动态确认收入预估（Revenue Forecast）v1.0

| 项 | 值 |
|---|---|
| 所属系统 | BDMS |
| 模块 | revenue_forecast（实时/动态确认收入预算预测） |
| 版本 | v1.0（草案，待 Rex 评审） |
| 作者 | Jerry |
| 日期 | 2026-11-08 |
| 前置 | PRD-REVENUE-FORECAST-v1.0（已通过，D1~D5 已拍板"全按建议"） |
| 状态 | **待 Rex 评审** |

---

## 1. 设计目标与范围边界

落地 PRD 双路径结构：

- **Part A（本版完整建设）**：解析**已提供的上一账期财务报告**（`计划确收底稿`为主），用报告**自带的 col3「交付预计完成时间」** + 金额列，规则判定 2026 预计可确收；不依赖 ONES。
- **Part B（本版仅占位）**：定义 ForecastProvider 接口插槽、`source` 数据位、界面"待接入"区域；返回 `not_configured`，不接真实 ONES。

铁律约束：引擎纯函数无副作用；Service 编排事务 + job；导入幂等；只读、不写回；不新增第三方依赖（标准库 + 既有 openpyxl）；不破坏 367 passed 基线。

---

## 2. 总体架构

沿用 BDMS 现有 `modules/<name>/{engine,service,exporter,...}` 分层 + Base 基类 + 集中 API：

```
web/main.py ── 页面路由 /forecast + 侧栏「确认收入管理」
web/api.py  ── /api/forecast/* （薄路由 → service）
                  │
modules/revenue_forecast/
   ├── report_parser.py     【Part A】财报 Excel → 规范化行（col3 混合值解析）
   ├── classifier.py        【Part A】col3 值 → 类别枚举（计入/排除/风险）
   ├── engine.py            【Part A】纯函数：规范化行 → 预估结果（总额/按月/明细/清单）
   ├── repository.py        持久化（快照表 + 结果表，source 列预留 Part B）
   ├── service.py           编排：上传→解析→计算→落库 + job/进度；读结果
   ├── exporter.py          导出 Excel（继承 BaseExporter）
   └── providers/
         ├── base.py        【Part B】ForecastProvider 抽象接口
         └── null_provider.py 【Part B】NotConfiguredProvider（占位）
```

数据流：

```
财报文件(上一账期)
   │ upload (异步 job + 进度条)
   ▼
report_parser → 规范化行[]
   ▼
classifier 标注每行 category
   ▼
engine.compute（纯函数）→ ForecastResult
   ▼
repository.persist（快照 + 结果，source='report'）
   ▼
GET 读模型 → 前端（Part A 数据区 + Part B 占位区）
```

---

## 3. Part A 核心抽象

### 3.1 规范化行（NormalizedRow）

report_parser 输出，每行一个履约义务：

| 字段 | 来源（计划确收底稿） | 说明 |
|---|---|---|
| obligation_id | col8 履约ID | 主键（BI 履约 ID） |
| contract_no | col9/col10 | 合同编号 |
| customer / project | col12/col13 | 客户/项目 |
| raw_due | col3 | **原始混合值**（日期或文本，保留原值） |
| due_date | col3 解析 | 解析出的日期 or None |
| due_kind | parser 标注 | date / status_text |
| category | classifier 填充 | 见 §3.2 枚举 |
| amount_total | col39 | 单项履约义务金额 |
| amount_recognized | col41 | 截止2025已确收 |
| amount_plan | col42 | 2026及以后计划确收 |
| amount_remaining | 计算 | max(amount_total − amount_recognized, 0)（D1） |

### 3.2 col3 类别映射（classifier，可配置枚举）

| category | 触发条件（col3） | 是否计入2026 | 去向 |
|---|---|---|---|
| `DUE_2026` | 日期 ∈ 2026 | ✅ 按 due_date 归月 | 主汇总 |
| `FUTURE_YEAR` | 日期 ≥ 2027 | ❌ | 跨年清单 |
| `IN_PIPELINE` | 含"100%确收"/"已提交资料" | ✅ 待确收额（D2 计入） | 主汇总（单列子类） |
| `ADJUSTED` | "调整"/"2026年调整" | 按调整口径 | DETAIL 细化 |
| `EXCEPTION` | "异常项目" | ❌（D3） | 风险清单 |
| `TERMINATED` | "终止" | ❌（D3） | 排除清单 |
| `NOT_STARTED` | "未立项"/"未预计" | ❌（D3） | 风险清单 |
| `ZERO_AMOUNT` | "金额为0" | ❌ | 零额清单 |
| `MISSING_DATE` | 空/无法解析 | ❌（fail-closed） | 风险清单 |

> 文本匹配规则、关键词、日期边界（2026-01-01~12-31）做成配置（settings/常量），不散落硬编码；这是 §7 字段漂移对策。

### 3.3 计算（engine.compute，纯函数）

输入 NormalizedRow[]，输出 ForecastResult：

- **总额**：sum(计入项金额)；`DUE_2026` 用 remaining，`IN_PIPELINE` 用待确收额；拆分新签/递延（对齐"汇总"口径，分类来自预算执行表交叉或 col 标识）。
- **按月分布**：`DUE_2026` 按 due_date 归 202601~12；`IN_PIPELINE` 单列（无明确未来月份）。
- **差异**：预估 vs col42 计划 vs 已实际确收。
- **明细**：每行（金额、category、是否计入及原因）。
- **清单**：风险 / 排除 / 跨年 / 零额。

幂等：同输入 → 同输出；engine 不碰 IO/时间/随机。

---

## 4. Part B 占位设计（ForecastProvider）

`providers/base.py` 定义未来 ONES 接入契约，本版不实现：

```python
class ForecastProvider(ABC):
    name: str
    @abstractmethod
    def status(self) -> ProviderStatus: ...          # ready | not_configured | error
    @abstractmethod
    def fetch(self, obligation_ids, year) -> "PartBForecast": ...
```

- `NotConfiguredProvider.status()` 恒返回 `not_configured`；`fetch()` 抛/返回明确"未配置"，**不伪装数据**。
- 结果行携带 `source ∈ {report, ones}`；本版只有 `report`。
- 界面 Part B 区读 `status`，显示"待接入 ONES 动态数据"占位。
- PRD §3.2 的 ONES 字段映射/team/认证信息归档到 DETAIL 备用，不在本版建调用链。

---

## 5. 数据模型（SQLite，新增表）

沿用既有 `CREATE TABLE IF NOT EXISTS` + 模块内建表/迁移列模式：

| 表 | 用途 | 关键字段 |
|---|---|---|
| `forecast_period` | 账期/版本 | period(账期), forecast_year, source_file, created_at, is_current |
| `forecast_line` | 明细结果 | period, obligation_id(PK逻辑), contract, customer, raw_due, due_date, category, in_plan(bool), amount_total/recognized/remaining/counted, source(预留ones), reason |
| `forecast_monthly` | 按月分布 | period, month, category_group, amount |
| `forecast_totals` | 总额/差异快照 | period, new_sign/deferred × estimate/plan/actual |

- 每次上传写新 period，旧版保留（D4：最新为准 + 上版快照可回溯一版）。
- `source` 列即 Part B 数据位；不物理删除，重算用 upsert/版本切换。

> 精确列类型/索引/约束在 DESIGN-DETAIL 定稿。

---

## 6. 接口（Web/API，REST）

页面：`GET /forecast` → 新模板，侧栏「确认收入管理」组新增一项（图标 📈，label 收入预估）。

API（挂 `/api/forecast`，薄路由 → service）：

| 方法/路径 | 作用 |
|---|---|
| `POST /api/forecast/upload` | 上传财报，启动异步 job，返回 job_id（进度条） |
| `GET /api/forecast/progress/{job_id}` | 轮询解析进度（对齐现有 generate-progress 模式） |
| `GET /api/forecast/periods` | 账期列表（当前/上版） |
| `GET /api/forecast/totals?period=` | 总额 + 计划/实际差异 |
| `GET /api/forecast/monthly?period=` | 按月分布 |
| `GET /api/forecast/lines?period=&category=&page=` | 明细分页/按类别筛选 |
| `GET /api/forecast/provider-status` | Part B 占位状态（恒 not_configured） |
| `GET /api/forecast/export?period=` | 导出 Excel |

> 请求/响应字段契约在 DESIGN-DETAIL 用明确 schema 固化。

---

## 7. 前端

- 新增 `templates/forecast.html`，继承 base，复用品牌/侧栏/css 变量与 chart.umd.min.js。
- 布局：顶部账期选择 + 刷新；KPI（预估总额、计划、差异）；按月柱/线图；Tab（明细 / 风险 / 跨年 / 排除）；**Part B 占位卡片**（"待接入 ONES 动态数据"，置灰）。
- 上传走异步 + 轮询进度，遵守"进度条铁律"；数字右对齐，全中文。
- 只读，无任何写回控件。

---

## 8. 模块划分与交付 Phase（建议，详细排期在 IMPLEMENTATION-PLAN）

| Phase | 内容 | 门 |
|---|---|---|
| P1 | report_parser + classifier + 单测（黄金枚举映射） | 自测 |
| P2 | engine.compute + repository + 单测（总额/按月/差异/幂等） | 自测 |
| P3 | service + job/进度 + API | 真实 HTTP 自测 |
| P4 | 前端 forecast.html + Part B 占位 | Playwright 实测 |
| P5 | exporter + 全量回归 + VERIFICATION | Rex 验收 |

Part B 真实逻辑不在任何 Phase（后续立项）。

---

## 9. 验收对齐（摘要）

- engine 同输入 3 次幂等；预估可逐项下钻复算；
- 与 col42 计划（2.23 亿锚点）/汇总可同口径对照、差异可解释；
- 异常/终止/未立项/跨年/缺值 100% 入清单；
- Part B 占位行为明确不造假；失败保留上版；进度条；
- 不破坏 367 passed；新增测试数 ≥ 新增判定分支数。

---

## 10. 待 Rex 评审确认

1. 模块/文件划分（§2）；
2. col3 → category 九类映射（§3.2）；
3. Part B Provider 插槽与 `source` 数据位方案（§4）；
4. 新增四张表与账期版本策略（§5）；
5. Phase 拆分（§8）。

**通过后进入 DESIGN-DETAIL。**

---

*Part B（ONES 动态数据）本版仅预留位置。*
