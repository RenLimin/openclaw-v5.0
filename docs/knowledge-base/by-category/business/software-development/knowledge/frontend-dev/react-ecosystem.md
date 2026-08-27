---
title: React 生态体系
description: React 核心概念、生态系统与最佳实践
source: React Official Docs; Next.js Docs; Redux Docs
version: 1.0
category: business
dimension: software-development
sub_area: react
type: knowledge
tags: [react, hooks, nextjs, state-management, frontend]
xref: [software-development/knowledge/frontend-dev/vue-ecosystem.md]
last_reviewed: 2026-08-27
---

# React 生态体系

## 核心概念

### 组件模型

React 基于**组件化**思想构建 UI。每个组件是一个独立、可复用的 UI 单元，接收 Props，返回 JSX。

| 概念 | 说明 |
|------|------|
| 函数组件 | 推荐方式，纯函数，接收 Props 返回 JSX |
| 类组件 | 遗留方式，使用 `this.state` 和生命周期 |
| 组合优于继承 | 通过 `children` 和 slot 模式复用逻辑 |
| 单向数据流 | Props 向下传递，事件向上冒泡 |

### Hooks（核心）

Hooks 是 React 16.8+ 的核心能力，让函数组件拥有状态和副作用。

| Hook | 用途 | 典型场景 |
|------|------|----------|
| `useState` | 组件局部状态 | 表单输入、开关状态 |
| `useEffect` | 副作用（订阅、请求、DOM） | 数据获取、事件监听 |
| `useContext` | 消费 Context | 主题、用户信息、国际化 |
| `useMemo` | 缓存计算结果 | 派生数据、昂贵计算 |
| `useCallback` | 缓存函数引用 | 子组件回调、依赖项优化 |
| `useRef` | 持久化可变值 | DOM 引用、定时器 ID |
| `useReducer` | 复杂状态逻辑 | 多状态联动、状态机 |

### 常用第三方 Hooks

| 库 | 能力 |
|---|---|
| `react-query` / `TanStack Query` | 服务端状态管理、缓存、乐观更新 |
| `react-hook-form` | 表单状态管理与校验 |
| `ahooks` | 常用 Hooks 集合（防抖、节流、Interval 等） |

## 路由

| 库 | 特点 |
|---|---|
| React Router v6 | 声明式路由、嵌套路由、Loader/Action |
| Next.js App Router | 文件系统路由、Server Components、嵌套布局 |

## 状态管理

| 方案 | 适用场景 |
|------|----------|
| `useState` + `useContext` | 小型应用、局部共享 |
| Zustand | 轻量、无样板代码、TypeScript 友好 |
| Redux Toolkit | 大型应用、时间旅行调试、中间件 |
| Jotai | 原子化状态、细粒度更新 |
| MobX | 响应式、OOP 风格 |

## SSR/SSG 框架

| 框架 | 渲染模式 | 适用场景 |
|------|----------|----------|
| Next.js | SSR/SSG/ISR/RSC | 全栈 React、SEO 友好 |
| Remix | SSR + 嵌套路由 | 表单密集型应用 |
| Gatsby | SSG | 内容型站点 |

## 最佳实践

1. **组件拆分**：单一职责，超过 200 行考虑拆分
2. **自定义 Hook 抽离**：复用有状态逻辑
3. **避免不必要的重渲染**：`React.memo` + `useMemo` + `useCallback`
4. **错误边界**：使用 `componentDidCatch` 包裹路由
5. **TypeScript 优先**：Props 类型定义是文档也是约束
