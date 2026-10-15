# BDMS v2.1 设计文档 vs 代码资产一致性审计报告

审计时间：2026-10-14
审计方式：只读核对，不修改代码
审计范围：7个设计声称模块 + 核心架构 + DB Schema + 测试工具

---

## A. 顶层一致性：模块存在性与依赖关系

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 7个设计声称模块目录存在 | ✅一致 | 7个模块(`contract_management`/`project_management`/`delivery_report`/`revenue`/`profit_management`/`dashboard`/`integration`)均存在，各模块均有实质代码。 |
| 额外模块存在 | ✅一致 | `master_data`/`settings`两个额外模块符合设计架构预留，不冲突。 |
| 依赖关系：`delivery_report`依赖`integration` → `revenue`依赖`delivery_report` → `profit_management`依赖`revenue` → `dashboard`只读各模块 | ✅一致 | 代码中跨模块引用与设计完全对齐：`dr_sheet_row`被`rr_sheet_row`引用，`revenue`结果被`profit_management`使用，`dashboard`读取所有模块宽表。 |
| 模块入口：所有模块均有`__init__.py`导出正确 | ✅一致 | 所有模块导出与设计文档一致，核心类均可正确导入。 |
| 模块架构分层：核心/业务/横切 | ✅一致 | 与设计文档分层对齐。 |

---

## B. 各模块接口契约核对

### B.1 `delivery_report`模块

| 检查项 | 状态 | 说明 | 证据 |
|--------|------|------|------|
| 15个Sheet导出功能存在 | ✅一致 | `SHEET_ORDER`文档声明与代码完全对齐，核心数据+统计Sheet+图例结构一致。 | 文档：`DESIGN-DETAIL-DELIVERY-REPORT-v2.1.md` §4.2；代码：`src/bdms/modules/delivery_report/engine.py:27` / `exporter.py:32` |
| 核心类：`DeliveryReportEngine`/`DeliveryReportService`/`DeliveryReportExporter`/`DeliveryReportValidator`存在 | ✅一致 | 四个核心类均存在，核心方法签名与文档一致：`compute`/`persist`/`load`/`generate`/`export`/`validate`/`apply_fixes`均实现。 | 代码：`engine.py:132`/`service.py:26`/`exporter.py:53`/`validator.py:41` |
| 核心类继承设计 | ⚠️差异 | 文档声称四个核心类继承`BaseEngine`/`BaseService`/`BaseExporter`/`BaseValidator`，实际均未继承。 | 文档：`DESIGN-DETAIL-DELIVERY-REPORT-v2.1.md` §1.5；代码：`delivery_report/*.py`类定义 |
| 统计Sheet对接dashboard连接器 | ✅一致 | 统计Sheet由`DeliveryReportConnector`实时聚合，代码与设计一致。 | 代码：`src/bdms/modules/delivery_report/exporter.py:84` |
| `stats_builders_c.py`文件存在 | ❌缺失 | 文档声称存在`stats_builders_c.py`存放C组统计结构定义，实际文件缺失，相关定义已内联到engine中。 | 文档：`DESIGN-DETAIL-DELIVERY-REPORT-v2.1.md` §1.5；`find src`无该文件 |

### B.2 `integration`模块

| 检查项 | 状态 | 说明 | 证据 |
|--------|------|------|------|
| 5个连接器存在(`ones`/`oa`/`timesheet`/`wecom_doc`/`local_import`) | ✅一致 | 5个连接器均已注册到`ConnectorRegistry`，名称与目标模块正确。 | 代码：`src/bdms/modules/integration/connectors/`各文件 |
| 浏览器自动化统一为Playwright | ✅一致 | 代码中已统一使用Playwright CDP方案，旧`osascript`相关适配器已标记deprecated，正确。 | 文档：`DESIGN-DETAIL-INTEGRATION-v2.1.md` §6；代码：`src/bdms/modules/integration/adapters/browser_adapter.py` |
| 企微文档连接器降级链优先级 | ⚠️差异 | 文档声称优先级：`API(优先) → 浏览器 → 本机导入`；实际代码优先级：`file_path → 本机预导出CSV → API(未实现)`，优先级顺序与文档不一致。 | 文档：`DESIGN-DETAIL-INTEGRATION-v2.1.md` §6.4；代码：`src/bdms/modules/integration/connectors/wecom_doc_connector.py:37`/`fetch`方法 |
| ONES浏览器自动化导出完整实现 | ⚠️差异 | 仅实现了查找缓存CSV功能，完整浏览器导出未实现，符合开发跟踪文档记录。 | 文档：`DESIGN-DETAIL-INTEGRATION-v2.1.md` §6.1；代码：`src/bdms/modules/integration/connectors/ones_connector.py:68`；`INTEGRATION-DEVELOPMENT-TRACKING.md` 1.1/1.2 |
| OA立项/结项审批导出 | ❌缺失 | 未实现，符合开发跟踪文档记录。 | `INTEGRATION-DEVELOPMENT-TRACKING.md` 1.4 |
| 企微API方案 | ❌缺失 | 未实现，仅返回空，符合开发跟踪文档记录。 | `INTEGRATION-DEVELOPMENT-TRACKING.md` 1.6 |
| 幂等写入 | ❌缺失 | 设计要求`source_id去重 + UPSERT + 变更日志`，未实现。 | `INTEGRATION-DEVELOPMENT-TRACKING.md` 3.3 |
| CLI命令：`bdms integration list/sync/promote` | ⚠️差异 | CLI子命令未实现，仅Web API提供部分端点。 | 文档：`DESIGN-OUTLINE-v2.1.md` §6.1；`grep integration src/bdms/cli/main.py`返回0命中 |
| Web API端点：`list_connectors`/`connector_status`/`sync`/`history` | ✅一致 | 4个端点已在`api_v2.py`实现，符合设计要求。 | 文档：`DESIGN-DETAIL-INTEGRATION-v2.1.md` §7；代码：`src/bdms/web/api_v2.py:151-183` |
| 重复连接器注册问题 | ⚠️差异 | `connectors.py`（根目录）存在旧连接器类定义，与`connectors/`目录下新实现重复，但当前导入的是正确的新实现，不会覆盖。 | 代码：`src/bdms/modules/integration/connectors.py` vs `src/bdms/modules/integration/connectors/*.py`；python验证：导入的是新实现。 |

### B.3 `contract_management`模块

| 检查项 | 状态 | 说明 | 证据 |
|--------|------|------|------|
| 核心类存在：`ContractService`/`ContractEngine`/`ContractValidator`/`ContractExporter` | ✅一致 | 所有核心类及核心方法(`create`/`scan`/`approve`/`export`/`validate`)均存在。 | 文档：`DESIGN-DETAIL-CONTRACT-MANAGEMENT-v2.1.md` §5；代码：`service.py:19`/`engine.py:37`/`validator.py:41`/`exporter.py:53` |
| 数据模型：`cr_contracts`/`cr_contract_clauses`/`cr_risk_scan_results`/`cr_import_validation`均使用 | ✅一致 | 所有设计声称的核心表均在业务代码中读写。 | 文档：`DESIGN-DETAIL-CONTRACT-MANAGEMENT-v2.1.md` §11；`grep`显示所有表在代码中引用。 |
| 文档模型：`Contract`/`ContractDocument`/`ContractClause`/`RiskScanResult`数据类存在 | ✅一致 | 所有设计数据类均存在，枚举和状态转换正确。 | 代码：`models.py` |
| kb_item风险分析功能存在 | ✅一致 | 设计要求的风险分析使用知识库条目功能已实现。 | 文档：`DESIGN-DETAIL-CONTRACT-MANAGEMENT-v2.1.md` §6；代码：`src/bdms/modules/contract_management/engine.py:290` |

### B.4 `project_management`模块

| 检查项 | 状态 | 说明 | 证据 |
|--------|------|------|------|
| 子模块结构：`after_sales`/`cost`/`change`/`risk` | ✅一致 | 所有设计子模块均存在，核心引擎类均实现。 | 文档：`DESIGN-DETAIL-PROJECT-MANAGEMENT-v2.1.md` §3；代码目录结构。 |
| 核心入口：`ProjectService`/`ProjectEngine` | ✅一致 | 核心类和方法均存在，符合设计。 | 文档：`DESIGN-DETAIL-PROJECT-MANAGEMENT-v2.1.md` §4；代码：`service.py:723`/`engine.py:132` |
| 核心表：`pm_projects`/`ct_*`/`rk_*`/`as_*`均引用 | ✅一致 | 设计声称的核心表均在代码中读写，正确。 | `grep`显示所有核心表在业务代码中引用。 |
| 财务服务：`FinancialService` | ✅一致 | 设计要求的利润视图/财务健康度评估已实现。 | 文档：`DESIGN-DETAIL-PROJECT-MANAGEMENT-v2.1.md` §6.2；代码：`financial_service.py:19` |

### B.5 `revenue`模块

| 检查项 | 状态 | 说明 | 证据 |
|--------|------|------|------|
| 依赖关系：依赖`delivery_report`的`dr_sheet_row`共享宽表 | ✅一致 | 代码中`save_sheet_rows`直接写入`rr_sheet_row`使用来自`delivery_report`的数据源，符合设计。 | 文档：`DESIGN-DETAIL-REVENUE-v2.1.md` §1.3；代码：`src/bdms/core/db.py:235` |
| Web导出端点：`revenue/export/{month}` | ✅一致 | 设计要求的Excel导出已实现，通过`SummaryEngine`生成。 | 文档：`DESIGN-DETAIL-REVENUE-v2.1.md` §7；代码：`src/bdms/web/api.py:220` |
| `RevenueReportExporter`/`UnifiedRevenueImporter`类存在 | ❌缺失 | 设计声称存在这两个类，实际导出逻辑内联在`api.py`和`SummaryEngine`中，无独立类。 | 文档：`DESIGN-DETAIL-REVENUE-v2.1.md` §5.1；`grep`查找无类定义。 |

### B.6 `profit_management`模块

| 检查项 | 状态 | 说明 | 证据 |
|--------|------|------|------|
| 核心类：`ProfitManagementEngine` | ✅一致 | 核心类存在，`check_budget_alert`/`get_cost_summary`方法已实现。 | 文档：`DESIGN-DETAIL-PROFIT-MANAGEMENT-v2.1.md` §3；代码：`src/bdms/modules/profit_management/engine.py:158` |
| `BudgetAlertService`/`ProfitImporter`类存在 | ❌缺失 | 文档声称存在这两个类，实际功能已内联到`engine.py`中，无独立类。 | 文档：`DESIGN-DETAIL-PROFIT-MANAGEMENT-v2.1.md` §3；`grep`查找无类定义。 |
| API端点：`profit/report/{project_id}`/`profit/alerts/{project_id}`存在 | ✅一致 | 两个端点已在`api_v2.py`实现，符合设计。 | 文档：`DESIGN-DETAIL-PROFIT-MANAGEMENT-v2.1.md` §7；代码：`src/bdms/web/api_v2.py:115/137` |

### B.7 `dashboard`模块

| 检查项 | 状态 | 说明 | 证据 |
|--------|------|------|------|
| 核心功能：`get_dashboard`/`compute_kpis`/`_load_sheet` | ✅一致 | 核心功能已实现，从各模块宽表聚合数据，符合设计。 | 文档：`DESIGN-DETAIL-DASHBOARD-v2.1.md` §5；代码：`src/bdms/modules/dashboard/engine.py` |
| `summary`/`trend`方法存在 | ⚠️差异 | `engine.py`实现了`compute_monthly_trend`，但是`service.py`未导出`summary`和`trend`方法，且Web API仅在`api.py`提供了`/{month}`端点，未提供`/summary`和`/trend`端点。 | 文档：`DESIGN-DETAIL-DASHBOARD-v2.1.md` §7；代码：`engine.py:195`/`service.py:41` |
| 定制化服务：`CustomizationService` | ✅一致 | `db_view_config`读写已实现，符合设计。 | 文档：`DESIGN-DETAIL-DASHBOARD-v2.1.md` §6.2；代码：`src/bdms/modules/dashboard/customization_service.py:4` |
| 数据源：`_revenue_conn`读取独立revenue.db | ✅一致 | 符合设计要求，确收入库在独立数据库，正确读取。 | 文档：`DESIGN-DETAIL-REVENUE-v2.1.md` §2；代码：`src/bdms/modules/dashboard/engine.py:98` |

---

## C. DB Schema一致性

| 检查项 | 状态 | 说明 | 证据 |
|--------|------|------|------|
| 核心模块表均已在schema_v21.py定义且实际存在于DB | ✅一致 | 所有设计声称的核心表(`dr_sheet_row`/`rr_sheet_row`/`cr_contracts`/`pm_projects`/`pf_profit_snapshot`/`db_view_config`等)均在schema中定义，且实际存在于`data/bdms.db`中。 | 对比`src/bdms/core/schemas_v21.py`与实际DB。 |
| schema中定义但业务代码未使用的表 | ⚠️差异 | `pf_budget_alert`/`pf_cost_item`在schema中定义，但业务代码未读写；`dash_snapshot`仅出现在迁移脚本中，未被业务代码引用；`pf_cash_flow`/`pf_cost_overhead`无业务代码引用。 | `grep -r "pf_budget_alert" src/ --include="*.py"`仅在schema中存在；`grep -r "pf_cost_item" src/`无引用；`grep -r "dash_snapshot" src/`仅在迁移脚本存在。 |
| DB存在但schema中未声明的表 | ⚠️差异 | `cr_import_validation`在DB中存在，但未在schema中声明，实际被`contract_management.validator`使用，DDL未显式声明在schema中。 | `cr_import_validation`在代码中被使用，但是`grep CREATE_TABLE src/`找不到DDL。 |
| 核心表列读写逻辑与设计一致 | ✅一致 | 所有设计的核心表列均在业务代码中正确读写，无漂移。 | 各模块核心表引用检查均正确。 |
| 收入模块使用独立数据库 | ✅一致 | 符合设计，`revenue.db`存在，且被正确读取。 | 文档：`DESIGN-DETAIL-REVENUE-v2.1.md` §2；代码：`dashboard.engine.py`。 |

---

## D. 已知差异点核查

| 检查项 | 状态 | 说明 | 证据 |
|--------|------|------|------|
| ONES连接器方案同步 | ⚠️差异 | 仅实现了缓存CSV查找，完整浏览器自动化导出未实现，符合开发跟踪记录。 | `INTEGRATION-DEVELOPMENT-TRACKING.md` 1.1/1.2 |
| 企微文档连接器降级链一致性 | ⚠️差异 | 优先级与文档不一致，文档`API → 浏览器 → 本机`；实际`文件路径 → 预导出CSV → API(未实现)`。 | 文档：`DESIGN-DETAIL-INTEGRATION-v2.1.md` §6.4；代码：`wecom_doc_connector.py:fetch` |
| 文档目录一致性 | ⚠️差异 | 设计声称`docs/`目录存放多个详细设计文档，实际所有设计文档均在项目根目录，`docs/`目录仅存在`DESIGN-OUTLINE-BROWSER-AUTOMATION-TECH-SELECTION-v1.0.md`，符合预期，不影响功能。 | 设计声称：`DESIGN-OUTLINE-v2.1.md` §8.1.8；实际：`ls docs/`只有1个文件。 |
| 架构文档路径一致性 | ✅一致 | 架构文档路径`docs/architecture/`在操作手册中正确引用，存在于该路径。 | `OPERATIONS-v2.1.md` §1；文件路径存在。 |

---

## E. 测试与工具一致性

| 检查项 | 状态 | 说明 | 证据 |
|--------|------|------|------|
| 测试覆盖：核心模块单元测试存在 | ✅一致 | `tests/test_e2e_v21.py`覆盖所有核心模块，测试用例符合设计要求。 | 文档：`VERIFICATION-v2.1.md`；代码：`tests/test_e2e_v21.py`。 |
| E2E测试要求：真实HTTP而非TestClient | ✅一致 | 测试代码使用真实HTTP客户端，符合设计要求。 | `VERIFICATION-v2.1.md` §17；`tests/`中E2E测试使用requests。 |
| 交付月报对比工具`compare_delivery_report.py` | ✅一致 | 文档声称存在该对比工具，实际存在。 | 文档：`DESIGN-DETAIL-DELIVERY-REPORT-v2.1.md`；`tools/compare_delivery_report.py`存在。 |
| 集成模块测试覆盖 | ⚠️差异 | 集成测试/E2E测试/黄金基准对比均未实现，符合开发跟踪文档记录。 | `INTEGRATION-DEVELOPMENT-TRACKING.md` §Phase 5。 |
| 文档验证手段：测试与文档声称一致 | ✅一致 | 核心模块测试覆盖与文档验证要求一致，仅集成模块未完成测试，已记录。 |

