---
title: CI/CD 流水线
description: 构建-测试-部署流水线、质量门禁与发布策略
source: GitHub Actions Docs; GitLab CI Docs; ArgoCD Docs
version: 1.0
category: business
dimension: software-development
sub_area: cicd
type: knowledge
tags: [cicd, github-actions, gitlab-ci, argocd, deployment]
last_reviewed: 2026-08-27
---

# CI/CD 流水线

## 标准流水线

```
代码提交 → Lint + TypeCheck → 单元测试 → 构建 → 集成测试 → 安全扫描 → 质量门禁 → 部署 → 验证
```

## CI 工具对比

| 工具 | 特点 | 适用 |
|------|------|------|
| GitHub Actions | 生态丰富、Marketplace | GitHub 项目 |
| GitLab CI | 内置、一体化 | GitLab 项目 |
| Jenkins | 高度可定制 | 复杂场景 |
| CircleCI | 速度快、并行 | 云原生项目 |

## 质量门禁

| 门禁 | 工具 | 失败则阻断 |
|------|------|-----------|
| Lint | ESLint / Prettier | ✅ |
| Type Check | TypeScript | ✅ |
| 单元测试 | Vitest / Jest | ✅ |
| 覆盖率 | c8 / istanbul | ✅ |
| 安全扫描 | Snyk / Trivy | ✅ |
| 性能基线 | Lighthouse CI | ⚠️ |

## 发布策略

| 策略 | 说明 | 风险 |
|------|------|------|
| 滚动更新 | 逐个替换 Pod | 低 |
| Blue-Green | 两套环境切换 | 中 |
| Canary | 小流量验证 | 低 |
| 灰度发布 | 按比例放量 | 低 |

## 环境管理

| 环境 | 用途 | 数据 |
|------|------|------|
| Dev | 开发调试 | Mock |
| Staging | 集成测试 | 脱敏 |
| Production | 真实业务 | 真实 |
