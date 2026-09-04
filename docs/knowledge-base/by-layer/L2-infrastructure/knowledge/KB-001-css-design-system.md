---
title: CSS 设计系统
layer: [L2]
stage: design
category: industry-practice
tags: [css, design-system, design-token, spacing, color, typography]
created: 2026-09-04
updated: 2026-09-04
confidence: high
sources:
  - title: Tailwind CSS Design System
    url: https://tailwindcss.com/docs/customizing-colors
    accessed: 2026-09-04
  - title: ClawHub frontend-design-guidelines
    url: https://clawhub.ai/wpank/skills/frontend-design-guidelines
    accessed: 2026-09-04
  - title: Stripe Design System
    url: https://stripe.com/docs/design
    accessed: 2026-09-04
---

# CSS 设计系统

## 1. 摘要
CSS 设计系统是一套可复用、可维护的设计规范，通过 CSS 变量（设计 tokens）统一管理颜色、间距、字体、阴影等设计属性，保证全系统设计一致性，降低维护成本。

## 2. 核心原则

### 设计 Tokens
将设计决策抽取为可复用的变量：
- 颜色：品牌色、中性色、语义色、背景色
- 间距：基于 4px/8px 网格的尺度
- 字体：字体系列、大小、行高、字重
- 圆角：不同大小组件使用不同尺度
- 阴影：不同层级卡片/组件使用不同深度
- 过渡：动效时长和缓动函数

### 一致性
- 相同类型组件使用相同 tokens
- 全局一致性 > 局部特殊性
- 组件设计遵循系统尺度，不自定义随机值

### 可维护性
- 一处修改，全局生效
- 明暗主题只需切换颜色变量
- 品牌色变更只需修改一处

## 3. 设计尺度规范

### 间距 (8px base)
| Token | Value | Use Case |
|---|---|---|
| `--s-1` | 0.25rem (4px) | 图标间距、紧凑内边距 |
| `--s-2` | 0.5rem (8px) | 输入框内边距、紧凑列表 |
| `--s-3` | 0.75rem (12px) | 按钮内边距、卡片内边距 |
| `--s-4` | 1rem (16px) | 默认元素间距 |
| `--s-6` | 1.5rem (24px) | 分区内边距、卡片间距 |
| `--s-8` | 2rem (32px) | 区块分隔、主内容区间距 |
| `--s-10` | 2.5rem (40px) | 大区块内边距 |
| `--s-12` | 3rem (48px) | 章节分隔 |
| `--s-16` | 4rem (64px) | 页面级垂直间距 |

### 圆角
| Token | Value | Use Case |
|---|---|---|
| `--r-sm` | 6px | 小按钮、输入框 |
| `--r-md` | 10px | 中组件 |
| `--r-lg` | 14px | 卡片、大容器 |
| `--r-xl` | 20px | 超大卡片、模态框 |

### 阴影
| Token | Value | Use Case |
|---|---|---|
| `--sh-sm` | 0 1px 2px rgba(0,0,0,0.04) | 导航、分隔 |
| `--sh-md` | 0 2px 8px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04) | 悬浮卡片 |
| `--sh-lg` | 0 8px 24px rgba(0,0,0,0.08), 0 2px 4px rgba(0,0,0,0.04) | 下拉菜单、模态框 |
| `--sh-xl` | 0 16px 48px rgba(0,0,0,0.12), 0 4px 8px rgba(0,0,0,0.04) | 浮动卡片、弹窗 |

### 字体尺度 (Major Third 1.25 ratio)
| Size | rem | px | Use Case |
|---|---|---|---|
| `text-xs` | 0.64rem | ~10px | 辅助文字、小字标注 |
| `text-sm` | 0.8rem | ~13px | 辅助说明、表格文字 |
| `text-base` | 1rem | 16px | 正文默认 |
| `text-lg` | 1.25rem | 20px | 小标题 |
| `text-xl` | 1.563rem | 25px | 页面标题 |
| `text-2xl` | 1.953rem | 31px | 大标题 |
| `text-3xl` | 2.441rem | 39px | 页面顶级标题 |

### 字体配对
| 场景 | 显示字体 | 正文字体 |
|---|---|---|
| SaaS Dashboard | Space Grotesk | Inter |
| Editorial / 博客 | Playfair Display | Source Sans 3 |
| 金融数据 | DM Sans | DM Mono |
| 开发工具 | JetBrains Mono | IBM Plex Mono |

## 4. 颜色系统规范

### 颜色角色
每个设计系统需要 5 种功能角色：
| Role | Purpose | Example |
|---|---|---|
| Primary | 品牌识别、主按钮、链接、激活状态 | 品牌蓝 |
| Neutral | 文本、边框、背景 | 灰度系列 |
| Accent | 次要操作、高亮、标签 | 浅蓝/浅紫 |
| Semantic | 反馈信息（成功/警告/错误） | 绿/黄/红 |
| Surface | 分层背景（页面/卡片/上浮元素） | 浅→深灰度分层 |

### 颜色分层（浅色主题示例）
| Surface | HSL | Purpose |
|---|---|---|
| `--c-bg` | `hsl(220 15% 96%)` | 页面背景 |
| `--c-surface` | `hsl(0 0% 100%)` | 卡片背景 |
| `--c-surface-2` | `hsl(220 15% 95%)` | 表格表头、输入框 |
| `--c-border` | `hsl(220 15% 88%)` | 边框 |
| `--c-border-2` | `hsl(220 15% 75%)` | 重边框 |
| `--c-text` | `hsl(220 15% 12%)` | 正文 |
| `--c-text-2` | `hsl(220 15% 25%)` | 次要文字 |
| `--c-muted` | `hsl(220 15% 45%)` | 辅助文字 |
| `--c-muted-2` | `hsl(220 15% 60%)` | 极淡文字 |

**深度原则：** 深色背景用浅色文字，浅色背景用深色文字，保持对比度 ≥ 4.5:1 (WCAG AA)

## 5. 实现方式

### CSS 变量方式（推荐）
```css
:root {
  --c-primary: #2563eb;
  --s-4: 1rem;
  --r-lg: 14px;
}
```
- 优点：运行时可修改，主题切换方便，无需构建工具
- 缺点：IE 不支持（现代前端无需关心）

### CSS-in-JS 方式
适合 React/Vue 等组件化框架，在 JS 中定义 tokens，注入到组件。

### Tailwind 方式
使用工具类，tokens 配置在 `tailwind.config.js` 中。

## 6. 变更历史
- 2026-09-04: 创建
