---
title: Web 可访问性（Accessibility）
description: WCAG 标准、ARIA 规范与无障碍 Web 开发实践
source: W3C WAI; WCAG 2.1; MDN Accessibility
version: 1.0
category: business
dimension: software-development
sub_area: accessibility
type: knowledge
tags: [accessibility, a11y, wcag, aria, inclusive-design]
last_reviewed: 2026-08-27
---

# Web 可访问性（Accessibility）

## 核心标准

### WCAG 2.1 四个原则（POUR）

| 原则 | 含义 | 前端关注点 |
|------|------|-----------|
| **P**erceivable（可感知） | 信息可被所有用户感知 | 替代文本、色彩对比度、字幕 |
| **O**perable（可操作） | 界面可被所有用户操作 | 键盘导航、焦点管理、跳过链接 |
| **U**nderstandable（可理解） | 内容和操作可理解 | 一致导航、错误提示、语言标识 |
| **R**obust（健壮性） | 兼容各种辅助技术 | 语义化 HTML、ARIA、兼容性 |

### 合规等级

| 等级 | 说明 | 目标 |
|------|------|------|
| A | 最低要求 | 必须达到 |
| AA | 行业标准 | **目标等级** |
| AAA | 最高要求 | 尽量达到 |

## 前端实现要点

### 语义化 HTML

| 实践 | 说明 |
|------|------|
| 使用 `<nav>`、`<main>`、`<article>` | 地标角色，屏幕阅读器导航 |
| 标题层级有序（h1→h6） | 不跳级，一个页面一个 h1 |
| `<button>` 用于交互，`<a>` 用于导航 | 不混用 |
| `<label>` 关联表单控件 | `for` 属性或嵌套 |
| `<table>` 加 `<caption>` 和 `<th>` | 屏幕阅读器理解表格结构 |

### ARIA（Accessible Rich Internet Applications）

当 HTML 语义不够时使用 ARIA 补充：

| 属性 | 用途 |
|------|------|
| `role` | 定义元素角色（`role="navigation"`、`role="alert"`） |
| `aria-label` | 无可见标签时提供名称 |
| `aria-labelledby` | 关联可见标签 |
| `aria-describedby` | 关联描述文本 |
| `aria-expanded` | 展开/折叠状态 |
| `aria-hidden` | 从辅助技术隐藏装饰性元素 |
| `aria-live` | 动态内容变更通知（`polite`/`assertive`） |

### 键盘导航

| 要求 | 实现 |
|------|------|
| 所有交互元素可 Tab 到达 | 使用原生可聚焦元素或 `tabindex` |
| 焦点可见 | `:focus-visible` 样式，不移除 outline |
| 焦点陷阱管理 | Modal 内焦点循环，关闭后回到触发点 |
| 跳过链接 | "Skip to content" 跳过导航栏 |

### 色彩与对比度

| 要求 | 标准 |
|------|------|
| 正文对比度 | ≥ 4.5:1（AA） |
| 大文本对比度 | ≥ 3:1（AA） |
| 非文本元素对比度 | ≥ 3:1（UI 组件、图标） |
| 不依赖颜色传递信息 | 配合图标/文字 |

## 测试工具

| 工具 | 用途 |
|------|------|
| axe DevTools | 自动化 a11y 扫描（浏览器插件） |
| Lighthouse a11y | 综合可访问性审计 |
| VoiceOver（macOS） | 屏幕阅读器测试 |
| NVDA（Windows） | 屏幕阅读器测试 |
| 键盘-only 导航测试 | Tab/Shift+Tab/Enter/Space/Arrow |
