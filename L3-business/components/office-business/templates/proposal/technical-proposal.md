---
title: 技术方案
description: 技术方案模板，含架构、设计、实现、部署
author: L3 Office 通用模板
created: 2026-09-08
updated: 2026-09-08
tags: [方案, 技术, 设计]
variables:
  - name: project_name
    type: string
    description: 项目名称
    required: true
  - name: client_name
    type: string
    description: 客户名称
    required: true
  - name: company_name
    type: string
    description: 我司名称
    required: true
  - name: date
    type: date
    description: 方案日期
    required: true
  - name: project_overview
    type: markdown
    description: 项目概述
    required: true
  - name: requirements
    type: markdown
    description: 需求分析
    required: true
  - name: overall_architecture
    type: markdown
    description: 总体架构设计
    required: true
  - name: functional_design
    type: markdown
    description: 功能模块设计
    required: true
  - name: non_functional
    type: markdown
    description: 非功能性设计（性能/安全/可扩展）
    required: true
  - name: deployment_arch
    type: markdown
    description: 部署架构
    required: true
  - name: implementation_plan
    type: markdown
    description: 实施计划（里程碑）
    required: true
  - name: team
    type: markdown
    description: 技术团队
    required: true
  - name: other_notes
    type: markdown
    description: 其他说明
    required: false
---

# {{ project_name }} 技术方案

**客户：** {{ client_name }}
**编制：** {{ company_name }}
**日期：** {{ date }}

---

## 一、项目概述

{{ project_overview }}

## 二、需求分析

{{ requirements }}

## 三、总体架构设计

{{ overall_architecture }}

## 四、功能模块设计

{{ functional_design }}

## 五、非功能性设计

{{ non_functional }}

## 六、部署架构

{{ deployment_arch }}

## 七、实施计划

{{ implementation_plan }}

## 八、技术团队

{{ team }}

{% if other_notes %}
## 九、其他说明

{{ other_notes }}
{% endif %}
