---
title: 季度工作报告
description: 季度总结报告，含目标回顾、成果分析、问题、下一步
author: L3 Office 通用模板
created: 2026-09-08
updated: 2026-09-08
tags: [报告, 季度, 总结]
variables:
  - name: report_title
    type: string
    description: 报告标题
    required: true
  - name: quarter
    type: string
    description: 报告季度（YYYY年QX）
    required: true
  - name: department
    type: string
    description: 部门/项目组
    required: true
  - name: reporter
    type: string
    description: 报告人
    required: true
  - name: goals_review
    type: markdown
    description: 季度目标回顾
    required: true
  - name: key_achievements
    type: markdown
    description: 主要成果
    required: true
  - name: kpi_metrics
    type: table
    description: KPI指标完成情况（指标/目标/实际/完成率/状态）
    required: false
  - name: problems_risks
    type: markdown
    description: 问题与风险
    required: false
  - name: next_quarter_plan
    type: markdown
    description: 下季度计划
    required: true
  - name: other_notes
    type: markdown
    description: 其他说明
    required: false
---

# {{ report_title }} — {{ quarter }}

**部门/项目组：** {{ department }}
**报告人：** {{ reporter }}

---

## 一、季度目标回顾

{{ goals_review }}

## 二、主要成果

{{ key_achievements }}

{% if kpi_metrics %}
## 三、KPI 指标完成情况

| 指标 | 目标 | 实际 | 完成率 | 状态 |
|------|------|------|--------|------|
{% for row in kpi_metrics %}
| {{ row.metric }} | {{ row.target }} | {{ row.actual }} | {{ row.rate }} | {{ row.status }} |
{% endfor %}
{% endif %}

{% if problems_risks %}
## 四、问题与风险

{{ problems_risks }}
{% endif %}

## 五、下季度工作计划

{{ next_quarter_plan }}

{% if other_notes %}
## 六、其他说明

{{ other_notes }}
{% endif %}
