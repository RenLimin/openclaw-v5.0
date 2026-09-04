---
title: "SLA 跟踪知识"
description: "服务级别协议定义、度量、监控、报告与违约处理的完整方法论"
source: "ITIL 4; ISO/IEC 20000-1:2018; SLA Management Best Practices"
version: "1.0.0"
category: "business"
dimension: "delivery-management"
sub_area: "capabilities"
type: "industry"
tags: ["sla_tracking", "service_level", "kpi", "ola", "service_management"]
capability: "sla_tracking"
xref:
  - path: "roles/project-manager/capability-map.md"
    relation: "referenced_by"
  - path: "capabilities/contract-interface.md"
    relation: "related_to"
last_reviewed: "2026-09-03"
---

# SLA 跟踪知识 SLA Tracking

## 概述 Overview

SLA（Service Level Agreement，服务级别协议）跟踪是交付管理框架中对承诺的服务级别进行定义、度量、监控、报告和持续改进的能力。SLA 是服务提供商与客户之间的 **服务绩效契约**，明确了服务范围、质量指标、考核方式和违约罚则。

在 DMS 框架中，SLA 跟踪是运营/运维交付模式下的核心控制机制——服务好不好不是感觉，而是数据说话，SLA 达成率直接关联客户满意度和合同收入。

## 核心概念 Key Concepts

### 1. SLA / OLA / UC
- **SLA 服务级别协议**：服务提供商与客户之间的外部协议，定义客户可感知的服务水平
- **OLA 运营级别协议**：内部部门之间的内部协议，支撑 SLA 的达成
- **UC 基础支持合同 Underpinning Contract**：与第三方供应商的外部合同，支撑 SLA 的达成
- 三者构成服务交付的层级承诺体系：SLA 面向客户，OLA 面向内部，UC 面向供应商

### 2. SLA 指标分类 SLA Metric Categories
- **可用性 Availability**：服务正常运行时间占比，如 99.9% 可用性
- **响应时间 Response Time**：从请求到响应的时长，如 P1 故障 15 分钟响应
- **解决时间 Resolution Time**：从请求到解决的时长，如 P1 故障 4 小时恢复
- **吞吐量 Throughput**：单位时间处理的请求量，如日均处理 1000 单
- **质量 Quality**：如首次解决率、客户满意度

### 3. 服务时间窗口 Service Window
SLA 生效的时间范围，如 7×24 小时、5×8 工作日、工作日 9:00-18:00 等。SLA 计算必须明确服务窗口，非服务时间不计入 SLA 计时。

### 4. SLA 违约与罚则 SLA Breach & Penalty
- SLA 未达标即为违约（breach）
- 罚则形式：服务 credits（服务费减免）、赔偿、合同终止权
- 通常设有豁免条款：客户原因、不可抗力、计划内维护等不计入违约

### 5. SLA 报表周期 SLA Reporting Cycle
SLA 达成情况的报告频率，通常为月度（monthly SLA report），由服务提供商提交客户确认。报表数据必须双方认可，争议需在约定时限内提出。

## 方法/流程 Methodology

DMS 框架下 SLA 管理采用 **定义-监控-报告-改进 PDCA 循环**：

### 1. 定义 SLA Define SLA
- 与客户协商确定 SLA 指标、目标值、测量方法、服务窗口、罚则
- SLA 指标必须符合 SMART 原则：Specific 具体、Measurable 可度量、Achievable 可实现、Relevant 相关、Time-bound 有时限
- 关键动作：
  - 识别服务目录（Service Catalog）
  - 为每项服务定义 SLA 指标和目标
  - 定义度量方法和数据来源
  - 定义报告频率和格式
  - 定义违约处理和申诉流程
- 输出：SLA 协议文档、SLA 度量手册

### 2. 监控 SLA Monitor SLA
- 实时采集服务数据（故障单、请求单、系统监控数据等）
- 自动计算 SLA 指标达成情况
- 设置分级预警：
  - 黄色预警：SLA 达成率接近阈值（如剩余时间 30%）
  - 红色预警：SLA 即将违约（如剩余时间 10%）
  - 违约触发：SLA 正式未达标
- 输出：实时 SLA 仪表盘、告警通知

### 3. 报告 SLA Report SLA
- 按周期生成 SLA 报告
- 报告内容：
  - 各项 SLA 指标达成率
  - 违约明细和原因分析
  - 改进措施和进展
  - 趋势分析
- 客户确认：报告提交客户审阅，处理争议
- 输出：周期 SLA 报告、客户确认记录

### 4. 改进 SLA Improve SLA
- 基于 SLA 数据分析瓶颈
- 制定改进措施（流程优化、技术升级、人员培训）
- 跟踪改进效果
- 必要时与客户协商调整 SLA 目标
- 输出：改进计划、SLA 修订版

## 度量指标 Metrics

| 指标名称 | 计算公式/定义 | 典型目标值 |
|---------|-------------|-----------|
| 服务可用性 Service Availability | 服务正常运行时间 / 总服务时间 × 100% | 99.9%（视服务等级） |
| SLA 达成率 SLA Achievement Rate | 达标的请求数 / 总请求数 × 100% | ≥ 95% |
| 平均响应时间 MTTA Mean Time to Acknowledge | 响应时间总和 / 总请求数 | 视优先级而定 |
| 平均解决时间 MTTR Mean Time to Resolve | 解决时间总和 / 已解决请求数 | 视优先级而定 |
| 首次解决率 FCR First Contact Resolution | 首次接触即解决的请求数 / 总请求数 | ≥ 70% |

## 常见陷阱 Common Pitfalls

1. **SLA 指标不可度量**："快速响应""高质量服务"等模糊表述，无法衡量也无法考核。SLA 必须量化、有明确计算方法和数据来源。
2. **指标太多抓不住重点**：一个 SLA 里塞几十个指标，客户和服务商都记不住。聚焦 3-5 个客户最关心的核心指标即可。
3. **数据来源不透明**：服务商自己统计自己的 SLA，客户不信任。必须定义清晰的度量方法，最好有双方认可的第三方数据或系统自动统计。
4. **SLA 与业务价值脱节**：为达标而达标，比如为了"响应时间达标"先接单但不解决问题。SLA 设计必须对齐客户真实业务目标。

## 与 DMS 框架的映射 DMS Framework Mapping

| DMS 模块 | 映射关系 |
|---------|---------|
| `sla-definition` 模块 | SLA 定义数据模型，含 sla_id, metric_name, target, service_window, calculation_method 字段 |
| `sla-engine` 引擎 | SLA 计时与达标判定核心引擎，支持暂停/恢复/超时升级 |
| `ticket-management` 模块 | 工单数据作为 SLA 度量的主要数据源 |
| `sla-reporting` 模块 | 周期 SLA 报告生成与客户确认流程 |
| `contract-interface` 能力 | SLA 条款关联合同，违约触发服务 credit 计算 |

## 参考 References

- AXELOS, *ITIL 4 Foundation*, 2019
- ISO/IEC 20000-1:2018, *Information technology — Service management — Part 1: Service management system requirements*
- Van Bon, J., *IT Service Management – An Introduction*, 2018
