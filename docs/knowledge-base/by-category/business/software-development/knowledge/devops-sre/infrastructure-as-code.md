---
title: 基础设施即代码（IaC）
description: Terraform、Pulumi、Ansible 与基础设施管理
source: Terraform Docs; Pulumi Docs; Ansible Docs
version: 1.0
category: business
dimension: software-development
sub_area: iac
type: knowledge
tags: [iac, terraform, pulumi, ansible, infrastructure]
last_reviewed: 2026-08-27
---

# 基础设施即代码（IaC）

## 工具对比

| 工具 | 语言 | 特点 | 适用 |
|------|------|------|------|
| Terraform | HCL | 声明式、状态管理、多云 | 云资源管理 |
| Pulumi | TS/Python/Go | 编程式、类型安全 | 复杂逻辑 |
| Ansible | YAML | 命令式、无 Agent | 配置管理 |
| Crossplane | YAML | K8s 原生 | 云原生 IaC |

## Terraform 核心

| 概念 | 说明 |
|------|------|
| Provider | 云厂商插件（AWS/GCP/Azure） |
| Resource | 基础设施对象（VM/网络/存储） |
| State | 基础设施当前状态（tfstate） |
| Module | 可复用基础设施组件 |
| Workspace | 多环境管理 |

## 最佳实践

1. **State 远程存储**：S3 + DynamoDB 锁
2. **Module 化**：封装可复用组件
3. **Plan → Apply**：先预览再执行
4. **多环境**：Workspace 或目录分离
5. **GitOps**：IaC 配置入版本控制
