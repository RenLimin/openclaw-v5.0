---
title: 前端工程化
description: 构建工具、CI/CD、测试体系与 monorepo 管理
source: Vite Docs; Turborepo Docs; Testing Library Docs
version: 1.0
category: business
dimension: software-development
sub_area: engineering
type: knowledge
tags: [frontend-engineering, vite, ci-cd, testing, monorepo]
xref: [software-development/knowledge/frontend-dev/react-ecosystem.md]
last_reviewed: 2026-08-27
---

# 前端工程化

## 构建工具

| 工具 | 特点 | 适用场景 |
|------|------|----------|
| **Vite** | ESM 原生、HMR 极快、Rollup 打包 | 现代项目首选 |
| Webpack | 生态成熟、配置灵活 | 遗留项目、复杂定制 |
| esbuild | Go 编写、极快转译 | 库打包、TS 编译 |
| Rollup | Tree Shaking 优秀 | 库/NPM 包打包 |
| Turbopack | Rust 编写、增量计算 | Next.js 未来方向 |

## 代码规范

| 工具 | 用途 |
|------|------|
| ESLint | 静态代码分析、错误检测 |
| Prettier | 代码格式化 |
| Stylelint | CSS/SCSS 规范 |
| Husky + lint-staged | Git 提交前自动校验 |
| commitlint | Commit message 规范 |

## 测试体系

### 测试金字塔

```
        /  E2E  \        ← 少量（关键流程）
       / Integration \    ← 适量（模块协作）
      /  Unit Testing  \  ← 大量（组件/函数）
```

| 类型 | 工具 | 覆盖目标 |
|------|------|----------|
| 单元测试 | Vitest / Jest | 函数、Hook、工具类 |
| 组件测试 | Testing Library | 组件渲染、交互、输出 |
| E2E 测试 | Playwright / Cypress | 关键用户流程 |
| 视觉回归 | Percy / Chromatic | UI 变更检测 |
| 性能测试 | Lighthouse CI | 性能预算门禁 |

## CI/CD 流程

### 标准流水线

```
代码提交 → Lint + TypeCheck → 单元测试 → 构建 → 预览部署 → E2E → 生产部署
```

| 阶段 | 工具 | 说明 |
|------|------|------|
| CI 触发 | GitHub Actions / GitLab CI | PR + Push 触发 |
| 质量门禁 | Lint + Test + TypeCheck | 任一失败则阻断 |
| 构建产物 | Docker Image / Static Files | 可部署产物 |
| 预览环境 | Vercel / Netlify / Docker | PR 级预览 |
| 生产部署 | Blue-Green / Canary | 零停机发布 |

## Monorepo 管理

| 工具 | 特点 |
|------|------|
| Turborepo | 增量构建、远程缓存、任务编排 |
| Nx | 依赖图分析、受影响项目检测 |
| pnpm workspaces | 轻量、磁盘效率高 |
| Lerna | 遗留方案，版本管理和发布 |

### Monorepo 结构示例

```
repo/
├── apps/
│   ├── web/          ← 前端应用
│   └── admin/        ← 管理后台
├── packages/
│   ├── ui/           ← 共享组件库
│   ├── utils/        ← 共享工具函数
│   └── types/        ← 共享类型定义
├── turbo.json
└── pnpm-workspace.yaml
```
