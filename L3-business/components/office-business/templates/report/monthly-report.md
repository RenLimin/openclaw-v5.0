---
title: 月度工作报告
description: 标准月度工作汇报，含完成情况、指标、问题、计划
author: L3 Office 通用模板
created: 2026-09-08
updated: 2026-09-08
tags: [报告, 月度, 工作]
variables:
  - name: report_title
    type: string
    description: 报告标题
    required: true
  - name: year_month
    type: string
    description: 报告年月（YYYY年MM月）
    required: true
  - name: department
    type: string
    description: 部门/项目组
    required: true
  - name: reporter
    type: string
    description: 报告人
    required: true
  - name: key_work_done
    type: markdown
    description: 重点工作完成情况
    required: true
  - name: kpi_metrics
    type: table
    description: KPI指标完成情况（指标/目标/实际/完成率/状态）
    required: false
  - name: problems_analysis
    type: markdown
    description: 问题分析
    required: false
  - name: next_month_plan
    type: markdown
    description: 下月工作计划
    required: true
  - name: other_notes
    type: markdown
    description: 其他说明
    required: false
---

# {{ report_title }} — {{ year_month }}

**部门/项目组：** {{ department }}
**报告人：** {{ reporter }}

---

## 一、重点工作完成情况

{{ key_work_done }}

{% if kpi_metrics %}
## 二、KPI 指标完成情况

| 指标 | 目标 | 实际 | 完成率 | 状态 |
|------|------|------|--------|------|
{% for row in kpi_metrics %}
| {{ row.metric }} | {{ row.target }} | {{ row.actual }} | {{ row.rate }} | {{ row.status }} |
{% endfor %}
{% endif %}

{% if problems_analysis %}
## 三、问题分析

{{ problems_analysis }}
{% endif %}

## 四、下月工作计划

{{ next_month_plan }}

{% if other_notes %}
## 五、其他说明

{{ other_notes }}
{% endif %}
