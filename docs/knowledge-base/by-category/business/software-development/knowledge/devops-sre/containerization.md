---
title: 容器化与编排
description: Docker、Kubernetes、Helm 与容器治理
source: Docker Docs; Kubernetes Docs; Helm Docs
version: 1.0
category: business
dimension: software-development
sub_area: containerization
type: knowledge
tags: [docker, kubernetes, helm, containers, orchestration]
last_reviewed: 2026-08-27
---

# 容器化与编排

## Docker

### 最佳实践

| 实践 | 说明 |
|------|------|
| 多阶段构建 | 减小镜像体积 |
| 最小基础镜像 | alpine/distroless，减少攻击面 |
| .dockerignore | 排除不必要文件 |
| 非 root 运行 | `USER 1000` |
| 镜像扫描 | Trivy/Snyk 集成到 CI |

## Kubernetes

### 核心资源

| 资源 | 用途 |
|------|------|
| Pod | 最小部署单元 |
| Deployment | 无状态应用管理 |
| StatefulSet | 有状态应用 |
| Service | 服务暴露（ClusterIP/NodePort/LoadBalancer） |
| Ingress | HTTP 路由 |
| ConfigMap/Secret | 配置和密钥 |
| HPA | 自动水平扩缩 |

### 资源管理

```yaml
resources:
  requests:
    cpu: "100m"
    memory: "128Mi"
  limits:
    cpu: "500m"
    memory: "512Mi"
```

## Helm

| 概念 | 说明 |
|------|------|
| Chart | 打包单元 |
| values.yaml | 可配置参数 |
| Release | Chart 的部署实例 |
| Repository | Chart 仓库 |
