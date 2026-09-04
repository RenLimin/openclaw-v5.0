---
title: 仪表盘数据可视化 UI 模式
layer: [L2]
stage: design
category: industry-practice
tags: [dashboard, ui, pattern, data-viz, cards, tables, grid]
created: 2026-09-04
updated: 2026-09-04
confidence: high
sources:
  - title: Linear Design System
    url: https://linear.app/
    accessed: 2026-09-04
  - title: Stripe Dashboard
    url: https://dashboard.stripe.com/
    accessed: 2026-09-04
  - title: ClawHub web-design
    url: https://clawhub.ai/wpank/skills/web-design
    accessed: 2026-09-04
---

# 仪表盘数据可视化 UI 模式

## 1. 摘要
仪表盘是数据密集型页面，核心目标是**快速概览、视觉层次清晰、信息密度合理**。本文档总结常见 UI 模式和最佳实践。

## 2. 布局原则

### 网格系统
- 使用 CSS Grid + `auto-fit` / `auto-fill` 实现响应式
- `repeat(auto-fit, minmax(240px, 1fr))` 自动适配不同屏幕宽度
- 移动端单列，桌面端多列

### 视觉层次
- 核心指标卡片 → 概览表格 → 详情分析
- 大数字 > 标签 > 辅助信息
- 分组信息用卡片分隔，避免信息过载

### 响应式断点
| 断点 | 布局调整 |
|---|---|
| < 480px | 单列，导航滚动 |
| 480-768px | 双列统计卡片 |
| 768-1024px | 三列统计卡片 |
| > 1024px | 完整布局 |

## 3. 组件模式

### 统计卡片 (Stat Card)
用于展示单个核心指标（净值、总资产、负债率等）。

**结构：**
- 标签（小字、大写、浅色）→ 指标值（大字体、粗体）→ 可选变化趋势

**交互：**
- hover 轻微上浮 + 阴影加深，提供微反馈
- 页面加载 stagger 动画，增强视觉体验

**示例 CSS：**
```css
.stat-card {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--r-lg);
  padding: var(--s-6);
  box-shadow: var(--sh-sm);
  transition: all var(--t-base);
  animation: fadeUp 0.5s ease-out backwards;
}
.stat-card:hover {
  box-shadow: var(--sh-md);
  transform: translateY(-2px);
}
.stat-label {
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--c-muted);
  margin-bottom: var(--s-2);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.stat-value {
  font-family: var(--font-display);
  font-size: 1.85rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--c-text);
}
```

### 数据表格
展示多行结构化数据（账户、交易、贷款、保险等）。

**最佳实践：**
- 表头背景浅灰色，与内容行区分
- 数字右对齐，使用 `tabular-nums` 保证对齐
- hover 行背景变浅，提供行反馈
- 边框只保留底线，视觉清爽
- 表头文字大写+浅色，增强层次

**示例 CSS：**
```css
.table { width: 100%; border-collapse: collapse; }
.table th, .table td {
  padding: var(--s-3) var(--s-4);
  text-align: left;
  border-bottom: 1px solid var(--c-border);
}
.table th {
  background: var(--c-surface-2);
  font-weight: 600;
  color: var(--c-muted);
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.table tbody tr:hover { background: var(--c-surface-2); }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
```

### 卡片分组
多个相关信息块分组展示。

**最佳实践：**
- 统一圆角、边框、阴影
- 内边距 `var(--s-6)` (24px) 比较舒适
- 卡片间距 `var(--s-6)`
- hover 加深阴影提供反馈

## 4. 进度条模式
用于预算进度展示。

**结构：**
- 外层容器（浅背景）+ 内层填充（根据状态变色）+ 文字百分比

**状态颜色：**
- 正常：绿色
- 预警：黄色
- 超支：红色

```css
.progress-bar {
  height: 6px;
  background: var(--c-surface-2);
  border-radius: 3px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  border-radius: 3px;
  transition: width var(--t-slow);
}
.progress-fill.status-ok { background: var(--c-success); }
.progress-fill.status-warning { background: var(--c-warning); }
.progress-fill.status-exceeded { background: var(--c-danger); }
```

## 5. 导航模式

### 顶栏导航
- 品牌 + 链接分组
- 激活项高亮（颜色+背景）
- 移动端横向滚动

```css
.nav {
  background: var(--c-surface);
  border-bottom: 1px solid var(--c-border);
  padding: 0 var(--s-8);
  display: flex;
  align-items: center;
  height: 64px;
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: var(--sh-sm);
}
.nav-links {
  display: flex;
  gap: 2px;
  list-style: none;
  flex: 1;
  overflow-x: auto;
}
.nav-links a {
  color: var(--c-muted);
  text-decoration: none;
  font-size: 0.85rem;
  font-weight: 500;
  padding: var(--s-2) var(--s-3);
  border-radius: var(--r-sm);
  white-space: nowrap;
  transition: all var(--t-fast);
}
.nav-links a:hover { color: var(--c-text); background: var(--c-surface-2); }
.nav-links a.active { color: var(--c-primary); background: rgba(37, 99, 235, 0.06); }
```

## 6. 微交互原则

- **入场动画**：统计卡片 staggered fade up，增强页面活力
- **hover**：轻微上浮 + 阴影加深，不夸张
- **过渡**：所有状态变化使用 `transition`，时长 150-250ms
- **尊重偏好**：尊重 `prefers-reduced-motion`，关闭动画

## 7. 可访问性
- 色彩对比度 ≥ 4.5:1（WCAG AA）
- 语义化 HTML（`<nav>`, `<main>`, `<table>`）
- 键盘可导航
- 数字不丢语义，表格表头正确使用 `<th>`

## 8. 变更历史
- 2026-09-04: 创建
