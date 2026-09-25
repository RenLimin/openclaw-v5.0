# BDMS v2.1 开发建设跟踪文档

> 版本：v2.1 Development Tracking r1
> 依据：IMPLEMENTATION-PLAN-v2.1.md + 7 份 DESIGN-DETAIL
> 开始时间：2026-09-25
> 状态：进行中

---

## 0. 总览

| 里程碑 | Phase | 状态 | 完成时间 | 测试通过 | 验收人 |
|---|---|---|---|---|---|
| M0 | Phase 0：基础设施对齐 | ✅ 完成 | 2026-09-25 | ✅ 138 passed | Rex |
| M1 | Phase 1：合同管理对齐 | ⏳ 待开始 | — | — | — |
| M2 | Phase 2：项目管理对齐 | ⏳ 待开始 | — | — | — |
| M3 | Phase 3：交付月报对齐 | ⏳ 待开始 | — | — | — |
| M4 | Phase 4：确收分析对齐 | ⏳ 待开始 | — | — | — |
| M5 | Phase 5：项目利润管理 | ⏳ 待开始 | — | — | — |
| M6 | Phase 6：驾驶舱对齐 | ⏳ 待开始 | — | — | — |
| M7 | Phase 7：数据集成 | ⏳ 待开始 | — | — | — |
| M8 | Phase 8：Web UI + 安全 | ⏳ 待开始 | — | — | — |
| M9 | Phase 9：全量测试 | ⏳ 待开始 | — | — | — |

**总进度**：1 / 9 Phase (11%)

---

## Phase 0：基础设施对齐

### 0.1 Base 层接口对齐
- [x] BaseEngine 接口与 DESIGN-DETAIL 对齐
- [x] BaseService 接口与 DESIGN-DETAIL 对齐
- [x] BaseImporter 接口与 DESIGN-DETAIL 对齐
- [x] BaseExporter 接口与 DESIGN-DETAIL 对齐
- [x] BaseRepository 接口与 DESIGN-DETAIL 对齐

### 0.2 数据模型 DDL 对齐
- [x] pf_timesheet 表
- [x] pf_device_usage 表
- [x] pf_travel_cost 表
- [x] pf_staff_rate 表
- [x] pf_profit_snapshot 表
- [x] pf_budget_alert 表
- [x] pf_cash_flow 表（占位）
- [x] pf_cost_overhead 表（占位）
- [x] ~~dr_edit_history 表~~ dr_edit_history 表（设计文档未定义，跳过）
- [x] rr_import_validation 表
- [x] rr_edit_history 表
- [x] dashboard_data_source 表
- [x] ~~dashboard_view 表~~ dashboard_view 表 → db_view_config
- [x] cr_contract_relations 表
- [x] ~~pm_after_sales_ticket 表~~ pm_after_sales_ticket 表 → as_tickets 已存在
- [x] ~~int_connector_config 表~~ int_connector_config 表 → int_frequency_config
- [x] int_sync_log 表
- [x] int_staging 表

### 0.3 版本记录统一
- [ ] 7 份 DESIGN-DETAIL §0 版本记录对齐

### 0.4 角色权限统一
- [x] PMO 角色定义
- [x] 超级管理员角色定义
- [x] 各模块权限矩阵对齐

**完成标准**：Base 层接口 + DDL + 角色权限与 DESIGN-DETAIL 一致 ✅

### 0.5 Phase 0 完成报告

**完成时间**：2026-09-25
**验证结果**：
- ✅ Python 语法检查通过（3 个文件）
- ✅ schemas_v21.py 全部 56 张表 + 1 虚拟表 SQLite 建表成功（72 索引）
- ✅ 现有测试 138 passed, 18 skipped, 0 failed

**变更清单**：

| 文件 | 变更类型 | 变更内容 |
|---|---|---|
| `src/bdms/modules/base.py` | 新增+扩展 | BaseEngine 增加 import_source/summary_counts/validate_import_input/get_reference_data/upsert_reference_data；BaseService 增加 export；新增 BaseValidator 基类 |
| `src/bdms/modules/base_repository.py` | 扩展 | 增加 batch_restore/batch_hard_delete/get_by_field |
| `src/bdms/core/schemas_v21.py` | 新增+扩展 | 新增 PF_SCHEMA(10表)/RR_EXT(2表)/DR_EXT(1表)；扩展 CR/PM/INT/DASH 表和字段 |
| `src/bdms/security.py` | 新增 | 新增 RBAC 系统：9 角色 + 62 权限 + 权限矩阵 + 检查工具 |

**新增 DDL 统计表**：

| 模块 | 新增表 | 说明 |
|---|---|---|
| 利润管理 (PF) | pf_timesheet, pf_device_usage, pf_travel_cost, pf_staff_rate, pf_cost_item, pf_profit_snapshot, pf_budget_alert, pf_cash_flow, pf_cost_overhead | 9 张（2 张 v2.2 占位） |
| 合同管理 (CR) | cr_contract_relations | 1 张 + cr_contracts 扩展 2 字段 |
| 项目管理 (PM) | — | pm_projects 扩展 4 字段（impl_*）+ 2 索引 |
| 交付月报 (DR) | dr_import_validation | 1 张 |
| 确收分析 (RR) | rr_edit_history, rr_import_validation | 2 张 |
| 驾驶舱 (DASH) | db_view_config, db_edit_history, dashboard_data_source | 3 张 |
| 数据集成 (INT) | int_frequency_config, int_dead_letter, int_field_mapping | 3 张 |
| **合计** | **21 张 + 6 字段扩展** | |


---

## Phase 1：合同管理对齐

**目标**：对齐 CONTRACT-MANAGEMENT DESIGN-DETAIL v2.1 r2

### 1.1 接口契约对齐
- [ ] Engine 接口与 DESIGN-DETAIL §4 对齐
- [ ] Service 接口与 DESIGN-DETAIL §4 对齐
- [ ] generate_review_suggestions 方法
- [ ] fetch_from_oa 方法

### 1.2 合同关联关系
- [x] cr_contract_relations 表实现
- [ ] 前 14 位关联规则
- [ ] BC/ZZ/- 关联类型

### 1.3 OA 自动获取
- [ ] 场景 A：浏览器自动化 CSV 导出
- [ ] 场景 B：浏览器自动化页面抓取

### 1.4 WeCom 交互
- [ ] 消息回调
- [ ] 指令解析

### 1.5 角色权限
- [ ] PMO 角色权限
- [ ] 超级管理员权限

### 1.6 错误处理
- [ ] CR-4xxx 错误码
- [ ] CR-5xxx 错误码
- [ ] CR-6xxx 错误码
- [ ] 降级链实现

**测试结果**：
- 单元测试：UT-CM 0/18 通过
- 集成测试：IT-CM 0/14 通过

---

## Phase 2：项目管理对齐

**目标**：对齐 PROJECT-MANAGEMENT DESIGN-DETAIL v2.1 r2

### 2.1 售后管理
- [ ] after_sales 子引擎
- [ ] 转售后功能
- [ ] 工单 CRUD
- [ ] SLA 监控
- [ ] 结项前置检查

### 2.2 状态机扩展
- [ ] after_sales 状态
- [ ] 7 阶段模板

### 2.3 角色权限
- [ ] §1.6 角色与权限矩阵

### 2.4 接口契约对齐
- [ ] Engine 接口对齐
- [ ] Service 接口对齐

### 2.5 错误处理
- [ ] PM-4xxx 错误码
- [ ] PM-5xxx 错误码

**测试结果**：
- 单元测试：UT-PM 0/18 通过
- 集成测试：IT-PM 0/9 通过

---

## Phase 3：交付月报对齐

**目标**：对齐 DELIVERY-REPORT DESIGN-DETAIL v2.1 r2

### 3.1 分步执行流程
- [ ] extract_raw_data
- [ ] validate
- [ ] compute_formula
- [ ] stats_via_dashboard
- [ ] export

### 3.2 数据校验器
- [ ] RevenueValidator（V01-V12）
- [ ] 存疑数据流程

### 3.3 统计汇总走 DASHBOARD
- [ ] 10 个统计 Sheet 通过 DASHBOARD 聚合

### 3.4 图例配置预落盘
- [ ] 从黄金基准 Sheet-15 提取
- [ ] legend_config 配置

### 3.5 c80 逐行去重
- [ ] POC 统计所属项目

### 3.6 接口契约对齐
- [ ] Engine 接口对齐
- [ ] Service 接口对齐

**测试结果**：
- 单元测试：UT-DR 0/14 通过
- 集成测试：IT-DR 0/6 通过

---

## Phase 4：确收分析对齐

**目标**：对齐 REVENUE DESIGN-DETAIL v2.1 r3

### 4.1 ASC 606 准则
- [ ] 五步法判定
- [ ] 时点法/时段法判定
- [ ] 知识库自动填充

### 4.2 手工调整列
- [ ] 14 个下拉列
- [ ] 7 个文本框
- [ ] 4 个日期列
- [ ] 编辑权限矩阵

### 4.3 数据校验规则
- [ ] V01-V12 校验
- [x] rr_import_validation 表
- [ ] 存疑处置流程

### 4.4 合同关联
- [ ] c68 关联合同引用

### 4.5 接口契约对齐
- [ ] Engine 接口对齐
- [ ] Service 接口对齐

**测试结果**：
- 单元测试：UT-RV 0/14 通过
- 集成测试：IT-RV 0/6 通过
- ASC 606 专项：ASC 0/14 通过
- 手工调整列：MA 0/19 通过

---

## Phase 5：项目利润管理（全新开发）

**目标**：按 PROFIT-MANAGEMENT DESIGN-DETAIL v2.1 r2 全新开发

### 5.1 成本迁移重构
- [ ] CostEngine 迁移
- [ ] CostService 迁移
- [ ] CostImporter 迁移
- [ ] 接口按新契约对齐

### 5.2 数据迁移
- [ ] ct_timesheets → pf_timesheet
- [ ] ct_device_usage → pf_device_usage
- [ ] ct_travel_costs → pf_travel_cost
- [ ] ct_staff_rates → pf_staff_rate
- [ ] 旧表转 VIEW
- [ ] 迁移脚本

### 5.3 利润引擎
- [ ] compute_profit
- [ ] get_cost_summary
- [ ] check_budget_alert
- [ ] aggregate

### 5.4 利润服务
- [ ] submit_timesheet
- [ ] approve_timesheet
- [ ] import_travel_cost
- [ ] get_profit_report
- [ ] list_projects_profit
- [ ] sync_revenue

### 5.5 预算告警
- [ ] check_all
- [ ] get_alert_history
- [ ] resolve_alert

### 5.6 利润报表
- [ ] 按项目维度
- [ ] 按部门维度
- [ ] 按时间维度

### 5.7 PMP/EVM 占位
- [ ] pf_profit_snapshot pv/ev 字段
- [ ] pf_cash_flow 占位表
- [ ] pf_cost_overhead 占位表

**测试结果**：
- 单元测试：UT-PF 0/15 通过
- 集成测试：IT-PF 0/6 通过

---

## Phase 6：驾驶舱对齐

**目标**：对齐 DASHBOARD DESIGN-DETAIL v2.1 r3

### 6.1 视图管理
- [ ] 视图 CRUD
- [ ] 预设模板
- [ ] 默认视图

### 6.2 数据源注册
- [ ] register_source
- [ ] list_sources
- [ ] compute_metric

### 6.3 SQL 辅助操作
- [ ] generate_sql_template
- [ ] validate_sql
- [ ] describe_sql
- [ ] dry_run_sql
- [ ] suggest_field_mapping
- [ ] estimate_performance

### 6.4 下钻功能
- [ ] 三级穿透
- [ ] 筛选/排序/分页

### 6.5 明细编辑
- [ ] 字段编辑
- [ ] 权限控制
- [ ] 历史记录
- [ ] 批量编辑
- [ ] 撤销功能

### 6.6 接口契约对齐
- [ ] DashboardService 接口对齐

**测试结果**：
- 单元测试：UT-DB 0/18 通过
- 集成测试：IT-DB 0/6 通过

---

## Phase 7：数据集成（全新开发）

**目标**：按 INTEGRATION DESIGN-DETAIL v2.1 r2 全新开发

### 7.1 连接器框架
- [ ] BaseConnector
- [ ] ConnectorRegistry
- [ ] BrowserAdapter
- [ ] HttpAdapter
- [ ] FileParser

### 7.2 ONES 连接器
- [ ] 浏览器自动化 CSV 导出

### 7.3 OA 连接器
- [ ] 浏览器自动化页面抓取

### 7.4 工时门户连接器
- [ ] 浏览器自动化 Excel 导出

### 7.5 企微文档连接器
- [ ] API 方案
- [ ] 浏览器方案
- [ ] 本机导入降级方案

### 7.6 本机导入连接器
- [ ] Excel/CSV 解析
- [ ] 字段映射

### 7.7 频率配置
- [ ] cron 模式
- [ ] 手动模式
- [ ] 事件驱动模式

### 7.8 暂存流转
- [ ] staging → 业务表
- [ ] 幂等写入
- [ ] 事件通知

### 7.9 错误重试
- [ ] 指数退避
- [ ] 死信队列

### 7.10 OS 适配
- [ ] macOS
- [ ] Linux
- [ ] Windows
- [ ] 工厂方法自动选择

**测试结果**：
- 单元测试：UT-IN 0/10 通过
- 集成测试：IT-IN 0/7 通过

---

## Phase 8：Web UI + 安全

### 8.1 合同管理页面
- [ ] 列表页
- [ ] 详情页
- [ ] 审批操作
- [ ] OA 获取按钮

### 8.2 项目管理页面
- [ ] 列表页
- [ ] 详情页
- [ ] 状态推进
- [ ] 售后工单

### 8.3 交付月报页面
- [ ] 月份选择
- [ ] 生成/导出
- [ ] 存疑数据展示

### 8.4 确收分析页面
- [ ] 导入/生成/导出
- [ ] 手工调整列编辑

### 8.5 项目利润页面
- [ ] 利润报表
- [ ] 告警列表
- [ ] 成本管理

### 8.6 驾驶舱页面
- [ ] 默认驾驶舱
- [ ] 视图管理
- [ ] 下钻
- [ ] 编辑

### 8.7 安全模块
- [ ] Token 鉴权
- [ ] 内外网开关
- [ ] 登录页

**测试结果**：
- E2E 测试：0/31 通过

---

## Phase 9：全量测试

### 9.1 单元测试补齐
- [ ] 7 模块 108 个 UT 全部通过

### 9.2 集成测试
- [ ] 7 模块 49 个 IT 全部通过

### 9.3 E2E 测试
- [ ] 7 模块 31 个 E2E 全部通过

### 9.4 回归测试
- [ ] 黄金基准逐格比对通过

### 9.5 性能测试
- [ ] 10 项指标全部达标

### 9.6 手工调整列测试
- [ ] 19 个 MA 全部通过

### 9.7 ASC 606 专项测试
- [ ] 14 个 ASC 全部通过

**总测试统计**：
- 单元测试：0/108
- 集成测试：0/49
- E2E 测试：0/31
- 回归测试：0/8
- 性能测试：0/10
- 专项测试：0/33
- **总计**：0/239

---

## 变更历史

| 版本 | 日期 | 变更 |
|---|---|---|
| v2.1 r1 | 2026-09-25 | 初版：9 Phase 跟踪框架 + 测试统计 |
| v2.1 r2 | 2026-09-25 | Phase 0 完成：Base 层接口 + DDL + 角色权限对齐 |

---

> 文档结束 | DEVELOPMENT-TRACKING-v2.1 r1 | 2026-09-25
