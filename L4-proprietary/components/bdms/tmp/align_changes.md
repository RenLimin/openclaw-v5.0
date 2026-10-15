# BDMS 文档-代码一致性对齐（混合方案 C）— 修改记录

执行时间：2026-10-14（13:54~）
依据：`tmp/docs_audit_report.md` 差异清单，最小变更，不重构现有逻辑。

## 1. 代码变更

### 1a. 新建 `src/bdms/modules/revenue/exporter.py`
- 新增类 `RevenueReportExporter`：`__init__(self, db_path: Optional[Path] = None)` / `export(self, month, out_path=None) -> Path`
- 将原 `src/bdms/web/api.py` revenue_export 内联 Excel 导出逻辑（汇总表 Sheet + 月度趋势 Sheet，openpyxl 样式）原样迁移，`out_path` 缺省时输出到 `paths.month_dir(month)/确收汇总_{month}.xlsx`
- 新增 `RevenueSummaryError(ValueError)`：汇总数据不可用时抛出，对应原 HTTP 400 语义
- 验证：`from bdms.modules.revenue.exporter import RevenueReportExporter` ✓；导出逻辑与原 api.py 内联逻辑行为一致（含原 openpyxl dict 值兼容性行为，未引入回归）

### 1b. `src/bdms/modules/revenue/importer.py` 追加 `UnifiedRevenueImporter`
- 文档契约：import_budget_exec / import_plan_draft / import_summary / import_all，均 `(excel_path, month) -> dict`
- `self._imp = AdaptiveImporter(db_path)`；import_budget_exec / import_plan_draft 直接委托
- import_summary：现有 importer.py 无对应逻辑，实现为读取「汇总表」sheet 的通用导入（写入 revenue_summary 表：period/summary_json/comparison_source）
- import_all：依次调用三个方法返回 dict
- 验证：`from bdms.modules.revenue.importer import UnifiedRevenueImporter` ✓；四个方法均存在 ✓

### 1c. `src/bdms/web/api.py` revenue_export 改调 RevenueReportExporter
- HTTP 行为不变：RevenueSummaryError → 400（原 summary error → 400）；其余异常 → 500「导出失败」
- 验证：`import bdms.web.api; import bdms.web.api_v2` → API_OK ✓

### 2a. 新建 `src/bdms/modules/profit_management/budget_alert.py`
- 类 `BudgetAlertService`：`__init__(self, db_path=None)` / `check(self, project_id, threshold=0.10)` 委托 `ProfitEngine(db_path).check_budget_alert(project_id, threshold)`，薄封装无新增业务逻辑
- 验证：`from bdms.modules.profit_management import BudgetAlertService` ✓

### 2b. 新建 `src/bdms/modules/profit_management/importer.py`
- 类 `ProfitImporter`：薄封装 ProfitService（先读 service.py 确认签名：submit_timesheet / approve_timesheet / import_travel_cost(project_id, file_path, operator)）
- 方法对齐文档契约：import_timesheet（委托 submit_timesheet 逐行提交）/ import_travel_cost / import_all（当前聚合 travel_cost；工时批量文件导入待建设）
- 验证：`from bdms.modules.profit_management import ProfitImporter` ✓

### 2c. `src/bdms/modules/profit_management/__init__.py` 导出新增类
- `__all__` 增加 BudgetAlertService / ProfitImporter

## 2. 文档同步（以代码为准）

### 3a. DESIGN-DETAIL-DELIVERY-REPORT-v2.1.md
- §1.5 文件结构：stats_builders_c.py 行移除，标注统计 Sheet 结构定义已内联至 engine.py
- §2 前新增实现状态说明：四个核心类实际直接实现，未继承 Base 基类；stats_builders_c.py 不存在（已内联 engine.py）
- §8 复用资产清单：stats_builders_c 行改为「已内联至 engine.py」；BaseEngine/BaseService/BaseExporter 行改为「实际未继承，直接实现」

### 3b. DESIGN-DETAIL-INTEGRATION-v2.1.md
- §6.1 ONES：标注「浏览器自动化已实现（Playwright CDP 自动新开 Chrome，含还原视图+导出）」；CLI 子命令/幂等写入/企微API 标注「待建设（见 INTEGRATION-DEVELOPMENT-TRACKING.md）」
- §6.4 企微降级链：更新为实际顺序（file_path 本机导入 → 月度目录 CSV → 缓存 CSV → 企微 API（待授权）→ 浏览器自动化（已实现可用））

### 3c. DESIGN-DETAIL-REVENUE-v2.1.md
- §3.3 RevenueReportExporter / §3.4 UnifiedRevenueImporter：标注「已实现」，注明文件路径与「签名以实际为准」

### 3d. DESIGN-DETAIL-PROFIT-MANAGEMENT-v2.1.md
- §3.3 BudgetAlertService / §3.4 ProfitImporter：标注「已实现」，注明文件路径与「签名以实际为准」

### 3e. DESIGN-DETAIL-DASHBOARD-v2.1.md
- §6.1 summary/trend 方法、§6.5 Web API 路由、§17 CLI/Web API：更新为「engine 已实现 compute_monthly_trend，service/Web 未暴露 summary/trend 端点（以代码为准）」

### 3f. `src/bdms/core/schemas_v21.py`
- CR_SCHEMA 末尾补 `cr_import_validation` DDL（先 PRAGMA table_info 查 data/bdms.db 实际结构后补录，与 DB 一致：batch_no/row_index/sheet_name/rule_code/severity/column_name/original_value/message/corrected_*/status/created_at）
- pf_cost_item / pf_budget_alert / pf_cash_flow / pf_cost_overhead / dash_snapshot：加注释「⚠️ 预留表，暂未接入业务」

## 3. 验证结果

1. `from bdms.modules.revenue.exporter import RevenueReportExporter; from bdms.modules.revenue.importer import UnifiedRevenueImporter; from bdms.modules.profit_management import BudgetAlertService, ProfitImporter` → **IMPORT_OK** ✓
2. `import bdms.web.api; import bdms.web.api_v2` → **API_OK** ✓
3. `PYTHONPATH=src python3 -m pytest tests/ -q`（pytest-timeout 未安装，去掉 --timeout；测试不依赖外部服务）→ **322 passed** ✓
4. `git diff --name-only`：未改 delivery_report/、dashboard/engine.py、tests/、tools/ 下任何文件 ✓（dashboard/delivery_report_connector.py 与 L2-infra 的 check_and_retry.py 为先前会话遗留的工作区改动，本次未触碰）

## 4. 未完成项 / 说明
- revenue import_summary 写入新建 revenue_summary 表（轻量通用导入），未接入现有月度汇总计算链路（该链路由 revenue-recognition 引擎维护，属于集成待建项，不改动）
- ProfitImporter.import_timesheet 为逐行委托 submit_timesheet 的薄封装；批量工时文件导入待建设（INTEGRATION-DEVELOPMENT-TRACKING.md 记录）
- 未改 delivery_report 业务逻辑、未改 DB 现有表结构、未删任何现有功能
