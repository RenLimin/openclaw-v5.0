---
type: adr
id: ADR-202608-022
date: 2026-09-01
title: L4 BDMS 交付中心运营引擎 — 数据采集 + 业务引擎 + 报告生成
status: accepted
deciders: [Rex]
layers: [L4]
tags: [bdms, delivery, data-collection, report, oa, ones, wecom, workhour]
supersedes: null
superseded_by: null
---

# [ADR-202608-022] L4 BDMS 交付中心运营引擎

## 1. 状态
**accepted** — 2026-09-01 起生效

## 2. 背景

Bangcle 交付中心需要自动化报告生成能力，包括数据采集（OA/ONES/WeCom/工时）、业务逻辑处理（关联查询/状态判定/考核计算/差异分析）和报告输出（Excel）。

之前这些能力散落在各脚本中，缺乏统一架构。需要注册为标准化 L4 组件。

## 3. 考虑的选项

### 选项 A: 独立脚本（各采集器独立运行）
- 优点：简单
- 缺点：无法复用、难以维护

### 选项 B: 分层架构（M1 采集 + M2 引擎 + M3 报告 + M4 审批 + M5 调度）
- 优点：清晰分层、可复用、可维护
- 缺点：初始工作量大

### 选项 C: 外部 BI 工具
- 优点：开箱即用
- 缺点：成本高、不可定制

## 4. 决策
我们选择 **选项 B**，因为需要长期可维护的标准化能力。

## 5. 后果
### 5.1 正面
- 5 个采集器统一架构（OA/ONES/WeCom/工时/API）
- 4 个业务引擎可复用（关联/状态/考核/差异）
- 2 个报告生成器（交付月报 12 Sheet + 确收月报 6Sheet）
- SQLite 持久化 + 每日自动备份

### 5.2 负面
- 初始开发工作量大（24 个 Python 文件，3157 行代码）
- 依赖 headful 浏览器（OA 导出需要 Playwright）

### 5.3 风险
- OA 系统变更导致自动化失效
- Cookie 过期需要重新登录

## 6. 实现计划
- [x] M1 数据采集（5 个采集器 + 清洗 + SQLite）
- [x] M2 业务引擎（关联查询/状态判定/考核计算/差异分析/汇总统计）
- [x] M3 报告生成（交付月报 + 确收月报）
- [x] M4 审批流程（合同解析 + 审批摘要）
- [x] M5 调度监控（cron 配置 + WeCom 投递接口）

## 7. 验证标准
- OA 合同台账 11,177 行成功导入
- 确收凭证 514 行 + 验收凭证 531 行成功导入
- 交付月报 12 Sheet + 确收月报 6Sheet 成功生成

## 8. 相关决策
- 相关 ADR: ADR-202608-006 (持久化适配)
- 相关 ADR: ADR-202608-016 (Office 文档生成)

## 9. 引用
- 设计文档: `docs/architecture/components/l4-delivery-center/DESIGN.md`
- 代码: `scripts/l4/delivery_center/`

## 10. 变更历史
- 2026-08-28: proposed
- 2026-09-01: accepted
