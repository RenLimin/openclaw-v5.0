---
title: 前端性能优化
description: Web 性能优化策略、Core Web Vitals 与优化工具
source: Google Web Dev; web.dev; Lighthouse
version: 1.0
category: business
dimension: software-development
sub_area: performance
type: knowledge
tags: [performance, core-web-vitals, lighthouse, optimization]
last_reviewed: 2026-08-27
---

# 前端性能优化

## Core Web Vitals

Google 定义的三个核心用户体验指标：

| 指标 | 全称 | 目标 | 说明 |
|------|------|------|------|
| **LCP** | Largest Contentful Paint | < 2.5s | 最大内容绘制，衡量加载速度 |
| **INP** | Interaction to Next Paint | < 200ms | 交互到下次绘制，衡量响应性 |
| **CLS** | Cumulative Layout Shift | < 0.1 | 累积布局偏移，衡量视觉稳定性 |

## 加载性能优化

### 资源优化

| 策略 | 方法 | 效果 |
|------|------|------|
| 代码分割 | 动态 `import()`、路由懒加载 | 减少首屏 JS 体积 |
| Tree Shaking | 移除未使用代码 | 减少包体积 |
| 资源压缩 | Gzip/Brotli、图片 WebP/AVIF | 减少传输体积 |
| 资源预加载 | `<link rel="preload/prefetch">` | 提前加载关键资源 |
| HTTP 缓存 | Cache-Control、ETag | 减少重复请求 |

### 渲染优化

| 策略 | 方法 |
|------|------|
| SSR/SSG | 服务端渲染/静态生成，加速首屏 |
| 关键 CSS 内联 | 首屏样式内联，非关键异步加载 |
| 字体优化 | `font-display: swap`、子集化 |
| 图片优化 | 响应式 `srcset`、懒加载 `loading="lazy"` |

## 运行时性能优化

| 策略 | 方法 |
|------|------|
| 避免重渲染 | `React.memo` / `v-once` / `shallowRef` |
| 虚拟化长列表 | `react-window` / `vue-virtual-scroller` |
| 防抖/节流 | 搜索输入、滚动事件 |
| Web Worker | 复杂计算移出主线程 |
| `requestAnimationFrame` | 动画使用 RAF 而非 `setTimeout` |

## 性能监控工具

| 工具 | 用途 |
|------|------|
| Lighthouse | 综合性能审计（CLI / Chrome DevTools） |
| Web Vitals 库 | 真实用户指标采集 |
| Chrome Performance Tab | 运行时性能分析 |
| Bundle Analyzer | 包体积分析（webpack-bundle-analyzer） |
| Sentry / Datadog RUM | 真实用户性能监控 |

## 性能预算

| 指标 | 建议阈值 |
|------|----------|
| 首屏 JS | < 200KB（gzip） |
| 首屏总资源 | < 1MB（gzip） |
| LCP | < 2.5s |
| TTI（可交互时间） | < 3.5s |
| 包体积增长 | 每次 PR 增量 < 10% |
