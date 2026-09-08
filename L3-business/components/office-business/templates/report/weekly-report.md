---
title: 项目周报
description: 标准项目周报模板，包含进度、风险、计划
author: L3 Office 通用模板
created: 2026-09-08
updated: 2026-09-08
tags: [报告, 周报, 项目]
variables:
  - name: project_name
    type: string
    description: 项目名称
    required: true
  - name: report_week
    type: string
    description: 报告周期（第几周）
    required: true
  - name: report_date_range
    type: string
    description: 报告日期范围（YYYY.MM.DD ~ YYYY.MM.DD）
    required: true
  - name: reporter
    type: string
    description: 报告人
    required: true
  - name: done_work_list
    type: list
    description: 本周完成工作列表
    required: true
  - name: next_plan_list
    type: list
    description: 下周计划工作列表
    required: true
  - name: risks_issues
    type: markdown
    description: 风险与问题描述
    required: false
  - name: other_notes
    type: markdown
    description: 其他说明
    required: false
---

# 项目周报 — {{ project_name }} ({{ report_week }})

**报告周期：** {{ report_date_range }}
**报告人：** {{ reporter }}

---

## 一、本周完成工作

{% for item in done_work_list %}
- {{ item }}
{% endfor %}

## 二、下周工作计划

{% for item in next_plan_list %}
- {{ item }}
{% endfor %}

{% if risks_issues %}
## 三、风险与问题

{{ risks_issues }}
{% endif %}

{% if other_notes %}
## 四、其他说明

{{ other_notes }}
{% endif %}
