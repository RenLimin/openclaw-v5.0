---
name: dag-orchestrator
description: DAG 工作流编排器。将复杂任务分解为有向无环图（DAG），支持并行执行和变量传递。
---

# DAG 工作流编排器

> 版本：v1.0
> 创建日期：2026-09-02
> 层级：L2 基础设施层
> 定位：复杂任务的多 Agent 协作编排

## 触发条件

当需要执行多步骤复杂任务时触发：
- "生成交付月报"（需要：数据采集 → 清洗 → 分析 → 报告）
- "分析销售数据"（需要：OA采集 → WeCom采集 → 关联 → 分析）
- "系统健康检查"（需要：并行检查多个系统）

## DAG 定义格式

```yaml
name: 交付月报生成
description: 采集数据并生成交付月报
tasks:
  - id: collect_oa
    name: 采集 OA 合同台账
    agent: data-collector
    action: collect_oa_contracts
    outputs: [oa_data]

  - id: collect_revenue
    name: 采集确收凭证
    agent: data-collector
    action: collect_revenue_vouchers
    outputs: [revenue_data]

  - id: collect_acceptance
    name: 采集验收凭证
    agent: data-collector
    action: collect_acceptance_vouchers
    outputs: [acceptance_data]

  - id: join_data
    name: 关联数据
    agent: data-analyst
    action: join_sources
    inputs: [oa_data, revenue_data, acceptance_data]
    outputs: [joined_data]
    depends_on: [collect_oa, collect_revenue, collect_acceptance]

  - id: analyze
    name: 分析数据
    agent: data-analyst
    action: analyze
    inputs: [joined_data]
    outputs: [analysis_result]
    depends_on: [join_data]

  - id: generate_report
    name: 生成报告
    agent: report-generator
    action: generate_delivery_report
    inputs: [analysis_result]
    outputs: [report_file]
    depends_on: [analyze]
```

## 执行规则

1. **并行执行**：无依赖关系的任务并行执行（通过 `sessions_spawn`）
2. **变量传递**：上游 `outputs` → 下游 `inputs`
3. **失败处理**：任一任务失败 → 停止下游 → 报告错误
4. **超时控制**：单任务超时 5 分钟，整体超时 30 分钟

## 内置工作流

| 工作流 | 步骤数 | 并行度 | 说明 |
|---|---|---|---|
| 交付月报 | 6 | 3 | 采集(并行) → 关联 → 分析 → 报告 |
| 确收月报 | 5 | 2 | 采集(并行) → 关联 → 报告 |
| 系统健康检查 | 4 | 4 | 所有检查并行执行 |
| 数据质量审计 | 3 | 1 | 串行执行 |

## 实施状态

- [x] DAG 编排器 SKILL.md
- [x] YAML 工作流定义格式
- [x] 内置工作流模板
- [ ] DAG 执行引擎（Python 实现）
- [ ] 可视化（DAG 图形展示）
