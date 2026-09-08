---
title: 项目状态汇报
description: 项目状态汇报，含进度、成本、质量、风险、下一步
author: L3 Office 通用模板
created: 2026-09-08
updated: 2026-09-08
tags: [汇报, 项目, 状态]
variables:
  - name: project_name
    type: string
    description: 项目名称
    required: true
  - name: reporting_period
    type: string
    description: 汇报周期
    required: true
  - name: report_date
    type: date
    description: 汇报日期
    required: true
  - name: project_manager
    type: string
    description: 项目经理
    required: true
  - name: progress_summary
    type: table
    description: 进度汇总（阶段/计划完成/实际完成/状态）
    required: true
  - name: cost_summary
    type: markdown
    description: 成本状态
    required: false
  - name: quality_summary
    type: markdown
    description: 质量状态
    required: false
  - name: risks_issues
    type: markdown
    description: 风险与问题
    required: false
  - name: next_steps
    type: list
    description: 下一步计划
    required: true
  - name: other_notes
    type: markdown
    description: 其他说明
    required: false
---

# 项目状态汇报 — {{ project_name }}

**汇报周期：** {{ reporting_period }}
**汇报日期：** {{ report_date }}
**项目经理：** {{ project_manager }}

---

## 一、进度状态

| 阶段 | 计划完成 | 实际完成 | 状态 |
|------|----------|----------|------|
{% for row in progress_summary %}
| {{ row.stage }} | {{ row.planned }}% | {{ row.actual }}% | {{ row.status }} |
{% endfor %}

{% if cost_summary %}
## 二、成本状态

{{ cost_summary }}
{% endif %}

{% if quality_summary %}
## 三、质量状态

{{ quality_summary }}
{% endif %}

{% if risks_issues %}
## 四、风险与问题

{{ risks_issues }}
{% endif %}

## 五、下一步计划

{% for step in next_steps %}
- {{ step }}
{% endfor %}

{% if other_notes %}
## 六、其他说明

{{ other_notes }}
{% endif %}
