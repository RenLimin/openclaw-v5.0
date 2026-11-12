# IMPLEMENTATION-PLAN — 确收分析及预测 v1.1

| 项 | 值 |
|---|---|
| 所属系统 | BDMS（Bangcle 专属概念） |
| 模块 | revenue_analysis（确收分析报告自动生成） |
| 版本 | v1.1 |
| 作者 | Jerry |
| 日期 | 2026-11-12 |
| 前置 | DESIGN-DETAIL-REVENUE-ANALYSIS-v1.1（已 Rex 终审通过 2026-11-12） |
| 状态 | **待 Rex 评审** |
| 基线 | 现有实现 2,147 行（engine 736 / exporter 332 / service 168 / config 220 / importer 172 / validator 173 / trend_builder 134 / caliber_builder 184） |

---

## 0. 版本记录

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-11-10 | 初版：M1–M4 里程碑（未含 Q1–Q8） |
| v1.1 | 2026-11-12 | 对齐 DESIGN-DETAIL v1.1（Q1–Q8）+ GAP-ANALYSIS 6 类根因；拆为 P0–P7 |

---

## 1. 复用资产清单（不重复建设 · Rex 2026-11-12 指令）

> 原则：**先复用、后扩展、最后才新建**。下表为已建能力，实施中直接调用，不重写。

| # | 资产 | 路径 | 用途 | 复用方式 |
|---|---|---|---|---|
| R1 | HeaderMapper | `bdms.core.header_mapper` | 表头名→列索引自适应映射（同名 nth 消歧） | 直接复用（importer 已用） |
| R2 | RR_SCHEMA 宽表 | `bdms.core.db`（`rr_sheet_row`/`rr_sheet_meta`） | 导入数据落地 | 直接复用（`save_sheet_rows` 幂等） |
| R3 | BaseEngine / BaseService | `bdms.modules.base` | 引擎/服务骨架 + 三模式幂等 | 继承，不重写 |
| R4 | OaConnector | `bdms.modules.integration.connectors.oa_connector` | OA 合同台账「合同下单（y/n）」 | 直接调用 `normalize()` |
| R5 | OnesConnector | `bdms.modules.integration.connectors.ones_connector` | ONES 履约义务按「销售合同编号」匹配 | 直接调用 `normalize()`（输出含 `销售合同编号/BI履约ID/履约项异常类型`） |
| R6 | md_reference | BDMS 库 | 33 PM + 18 销售团队 + 状态/原因枚举 | 图例重建唯一数据源 |
| R7 | caliber_builder | `revenue_analysis/caliber_builder.py` | 双口径（锁定/动态） | **已验证准确**（119,085,304.74 元），不重造 |
| R8 | trend_builder | `revenue_analysis/trend_builder.py` | 趋势 19 行构建 | **修正 row_index 映射**（GAP 根因 5） |
| R9 | validator | `revenue_analysis/validator.py` | 导入校验 | 扩展（增加实际列/偏差列校验） |
| R10 | exporter | `revenue_analysis/exporter.py` | Excel 导出 | 扩展（单位层 + 10 sheet 完整） |
| R11 | config 常量 | `revenue_analysis/config.py` | 列映射/枚举/公式 | 扩展（93 列 + 202606 映射） |
| R12 | 测试骨架 | `tests/test_revenue_analysis_p3.py` / `_service.py` | pytest + 真实 HTTP | 沿用模式，新增 phase 测试文件 |

**不新建**：表头映射器、宽表存储、OA/ONES 取数、双口径计算、导出器骨架。

---

## 2. 实施范围总览

### 2.1 差距根因 → Phase 映射

| GAP 根因 | 对应 Phase |
|---|---|
| 1. 单位口径层缺失 | P0 |
| 2. 透视引擎缺失（差异/重拆/产线） | P1 |
| 3. 历史台账逻辑缺失 | P4 |
| 4. 实际确收列未利用 | P0 |
| 5. 趋势行映射错位 | P2 |
| 6. 账期透传 bug | P2 / P5 |

### 2.2 Q1–Q8 → Phase 映射

| 确认项 | Phase |
|---|---|
| Q1 偏差归因 | P2 |
| Q2 分桶引擎 | P3 |
| Q3 跨期继承 | P3 |
| Q4 消失口径 | P2（预警清单） |
| Q5 同比区 | P5 |
| Q6/Q7 台账快照 | P4 |
| Q8 年度目标 + 预测 | P7 |

### 2.3 Phase 总表

| Phase | 内容 | PRD 验收 | 依赖 | 预计 |
|---|---|---|---|---|
| **P0** | 导入层补齐 93 列 + 单位层 | A1, A2, A3 | — | 1.0d |
| **P1** | 透视引擎（差异/重拆/产线） | A4, A5 | P0 | 1.5d |
| **P2** | 趋势修正 + Q1 归因引擎 + Q4 预警 | A6, A7 | P0 | 2.0d |
| **P3** | Q2 分桶引擎 + Q3 跨期继承 | 分桶测试 | P0, P2 | 2.5d |
| **P4** | F7 台账时序 + Q6/Q7 快照 | A9 | P0, P3 | 2.0d |
| **P5** | F6 汇总分析完整化 + Q5 同比 | A8 | P4 | 2.0d |
| **P6** | F8 图例重建 + F9 概览/导出 | A10, A11, A12 | P0–P5 | 2.0d |
| **P7** | Q8 年度目标 + 预测模型 | 预测测试 | P5 | 1.5d |
| | **合计** | | | **14.5d** |

> 每 Phase 收尾：独立测试 + 全量回归（456 passed 基线）+ commit（隔离 index）。

---

## 3. P0 — 导入层补齐 + 单位层（F1 + F2）

### 3.1 目标
- 预算执行表导入覆盖 **93 列**（202606 权威映射），实际确收列（AL–AQ）不再恒 0
- 分析/透视/台账/汇总 sheet 导出单位统一 **万元**（内部仍元，仅展示层转换）

### 3.2 涉及文件

| 文件 | 动作 | 说明 |
|---|---|---|
| `config.py` | 修改 | 新增 `BUDGET_COLUMNS_202606`（93 列 A–CO）+ `BUDGET_COLUMNS_202609`（现状 45 列保留兼容）；`ACTUAL_MONTHS` 按账期参数化 |
| `importer.py` | 修改 | `import_budget_exec` 表头自适应已支持 93 列；增加实际列/偏差列（BA–CO）映射；`zero_semantic` 标记保留 |
| `exporter.py` | 修改 | 新增单位转换层：`_to_wan(v)`（元→万元，2 位小数）；分析/透视/台账/汇总 sheet 应用；预算执行表/底稿保持元 |
| `engine.py` | 修改 | `_build_summary` 等分析层构建函数输出元，由 exporter 统一转万元（不回写） |
| `tests/test_revenue_analysis_p0_import_unit.py` | 新建 | 导入 93 列断言 + 单位转换断言 |

### 3.3 任务项
1. config 扩展 93 列映射（依据 DESIGN-DETAIL v1.1 §9）
2. importer 验证 202606 黄金文件导入后有效列 ≥ 90、行数差 ≤ 2
3. exporter 单位层：`_to_wan` + 各 sheet 应用
4. 测试：A1（列数/非空率）、A2（行数差）、A3（汇总逐格误差 ≤1e-6）

### 3.4 验收
- A1：预算执行表导入后有效列 ≥ 90；实际确收列非空率与 golden 一致（±0.5%）
- A2：底稿/预算行数与 golden 差异 ≤ 2，差异行入校验报告不静默
- A3：「汇总」逐格与 golden 比对，金额格相对误差 ≤ 1e-6，完成率绝对误差 ≤ 1e-6

### 3.5 复用
R1 HeaderMapper、R2 RR_SCHEMA、R11 config

---

## 4. P1 — 透视引擎（F3 + F4）

### 4.1 目标
- 差异分析：按原因类别（7 类）× 新签/递延 聚合滞后未完成（golden 8 行 + 总计 = 170.58 万）
- 重拆履约：合同级提前/滞后同增清单（golden 6 合同，提前 253.20 / 滞后 181.50 万）
- 产线展开：为 P5 汇总分析产线 9 列提供 group-by 能力

### 4.2 涉及文件

| 文件 | 动作 | 说明 |
|---|---|---|
| `pivot_builder.py` | **新建** | 通用 group-by 透视：`pivot(rows, key_fn, value_fn, filter_fn)` |
| `engine.py` | 修改 | `_build_diff` / `_build_restructure` 重写为调用 pivot_builder；修正标题账期透传（GAP 根因 6） |
| `tests/test_revenue_analysis_p1_pivot.py` | 新建 | 8 类原因 + 总计逐格；6 合同逐行 |

### 4.3 任务项
1. pivot_builder 实现（纯函数，无副作用）
2. `_build_diff` 重写：筛选 col45=空白 → col36 按 col63×col0 求和（实证规则）
3. `_build_restructure` 重写：按合同编号聚合提前/滞后
4. 标题账期参数化（`202601-{MM}` 由 period 驱动）
5. 测试：A4、A5

### 4.4 验收
- A4：8 行类别 + 总计逐格对齐 golden（170.58 万，abs 0.01 万）；筛选条件行结构一致
- A5：合同编号 + 金额逐行对齐；总计 提前 253.20 / 滞后 181.50 万

### 4.5 复用
R3 BaseEngine、R9 validator

---

## 5. P2 — 趋势修正 + Q1 归因引擎 + Q4 预警（F5 + Q1 + Q4）

### 5.1 目标
- 预算趋势分析 19 行模板严格映射（修正 GAP 根因 5：row_index 偏移、标签错位）
- Q1 偏差状态/原因**自动归因引擎**：仅两条硬规则，其余留空 + 人工校验清单
- Q4 新签消失预警清单（汇率差等）

### 5.2 涉及文件

| 文件 | 动作 | 说明 |
|---|---|---|
| `trend_builder.py` | 修改 | 修正 row_index → golden 19 行模板对齐；R18/R19 标签修正 |
| `attribution_engine.py` | **新建** | Q1 归因引擎：`compute_attribution(period)` → 触发条件 → 硬规则 → 留空清单 |
| `engine.py` | 修改 | `compute_budget_trend` 调用修正；`compute` 集成归因结果 |
| `service.py` | 修改 | 新增 `attribution(period)` / `alerts(period)` |
| `tests/test_revenue_analysis_p2_trend_attribution.py` | 新建 | 趋势 19 行 + 归因 106 触发行 |

### 5.3 归因引擎规则（DESIGN-DETAIL v1.1 §2）
- 触发：`AK>0` 或 `AI<0`
- 硬规则 1：`AT=合同终止` → BL=`客户原因-终止`
- 硬规则 2：`BF=3：交付异常` → BK=`差异确收（异常项目）` + BL=`综合原因-项目异常`
- 未命中 → **留空** + 待人工清单（附上下文特征矩阵）
- 校验：BK 非空 ⇔ BL 非空

### 5.4 任务项
1. trend_builder row_index 修正 + R19 确收率重算
2. attribution_engine 实现（两条硬规则 + 留空清单）
3. Q4 预警：新签消失行（分类=新签 且 AR/AS≠0）→ 预警清单 + 底稿 N 备注上下文
4. 测试：A6、A7 + 归因用例

### 5.5 验收
- A6：R4–R18 计数、金额对齐 golden（如 R18 期初 2,075 合同 / 19,122.57 万）
- A7：R19 新签预计确收率与 golden 一致
- 归因：106 触发行正确识别；AT=终止 → 客户原因-终止；BF=异常 → 异常项目；其余留空入清单

### 5.6 复用
R8 trend_builder、R11 config（FILL_STATUS/TREND_CATEGORY_MAP）

---

## 6. P3 — Q2 分桶引擎 + Q3 跨期继承

### 6.1 目标
- 预算填报（BQ）/预算趋势（BU）**分桶引擎**：上期继承优先 + 7 桶规则 + 留空提示
- Q3 跨期继承：按履约 ID 继承上期桶 + 本期人工改判
- 集成 OA/ONES 现成连接器（不重造）

### 6.2 涉及文件

| 文件 | 动作 | 说明 |
|---|---|---|
| `bucket_engine.py` | **新建** | `compute_buckets(period, prev_period)` → 继承/规则/留空 |
| `engine.py` | 修改 | `compute` 集成分桶结果 |
| `service.py` | 修改 | 新增 `buckets(period)` |
| `tests/test_revenue_analysis_p3_bucket.py` | 新建 | 继承 8058/8062 + 规则 + fail-closed |

### 6.3 分桶规则（DESIGN-DETAIL v1.1 §3）
- 优先级：合同消失 > 已归档但未下单 > 已下单但无法交付 > 已交付但无法确收 > 未来可确收 > 之前年度已确收 > 本年度正常可确收
- 信号源：OA 下单（R4）+ ONES 匹配（R5）+ BF 周报状态 + BX 预估日期
- 上期有值 → 继承；上期无值 → 规则；规则未覆盖 → **留空 + 提示**
- **fail-closed**：任一信号源缺失 → 该行留空 + 提示，不推断

### 6.4 任务项
1. bucket_engine 实现（继承 + 规则 + 优先级）
2. OA/ONES connector 调用封装（认证/缺失 fail-closed）
3. 分桶结果持久化（`ra_bucket` 表，DESIGN-DETAIL v1.1 §10.1）
4. 测试：继承行数、规则分桶、留空清单、fail-closed

### 6.5 验收
- 上期继承：8058/8062 行继承 202605（202606 实证）
- 规则分桶：OA/ONES/BF 信号正确分类
- 规则未覆盖：留空 + 人工清单
- 信号源缺失：fail-closed 报错，不伪造

### 6.6 复用
R4 OaConnector、R5 OnesConnector、R11 config

---

## 7. P4 — 台账时序（F7 + Q6/Q7）

### 7.1 目标
- 月度汇总记录：统计期 × 合同期交叉台账（golden 266×11，19 统计期 × 12 合同期）
- 履约汇总记录：每期 7 行（golden 126×6，18 期历史）
- Q6 连续性：每期生成后自动 upsert 快照，缺月告警
- Q7 跨期重述：重述只影响当期，历史快照不可变

### 7.2 涉及文件

| 文件 | 动作 | 说明 |
|---|---|---|
| `ledger_engine.py` | **新建** | 台账构建 + 快照 upsert + 连续性检查 |
| `engine.py` | 修改 | `_build_monthly_record` / `_build_perf_record` 重写为时序台账（修复 GAP 根因 3：整表预算行灌入） |
| `service.py` | 修改 | 新增 `snapshot(period)` |
| `tests/test_revenue_analysis_p4_ledger.py` | 新建 | 202605/202606 两期逐格 + 幂等 |

### 7.3 关键口径（DESIGN-DETAIL v1.1 §7）
- 月度台账：`(统计期间, 合同期间)` 唯一，每期 upsert
- 历史统计期行**不回写**（快照不可变）
- 重述只影响**当期**写入的行
- 缺月检测：上一统计期非连续 → 警告日志 + Web 提示

### 7.4 任务项
1. ledger_engine 实现（构建 + upsert + 连续性检查）
2. `_build_monthly_record` 重写：按 (统计期, 合同期) 交叉聚合（新签/递延 × 预计/实际）
3. `_build_perf_record` 重写：每期 7 行（分类 × 预计/实际/完成率）
4. 快照持久化（`ra_snapshot` 表）
5. 测试：A9

### 7.5 验收
- A9：202605/202606 两期台账逐格对齐 golden；重跑 2 期行数、金额零变化（幂等）

### 7.6 复用
R2 RR_SCHEMA、R3 BaseEngine

---

## 8. P5 — 汇总分析完整化 + Q5 同比（F6）

### 8.1 目标
- 汇总分析 64×50 完整重建：月度主体 + 同比区（Y26/Y25/增长率/确收度增长）+ 产线 9 列展开 + 年度目标差距
- Q5 同比区：从月度汇总记录取去年同期（实证 `SUMIFS` 口径）

### 8.2 涉及文件

| 文件 | 动作 | 说明 |
|---|---|---|
| `engine.py` | 修改 | `_build_summary_analysis` 重写为 64×50 完整结构 |
| `tests/test_revenue_analysis_p5_summary_analysis.py` | 新建 | 64×50 结构 + 同比 5 指标 + 年度目标 |

### 8.3 结构（golden 实证）
- 月度主体：R2–R17（12 个月 + 小计 + 合计）
- 同比区：V6:AD6（Y25 同期）+ AG6:AP19（月度新签同比）
- 产线展开：9 列（所属产线 CO）
- 年度目标：C21/F21/AI21 读取 `ra_annual_target`

### 8.4 任务项
1. `_build_summary_analysis` 重写（64×50）
2. 同比区：从月度台账取去年同期（`SUMIFS` 等价逻辑）
3. 产线展开：按 CO 所属产线 group-by
4. 年度目标差距：锁定预计 vs 目标
5. 测试：A8

### 8.5 验收
- A8：64×50；同比 5 指标与 golden 一致；年度目标 23,000、差距自动算

### 8.6 复用
R6 md_reference（产线）、P1 pivot_builder（产线 group-by）、P4 ledger_engine（同比数据源）

---

## 9. P6 — 图例重建 + 概览/导出（F8 + F9）

### 9.1 目标
- 图例 506×16 重建：PM 名册 33 人 + 偏差/验收/团队产线 4 段枚举（数据源 md_reference）
- 概览输出：锁定/动态/实际/差距 + 提前·滞后·消失 + 未来确收
- 导出 10 Sheet 完整 + 真实 HTTP 端到端

### 9.2 涉及文件

| 文件 | 动作 | 说明 |
|---|---|---|
| `engine.py` | 修改 | `_build_legend` 重写（从 md_reference 聚合）；`_build_summary` 补齐 R20–R28 履约维度 |
| `exporter.py` | 修改 | 10 sheet 导出完整性 + 样式（`#,##0.00` 万元） |
| `service.py` | 修改 | `overview(period)` 输出 |
| `tests/test_revenue_analysis_p6_legend_export.py` | 新建 | 图例 506×16 + 导出 10 sheet + 真实 HTTP |

### 9.3 任务项
1. `_build_legend` 重写：md_reference 聚合（PM 33 人 + 枚举段）
2. `_build_summary` 补齐 R20–R28（提前/滞后/消失/校验）
3. exporter 10 sheet 完整性 + 单位层 + 样式
4. overview 输出（双口径 + 差异 + 风险清单）
5. 真实 HTTP 端到端测试（非 TestClient）
6. 测试：A10、A11、A12

### 9.4 验收
- A10：PM 段 33 人逐行一致；枚举段与 golden 行数差 ≤ 2
- A11：真实 HTTP 端到端（非 TestClient）；长任务 job 进度 25/55/75/95/100
- A12：失败 fail-closed，保留上期结果；不新增第三方依赖

### 9.5 复用
R6 md_reference、R10 exporter、R12 测试骨架

---

## 10. P7 — Q8 年度目标 + 预测模型

### 10.1 目标
- 年度目标独立维护（人工填写，不写死代码）
- 预测模型：双口径 + future 桶 + 实际达成 + 差距 + 风险清单

### 10.2 涉及文件

| 文件 | 动作 | 说明 |
|---|---|---|
| `forecast_engine.py` | **新建** | 预测模型（独立于归因/分桶） |
| `service.py` | 修改 | 新增 `set_annual_target` / `get_annual_target` / `forecast(period)` |
| `tests/test_revenue_analysis_p7_forecast.py` | 新建 | 目标维护 + 预测输出 |

### 10.3 任务项
1. `ra_annual_target` 表 + service 维护方法
2. forecast_engine：锁定/动态 + future + 实际 + 差距 + 风险
3. CLI：`bdms revenue-analysis target set/get`
4. 测试：目标维护 + 预测输出

### 10.4 验收
- 年度目标可人工填写/编辑（Web + CLI）
- 预测输出含双口径、future、实际、差距、风险清单
- 汇总分析 C21/F21/AI21 读取目标值

### 10.5 复用
R3 BaseService、P5 汇总分析

---

## 11. 里程碑与交付节奏

| 里程碑 | Phase | 交付物 | 验收 | 预计 |
|---|---|---|---|---|
| M1 | P0 | 93 列导入 + 单位层 | A1/A2/A3 | 1.0d |
| M2 | P1 | 透视引擎 | A4/A5 | 1.5d |
| M3 | P2 | 趋势 + 归因 + 预警 | A6/A7 + 归因 | 2.0d |
| M4 | P3 | 分桶 + 继承 | 分桶测试 | 2.5d |
| M5 | P4 | 台账时序 | A9 | 2.0d |
| M6 | P5 | 汇总分析 + 同比 | A8 | 2.0d |
| M7 | P6 | 图例 + 概览/导出 | A10/A11/A12 | 2.0d |
| M8 | P7 | 年度目标 + 预测 | 预测测试 | 1.5d |

**每里程碑收尾**：
1. 独立测试（新 phase 测试文件）
2. 全量回归（`456 passed` 基线不破）
3. commit（隔离 index，仅本 phase 文件）
4. 更新 `DEVELOPMENT-TRACKING` 状态

---

## 12. 测试策略

### 12.1 分层

| 层 | 内容 | 工具 |
|---|---|---|
| 单元 | 各 builder/engine 纯函数 | pytest |
| 集成 | import → compute → export 全链路 | pytest + 真实 xlsx |
| E2E | 真实 HTTP（非 TestClient） | pytest + requests |
| 黄金回归 | 202606 逐 sheet 逐格对比 | 自定义比对脚本 |

### 12.2 黄金回归锚点（202606）

| 锚点 | 值 |
|---|---|
| 触发行数 | 106 |
| 差异透视总计 | 170.58 万 |
| 重拆履约滞后 | 181.50 万 |
| Y25 同比 | V6=7292.814 / W6=2192.802 |
| 台账快照 | 202605/202606 逐格 |
| 锁定口径 | 119,085,304.74 元 = 11,908.53 万 |

### 12.3 回归基线
- 现有：`456 passed, 16 skipped, 2 deselected`
- 每 phase 后：全量回归不破基线

---

## 13. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 93 列映射与 202609 列结构差异 | 导入断裂 | 表头自适应（R1）+ 双套映射（202606/202609） |
| Q1 归因覆盖率低 | 自动归因行数少 | **设计允许留空 + 人工校验**；上下文矩阵辅助 |
| OA/ONES connector 认证失败 | 分桶 fail-closed | 报错 + 提示，不伪造 |
| 台账历史数据缺失 | 同比/继承无法算 | fail-closed + 提示；历史台账从快照恢复 |
| 单位转换层遗漏 | 导出仍元 | exporter 统一 `_to_wan` + 逐 sheet 断言 |
| 测试基线回归 | 破 456 passed | 每 phase 全量回归 + 隔离 index commit |

---

## 14. 变更历史

- 2026-11-10: v1.0 — 初版 M1–M4（未含 Q1–Q8）
- 2026-11-12: v1.1 — 对齐 DESIGN-DETAIL v1.1（Q1–Q8）+ GAP 6 类根因；拆为 P0–P7；补复用资产清单（Rex 2026-11-12 指令）
