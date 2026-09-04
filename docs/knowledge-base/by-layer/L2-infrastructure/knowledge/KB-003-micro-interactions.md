---
title: 微交互设计模式
layer: [L2]
stage: design
category: industry-practice
tags: [micro-interactions, animation, transition, ux, feedback]
created: 2026-09-04
updated: 2026-09-04
confidence: high
sources:
  - title: ClawHub frontend-design-guidelines
    url: https://clawhub.ai/wpank/skills/frontend-design-guidelines
    accessed: 2026-09-04
  - title: Nielsen Norman Group Microinteractions
    url: https://www.nngroup.com/articles/microinteractions/
    accessed: 2026-09-04
---

# 微交互设计模式

## 1. 摘要
微交互是**短小、单一目的**的用户交互，提供即时反馈，增强用户体验，让界面更生动。恰当的微交互不引人注目，但能显著提升体验质感。

## 2. 核心原则

### 目的
每一个微交互都应该有明确目的：
- 提供操作反馈
- 引导用户注意力
- 增强空间感和层次
- 减少操作焦虑

### 不做什么
- 不滥用动画，避免分散注意力
- 不影响性能，只动画 transform 和 opacity（GPU 加速）
- 不强制动效，尊重用户 `prefers-reduced-motion` 设置

### 时长原则
- 短操作：100-200ms
- 页面入场：300-500ms
- 复杂过渡：不超过 600ms
- 越长越慢，越短越快

## 3. 常见模式

### 页面入场
- 统计卡片 staggered fade-up 动画
- 每个卡片延迟 50-100ms，创造节奏感

```css
.stat-card { animation: fadeUp 0.5s ease-out backwards; }
.stat-card:nth-child(1) { animation-delay: 0.05s; }
.stat-card:nth-child(2) { animation-delay: 0.1s; }
.stat-card:nth-child(3) { animation-delay: 0.15s; }
.stat-card:nth-child(4) { animation-delay: 0.2s; }

@keyframes fadeUp {
  from { opacity: 0; transform: translateY(12px); }
  to   { opacity: 1; transform: translateY(0); }
}
```

### 卡片悬浮
- hover 卡片时轻微上浮 (Y -2px)
- 阴影稍微加深
- 提升立体感和交互感

```css
.stat-card {
  transition: all 250ms cubic-bezier(0.4, 0, 0.2, 1);
}
.stat-card:hover {
  box-shadow: var(--sh-md);
  transform: translateY(-2px);
}
```

### 按钮点击
- 点击轻微缩小（scale 0.95），提供 tactile feedback

```css
.btn:active { transform: scale(0.95); }
```

### 导航激活
- 激活状态背景色变化，文字颜色变化，过渡平滑

### 加载状态
- 骨架屏比 spinner 更好，提前占位，减少布局跳动

## 4. 性能注意事项
- 只动画 `transform` 和 `opacity`，避免触发重排重绘
- 使用 `will-change: transform, opacity` 提示浏览器提前准备
- 避免同时动画大量元素，合理使用 stagger
- CSS 动画比 JS 动画性能更好

## 5. 无障碍
- 尊重用户的 `prefers-reduced-motion` 设置，关闭不必要动画

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

## 6. 变更历史
- 2026-09-04: 创建
