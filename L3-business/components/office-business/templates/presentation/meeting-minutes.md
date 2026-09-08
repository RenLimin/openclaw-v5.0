---
title: 会议纪要
description: 标准会议纪要，含参会人员、议程、决议、行动项
author: L3 Office 通用模板
created: 2026-09-08
updated: 2026-09-08
tags: [会议, 纪要, 记录]
variables:
  - name: meeting_topic
    type: string
    description: 会议主题
    required: true
  - name: meeting_time
    type: string
    description: 会议时间
    required: true
  - name: meeting_location
    type: string
    description: 会议地点
    required: true
  - name: chairperson
    type: string
    description: 主持人
    required: true
  - name: attendees
    type: list
    description: 参会人员列表
    required: true
  - name: recorder
    type: string
    description: 记录人
    required: true
  - name: meeting_agenda
    type: list
    description: 会议议程
    required: true
  - name: meeting_decisions
    type: markdown
    description: 会议决议
    required: true
  - name: action_items
    type: table
    description: 行动项表格（任务/责任人/截止日期）
    required: false
  - name: next_meeting
    type: string
    description: 下次会议时间/议题
    required: false
  - name: other_notes
    type: markdown
    description: 其他说明
    required: false
---

# 会议纪要 — {{ meeting_topic }}

**时间：** {{ meeting_time }}
**地点：** {{ meeting_location }}
**主持人：** {{ chairperson }}
**记录人：** {{ recorder }}

---

## 一、参会人员

{% for person in attendees %}
- {{ person }}
{% endfor %}

## 二、会议议程

{% for item in meeting_agenda %}
- {{ item }}
{% endfor %}

## 三、会议决议

{{ meeting_decisions }}

{% if action_items %}
## 四、行动项

| 任务 | 责任人 | 截止日期 |
|------|----------|------------|
{% for item in action_items %}
| {{ item.task }} | {{ item.owner }} | {{ item.deadline }} |
{% endfor %}
{% endif %}

{% if next_meeting %}
## 五、下次会议

{{ next_meeting }}
{% endif %}

{% if other_notes %}
## 六、其他说明

{{ other_notes }}
{% endif %}
