---
title: 测试策略
description: 测试金字塔、测试左移、覆盖率策略与质量度量
source: ISTQB; "Agile Testing" Lisa Crispin; Google Testing Blog
version: 1.0
category: business
dimension: software-development
sub_area: test-strategy
type: knowledge
tags: [test-strategy, test-pyramid, shift-left, coverage]
last_reviewed: 2026-08-27
---

# 测试策略

## 测试金字塔

```
        /  E2E  \        ← 少量（关键业务流程）
       / Integration \    ← 适量（模块间协作）
      /  Unit 测试     \  ← 大量（函数、类、逻辑）
```

| 层级 | 范围 | 速度 | 成本 | 覆盖率目标 |
|------|------|------|------|-----------|
| 单元测试 | 单个函数/类 | 极快 | 低 | 70-80% |
| 集成测试 | 模块间协作 | 快 | 中 | 15-20% |
| E2E 测试 | 完整业务流程 | 慢 | 高 | 5-10% |

## 测试左移（Shift-Left）

| 阶段 | 活动 | 价值 |
|------|------|------|
| 需求评审 | 识别歧义、遗漏 | 减少后期返工 |
| 设计评审 | 可测试性评估 | 降低测试成本 |
| 开发阶段 | TDD/BDD | 内建质量 |
| 代码审查 | 测试覆盖审查 | 发现盲区 |

## 覆盖率策略

| 指标 | 目标 | 说明 |
|------|------|------|
| 行覆盖率 | > 80% | 基础门槛 |
| 分支覆盖率 | > 70% | 条件覆盖 |
| 关键路径覆盖率 | 100% | 核心业务逻辑 |

**注意**：覆盖率是必要条件，不是充分条件。关注测试质量而非数字。

## 质量度量

| 指标 | 说明 |
|------|------|
| 缺陷密度 | 每千行代码缺陷数 |
| 逃逸率 | 生产环境发现的缺陷占比 |
| MTTR | 平均修复时间 |
| Flaky Test 率 | 不稳定测试占比 |
