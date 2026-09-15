---
type: correct
id: EXP-20260915-016
date: 2026-09-15
title: L2+L4 分层 Web UI 组件库的构建经验
layers: [L2, L4]
phase: develop
category: project-experience
severity: medium
tags: [web-ui, component-library, jinja2, css, responsive, L2, L4]
status: active
---

# [EXP-20260915-016] L2+L4 分层 Web UI 组件库的构建经验

## 1. 背景

系统有多个 L4 业务组件（FIN-L4 / SCA / DMS 等），每个都有 Web UI。如果各自写一套样式和组件：
- 视觉不统一（按钮、卡片、表格各不一样）
- 重复劳动（每个项目都写一遍侧边栏、表单、表格）
- 维护成本高（改个主题色要改 N 个项目）
- 响应式断点不一致

目标：构建一套 L2 级别的 Web UI 组件库，L4 业务组件直接复用，只写业务特有样式。

## 2. 问题

1. 如何分层（L2 放什么，L4 放什么）
2. 如何在 Jinja2 模板中实现组件复用（不是 React/Vue 的组件模型）
3. 如何做主题切换（深色/浅色）
4. 如何保证响应式一致
5. 零构建步骤（不能引入 Node.js 构建链）

## 3. 方案

### 3.1 分层架构

```
L2 web-common (基础设施层)
├── macros/                     # Jinja2 宏组件库
│   ├── layout.html              # 基础布局宏 (base_layout)
│   ├── components.html          # 通用组件 (card / stat-card / badge ...)
│   └── forms.html               # 表单组件 (button / input / select ...)
└── static/css/
    ├── base.css                 # CSS 变量 + reset + 工具类
    ├── layout.css               # 侧边栏布局 + 响应式断点
    ├── components.css           # 卡片 / 表格 / 徽章 / 进度条
    └── forms.css                # 表单控件样式

L4 业务层 (每个业务组件独立)
├── templates/
│   ├── base.html                # 继承 L2 layout，注入业务变量
│   ├── dashboard.html           # 业务页面
│   └── ...
└── static/
    └── style.css                # 业务特有样式（只写增量，不覆盖基础）
```

### 3.2 Jinja2 宏组件模式

用 Jinja2 的 `macro` + `call` 实现组件复用：

```jinja2
{# components.html #}
{% macro card(title='', variant='default') %}
<div class="card card-{{ variant }}">
  {% if title %}
  <div class="card-header">
    <h3 class="card-title">{{ title }}</h3>
  </div>
  {% endif %}
  <div class="card-body">
    {{ caller() }}
  </div>
</div>
{% endmacro %}
```

业务页面使用：
```jinja2
{% from "components.html" import card with context %}

{% call card(title='账户总览') %}
  <p>这里是卡片内容</p>
{% endcall %}
```

### 3.3 CSS 变量驱动的主题系统

所有颜色/间距/圆角/阴影都用 CSS 变量定义，深浅主题通过 `data-theme` 属性切换：

```css
:root {
    --c-bg: #f7f8fa;
    --c-primary: #2563eb;
    --c-success: #059669;
    --s-4: 1rem;
    --r-md: 10px;
    --sh-md: 0 2px 8px rgba(0,0,0,0.06);
}
[data-theme="dark"] {
    --c-bg: #0f1115;
    --c-primary: #3b82f6;
    --c-success: #10b981;
    /* ... 深色变量 ... */
}
```

**切换逻辑**：一行 JS 搞定
```javascript
document.documentElement.setAttribute('data-theme', 'dark');
localStorage.setItem(storageKey, 'dark');
```

图表库（ECharts）也跟随主题切换：监听 `themechange` 事件，重新初始化图表。

### 3.4 响应式断点统一

4 档断点，所有业务组件共享：

| 断点 | 设备 | 关键变化 |
|---|---|---|
| ≥ 1200px | 桌面大 | 4 列网格、完整侧边栏 |
| ≤ 1200px | 桌面 | 3 列变 2 列 |
| ≤ 1024px | 平板 | 侧边栏变窄、4 列变 2 列 |
| ≤ 768px | 移动端 | 侧边栏抽屉式、单列布局 |
| ≤ 480px | 小屏手机 | 单卡片全宽、字号缩小 |

**移动端侧边栏**：固定在左侧，默认 `translateX(-100%)`，点汉堡按钮滑出。

### 3.5 L4 业务层的增量原则

L4 只写业务特有样式，遵守三条规则：
1. **不覆盖基础样式**：不在 L4 里改 `--c-primary` 等全局变量
2. **只加不减**：L4 的 CSS 是增量的，复用 L2 的所有样式
3. **命名空间**：业务样式加前缀（`.budget-*` / `.portfolio-*`），避免污染

L4 需要新增的样式只有：
- 业务模块特有布局（预算进度条、投资持仓列表等）
- 业务模块特有状态（超支红 / 预警黄 / 正常绿）

### 3.6 UX 三件套规范

每个数据展示页面必须有：

| 状态 | 样式类 | 说明 |
|---|---|---|
| 加载中 | `.skeleton` / `.loading-state` | 骨架屏或 spinner，不让用户盯着空白等 |
| 空状态 | `.empty-state` | 图标 + 标题 + 描述 + 行动按钮（引导用户下一步） |
| 错误 | `.error-banner` / `.error-page` | 明确说清错误原因 + 提供重试/返回操作 |

## 4. 验证

- ✅ FIN-L4 12 个页面全部复用 L2 组件库
- ✅ 深浅主题一键切换，包括图表
- ✅ 4 档响应式断点全部验证（桌面/平板/手机/小屏）
- ✅ L4 业务样式只有约 680 行（如果从零写预计 2000+ 行）
- ✅ 零构建步骤，`python main.py` 直接跑
- ✅ 可复用：下一个 L4 业务组件直接 import 就能用

## 5. 教训

**为什么有效**：
1. **分层清晰**：L2 管通用，L4 管业务，职责不交叉
2. **零构建**：纯 CSS + Jinja2 宏，不需要 Node.js / Webpack / Vite
3. **主题系统简洁**：CSS 变量 + data 属性，切换成本极低
4. **渐进增强**：新业务组件接入成本极低（引用 base.css 就能用所有组件）

**可推广条件**：
- 多业务组件共享设计语言的系统
- 后端渲染（Jinja2 / Django templates 等）场景
- 不想引入前端构建链的轻量项目

**踩过的坑**：
1. **宏的 context 问题**：宏默认不继承模板变量，要用 `with context` 才会传进去
2. **CSS 变量继承**：业务层不要覆盖基础变量，否则主题切换会出问题
3. **图表主题同步**：ECharts 不支持 CSS 变量，要手动监听主题切换并重绘
4. **响应式表格**：移动端表格会横向溢出，要用 `.table-wrapper` + `overflow-x: auto`
5. **字体加载闪烁**：Google Fonts 远程加载会有 FOIT，考虑本地 fallback 字体栈

## 6. 升级判断

- [x] 影响 ≥ 2 个层级 → 是（L2 基础设施 + L4 业务层）
- [ ] 涉及 L1/L2 契约 → 否
- [x] 多模块对齐 → 是（所有 L4 组件都用同一套）
- ⚠️ 建议升级为 ADR，但当前规模尚小，先保持卡片观察

## 7. 引用

- 相关 ADR: ADR-202609-027 (FIN-L4 架构)
- 组件库路径: `L2-infra/components/web-common/`
- 业务样式: `L4-proprietary/components/fin-l4/src/fin_l4/web/static/style.css`

## 8. 变更历史

- 2026-09-15: 创建
