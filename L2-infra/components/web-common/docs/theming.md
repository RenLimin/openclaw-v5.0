# Theming — 主题定制指南

> web-common v2.0 设计系统 · 业务系统如何定制品牌主题

## 概览

web-common 的 Design Tokens 采用**三层结构**，业务系统可以按需覆盖：

```
┌─────────────────────────────────────────┐
│  L1 基础层（base.css）                    │  ← v1 变量 + 默认值
│  原始颜色/间距/字号/阴影定义               │
├─────────────────────────────────────────┤
│  L2 语义层（tokens.css）                  │  ← v2 语义别名（推荐使用）
│  --c-text-secondary / --radius / --sh-*  │
├─────────────────────────────────────────┤
│  L3 业务覆盖层（业务系统自定义 CSS）        │  ← ★ 业务系统在这里定制
│  覆盖 --c-primary 等变量实现品牌化         │
└─────────────────────────────────────────┘
```

**原则**：业务系统**不修改** base.css / tokens.css，只在自己项目的 CSS 中覆盖变量。

## 1. 快速开始（3 步）

### Step 1：在业务 CSS 中覆盖品牌变量

```css
/* L4-proprietary/components/xxx/static/css/theme.css */
:root {
    /* 品牌色 */
    --c-primary:       #7c3aed;   /* 品牌紫 */
    --c-primary-hover: #6d28d9;
    --c-primary-light: #ede9fe;
    /* 强调色 */
    --c-success:  #059669;
    --c-warning:  #d97706;
    --c-error:    #dc2626;
    /* 圆角风格 */
    --radius: 12px;
    --r-lg:   16px;
}
```

### Step 2：在页面引入顺序（必须在 tokens.css 之后）

```html
<link rel="stylesheet" href="/static/web-common/css/base.css">
<link rel="stylesheet" href="/static/web-common/css/tokens.css">
<link rel="stylesheet" href="/static/xxx/css/theme.css">   <!-- ★ 业务覆盖 -->
```

### Step 3：验证

- 打开页面确认品牌色生效
- 切换暗色模式确认暗色覆盖也生效（如有需要，在 `[data-theme="dark"]` 下再覆盖）

## 2. 可覆盖的变量清单

### 品牌色（最常定制）

| 变量 | 默认（亮色） | 说明 |
|---|---|---|
| `--c-primary` | #2563eb | 主色：按钮、链接、选中态 |
| `--c-primary-hover` | #1d4ed8 | hover/按压色 |
| `--c-primary-light` | #dbeafe | 浅色背景（选中行、提示） |

### 中性色（可调明暗基调）

| 变量 | 默认（亮色） | 说明 |
|---|---|---|
| `--c-bg` | #f7f8fa | 页面背景 |
| `--c-surface` | #ffffff | 卡片背景 |
| `--c-sidebar` | #ffffff | 侧边栏背景 |
| `--c-text` | #1a1d23 | 正文色 |
| `--c-text-secondary` | #3d4250 | 次要文字 |
| `--c-text-muted` | #6b7280 | 辅助文字 |

### 形状（圆角/阴影风格）

| 变量 | 默认 | 说明 |
|---|---|---|
| `--r-sm` / `--radius` / `--r-lg` / `--r-xl` | 6/10/14/20px | 圆角梯度 |
| `--sh-sm` / `--shadow` / `--sh-lg` / `--sh-xl` | 分层阴影 | 阴影层级 |

### 排版（字体/字号基调）

| 变量 | 默认 | 说明 |
|---|---|---|
| `--ff-sans` | 系统字体栈 | 正文字体族 |
| `--ff-mono` | 等宽字体栈 | 代码字体族 |
| `--fs-base` | 0.9375rem | 基准字号 |

## 3. 暗色模式定制

业务系统可以覆盖暗色变量（可选，默认暗色已完整）：

```css
[data-theme="dark"] {
    --c-primary: #a78bfa;        /* 暗色下用更亮的品牌色 */
    --c-bg:      #0b0d12;        /* 更深的背景 */
    --c-surface: #151821;
}
```

**暗色适配要点**：
- 品牌色在暗色下通常提高亮度（保证对比度 ≥ 4.5:1）
- 深色背景避免纯黑，用带色调的深灰（#0f1115 系）
- 阴影在暗色下几乎不可见，主要靠边框+层级区分

## 4. 业务系统示例

### BDMS（默认蓝）

```css
:root {
    --c-primary: #2563eb;
    --c-primary-hover: #1d4ed8;
}
```

### 示例：金融风格（深蓝金）

```css
:root {
    --c-primary:       #0f4c81;
    --c-primary-hover: #0b3a63;
    --c-primary-light: #e8f0f8;
    --c-warning:       #b8860b;   /* 金色强调 */
    --radius: 8px;                /* 更锐利的金融风 */
}
```

### 示例：健康风格（绿松）

```css
:root {
    --c-primary:       #0d9488;
    --c-primary-hover: #0f766e;
    --c-primary-light: #ccfbf1;
    --radius: 16px;               /* 更圆润亲和 */
    --r-lg: 20px;
}
```

## 5. 常见问题

### Q1：为什么我的覆盖不生效？

检查顺序：
1. 覆盖 CSS 是否在 tokens.css **之后**加载（后加载的覆盖才生效）
2. 是否用了正确的变量名（拼写错误静默失效）
3. 是否在 `:root` 选择器内（CSS 变量必须定义在根元素）

### Q2：如何只改某个页面的主题？

在页面级 CSS 中覆盖即可，但注意作用域：

```css
/* 仅登录页品牌色 */
.login-page {
    --c-primary: #e11d48;
}
```

### Q3：业务系统新增了组件样式，如何遵循 tokens 规范？

- 颜色用 `var(--c-*)`，间距用 `var(--s-*)`，字号用 `var(--fs-*)`
- 圆角/阴影/过渡用 `var(--r-*)` / `var(--sh-*)` / `var(--t-*)`
- 禁止硬编码设计值（除了业务特有的专有色值）

## 6. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-10-17 | 初版：主题定制指南（三层结构 + 快速开始 + 覆盖清单 + 示例） |
