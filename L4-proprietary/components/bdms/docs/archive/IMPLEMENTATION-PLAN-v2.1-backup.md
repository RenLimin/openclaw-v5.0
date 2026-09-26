# BDMS v2.1 开发落地计划

> 版本：v2.1 Implementation Plan（2026-09-20）
> 来源：9 份详细设计文档的 P0 优化项 + 实施步骤
> 分支：main（直接开发）
> 测试：交付验收 7 步法
> 状态：待执行

---

## 0. 全局决策

| 决策项 | 结论 | 来源 |
|---|---|---|
| Git 分支 | main 直接开发 | Rex 拍板 |
| 开发顺序 | 按依赖关系串行 | Rex 拍板 |
| 测试策略 | 交付验收 7 步法 | Rex 拍板 |
| Token 消耗 | 核心功能 🔒 NO_TOKEN，AI 功能 ⚡ OPTIONAL | 各模块设计文档 |

---

## 1. 跨模块 P0 优化项汇总

以下优化项在多个模块中共同涉及，需优先落地：

| P0 优化项 | 涉及模块 | 说明 |
|---|---|---|
| **Repository Interface（仓储接口）** | 全部 | Base 层定义 `BaseRepository` 接口，各模块实现具体仓储 |
| **统一审计字段** | 全部 | 所有业务表增加 `created_at/updated_at/created_by/updated_by`，Base 层提供 `AuditMixin` |
| **统一软删除** | 全部 | 所有业务表增加 `deleted_at` 字段，BaseRepository 自动过滤已删除记录 |
| **领域事件 + Outbox** | 全部 | 引入 outbox 表，事件与业务数据同事务写入，后台 worker 异步发布 |
| **熔断器机制** | INTEGRATION | BaseConnector 增加熔断器装饰器 |
| **数据质量规则引擎** | INTEGRATION | 可配置的数据质量校验规则 |
| **知识图谱关联** | KNOWLEDGE-BASE | 建立 kb_relation 表，记录知识条目间语义关联 |
| **INTEGRATION 导入通道** | KNOWLEDGE-BASE | 外部知识源自动同步到知识库 |
| **自定义看板** | DASHBOARD | 用户自选指标 + 拖拽布局 + 多视图 + 预设模板 |

---

## 2. 开发路线图

### Phase 0：基础设施层（Base + Data Model）

**目标**：为所有模块提供统一的接口契约、数据模型和通用工具。

#### Phase 0.1：Base 层加固

| 步骤 | 内容 | 产出 | 验收 |
|---|---|---|---|
| 1.1 | 定义 `BaseRepository` 接口 | `base/repository.py` | 接口定义完整 |
| 1.2 | 实现 `AuditMixin`（统一审计字段） | `base/mixins.py` | 所有表自动继承 |
| 1.3 | 实现软删除过滤（`deleted_at`） | `base/repository.py` | 查询自动过滤已删除 |
| 1.4 | 完善 `BaseEngine`（+ type hints + docstring） | `base/engine.py` | 现有测试全绿 |
| 1.5 | 完善 `BaseService`（+ job 钩子） | `base/service.py` | 现有测试全绿 |
| 1.6 | 完善 `BaseExporter`（统一样式常量） | `base/exporter.py` | 现有测试全绿 |
| 1.7 | 新增 `BaseImporter`（校验/幂等/重试） | `base/importer.py` | 单测通过 |

**验收标准**：Base 层 4 个基类 + 2 个 Mixin 全部通过单测，现有 delivery_report/revenue 模块接入后全量回归。

#### Phase 0.2：数据模型初始化

| 步骤 | 内容 | 产出 | 验收 |
|---|---|---|---|
| 2.1 | 扩展 `init_db()` 加载所有 schema | `core/db.py` | 初始化后 33+ 张表全存在 |
| 2.2 | 新增 `dash_snapshot` 表 | schema 文件 | DDL 执行成功 |
| 2.3 | 新增 `dash_user_config` 表 | schema 文件 | DDL 执行成功 |
| 2.4 | 新增 `int_staging` + `int_sync_log` 表 | schema 文件 | DDL 执行成功 |
| 2.5 | 新增 `kb_relation` 表（知识图谱） | schema 文件 | DDL 执行成功 |
| 2.6 | 新增 `outbox_events` 表（领域事件） | schema 文件 | DDL 执行成功 |
| 2.7 | 编写 `verify_schema.py` | 验证脚本 | 表名/字段/索引全对齐 |

**验收标准**：`verify_schema.py` 一键验证所有表结构。

---

### Phase 1：核心域模块

#### Phase 1.1：Contract Management（合同管理）

**依赖**：Phase 0 完成

| 步骤 | 内容 | 产出 | 验收 |
|---|---|---|---|
| 1.1.1 | 6 张 `cr_` 表 SQLAlchemy 模型 | `contract_management/models.py` | DDL 执行成功 |
| 1.1.2 | `ContractManagementEngine`（调用 L3 contract-approval） | `contract_management/engine.py` | 状态机 + 风险扫描 + 分级 |
| 1.1.3 | `ContractManagementService`（11 个核心方法） | `contract_management/service.py` | 创建→审批→签署全流程 |
| 1.1.4 | `ContractOCRImporter`（对接 OCR） | `contract_management/ocr_importer.py` | OCR 导入可用 |
| 1.1.5 | `ContractExporter`（4 种导出） | `contract_management/exporter.py` | Excel/PDF/CSV 导出 |
| 1.1.6 | docx 生成（模板引擎 + 占位符） | `contract_management/docx_generator.py` | 生成带水印的合同 docx |
| 1.1.7 | 条款库解耦（`cr_clause_library`） | 新增表 + 适配模板引擎 | 条款可复用 |
| 1.1.8 | 合同标的对比分析 | `engine.analyze_subject()` | 自动对比知识库 |
| 1.1.9 | CLI `bdms contract` 命令族 | `contract_management/cli.py` | ~20 个子命令 |
| 1.1.10 | 审计日志 + 加密/脱敏验证 | — | 安全验收通过 |

**验收标准**：交付验收 7 步法。

#### Phase 1.2：Project Management（项目管理）

**依赖**：Phase 0 完成，Phase 1.1 完成（合同关联）

| 步骤 | 内容 | 产出 | 验收 |
|---|---|---|---|
| 1.2.1 | pm_ 5 张 + ct_ 4 张 + rk_ 3 张表模型 | `project_management/models.py` | DDL 执行成功 |
| 1.2.2 | `ProjectEngine`（核心状态机 + CRUD） | `project_management/engine.py` | 7 种状态转换正确 |
| 1.2.3 | `DeliveryReportEngine`（交付报告） | `project_management/delivery_report/engine.py` | 月报计算正确 |
| 1.2.4 | `RevenueEngine`（收入确认） | `project_management/revenue/engine.py` | 收入计算正确 |
| 1.2.5 | `CostEngine`（工时/设备/差旅） | `project_management/cost/engine.py` | 成本汇总正确 |
| 1.2.6 | `RiskEngine`（风险全生命周期） | `project_management/risk/engine.py` | 上报→评审→处置→关闭 |
| 1.2.7 | `ChangeManagementEngine`（变更管理） | `project_management/change/engine.py` | 变更请求→影响分析→执行 |
| 1.2.8 | `ProjectFinancialService`（利润视图） | `project_management/financial_service.py` | 利润汇总/趋势/预警 |
| 1.2.9 | `ProjectManagementService`（统一编排） | `project_management/service.py` | 跨子引擎事务编排 |
| 1.2.10 | 结项检查（四重检查） | `service.close_project()` | 未完成子项阻止结项 |
| 1.2.11 | 售后完结触发结项 | `service.complete_after_sales()` | 售后完结→项目结项 |
| 1.2.12 | CLI `bdms project` 命令族 | `project_management/cli.py` | ~40 个子命令 |

**验收标准**：交付验收 7 步法。

---

### Phase 2：横切支撑模块

#### Phase 2.1：After Sales（售后管理）

**依赖**：Phase 1.2 完成（项目→售后移交）

| 步骤 | 内容 | 产出 | 验收 |
|---|---|---|---|
| 2.1.1 | 3 张 `as_` 表模型 | `after_sales/models.py` | DDL 执行成功 |
| 2.1.2 | `AfterSalesService`（工单全生命周期） | `after_sales/service.py` | 7 种状态流转正确 |
| 2.1.3 | SLA 计算逻辑 | `after_sales/sla_calculator.py` | 工作时间 + 暂停机制 |
| 2.1.4 | `transfer_to_after_sales`（项目移交） | `after_sales/service.py` | 验收后自动移交 |
| 2.1.5 | `complete_after_sales`（售后完结→结项） | `after_sales/service.py` | 触发项目结项 |
| 2.1.6 | `AfterSalesAnalyticsService`（分析） | `after_sales/analytics.py` | 趋势/产品-版本/重复识别 |
| 2.1.7 | 关联合同获取 SLA 等级 | `after_sales/service.py` | 合同→售后 SLA 自动配置 |
| 2.1.8 | 关联知识库 FAQ | `after_sales/service.py` | 工单创建时自动匹配 FAQ |
| 2.1.9 | 解决方案沉淀到知识库 | `after_sales/service.py` | 解决后推荐写入 KB |
| 2.1.10 | CLI `bdms after-sales` 命令族 | `after_sales/cli.py` | ~25 个子命令 |

**验收标准**：交付验收 7 步法。

#### Phase 2.2：Integration（数据集成）

**依赖**：Phase 0 完成

| 步骤 | 内容 | 产出 | 验收 |
|---|---|---|---|
| 2.2.1 | `int_staging` + `int_sync_log` 表 | schema 文件 | DDL 执行成功 |
| 2.2.2 | `BaseConnector` + `LocalPathConnector` | `integration/connectors/base.py` | 抽象层完整 |
| 2.2.3 | 熔断器装饰器 | `integration/circuit_breaker.py` | 连续 N 次失败 → 暂停 |
| 2.2.4 | 数据质量规则引擎 | `integration/quality_engine.py` | 可配置校验规则 |
| 2.2.5 | `OnesConnector`（API + 浏览器兜底） | `integration/connectors/ones.py` | ONES 增量同步 |
| 2.2.6 | `OaConnector` | `integration/connectors/oa.py` | OA 全量同步 |
| 2.2.7 | `TimesheetConnector` | `integration/connectors/timesheet.py` | 工时同步 |
| 2.2.8 | `WecomDocConnector` | `integration/connectors/wecom_doc.py` | 企微文档同步 |
| 2.2.9 | `FinanceConnector` | `integration/connectors/finance.py` | 财务报表导入 |
| 2.2.10 | `IntegrationService` + 事件集成 | `integration/service.py` | 同步→事件→消费 |
| 2.2.11 | CLI `bdms integration` 命令族 | `integration/cli.py` | ~15 个子命令 |

**验收标准**：交付验收 7 步法。

#### Phase 2.3：Knowledge Base（知识库）

**依赖**：Phase 0 完成

| 步骤 | 内容 | 产出 | 验收 |
|---|---|---|---|
| 2.3.1 | kb_ 系列表 + FTS5 + kb_relation | schema 文件 | DDL 执行成功 |
| 2.3.2 | `KnowledgeBaseService` CRUD + 生命周期 | `knowledge_base/service.py` | 创建→审核→发布→版本 |
| 2.3.3 | `EmbeddingProvider`（L2 Memory-009） | `knowledge_base/embedding.py` | 向量生成 < 50ms |
| 2.3.4 | `SearchEngine`（FTS5 + 语义 + RRF 融合） | `knowledge_base/search.py` | 混合检索可用 |
| 2.3.5 | `KnowledgeImporter`（Markdown/JSON/INTEGRATION） | `knowledge_base/importer.py` | 多源导入 |
| 2.3.6 | 知识图谱关联（`kb_relation`） | `knowledge_base/relation.py` | 关联推荐 |
| 2.3.7 | INTEGRATION 导入通道 | `knowledge_base/importer.py` | 外部知识源同步 |
| 2.3.8 | CLI `bdms knowledge` 命令族 | `knowledge_base/cli.py` | ~30 个子命令 |

**验收标准**：交付验收 7 步法。

#### Phase 2.4：Dashboard（看板）

**依赖**：Phase 1 + Phase 2.1 + Phase 2.3（数据源就绪）

| 步骤 | 内容 | 产出 | 验收 |
|---|---|---|---|
| 2.4.1 | `dash_snapshot` + `dash_user_config` 表 | schema 文件 | DDL 执行成功 |
| 2.4.2 | 12 个指标聚合查询实现 | `dashboard/metrics/` | 各指标计算正确 |
| 2.4.3 | `DashboardService` 四接口 | `dashboard/service.py` | summary/trend/drill/compare |
| 2.4.4 | `SnapshotRepository` + 缓存机制 | `dashboard/snapshot.py` | 缓存命中 < 200ms |
| 2.4.5 | `DashboardCustomizationService` | `dashboard/customization.py` | 自定义视图 CRUD |
| 2.4.6 | 前端页面（12 KPI + 告警区） | `dashboard/templates/` | 页面渲染正确 |
| 2.4.7 | 自定义配置界面（拖拽 + 预设模板） | `dashboard/templates/config.html` | 拖拽布局可用 |
| 2.4.8 | 事件总线订阅 + 缓存失效 | `dashboard/events.py` | 数据变更自动刷新 |
| 2.4.9 | CLI `bdms dashboard` 命令族 | `dashboard/cli.py` | ~15 个子命令 |

**验收标准**：交付验收 7 步法。

---

## 3. 工时估算

| Phase | 模块 | 预估工时 | 累计 |
|---|---|---|---|
| 0.1 | Base 层加固 | 1d | 1d |
| 0.2 | 数据模型初始化 | 0.5d | 1.5d |
| 1.1 | Contract Management | 2d | 3.5d |
| 1.2 | Project Management | 3.5d | 7d |
| 2.1 | After Sales | 2d | 9d |
| 2.2 | Integration | 2.5d | 11.5d |
| 2.3 | Knowledge Base | 3d | 14.5d |
| 2.4 | Dashboard | 2d | 16.5d |
| **合计** | | **16.5d** | |

> 注：工时为估算值，实际开发中可能因外部系统接口调试、OCR 集成等因素延长。

---

## 4. 交付验收 7 步法（每个模块通用）

| 步骤 | 验收内容 | 通过标准 |
|---|---|---|
| ① 独立审计 | 代码 + 接口契约 + 数据模型 | 与设计文档完全对齐 |
| ② 契约对齐 | 跨模块接口调用 | 接口签名一致，调用无误 |
| ③ 全入口执行 | CLI + Web API 全量执行 | 所有命令/API 无崩溃 |
| ④ 黄金基准 | 对比已有数据（如有） | 零差异 |
| ⑤ 幂等测试 | 重复执行关键操作 | 结果一致，无副作用 |
| ⑥ 调用点扫描 | 所有引用点检查 | 无悬空引用，无 404 |
| ⑦ 回归锁定 | 现有测试全量通过 | 已有功能无退化 |

---

## 5. 开发规范

### 5.1 代码规范

- 所有公共方法必须有完整 type hints
- 所有公共类/方法必须有 docstring
- 异常类型统一 + 错误码映射
- 日志格式统一（结构化日志）
- 配置从 `sys_settings` 读取，不硬编码

### 5.2 Token 消耗标记

| 标记 | 含义 | 本阶段是否使用 |
|---|---|---|
| 🔒 NO_TOKEN | 纯代码逻辑 | ✅ 全部核心功能 |
| ⚡ OPTIONAL_TOKEN | 可选 AI 功能 | ❌ 本阶段不实现 |
| 🔥 REQUIRED_TOKEN | 必须 AI 功能 | ❌ 本阶段不实现 |

### 5.3 Git 提交规范

- 每个模块完成后提交一次
- commit message 格式：`feat(v2.1): [模块名] - 简要描述`
- 提交前确保：单测通过 + 凭据扫描通过 + 无明文密钥

---

## 6. 待确认事项

| 事项 | 状态 | 说明 |
|---|---|---|
| ONES API 可用性 | ⏳ 待确认 | 确认 ONES 是否有 API 或必须走浏览器自动化 |
| OA 系统接口文档 | ⏳ 待确认 | 确认 OA 系统 API 格式 |
| 工时系统接口 | ⏳ 待确认 | 确认工时门户是否支持 API |
| 企业微信文档 API | ⏳ 待确认 | 确认企微文档 API 权限和格式 |
| 电子签名服务选型 | ⏳ 待确认 | e签宝/法大大/腾讯电子签（P1） |
| 外部知识源清单 | ⏳ 待确认 | SharePoint/Confluence/文件共享的具体配置 |

---

_本计划基于 9 份详细设计文档汇总，开发过程中如有设计变更，需同步更新对应文档。_

<!-- project: github.com/RenLimin/openclaw-v5.0 -->
