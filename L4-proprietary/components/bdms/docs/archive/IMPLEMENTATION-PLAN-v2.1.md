# BDMS v2.1 开发落地计划

> 版本：v2.1 Implementation Plan r2（2026-09-20）
> 来源：9 份详细设计文档的 P0 优化项 + 实施步骤 + Rex Review 意见
> 分支：main（直接开发）
> 测试：交付验收 7 步法（每个 Phase 结束后强制执行）
> 状态：设计阶段，待 Rex 审核
> 代码冻结：✅ 人工审核通过前不启动任何开发

---

## 0. 全局决策

| 决策项            | 结论                                        | 来源                 |
| -------------- | ----------------------------------------- | ------------------ |
| Git 分支         | main 直接开发                                 | Rex 拍板             |
| 开发顺序           | 按依赖关系串行，每 Phase 验收通过再进下一个                 | Rex 拍板 + Review 反馈 |
| 测试策略           | 交付验收 7 步法（每 Phase 结束自动执行）                 | Rex 拍板             |
| Token 消耗       | 核心功能 🔒 NO_TOKEN，AI 功能 ⚡ OPTIONAL         | 各模块设计文档            |
| 发布节奏           | **MVP 先行 + Full 后补**，两期交付                 | Review 反馈          |
| 数据迁移           | Phase 0.2 产出 `migrate_v1_to_v2.py`，不丢现有数据 | Review 反馈          |
| 领域事件 / Outbox  | MVP 不上，Full 版再加                           | Review 反馈          |
| Integration 拆分 | P0 本地文件导入 + 手动上传；P1 系统对接（等接口确认）           | Review 反馈          |

---

## 1. 跨模块 P0 优化项汇总（MVP 范围）

以下优化项在多个模块中共同涉及，需优先落地：

| P0 优化项 | 涉及模块 | MVP 范围 | 说明 |
|---|---|---|---|
| **Repository Interface（仓储接口）** | 全部 | ✅ MVP | Base 层定义 `BaseRepository` 接口，各模块实现具体仓储 |
| **统一审计字段** | 全部 | ✅ MVP | 所有业务表增加 `created_at/updated_at/created_by/updated_by`，Base 层提供 `AuditMixin` |
| **统一软删除** | 全部 | ✅ MVP | 所有业务表增加 `deleted_at` 字段，BaseRepository 自动过滤已删除记录 |
| **熔断器机制** | INTEGRATION | ❌ Full | BaseConnector 增加熔断器装饰器 |
| **数据质量规则引擎** | INTEGRATION | ❌ Full | 可配置的数据质量校验规则 |
| **知识图谱关联** | KNOWLEDGE-BASE | ❌ Full | 建立 kb_relation 表，记录知识条目间语义关联 |
| **INTEGRATION 导入通道** | KNOWLEDGE-BASE | ❌ Full | 外部知识源自动同步到知识库 |
| **自定义看板** | DASHBOARD | ❌ Full | 用户自选指标 + 拖拽布局 + 多视图 + 预设模板 |
| **领域事件 + Outbox** | 全部 | ❌ Full | MVP 用直接调用 + 事务，Full 版再上 outbox + worker |

---

## 2. 版本拆分总览

### 2.1 MVP 版（目标：7-10 天可用）

**目标**：跑通核心业务链路（合同 → 项目 → 交付 → 确收 → 看板），替换 v1.0 全部功能。

**范围**：
- ✅ Phase 0：Base 层加固 + 数据模型 + v1 数据迁移
- ✅ Phase 1.1：Contract Management（合同管理核心）
- ✅ Phase 1.2：Project Management（核心状态机 + 交付报表 + 确收 + 成本 + 风险）
- ✅ Phase 2.4：Dashboard 基础版（固定指标 + 快照缓存）
- ✅ Integration P0（本地文件导入 + 手动上传）

**不含**：售后管理 / 知识库 / 自定义看板 / 系统集成对接 / 领域事件 outbox / 变更管理

### 2.2 Full 版（目标：MVP 之后，按优先级迭代）

**目标**：覆盖完整 16 阶段流程，补齐横切支撑能力。

**范围**：
- Phase 2.1：After Sales（售后管理）
- Phase 2.2：Integration P1（系统对接：ONES / OA / 工时 / 企微文档 / 财务）
- Phase 2.3：Knowledge Base（知识库 + 知识图谱 + 混合检索）
- Phase 2.4：Dashboard Full（自定义看板 + 拖拽布局 + 多视图）
- 领域事件 + Outbox 模式
- 变更管理引擎（Project Management 补充）

---

## 3. MVP 开发路线图

### Phase 0：基础设施层（Base + Data Model + 数据迁移）

**目标**：为所有模块提供统一的接口契约、数据模型和通用工具；v1.0 数据无损迁移。

#### Phase 0.1：Base 层加固

| 步骤 | 内容 | 产出 | 验收 |
|---|---|---|---|
| 0.1.1 | 定义 `BaseRepository` 接口 | `base/repository.py` | 接口定义完整 |
| 0.1.2 | 实现 `AuditMixin`（统一审计字段） | `base/mixins.py` | 所有表自动继承 |
| 0.1.3 | 实现软删除过滤（`deleted_at`） | `base/repository.py` | 查询自动过滤已删除 |
| 0.1.4 | 完善 `BaseEngine`（+ type hints + docstring） | `base/engine.py` | 现有测试全绿 |
| 0.1.5 | 完善 `BaseService`（+ job 钩子） | `base/service.py` | 现有测试全绿 |
| 0.1.6 | 完善 `BaseExporter`（统一样式常量） | `base/exporter.py` | 现有测试全绿 |
| 0.1.7 | 新增 `BaseImporter`（校验/幂等/重试） | `base/importer.py` | 单测通过 |

**验收标准**：Base 层 4 个基类 + 2 个 Mixin 全部通过单测，现有 delivery_report/revenue 模块接入后全量回归。

#### Phase 0.2：数据模型初始化 + v1 迁移

| 步骤 | 内容 | 产出 | 验收 |
|---|---|---|---|
| 0.2.1 | 扩展 `init_db()` 加载所有 schema | `core/db.py` | 初始化后 25+ 张表全存在 |
| 0.2.2 | MVP 新增表：contract / project / cost / risk | schema 文件 | DDL 执行成功 |
| 0.2.3 | 新增 `dash_snapshot` 表（MVP 用） | schema 文件 | DDL 执行成功 |
| 0.2.4 | 新增 `int_staging` + `int_sync_log` 表（P0 用） | schema 文件 | DDL 执行成功 |
| 0.2.5 | 编写 `verify_schema.py` | 验证脚本 | 表名/字段/索引全对齐 |
| 0.2.6 | 编写 `migrate_v1_to_v2.py` | 迁移脚本 | v1 数据无损迁到 v2 结构 |
| 0.2.7 | 迁移脚本幂等测试 | — | 重复执行不丢数据、不报错 |

**验收标准**：
1. `verify_schema.py` 一键验证所有表结构
2. `migrate_v1_to_v2.py` 对 v1.0 生产库执行后，数据零丢失（按月报 18 项黄金基准对比）
3. 迁移脚本幂等：重复执行 3 次结果一致

---

### Phase 1：核心域模块

#### Phase 1.1：Contract Management（合同管理 — MVP）

**依赖**：Phase 0 完成

**MVP 范围**：核心 CRUD + 风险扫描 + 分级审批 + docx 生成 + OCR 导入 + 4 种导出

| 步骤 | 内容 | 产出 | 验收 |
|---|---|---|---|
| 1.1.1 | 6 张 `cr_` 表 SQLAlchemy 模型 | `contract_management/models.py` | DDL 执行成功 |
| 1.1.2 | `ContractManagementEngine`（调用 L3 contract-approval） | `contract_management/engine.py` | 状态机 + 风险扫描 + 分级 |
| 1.1.3 | `ContractManagementService`（核心方法） | `contract_management/service.py` | 创建→审批→签署全流程 |
| 1.1.4 | `ContractOCRImporter`（对接 L2 OCR-001） | `contract_management/ocr_importer.py` | OCR 导入可用 |
| 1.1.5 | `ContractExporter`（4 种导出） | `contract_management/exporter.py` | Excel/PDF/CSV/Word 导出 |
| 1.1.6 | docx 生成（模板引擎 + 占位符） | `contract_management/docx_generator.py` | 生成带水印的合同 docx |
| 1.1.7 | 合同标的对比分析（MVP：精确匹配） | `engine.analyze_subject()` | 可对比基础信息 |
| 1.1.8 | CLI `bdms contract` 命令族 | `contract_management/cli.py` | ~15 个核心子命令 |
| 1.1.9 | 单元测试（引擎层 100% 覆盖） | `tests/contract_management/` | 引擎层覆盖率 ≥ 90% |

**验收标准**：交付验收 7 步法 + 合同从创建到签署端到端跑通。

> **Full 版补充**（MVP 不含）：条款库解耦（`cr_clause_library`）、电子签名集成、更细粒度的标的对比（语义匹配）。

#### Phase 1.2：Project Management（项目管理 — MVP）

**依赖**：Phase 0 完成，Phase 1.1 完成（合同关联）

**MVP 范围**：核心状态机 + 交付报表 + 确收 + 成本 + 风险 + 财务视图

| 步骤 | 内容 | 产出 | 验收 |
|---|---|---|---|
| 1.2.1 | pm_ 5 张 + cost_ 3 张 + risk_ 3 张表模型 | `project_management/models.py` | DDL 执行成功 |
| 1.2.2 | `ProjectEngine`（核心状态机 + CRUD） | `project_management/engine.py` | 7 种状态转换正确 |
| 1.2.3 | `DeliveryReportEngine`（交付报告） | `project_management/delivery_report/engine.py` | 月报计算正确（对齐 18 项黄金基准） |
| 1.2.4 | `RevenueEngine`（收入确认） | `project_management/revenue/engine.py` | 收入计算正确（沿用 v1.0 逻辑） |
| 1.2.5 | `CostEngine`（工时/设备/差旅） | `project_management/cost/engine.py` | 成本汇总正确 |
| 1.2.6 | `RiskEngine`（风险全生命周期） | `project_management/risk/engine.py` | 上报→评审→处置→关闭 |
| 1.2.7 | `ProjectFinancialService`（利润视图） | `project_management/financial_service.py` | 利润汇总/趋势/预警 |
| 1.2.8 | `ProjectManagementService`（统一编排） | `project_management/service.py` | 跨子引擎事务编排 |
| 1.2.9 | 结项检查（MVP：基础三重检查） | `service.close_project()` | 未完成交付/确收/成本阻止结项 |
| 1.2.10 | CLI `bdms project` 命令族 | `project_management/cli.py` | ~25 个核心子命令 |
| 1.2.11 | 单元测试（引擎层 100% 覆盖） | `tests/project_management/` | 引擎层覆盖率 ≥ 90% |

**验收标准**：交付验收 7 步法 + 项目从立项到结项端到端跑通 + 月报 18 项黄金基准零差异。

> **Full 版补充**（MVP 不含）：变更管理引擎、售后完结触发结项、更细的结项检查（五重以上）、更多子命令。

---

### Phase 2：横切支撑模块（MVP 范围）

#### Phase 2.2 Lite：Integration P0（本地文件导入）

**依赖**：Phase 0 完成
**优先级**：先做，为后续模块提供数据录入能力

| 步骤 | 内容 | 产出 | 验收 |
|---|---|---|---|
| 2.2.Lite.1 | `int_staging` + `int_sync_log` 表（已在 Phase 0.2 建） | — | — |
| 2.2.Lite.2 | `BaseConnector` + `LocalFileConnector` | `integration/connectors/base.py` | 抽象层完整 |
| 2.2.Lite.3 | `ExcelImporter`（Excel → staging → 目标表） | `integration/excel_importer.py` | 支持模板化导入 |
| 2.2.Lite.4 | `IntegrationService` + 基础校验 | `integration/service.py` | 导入→校验→落地 |
| 2.2.Lite.5 | CLI `bdms import` 命令族 | `integration/cli.py` | ~5 个核心子命令 |

**验收标准**：交付验收 7 步法（Lite 版）+ 能从 Excel 批量导入合同/项目/成本数据。

> **Full 版补充**（MVP 不含）：熔断器、数据质量规则引擎、ONES/OA/工时/企微文档/财务等系统连接器、浏览器自动化兜底。

#### Phase 2.4 Lite：Dashboard 基础版

**依赖**：Phase 1 完成 + Phase 2.2 Lite 完成（数据源就绪）

| 步骤 | 内容 | 产出 | 验收 |
|---|---|---|---|
| 2.4.Lite.1 | `dash_snapshot` 表（已在 Phase 0.2 建） | — | — |
| 2.4.Lite.2 | 8 个核心指标聚合查询 | `dashboard/metrics/` | 各指标计算正确 |
| 2.4.Lite.3 | `DashboardService` 三接口 | `dashboard/service.py` | summary/trend/drill |
| 2.4.Lite.4 | `SnapshotRepository` + TTL 缓存 | `dashboard/snapshot.py` | 缓存命中 < 200ms |
| 2.4.Lite.5 | 前端页面（8 KPI + 趋势图） | `dashboard/templates/` | 页面渲染正确 |
| 2.4.Lite.6 | CLI `bdms dashboard` 命令族 | `dashboard/cli.py` | ~5 个核心子命令 |

**验收标准**：交付验收 7 步法（Lite 版）+ 看板页面可正常展示 8 个核心指标。

**8 个核心指标（MVP）**：
1. 合同数/合同金额（本月/累计）
2. 项目数（按状态分布）
3. 交付中项目数 / 延期交付数
4. 本月确认收入 / 累计确认收入
5. 本月成本 / 累计成本
6. 毛利率（本月 / 累计）
7. 风险项目数 / 高风险项目数
8. 未结项项目平均周期

> **Full 版补充**（MVP 不含）：自定义看板、拖拽布局、多视图、预设模板、对比分析、告警区。

---

### Phase 3：Web UI 扩展（MVP 范围内，2026-09-21 新增）

**依赖**：Phase 1 + Phase 2.4 完成
**设计文档**：`DESIGN-WEB-UI-v2.1.md`

| 步骤 | 内容 | 产出 | 验收 |
|---|---|---|---|
| 3.1 | 合同 API 路由 | `web/contract.py` | 10 个 API 端点 |
| 3.2 | 项目 API 路由 | `web/project.py` | 14 个 API 端点 |
| 3.3 | Dashboard MVP API | `web/dashboard_mvp.py` | 2 个 API 端点 |
| 3.4 | 合同页面模板 + JS | `web/templates/contract.html` `web/static/js/contract.js` | 列表 + 详情 + 审批 |
| 3.5 | 项目页面模板 + JS | `web/templates/project.html` `web/static/js/project.js` | 列表 + 详情 + 状态推进 |
| 3.6 | Dashboard 页面模板 | `web/templates/dashboard_mvp.html` | 8 个核心指标卡片 |
| 3.7 | 侧边栏 + 路由注册 | `web/main.py` | 新增入口 + 跳转 |
| 3.8 | 联调测试 | — | 10 项验收标准全部通过 |

**验收标准**：详见 `DESIGN-WEB-UI-v2.1.md` §6

**工时估算**：~4h

---

## 4. Full 版路线图（MVP 上线后再细化）

> 以下为 Full 版模块清单，具体步骤在 MVP 接近完成时再细化。

| Phase | 模块 | 预估工时 | 核心价值 |
|---|---|---|---|
| F.1 | After Sales（售后管理） | 2d | 售后工单 + SLA 计算 + 知识库联动 |
| F.2 | Integration P1（系统对接） | 2.5d | ONES/OA/工时/企微文档/财务 自动同步 |
| F.3 | Knowledge Base（知识库） | 3d | 混合检索 + 知识图谱 + 多源导入 |
| F.4 | Dashboard Full（自定义看板） | 1.5d | 自定义指标 + 拖拽布局 + 多视图 |
| F.5 | 领域事件 + Outbox 改造 | 1d | 模块解耦 + 异步事件驱动 |
| F.6 | Project Management 补全（变更管理等） | 1d | 变更管理 + 更细结项检查 |
| **合计** | | **~11d** | |

---

## 5. 工时估算（MVP）

| Phase | 模块 | 预估工时 | 累计 |
|---|---|---|---|
| 0.1 | Base 层加固 | 1d | 1d |
| 0.2 | 数据模型 + 迁移脚本 | 1d | 2d |
| 1.1 | Contract Management MVP | 2d | 4d |
| 1.2 | Project Management MVP | 3d | 7d |
| 2.2 Lite | Integration P0 | 0.5d | 7.5d |
| 2.4 Lite | Dashboard MVP | 1d | 8.5d |
| **合计** | | **~8.5d** | |

> 注：工时为估算值，实际可能因设计变更、集成调试等因素调整。每 Phase 结束后根据实际进度重新校准。

---

## 6. 每 Phase 验收流程（强制执行）

每个 Phase 完成后，**自动执行交付验收 7 步法**，产出验收报告，等 Rex 确认后才进入下一 Phase。

| 步骤 | 验收内容 | 通过标准 | 负责人 |
|---|---|---|---|
| ① 独立审计 | 代码 + 接口契约 + 数据模型 | 与设计文档完全对齐 | Jerry（自动） |
| ② 契约对齐 | 跨模块接口调用 | 接口签名一致，调用无误 | Jerry（自动） |
| ③ 全入口执行 | CLI + Web API 全量执行 | 所有命令/API 无崩溃 | Jerry（自动） |
| ④ 黄金基准 | 对比已有数据（如有） | 零差异 | Jerry（自动） |
| ⑤ 幂等测试 | 重复执行关键操作 | 结果一致，无副作用 | Jerry（自动） |
| ⑥ 调用点扫描 | 所有引用点检查 | 无悬空引用，无 404 | Jerry（自动） |
| ⑦ 回归锁定 | 现有测试全量通过 | 已有功能无退化 | Jerry（自动） |

**流程**：
1. Jerry 完成 Phase 开发
2. 自动跑 7 步法，产出 `VERIFICATION-<phase>-v2.1.md`
3. 报告发给 Rex 审核
4. ✅ Rex 通过 → 进入下一 Phase
5. ❌ 有问题 → 修复后重跑，重新提交审核

---

## 7. 开发规范

### 7.1 代码规范

- 所有公共方法必须有完整 type hints
- 所有公共类/方法必须有 docstring
- 异常类型统一 + 错误码映射
- 日志格式统一（结构化日志）
- 配置从 `sys_settings` 读取，不硬编码

### 7.2 测试策略

| 层级 | 覆盖率要求 | 说明 |
|---|---|---|
| 引擎层（Engine） | ≥ 90% | 纯函数，好测，必须全覆盖 |
| 服务层（Service） | ≥ 70% | 关键路径必测，边缘场景可选 |
| 仓储层（Repository） | ≥ 60% | CRUD 必测，复杂查询必测 |
| CLI / Web 层 | 冒烟即可 | 每个入口至少跑通一次 |
| 导入导出层 | 核心路径必测 | 正常路径 + 异常路径 |

### 7.3 Token 消耗标记

| 标记 | 含义 | MVP 阶段是否使用 |
|---|---|---|
| 🔒 NO_TOKEN | 纯代码逻辑 | ✅ 全部核心功能 |
| ⚡ OPTIONAL_TOKEN | 可选 AI 功能 | ❌ MVP 不实现 |
| 🔥 REQUIRED_TOKEN | 必须 AI 功能 | ❌ MVP 不实现 |

### 7.4 Git 提交规范

- 每个 Phase 完成后提交一次（含该 Phase 全部代码 + 测试 + 文档）
- commit message 格式：`feat(v2.1-mvp): [Phase名] - 简要描述`
- 提交前确保：单测通过 + 凭据扫描通过 + 无明文密钥
- 每次提交后立即 push（代理可用时走代理，不可用时走直连绕过）

---

## 8. 风险与回滚预案

| 风险 | 概率 | 影响 | 预案 |
|---|---|---|---|
| 数据模型设计有缺陷，后期改表影响大 | 中 | 高 | Phase 0.2 完成后先做一次 schema review，确认后再进 Phase 1 |
| 现有 v1.0 数据有脏数据，迁移失败 | 中 | 中 | 迁移脚本先在测试库上跑 3 次，验证幂等；生产库迁移前先备份 |
| 某个模块复杂度超预期，工期延误 | 高 | 中 | 模块内再拆 P0/P1，先跑通核心路径，边缘功能后补 |
| 外部系统接口不确认，Integration 卡壳 | 高 | 低（MVP 不依赖） | MVP 只做本地文件导入，系统对接放 Full 版，不卡进度 |
| 设计文档有遗漏，开发中发现缺设计 | 中 | 中 | 发现后先补设计文档，再写代码；不允许边想边写 |

---

## 9. 待确认事项（不阻塞 MVP，但 Full 版需要）

| 事项 | 状态 | 影响范围 | 说明 |
|---|---|---|---|
| ONES API 可用性 | ⏳ 待确认 | Full / Integration P1 | 确认 ONES 是否有 API 或必须走浏览器自动化 |
| OA 系统接口文档 | ⏳ 待确认 | Full / Integration P1 | 确认 OA 系统 API 格式 |
| 工时系统接口 | ⏳ 待确认 | Full / Integration P1 | 确认工时门户是否支持 API |
| 企业微信文档 API | ⏳ 待确认 | Full / Integration P1 | 确认企微文档 API 权限和格式 |
| 电子签名服务选型 | ⏳ 待确认 | Full / Contract | e签宝/法大大/腾讯电子签 |
| 外部知识源清单 | ⏳ 待确认 | Full / Knowledge Base | SharePoint/Confluence/文件共享的具体配置 |

> 以上事项**不阻塞 MVP 开发**，可以在 MVP 开发过程中并行确认。

---

_本计划基于 9 份详细设计文档 + Rex Review 反馈汇总。开发过程中如有设计变更，需同步更新对应文档。_

<!-- project: github.com/RenLimin/openclaw-v5.0 -->
