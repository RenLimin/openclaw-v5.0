# BDMS v2.1 开发建设计划（IMPLEMENTATION-PLAN）

> 版本：v2.1 Implementation Plan r1（2026-09-25）
> 依据：PRD-v2.1 + DESIGN-OUTLINE-v2.1 + 7 份 DESIGN-DETAIL（已审核通过）+ VERIFICATION-v2.1
> 状态：待 Rex 审核

---

## 0. 版本定位

| 维度 | v1.0（现有） | v2.1（本次迭代） |
|---|---|---|
| 模块数 | 5 | **7**（+项目利润 +驾驶舱独立） |
| 代码状态 | 部分模块已有代码 | **重构 + 迁移 + 补齐** |
| 架构 | 平层 | **分层**（core + base + modules + L3） |
| 测试 | 无系统测试 | **7 层测试方案**（VERIFICATION-v2.1） |

---

## 1. 现有代码资产盘点

### 1.1 已实现模块（可复用/重构）

| 模块 | 代码行数 | 状态 | 重构需求 |
|---|---|---|---|
| contract_management | 2,383 | ✅ 已实现 | 对齐新接口契约 + OS 依赖 + 角色权限 |
| project_management | 3,069 | ✅ 已实现 | 新增 after_sales 子引擎 + 角色权限 |
| delivery_report | 2,889 | ✅ 已实现 | 对齐分步流程 + 校验器 + 统计走 DASHBOARD |
| revenue | 2,181 | ✅ 已实现 | 对齐 ASC 606 + 校验规则 + 手工调整列 |
| dashboard | 1,151 | ✅ 已实现 | 扩展为驾驶舱（视图管理 + 下钻 + 编辑 + 数据源注册） |
| master_data | 654 | ✅ 已实现 | 基本不变 |
| settings | 420 | ✅ 已实现 | 基本不变 |

### 1.2 待开发模块

| 模块 | 代码行数 | 状态 | 说明 |
|---|---|---|---|
| profit_management | 0 | ❌ 未开发 | 全新模块（含成本迁移重构） |
| integration | 0 | ❌ 未开发 | 全新横切模块（5 连接器） |

### 1.3 需迁移重构的代码

| 资产 | 当前位置 | 目标位置 | 迁移方式 |
|---|---|---|---|
| CostEngine/CostService/CostImporter | project_management/cost/ | profit_management/ | **迁移重构**（逻辑内核保留，接口按新契约对齐） |
| ct_timesheets 表 | core/schemas.py | pf_timesheet（新表） | 数据迁移 + 旧表转 VIEW |
| ct_device_usage 表 | core/schemas.py | pf_device_usage（新表） | 同上 |
| ct_travel_costs 表 | core/schemas.py | pf_travel_cost（新表） | 同上 |
| ct_staff_rates 表 | core/schemas.py | pf_staff_rate（新表） | 同上 |

---

## 2. 开发原则

| 原则 | 落地方式 |
|---|---|
| **先迁移后开发** | 成本模块迁移重构完成后再开发利润模块 |
| **先核心后扩展** | MVP 核心链路（合同→项目→交付→确收→利润→驾驶舱）先行 |
| **接口驱动** | 先定义接口契约（Base 层），再实现具体逻辑 |
| **测试先行** | 每个 Phase 先写测试用例，再写实现代码 |
| **幂等可重入** | 所有生成/计算操作支持 auto/read/regenerate 三模式 |
| **DB 共享解耦** | 模块间不直接调用，通过 DB 共享 + 事件总线 |

---

## 3. Phase 拆分

### Phase 0：基础设施对齐（Base 层 + 数据模型）

**目标**：对齐 7 份 DESIGN-DETAIL 的数据模型 + Base 层接口契约。

| 任务 | 描述 | 产出 | 工时 |
|---|---|---|---|
| P0-01 | Base 层接口对齐 | BaseEngine/BaseService/BaseImporter/BaseExporter 接口与 7 份 DESIGN-DETAIL 对齐 | 0.5d |
| P0-02 | 数据模型 DDL 对齐 | 7 份 DESIGN-DETAIL 的 DDL 与现有 schemas_v21.py 对齐（pf_* 新表 + dr_edit_history + rr_edit_history + rr_import_validation + dashboard_data_source） | 0.5d |
| P0-03 | 版本记录统一 | 7 份 DESIGN-DETAIL 的 §0 版本记录与 IMPLEMENTATION-PLAN 对齐 | 0.2d |
| P0-04 | 角色权限统一 | 7 份 DESIGN-DETAIL 的角色体系（PMO/超级管理员）与现有代码对齐 | 0.3d |

**Phase 0 验收**：
- [ ] Base 层接口与 DESIGN-DETAIL 一致
- [ ] DDL 与 DESIGN-DETAIL 一致
- [ ] 角色权限与 DESIGN-DETAIL 一致

---

### Phase 1：合同管理对齐（contract_management）

**目标**：对齐 CONTRACT-MANAGEMENT DESIGN-DETAIL v2.1 r2。

| 任务 | 描述 | 产出 | 工时 |
|---|---|---|---|
| P1-01 | 接口契约对齐 | Engine/Service 接口与 DESIGN-DETAIL §4 对齐（含 generate_review_suggestions + fetch_from_oa） | 0.5d |
| P1-02 | 合同关联关系 | 实现 cr_contract_relations 表 + 关联规则（前 14 位 + BC/ZZ/-） | 0.5d |
| P1-03 | OA 自动获取 | 场景 A/B 的浏览器自动化集成（I-02 连接器） | 1d |
| P1-04 | WeCom 交互 | 场景 C 的消息回调 + 指令解析 | 0.5d |
| P1-05 | 角色权限 | PMO/超级管理员角色实现 | 0.3d |
| P1-06 | 错误处理 | CR-4xxx/5xxx/6xxx 错误码 + 降级链 | 0.3d |

**Phase 1 验收**：
- [ ] 接口与 DESIGN-DETAIL 一致
- [ ] 合同关联规则通过 UT-CM-15/16
- [ ] OA 自动获取通过 IT-CM-13
- [ ] WeCom 交互通过 IT-CM-14

---

### Phase 2：项目管理对齐（project_management）

**目标**：对齐 PROJECT-MANAGEMENT DESIGN-DETAIL v2.1 r2。

| 任务 | 描述 | 产出 | 工时 |
|---|---|---|---|
| P2-01 | 售后管理 | after_sales 子引擎（转售后/工单 CRUD/SLA 监控/结项前置检查） | 1d |
| P2-02 | 状态机扩展 | after_sales 状态 + 7 阶段模板 | 0.3d |
| P2-03 | 角色权限 | §1.6 角色与权限矩阵实现 | 0.3d |
| P2-04 | 接口契约对齐 | Engine/Service 接口与 DESIGN-DETAIL §3 对齐 | 0.5d |
| P2-05 | 错误处理 | PM-4xxx/5xxx 错误码 | 0.2d |

**Phase 2 验收**：
- [ ] 售后管理通过 IT-PM-02
- [ ] after_sales 状态机通过 UT-PM-07/08
- [ ] 角色权限通过 UT-PM（权限矩阵）

---

### Phase 3：交付月报对齐（delivery_report）

**目标**：对齐 DELIVERY-REPORT DESIGN-DETAIL v2.1 r2。

| 任务 | 描述 | 产出 | 工时 |
|---|---|---|---|
| P3-01 | 分步执行流程 | extract_raw_data → validate → compute_formula → stats_via_dashboard → export | 1d |
| P3-02 | 数据校验器 | RevenueValidator（12 条规则 V01-V12）+ 存疑数据流程 | 0.5d |
| P3-03 | 统计汇总走 DASHBOARD | 10 个统计 Sheet 通过 DASHBOARD 实时聚合生成 | 0.5d |
| P3-04 | 图例配置预落盘 | 从黄金基准 Sheet-15 提取 → md_reference legend_config | 0.3d |
| P3-05 | c80 逐行去重 | POC 统计所属项目实现 | 0.2d |
| P3-06 | 接口契约对齐 | Engine/Service 接口与 DESIGN-DETAIL §3 对齐 | 0.3d |

**Phase 3 验收**：
- [ ] 分步流程通过 IT-DR-01/02/03
- [ ] 校验规则通过 UT-DR-10/11/12
- [ ] c80 去重通过 UT-DR-09

---

### Phase 4：确收分析对齐（revenue）

**目标**：对齐 REVENUE DESIGN-DETAIL v2.1 r3。

| 任务 | 描述 | 产出 | 工时 |
|---|---|---|---|
| P4-01 | ASC 606 准则 | 五步法 + 时点法/时段法判定 + 知识库自动填充 | 0.5d |
| P4-02 | 手工调整列 | 14 个下拉列 + 7 个文本框 + 4 个日期列 + 编辑权限矩阵 | 0.5d |
| P4-03 | 数据校验规则 | V01-V12 校验 + rr_import_validation 表 + 存疑处置流程 | 0.5d |
| P4-04 | 合同关联 | c68 关联合同引用 CONTRACT §6 关联规则 | 0.2d |
| P4-05 | 接口契约对齐 | Engine/Service 接口与 DESIGN-DETAIL §3 对齐 | 0.3d |

**Phase 4 验收**：
- [ ] ASC 606 通过 ASC-06~11
- [ ] 手工调整列通过 MA-01~19
- [ ] 校验规则通过 V01-V12

---

### Phase 5：项目利润管理（profit_management）— 全新开发

**目标**：按 PROFIT-MANAGEMENT DESIGN-DETAIL v2.1 r2 全新开发。

| 任务 | 描述 | 产出 | 工时 |
|---|---|---|---|
| P5-01 | 成本迁移重构 | CostEngine/CostService/CostImporter 从 project_management/cost/ 迁移到 profit_management/ | 1d |
| P5-02 | 数据迁移 | ct_* 表 → pf_* 新表 + 旧表转 VIEW + 迁移脚本 | 0.5d |
| P5-03 | 利润引擎 | ProfitEngine（compute_profit / get_cost_summary / check_budget_alert / aggregate） | 1d |
| P5-04 | 利润服务 | ProfitService（submit_timesheet / approve_timesheet / import_travel_cost / get_profit_report / list_projects_profit / sync_revenue） | 1d |
| P5-05 | 预算告警 | BudgetAlertService（check_all / get_alert_history / resolve_alert） | 0.3d |
| P5-06 | 利润报表 | ProfitExporter（按项目/部门/时间维度） | 0.3d |
| P5-07 | PMP/EVM 占位 | pf_profit_snapshot 预留 pv/ev 字段 + pf_cash_flow/pf_cost_overhead 占位表 | 0.2d |

**Phase 5 验收**：
- [ ] 成本迁移通过 IT-PF-01（全流程）
- [ ] 利润计算通过 UT-PF-01~03
- [ ] 预算告警通过 UT-PF-08/09
- [ ] 数据迁移通过 IT-PF-06

---

### Phase 6：驾驶舱对齐（dashboard）

**目标**：对齐 DASHBOARD DESIGN-DETAIL v2.1 r3。

| 任务 | 描述 | 产出 | 工时 |
|---|---|---|---|
| P6-01 | 视图管理 | DashboardCustomizationService（视图 CRUD + 预设模板 + 默认视图） | 0.5d |
| P6-02 | 数据源注册 | DashboardDataSourceService（register_source / list_sources / compute_metric） | 0.5d |
| P6-03 | SQL 辅助操作 | generate_sql_template / validate_sql / describe_sql / dry_run_sql / suggest_field_mapping / estimate_performance | 0.5d |
| P6-04 | 下钻功能 | drill_down 三级穿透 + 筛选/排序/分页 | 0.3d |
| P6-05 | 明细编辑 | DashboardEditService（字段编辑 + 权限 + 历史 + 批量 + 撤销） | 0.5d |
| P6-06 | 接口契约对齐 | DashboardService 接口与 DESIGN-DETAIL §6 对齐 | 0.3d |

**Phase 6 验收**：
- [ ] 视图 CRUD 通过 UT-DB-10
- [ ] 数据源注册通过 UT-DB-16/17
- [ ] 下钻三级通过 UT-DB-04/05/06
- [ ] 字段编辑通过 UT-DB-12/13/14/15

---

### Phase 7：数据集成（integration）— 全新开发

**目标**：按 INTEGRATION DESIGN-DETAIL v2.1 r2 全新开发。

| 任务 | 描述 | 产出 | 工时 |
|---|---|---|---|
| P7-01 | 连接器框架 | BaseConnector + ConnectorRegistry + 适配器（BrowserAdapter / HttpAdapter / FileParser） | 0.5d |
| P7-02 | ONES 连接器 | ones_connector（浏览器自动化 CSV 导出） | 0.5d |
| P7-03 | OA 连接器 | oa_connector（浏览器自动化页面抓取） | 0.5d |
| P7-04 | 工时门户连接器 | timesheet_connector（浏览器自动化 Excel 导出） | 0.3d |
| P7-05 | 企微文档连接器 | wecom_doc_connector（API + 浏览器 + 本机导入多方案降级） | 0.5d |
| P7-06 | 本机导入连接器 | local_import_connector（Excel/CSV 解析 + 字段映射） | 0.3d |
| P7-07 | 频率配置 | configure_frequency（cron / 手动 / 事件驱动） | 0.2d |
| P7-08 | 暂存流转 | staging → 幂等写入业务表 + 事件通知 | 0.3d |
| P7-09 | 错误重试 | 指数退避 + 死信队列 | 0.2d |
| P7-10 | OS 适配 | create_browser_adapter 工厂方法（macOS/Linux/Windows） | 0.3d |

**Phase 7 验收**：
- [ ] 5 连接器通过 UT-IN-01~10
- [ ] OS 适配通过 IT-IN（多平台）
- [ ] 幂等通过 IT-IN-06

---

### Phase 8：Web UI + 安全

**目标**：对齐各模块 DESIGN-DETAIL 的 Web API + 安全模块。

| 任务 | 描述 | 产出 | 工时 |
|---|---|---|---|
| P8-01 | 合同管理页面 | 列表/详情/审批操作 + OA 获取按钮 | 0.5d |
| P8-02 | 项目管理页面 | 列表/详情/状态推进 + 售后工单 | 0.5d |
| P8-03 | 交付月报页面 | 月份选择 + 生成/导出 + 存疑数据展示 | 0.3d |
| P8-04 | 确收分析页面 | 导入/生成/导出 + 手工调整列编辑 | 0.5d |
| P8-05 | 项目利润页面 | 利润报表 + 告警列表 + 成本管理 | 0.3d |
| P8-06 | 驾驶舱页面 | 默认驾驶舱 + 视图管理 + 下钻 + 编辑 | 0.5d |
| P8-07 | 安全模块 | Token 鉴权 + 内外网开关 + 登录页 | 0.3d |

**Phase 8 验收**：
- [ ] 各页面 E2E 通过（真实 HTTP）
- [ ] 权限矩阵通过 E2E

---

### Phase 9：集成测试 + 回归测试 + 性能测试

**目标**：按 VERIFICATION-v2.1 执行全量测试。

| 任务 | 描述 | 产出 | 工时 |
|---|---|---|---|
| P9-01 | 单元测试补齐 | 7 模块 108 个 UT 全部通过 | 1d |
| P9-02 | 集成测试 | 7 模块 49 个 IT 全部通过 | 1d |
| P9-03 | E2E 测试 | 7 模块 31 个 E2E 全部通过 | 1d |
| P9-04 | 回归测试 | 黄金基准逐格比对通过 | 0.5d |
| P9-05 | 性能测试 | 10 项指标全部达标 | 0.3d |
| P9-06 | 手工调整列测试 | 19 个 MA 全部通过 | 0.2d |
| P9-07 | ASC 606 专项测试 | 14 个 ASC 全部通过 | 0.2d |

**Phase 9 验收**：
- [ ] 单元测试覆盖率 ≥ 80%
- [ ] 黄金基准逐格比对通过
- [ ] 性能指标全部达标

---

## 4. 依赖关系图

```
Phase 0 (基础设施对齐)
    │
    ├──→ Phase 1 (合同管理对齐)
    │         │
    │         └──→ Phase 2 (项目管理对齐)
    │                   │
    │                   └──→ Phase 3 (交付月报对齐)
    │                             │
    │                             └──→ Phase 4 (确收分析对齐)
    │                                       │
    │                                       └──→ Phase 5 (项目利润管理)
    │                                                 │
    │                                                 └──→ Phase 6 (驾驶舱对齐)
    │                                                           │
    │                                                           └──→ Phase 7 (数据集成)
    │                                                                     │
    │                                                                     └──→ Phase 8 (Web UI + 安全)
    │                                                                               │
    │                                                                               └──→ Phase 9 (全量测试)
```

**关键路径**：Phase 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9

---

## 5. 里程碑

| 里程碑 | Phase | 交付物 | 验收标准 | 预估工时 |
|---|---|---|---|---|
| M0 | Phase 0 | Base 层 + DDL 对齐 | 接口与 DESIGN-DETAIL 一致 | 1.5d |
| M1 | Phase 1 | 合同管理对齐 | UT-CM 18 个 + IT-CM 14 个通过 | 3.1d |
| M2 | Phase 2 | 项目管理对齐 | UT-PM 18 个 + IT-PM 9 个通过 | 2.1d |
| M3 | Phase 3 | 交付月报对齐 | UT-DR 14 个 + IT-DR 6 个通过 | 2.5d |
| M4 | Phase 4 | 确收分析对齐 | UT-RV 14 个 + IT-RV 6 个通过 | 2.0d |
| M5 | Phase 5 | 项目利润管理 | UT-PF 15 个 + IT-PF 6 个通过 | 3.5d |
| M6 | Phase 6 | 驾驶舱对齐 | UT-DB 18 个 + IT-DB 6 个通过 | 2.6d |
| M7 | Phase 7 | 数据集成 | UT-IN 10 个 + IT-IN 7 个通过 | 3.6d |
| M8 | Phase 8 | Web UI + 安全 | E2E 全链通过 | 2.7d |
| M9 | Phase 9 | 全量测试 | 252 用例全通过 | 4.2d |

**总预估工时**：~25.8 人天

---

## 6. 风险与缓解

| 风险 | 影响 | 概率 | 缓解 |
|---|---|---|---|
| 成本迁移重构影响现有功能 | 高 | 中 | 迁移前全量测试 + 兼容 VIEW + 灰度切换 |
| 黄金基准数据不完整 | 中 | 低 | 提前确认 202606 基准文件可访问 |
| 浏览器自动化 OS 适配 | 中 | 中 | 工厂方法自动选择 + 多 OS 测试 |
| 利润模块全新开发工期超预期 | 中 | 中 | 按 DESIGN-DETAIL 契约开发，避免返工 |
| 跨模块集成测试复杂度高 | 高 | 中 | 分 Phase 集成 + 全量回归 |

---

## 7. 变更历史

| 版本 | 日期 | 变更 |
|---|---|---|
| v2.1 r1 | 2026-09-25 | 初版：基于 7 份 DESIGN-DETAIL 重编，9 Phase + 里程碑 + 依赖图 |

---

> 文档结束 | IMPLEMENTATION-PLAN-v2.1 r1 | 2026-09-25
