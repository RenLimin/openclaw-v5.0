---
title: 年度工作报告
description: 年度工作总结与计划，全年回顾 + 下年规划
author: L3 Office 通用模板
created: 2026-09-08
updated: 2026-09-08
tags: [报告, 年度, 总结计划]
variables:
  - name: report_title
    type: string
    description: 报告标题
    required: true
  - name: year
    type: string
    description: 报告年度（YYYY年）
    required: true
  - name: department
    type: string
    description: 部门/项目组
    required: true
  - name: reporter
    type: string
    description: 报告人
    required: true
  - name: year_goals_review
    type: markdown
    description: 年度目标回顾
    required: true
  - name: key_achievements
    type: markdown
    description: 主要成果总结
    required: true
  - name: key_data
    type: table
    description: 核心数据指标（指标/目标/实际/同比）
    required: false
  - name: problems_lessons
    type: markdown
    description: 问题与经验教训
    required: false
  - name: next_year_goals
    type: markdown
    description: 下年度目标与计划
    required: true
  - name: other_notes
    type: markdown
    description: 其他说明
    required: false
---

# {{ report_title }} — {{ year }}

**部门/项目组：** {{ department }}
**报告人：** {{ reporter }}

---

## 一、年度目标回顾

{{ year_goals_review }}

## 二、主要成果总结

{{ key_achievements }}

{% if key_data %}
## 三、核心数据指标

| 指标 | 目标 | 实际 | 同比 |
|------|------|------|------|
{% for row in key_data %}
| {{ row.metric }} | {{ row.target }} | {{ row.actual }} | {{ row.yoy }} |
{% endfor %}
{% endif %}

{% if problems_lessons %}
## 四、问题与经验教训

{{ problems_lessons }}
{% endif %}

## 五、下年度目标与计划

{{ next_year_goals }}

{% if other_notes %}
## 六、其他说明

{{ other_notes }}
{% endif %}
