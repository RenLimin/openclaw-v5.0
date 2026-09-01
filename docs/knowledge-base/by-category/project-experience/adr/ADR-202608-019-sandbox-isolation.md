---
type: adr
id: ADR-202608-019
date: 2026-09-01
title: L2 沙箱隔离 — Docker 后端 + 加固基线
status: accepted
deciders: [Rex]
layers: [L2]
tags: [sandbox, docker, isolation, security]
supersedes: null
superseded_by: null
---

# [ADR-202608-019] L2 沙箱隔离

## 1. 状态
**accepted** — 2026-09-01 起生效

## 2. 背景

Agent 执行不可信代码时需要隔离环境，防止恶意操作影响主机系统。需要标准化的沙箱隔离能力。

## 3. 考虑的选项

### 选项 A: Docker 容器隔离
- 优点：成熟、可控、资源限制精确
- 缺点：需要 Docker 运行时

### 选项 B: macOS sandbox-exec
- 优点：原生支持
- 缺点：配置复杂、灵活性差

### 选项 C: 不隔离（信任所有代码）
- 优点：零开销
- 缺点：安全风险极高

## 4. 决策
我们选择 **选项 A**，因为 Docker 提供最佳的隔离性和可控性。

## 5. 后果
### 5.1 正面
- 不可信代码在容器内运行，不影响主机
- 资源限制（CPU/内存/网络）精确控制
- 支持自定义沙箱镜像

### 5.2 负面
- 需要 Docker 运行时（colima）
- 容器启动有延迟

### 5.3 风险
- Docker 运行时故障会导致沙箱不可用

## 6. 实现计划
- [x] 部署 colima + Docker
- [x] 配置加固基线（readOnlyRoot/network:none/capDrop:ALL）
- [x] 验证 uid=1000 隔离

## 7. 验证标准
- 沙箱内写操作被拦截
- 沙箱内网络断开
- 上层通道不受影响

## 8. 相关决策
- 相关 ADR: ADR-202608-006 (持久化适配)

## 9. 引用
- 设计文档: `docs/architecture/components/sandbox/DESIGN.md`

## 10. 变更历史
- 2026-08-24: proposed
- 2026-09-01: accepted
