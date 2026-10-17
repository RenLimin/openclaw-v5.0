# DESIGN-TOKENS — Design Tokens 参考文档

> web-common v2.0 设计系统 · 语义化变量体系

## 概览

Design Tokens 是 web-common 设计系统的核心，它将所有设计属性（颜色、间距、字号、圆角、阴影等）标准化为 CSS 变量，保证：

1. **一致性**：全项目使用统一的设计值
2. **可维护性**：修改一个 token 就能影响所有使用处
3. **可扩展性**：支持主题切换（亮色/暗色）
4. **桥接兼容**：保留 v1 变量，不破坏现有代码

## 命名规范

| 前缀 | 类别 | 示例 |
|---|---|---|
| `--c-` | 颜色 (Color) | `--c-primary`, `--c-text` |
| `--s-` | 间距 (Space) | `--s-4`, `--s-6` |
| `--fs-` | 字号 (Font Size) | `--fs-base`, `--fs-xl` |
| `--r-` | 圆角 (Radius) | `--radius`, `--r-full` |
| `--sh-` | 阴影 (Shadow) | `--shadow`, `--sh-lg` |
| `--bp-` | 断点 (Breakpoint) | `--bp-md`, `--bp-xl` |
| `--t-` | 过渡 (Transition) | `--t-base`, `--t-fast` |
| `--lh-` | 行高 (Line Height) | `--lh-base`, `--lh-tight` |
| `--fw-` | 字重 (Font Weight) | `--fw-normal`, `--fw-bold` |
| `--ff-` | 字体族 (Font Family) | `--ff-sans`, `--ff-mono` |

## 颜色体系

### 品牌色

| Token | 亮色 | 暗色 | 用途 |
|---|---|---|---|
| `--c-primary` | #2563eb | #3b82f6 | 主按钮、链接、选中态 |
| `--c-primary-hover` | #1d4ed8 | #60a5fa | hover 态（别名 `--c-primary-d`） |
| `--c-primary-light` | #dbeafe | #1e3a5f | 轻量背景（别名 `--c-primary-l`） |

### 功能色

| Token | 亮色 | 暗色 | 用途 |
|---|---|---|---|
| `--c-success` | #059669 | #10b981 | 成功状态、已通过 |
| `--c-success-light` | #d1fae5 | #065f46 | 成功浅背景 |
| `--c-warning` | #d97706 | #f59e0b | 警告状态、待审核 |
| `--c-warning-light` | #fef3c7 | #451a03 | 警告浅背景 |
| `--c-error` | #dc2626 | #ef4444 | 错误状态、驳回（别名 `--c-danger`） |
| `--c-error-light` | #fee2e2 | #7f1d1d | 错误浅背景（别名 `--c-danger-l`） |
| `--c-info` | #0284c7 | #38bdf8 | 信息提示 |
| `--c-info-light` | #cffafe | #083344 | 信息浅背景 |

### 中性色（Surface 层级）

| Token | 亮色 | 暗色 | 用途 |
|---|---|---|---|
| `--c-bg` | #f7f8fa | #0f1115 | 页面背景 |
| `--c-sidebar` | #ffffff | #161922 | 侧边栏背景 |
| `--c-surface` | #ffffff | #1a1d26 | 卡片/面板背景 |
| `--c-surface-2` | #f0f1f4 | #242836 | 次级表面（表格头、侧栏） |
| `--c-surface-3` | #e9ebf0 | #2f3545 | 三级表面（hover 行、分隔线） |
| `--c-border` | #e4e6eb | #2a2e3d | 默认边框 |
| `--c-border-light` | #f1f5f9 | #1a1d26 | 浅色边框（卡片内分隔） |
| `--c-border-strong` | #d1d5db | #3a3f52 | 强调边框（输入框 focus） |

### 文字色

| Token | 亮色 | 暗色 | 用途 |
|---|---|---|---|
| `--c-text` | #1a1d23 | #f0f2f5 | 正文 |
| `--c-text-secondary` | #3d4250 | #c9cdd6 | 次要文字（别名 `--c-text-2`） |
| `--c-text-muted` | #6b7280 | #8b92a5 | 辅助文字、占位符（别名 `--c-muted`） |
| `--c-text-inverse` | #ffffff | #0f172a | 反色文字（深色按钮内） |

## 间距体系

基于 4px 网格，1rem = 16px 基准：

| Token | rem | px | 典型用途 |
|---|---|---|---|
| `--s-0` | 0 | 0 | 无间距 |
| `--s-1` | 0.25rem | 4px | 元素内微间距 |
| `--s-2` | 0.5rem | 8px | 紧凑元素间距 |
| `--s-3` | 0.75rem | 12px | 卡片内间距（小） |
| `--s-4` | 1rem | 16px | 卡片内间距（默认） |
| `--s-5` | 1.25rem | 20px | 卡片内间距（大） |
| `--s-6` | 1.5rem | 24px | 区块间距 |
| `--s-8` | 2rem | 32px | 大区块间距 |
| `--s-10` | 2.5rem | 40px | 页面顶部间距 |
| `--s-12` | 3rem | 48px | 大页面间距 |
| `--s-16` | 4rem | 64px | 超大间距 |

## 字号体系

| Token | rem | px | 行高 | 用途 |
|---|---|---|---|---|
| `--fs-xs` | 0.75rem | 12px | 1.25 | 标签、辅助文字、角标 |
| `--fs-sm` | 0.875rem | 14px | 1.4 | 表单、表格、紧凑正文 |
| `--fs-base` | 0.9375rem | 15px | 1.6 | 正文（默认） |
| `--fs-lg` | 1.125rem | 18px | 1.5 | 小标题、强调文字 |
| `--fs-xl` | 1.25rem | 20px | 1.4 | 卡片标题 |
| `--fs-2xl` | 1.5rem | 24px | 1.3 | 页面二级标题 |
| `--fs-3xl` | 2rem | 32px | 1.2 | 页面主标题 |

**使用要点**：正文永远使用 `--fs-base`，不要随意使用其他字号。

## 行高体系

| Token | 值 | 用途 |
|---|---|---|
| `--lh-tight` | 1.2 | 大标题（减少行高让标题更紧凑） |
| `--lh-base` | 1.5 | 正文、段落 |
| `--lh-loose` | 1.6 | 大段落文字、宽松排版 |

## 字重体系

| Token | 值 | 用途 |
|---|---|---|
| `--fw-light` | 300 | 轻量文字、次要信息 |
| `--fw-normal` | 400 | 普通正文 |
| `--fw-medium` | 500 | 小标题、强调文字 |
| `--fw-semibold` | 600 | 卡片标题、按钮文字 |
| `--fw-bold` | 700 | 大标题、重量级强调 |

## 字体族体系

| Token | 值 | 用途 |
|---|---|---|
| `--ff-sans` | -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif, "Apple Color Emoji", "Segoe UI Emoji" | 正文、UI 元素（默认字体） |
| `--ff-mono` | SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace | 代码、等宽文字 |

## 圆角体系

| Token | 值 | 典型用途 |
|---|---|---|
| `--r-none` | 0 | 无圆角 |
| `--r-sm` | 6px | 小按钮、标签 |
| `--radius` | 10px | 默认圆角（卡片、按钮、输入框）（别名 `--r-md`） |
| `--r-lg` | 14px | 大卡片、模态框 |
| `--r-xl` | 20px | 超大卡片、英雄区 |
| `--r-full` | 9999px | 圆形元素、胶囊按钮 |

## 阴影体系

| Token | 值 | 典型用途 |
|---|---|---|
| `--sh-sm` | 0 1px 2px rgba(0,0,0,0.04) | 轻微阴影（小卡片） |
| `--shadow` | 0 2px 8px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04) | 默认阴影（卡片、浮层）（别名 `--sh-md`） |
| `--sh-lg` | 0 8px 24px rgba(0,0,0,0.08), 0 2px 4px rgba(0,0,0,0.04) | 大阴影（下拉菜单、模态框） |
| `--sh-xl` | 0 16px 48px rgba(0,0,0,0.12), 0 4px 8px rgba(0,0,0,0.04) | 超大阴影（浮层、模态框） |

## 断点体系

| Token | 值 | 设备 |
|---|---|---|
| `--bp-sm` | 480px | 手机横屏 |
| `--bp-md` | 768px | 平板竖屏 |
| `--bp-lg` | 1024px | 平板横屏 / 小屏笔记本 |
| `--bp-xl` | 1200px | 桌面端 |

用法示例：
```css
@media (min-width: calc(var(--bp-md) + 2 * var(--s-4))) {
    /* 平板及以上样式 */
}
```

## 过渡/动效体系

### 时长 Tokens

| Token | 值 | 用途 |
|---|---|---|
| `--dur-fast` | 150ms | hover 反馈、小交互（按钮按压、链接变色） |
| `--dur-base` | 250ms | 默认过渡（主题切换、展开收起、面板切换） |
| `--dur-slow` | 400ms | 慢过渡（弹窗出现、大型面板切换） |

### 缓动函数 Tokens

| Token | 值 | 用途 |
|---|---|---|
| `--ease-standard` | cubic-bezier(0.4, 0, 0.2, 1) | 标准缓动（Material 风格，默认推荐） |
| `--ease-in` | cubic-bezier(0.4, 0, 1, 1) | 加速缓动（元素进入场景） |
| `--ease-out` | cubic-bezier(0, 0, 0.2, 1) | 减速缓动（元素退出场景） |
| `--ease-in-out` | cubic-bezier(0.4, 0, 0.2, 1) | 对称缓动（往返动画） |

### 完整过渡 Tokens（组合值，直接用于 transition 属性）

| Token | 值 | 用途 |
|---|---|---|
| `--t-fast` | 150ms cubic-bezier(0.4, 0, 0.2, 1) | 快速过渡（hover 反馈） |
| `--t-base` | 250ms cubic-bezier(0.4, 0, 0.2, 1) | 默认过渡（主题切换、展开收起） |
| `--t-slow` | 400ms cubic-bezier(0.4, 0, 0.2, 1) | 慢过渡（动画、大型切换） |

### 动效规范

1. **hover 反馈**：一律使用 `--t-fast`（150ms），反馈即时不拖沓
2. **状态切换**（展开/收起/主题）：使用 `--t-base`（250ms），兼顾流畅与响应
3. **弹窗/浮层出现**：使用 `--t-slow`（400ms）+ `--ease-out`，退出用 `--ease-in`
4. **不滥用动效**：仅交互节点加过渡，内容区避免持续动画；尊重 `prefers-reduced-motion`（base.css 已内置媒体查询）

## 使用指南

### 引入顺序

Tokens 必须在 `base.css` 之后引入，因为语义别名依赖 base.css 里的原始变量：

```html
<link rel="stylesheet" href="/static/css/base.css">
<link rel="stylesheet" href="/static/css/tokens.css">
```

### 暗色主题

暗色主题通过 HTML 属性 `data-theme="dark"` 激活，放在 `<html>` 标签上：

```html
<html data-theme="dark">
```

JS 可以通过切换这个属性来切换主题：
```javascript
document.documentElement.dataset.theme = 
  document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
```

### 向后兼容

v1 变量（`--c-primary`, `--s-4`, `--r-md` 等）保留在 `base.css` 中，仍然可以使用。新代码推荐使用 v2 语义别名（`--radius`, `--c-text-secondary` 等），更易读更语义化。

### 使用示例

```css
.card {
  background: var(--c-surface);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: var(--s-4);
  margin-bottom: var(--s-6);
}

.card-title {
  font-size: var(--fs-xl);
  color: var(--c-text);
  margin-bottom: var(--s-3);
}

.card-text {
  font-size: var(--fs-base);
  color: var(--c-text-secondary);
  line-height: 1.6;
}
```

## 维护原则

1. **单一来源**：所有设计值都定义在这里，不硬编码到 CSS 中
2. **语义优先**：优先使用语义化名称（`--c-text-secondary`）而非数值名称
3. **不删除**：旧 token 保留，不删除，只标记废弃
4. **向后兼容**：修改 token 值不改变名称，保证现有代码不被破坏
