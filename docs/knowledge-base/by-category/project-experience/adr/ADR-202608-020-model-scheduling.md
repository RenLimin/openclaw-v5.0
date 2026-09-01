---
type: adr
id: ADR-202608-020
date: 2026-09-01
title: L2 模型调度 — 智能模型路由 + 多级 fallback
status: accepted
deciders: [Rex]
layers: [L2]
tags: [model, routing, fallback, token-compression]
supersedes: null
superseded_by: null
---

# [ADR-202608-020] L2 模型调度

## 1. 状态
**accepted** — 2026-09-01 起生效

## 2. 背景

不同任务类型（编码/推理/研究/对话）需要不同模型，且 provider 可能不可用。需要智能路由能力，按任务类型、用量、网络健康选择最优模型。

## 3. 考虑的选项

### 选项 A: 固定主模型
- 优点：配置简单
- 缺点：无法适应不同任务，单点故障

### 选项 B: 智能路由（任务分类 + 多级 fallback + token 压缩）
- 优点：最优模型选择、自动降级、成本优化
- 缺点：配置复杂

### 选项 C: 外部路由服务
- 优点：专业路由
- 缺点：额外成本、依赖外部服务

## 4. 决策
我们选择 **选项 B**，因为需要在成本和性能之间取得平衡。

## 5. 后果
### 5.1 正面
- 编码任务用 ark-code-latest，推理用 deepseek-v4-flash
- provider 故障时自动降级
- token 压缩减少 API 成本

### 5.2 负面
- 路由规则需要维护
- 用量追踪需要定期同步

### 5.3 风险
- 所有 provider 不可用时无模型可用

## 6. 实现计划
- [x] 模型注册表（自动同步 openclaw.json）
- [x] 路由规则（多级 fallback + token 压缩）
- [x] 用量追踪（每周从 provider API 获取）
- [x] 健康探测（每小时 ping provider）
- [x] 代理服务（proxy.py，自动启动）

## 7. 验证标准
- 编码任务路由到 ark-code-latest
- provider 故障时 5 秒内降级到 fallback

## 8. 相关决策
- 相关 ADR: ADR-202608-015 (动态压缩模型路由)

## 9. 引用
- 设计文档: `docs/architecture/components/model-scheduling/DESIGN.md`

## 10. 变更历史
- 2026-08-24: proposed
- 2026-09-01: accepted
