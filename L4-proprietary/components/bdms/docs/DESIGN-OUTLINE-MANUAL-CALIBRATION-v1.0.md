# DESIGN-OUTLINE — BDMS 人工数据校准与填写 v1.0

> 状态：**待 Rex 审核** | 作者：Jerry 🦞 | 日期：2026-10-28
> 依据：`PRD-MANUAL-CALIBRATION-v1.0.md`（已通过）
> 范围：交付月报模块（delivery_report）域内，新增校准能力
> 文档铁律：本大纲通过后才进入 DESIGN-DETAIL。

---

## 0. 设计定位

在**不重写交付月报模块**的前提下，为其增加一层独立的「人工校准能力」。
核心约束：原始数据 `dr_sheet_row.data` 永远只读，所有报表读取与导出统一经过
一个**校准解析层**，使校准值在「界面 / 校验 / 导出」三处口径一致。

设计采取**旁路增量**而非侵入改造：
- 校准数据独立存储（新表 `dr_calibration`），与原始行数据解耦；
- 现有 engine / validator / exporter 通过一个新组件 `CalibrationService`
  获得「有效数据集」，自身的核心算法保持不变；
- 仅废弃一条破坏性旧路径（`apply_manual_fixes`）。

---

## 1. 设计目标与原则

### 1.1 目标
1. 原值不可变：任何校准不修改 `dr_sheet_row.data`。
2. 单一事实口径：界面展示、重校验、Excel 导出共用同一「校准解析」入口。
3. 可溯可撤销：每条校准留痕（原值/新值/人/时间/原因），支持撤销与修改。
4. 自动闭环：保存校准后自动增量重校验并流转问题状态。
5. 最小侵入：复用现有 validator 规则、exporter 写出、job 异步框架。

### 1.2 原则
- **组合优于继承**：以 `CalibrationService` 被各组件依赖，不改动 Base 层契约。
- **增量优于全量**：重校验只跑受影响 Sheet/行，避免 25k 问题全量重跑。
- **默认安全**：approved 月报锁定校准；写操作走显式校验 + 留痕。
- **可逆优先**：所有改动可通过撤销校准回滚。

---

## 2. 整体架构

### 2.1 分层视图（交付月报域）

```
┌─────────────────────────────────────────────────────────────┐
│  Web 层  report.html（问题校准对话框 / 数据浏览编辑模式）        │
│          api.py（新增校准路由，复用 job 轮询）                   │
└───────────────┬─────────────────────────────────────────────┘
                │ HTTP / JSON
┌───────────────▼─────────────────────────────────────────────┐
│  Service 层                                                 │
│   DeliveryReportService（现有，扩展校准编排）                   │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ CalibrationService（新增）                            │   │
│   │  · apply_overlays(raw) → effective  校准解析          │   │
│   │  · upsert / revoke / history        校准写与留痕       │   │
│   │  · ledger(month)                    台账数据          │   │
│   └─────────────────────────────────────────────────────┘   │
└───────┬───────────────┬───────────────┬─────────────────────┘
        │               │               │
┌───────▼──────┐ ┌──────▼──────┐ ┌──────▼──────────────────────┐
│ Validator    │ │ Engine      │ │ Exporter                    │
│ (现有规则)    │ │ (现有加载)   │ │ (现有写出 + 新增校准台账Sheet) │
│ 输入=有效数据集│ │ load 经解析层│ │ 输入=有效数据集              │
└──────────────┘ └─────────────┘ └─────────────────────────────┘
        │               │               │
┌───────▼───────────────▼───────────────▼─────────────────────┐
│  数据层  bdms.db                                             │
│   dr_sheet_row（原始，只读）  dr_import_validation（问题）      │
│   dr_calibration（新增，校准覆盖层 + 留痕）                     │
│   dr_review_status（现有，状态/KPI）                           │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 关键设计：统一校准解析层

`CalibrationService.apply_overlays(month, raw_sheets)` 是唯一口径入口：
- 输入：engine 从 `dr_sheet_row` 读出的原始 DataFrame 集合；
- 处理：把该月**生效**校准按 `(sheet, row_index, column)` 覆盖到对应单元格；
- 输出：**有效数据集**（effective），供界面、validator、exporter 共同使用。

> 红线：禁止任何模块绕过该层直接读 `dr_sheet_row` 后对外呈现/导出。
> DETAILED 阶段将 grep 所有读取调用点，强制收口到这一层。

---

## 3. 模块划分

### 3.1 新增组件

| 组件 | 位置（建议） | 职责 |
|---|---|---|
| **CalibrationService** | `modules/delivery_report/calibration.py` | 校准 CRUD、覆盖层应用、留痕快照、台账组装、类型/枚举校验 |
| **校准存储** | `core/db.py`（新增表访问助手） | `dr_calibration` 表的读写（沿用现有 `_db` 助手风格） |
| **校准 API 路由** | `web/api.py` | 提交/撤销/修改/记录查询/台账导出；复用 job 轮询 |
| **校准对话框 + 编辑模式** | `templates/report.html` | 问题清单校准弹窗、数据浏览行内编辑 |

### 3.2 复用 / 微调组件

| 组件 | 改动 |
|---|---|
| `DeliveryReportEngine.load` | 增加经校准解析层返回有效数据集的选项（保留 raw 读取能力供对比/审计） |
| `DeliveryReportValidator` | 规则不变；输入改用有效数据集；**废弃** `apply_manual_fixes` |
| `DeliveryReportExporter` | 主体写有效数据集；新增「校准台账」Sheet + 单元格标记 |
| `DeliveryReportService` | 新增校准编排方法；`revalidate` 基于有效数据集；`apply_fixes` 改走覆盖层或移除 |
| job 异步框架 | 大批量重校验走 job + 前端轮询（沿用生成月报机制） |

### 3.3 模块依赖关系

```
api.py
  └─ DeliveryReportService
       ├─ CalibrationService ── db helpers (dr_calibration)
       ├─ Engine.load ──(raw)── CalibrationService.apply_overlays ── effective
       ├─ Validator.collect_suspicious(effective)
       └─ Exporter.export(effective + ledger)
```
依赖单向向下；CalibrationService 不依赖 validator/exporter，可独立单测。

---

## 4. 数据流

### 4.1 提交校准（主路径，P0）
```
用户在问题清单点「校准」→ 填校准值+原因 → POST /calibrations
  1. 校验：月报未 approved（BR-06）、类型/枚举合法（BR-03/04）、原因非空（BR-02）
  2. CalibrationService.upsert：
       - 读原值；若已有生效校准，旧值入快照
       - 写 dr_calibration（原值/新值/人/时间/原因/状态=active）
       - 回填对应 dr_import_validation.corrected_value
  3. 自动重校验（增量，受影响 Sheet/行）：
       - engine 取 raw → apply_overlays → effective
       - validator 重跑受影响规则
       - 问题流转 confirmed/pending，重算 review_status KPI
  4. 返回结果（小批量同步；大批量返回 job_id 走轮询）
```

### 4.2 撤销 / 修改校准
- 撤销：校准条目置 `revoked`（保留快照），删覆盖效果 → 重校验。
- 修改：旧校准值入快照，写新值 → 重校验。

### 4.3 导出
- effective 数据集写各 Sheet（已校准单元格加标记）；
- 追加「校准台账」Sheet（当月全部 active 校准）。

### 4.4 补填空值
- 与 4.1 同路径，仅原值为空；非空规则重跑后问题转 confirmed。

---

## 5. 数据架构（概要，详细字段在 DETAILED）

### 5.1 新增表 `dr_calibration`（倾向方案，名称 DETAILED 最终确认）

| 字段（概要） | 说明 |
|---|---|
| id | 主键 |
| month / sheet / row_index / column_name | 唯一定位单元格 |
| original_value | 提交时的原始值快照（来自 dr_sheet_row） |
| corrected_value | 当前生效校准值 |
| reason | 校准原因（必填） |
| operator | 操作人 |
| status | active / revoked |
| previous_value | 上一条校准值快照（修改时留痕） |
| created_at / updated_at / resolved_at | 时间戳 |

约束：`(month, sheet, row_index, column_name)` 同一时刻至多一条 `active`。

### 5.2 现有表关系
- `dr_sheet_row`：**只读**，不新增写路径。
- `dr_import_validation`：同步 `corrected_value` 便于问题视图；状态由重校验驱动。
- `dr_review_status`：KPI（total_errors / pending_fixes）由每次重校验重算。

### 5.3 表设计原则
沿用 v2.1 统一 DB、显式 schema、`_db` 助手访问；不引入 ORM；迁移用幂等建表（CREATE TABLE IF NOT EXISTS），保证重复执行安全。

---

## 6. 接口与 API 概要（契约细节在 DETAILED）

| 方法 | 路径（拟） | 用途 |
|---|---|---|
| POST | `/api/report/calibrations/{month}` | 提交/修改校准（单条；可含批量小数组） |
| POST | `/api/report/calibrations/{month}/revoke` | 撤销校准 |
| GET | `/api/report/calibrations/{month}` | 查询校准记录（支持按 sheet/行/状态过滤） |
| GET | `/api/report/calibrations/{month}/overview` | 校准总览/KPI |
| GET | `/api/report/sheets/{month}` | 动态返回当月实际 Sheet 列表（补齐 15） |
| POST | `/api/report/revalidate-calibration/{month}` | 触发重校验（大批量返回 job_id） |
| GET | `/api/report/calibration-ledger/{month}` | 校准台账（导出/预览） |

> 已有的 review-issues / resolve / batch-resolve / approve / reject / export 保留。

---

## 7. 前端概要

- **问题清单**：每条问题加「校准」按钮 → 对话框（原值只读 + 校准值 + 原因必填）。
- **数据浏览**：
  - Sheet 下拉改为 `/report/sheets/{month}` 动态填充；
  - 「进入编辑」后单元格可点选发起校准，复用同一对话框；
  - 已校准单元格有视觉标记 + 可查记录。
- **反馈**：保存后 toast；大批量重校验显示分步进度条（遵守进度条铁律）。

---

## 8. 旧路径收敛（破坏性方法处理）

排查确认的破坏性链路：
```
service.apply_fixes() (service.py:775)
  └─ validator.apply_manual_fixes() (validator.py:191)   ← 直接 UPDATE dr_sheet_row
        ↑ 另在 service.py:756 被内部调用
```
收敛动作（DETAILED 给契约、开发期执行）：
1. grep 全代码库确认无 Web/CLI 外部入口依赖该方法；
2. `apply_fixes` 改走 `CalibrationService` 覆盖层；`apply_manual_fixes` 标记废弃/删除；
3. 增加测试锁定「原始行不可变」。

---

## 9. 风险与对策

| 风险 | 对策 |
|---|---|
| 多读取路径绕过解析层导致口径不一 | 统一入口 + grep 调用点收口 + 回归测试 |
| 全量重校验慢 | 增量重跑受影响范围；大批量异步 job + 进度条 |
| 校准与问题行错位（行号变化） | 以生成期固定 row_index 定位；重新生成月报时校准按既定策略处理（DETAILED 明确：重生成默认使校准失效并提示） |
| approved 后误改 | BR-06 锁定，需先驳回 |
| 枚举集合动态变化 | 校准保存时实时取主数据 legend 校验 |

---

## 10. 实施阶段（粗，工时在 IMPLEMENTATION-PLAN）

- **P1 基础**：建 `dr_calibration` + db 助手 + CalibrationService（覆盖应用/留痕）。
- **P2 校准闭环**：提交/撤销/修改 API + 自动增量重校验 + 问题流转。
- **P3 前端**：校准对话框 + 问题清单接入 + 校准总览。
- **P4 浏览增强**：动态 Sheet（15）+ 数据浏览编辑模式。
- **P5 导出**：effective 导出 + 校准台账 Sheet + 单元格标记。
- **P6 收敛**：废弃 apply_manual_fixes、调用点收口、E2E 与幂等验收。

每阶段产出可验证结果；进入 DETAILED 前需 Rex 对本大纲明确「通过」。

---

## 变更记录

- 2026-10-28 v1.0：Jerry 初稿，依据已通过 PRD，核心为统一校准解析层 + 旁路增量。
