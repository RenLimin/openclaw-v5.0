# Web Common — L2 通用 Web UI 组件库

> L2 基础设施层 · 可复用 Jinja2 宏 + CSS + JS 库
>
> **2026-09-11**：基于实际代码重写，对齐 macros + static + examples 三层结构。

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 组件类 | Web 通用 UI |
| 状态 | ✅ 已建设 |
| 设计原则 | 零依赖、CSS 变量驱动、宏即组件、渐进增强 |

## 2. 设计约束

1. **零运行时依赖**：仅 Jinja2 + FastAPI，不引入 React/Vue/Angular 等前端框架。
2. **CSS 变量驱动**：主题色、间距、圆角、字体全部通过 CSS 变量配置，覆盖变量即可换肤。
3. **宏即组件**：每个 Jinja2 宏是独立的 UI 单元，参数化配置，不复制 HTML。
4. **渐进增强**：基础功能纯 HTML+CSS 可用，JS 只做增强（主题切换、Toast 提示）。
5. **可被 import**：宏目录加入 Jinja2 `FileSystemLoader` 搜索路径即可使用，无需 copy 代码。
6. **响应式**：4 档断点（1200 / 1024 / 768 / 480），移动端友好。
7. **无障碍**：语义化 HTML + ARIA label + `prefers-reduced-motion` 支持。

## 3. 架构

```
┌─────────────────────────────────────────────────────────┐
│                    L4 业务组件                          │
│                   (FastAPI App)                         │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │  业务模板 (templates/dashboard.html)              │  │
│  │  {% from "layout.html" import base_layout %}       │  │
│  │  {% from "components.html" import card, table %}   │  │
│  └───────────────┬───────────────────────────────────┘  │
│                  │ import                               │
│  ┌───────────────▼───────────────────────────────────┐  │
│  │  macros/ — Jinja2 宏                              │  │
│  │  ├── layout.html    基础布局 + 页头               │  │
│  │  ├── components.html 卡片/表格/徽章/进度条/分页.. │  │
│  │  ├── forms.html     输入/选择/按钮/开关..         │  │
│  │  ├── icons.html     19+ 内联 SVG 图标             │  │
│  │  └── __init__.py    setup_web_common() 挂载工具   │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │  static/ — CSS + JS                               │  │
│  │  ├── css/                                         │  │
│  │  │   ├── base.css     重置 + CSS 变量 + 工具类    │  │
│  │  │   ├── layout.css   侧边栏布局 + 响应式         │  │
│  │  │   ├── components.css  组件样式                 │  │
│  │  │   └── forms.css    表单样式                    │  │
│  │  └── js/                                          │  │
│  │      ├── theme.js   深浅主题切换                 │  │
│  │      └── toast.js   Toast 消息提示                │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │  examples/ — Demo 应用                            │  │
│  │  ├── demo_app.py     FastAPI Demo (4 个页面)      │  │
│  │  └── templates/      示例页面模板                │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 3.1 模块职责

| 模块 | 文件 | 职责 |
|---|---|---|
| 布局宏 | `macros/layout.html` | `base_layout`（完整页面骨架）+ `page_header`（标题区） |
| 组件宏 | `macros/components.html` | `card` / `stat_card` / `dashboard_grid` / `table` / `badge` / `progress_bar` / `chart_container` / `pagination` / `filter_bar` / `info_grid` |
| 表单宏 | `macros/forms.html` | `input` / `textarea` / `select` / `button` / `form_row` / `checkbox` / `switch` / `form_group` |
| 图标宏 | `macros/icons.html` | 19+ 内联 SVG 图标（`currentColor` 继承），`_svg` 基础宏 + `icon_home` / `icon_check` / `icon_edit` / ... |
| Python 工具 | `macros/__init__.py` | `setup_web_common()` — 一键挂载到 FastAPI |
| 基础样式 | `static/css/base.css` | CSS 重置 + 主题变量 + 排版 + 工具类 |
| 布局样式 | `static/css/layout.css` | 侧边栏 + 主内容区 + 4 档响应式断点 |
| 组件样式 | `static/css/components.css` | 卡片/表格/按钮/徽章/分页/模态框 |
| 表单样式 | `static/css/forms.css` | 输入框/选择器/按钮/开关样式 |
| 主题 JS | `static/js/theme.js` | `Theme` API：get/set/toggle/onChange |
| Toast JS | `static/js/toast.js` | `Toast` API：success/error/warning/info |
| Demo 应用 | `examples/demo_app.py` | 4 个演示页面：仪表盘/表格/表单/组件 |
| 测试 | `tests/test_macros.py` | 宏渲染测试（40+ 用例） |
| 测试 | `tests/test_integration.py` | 集成测试（FastAPI + 资源完整性） |

## 4. 核心 API

### 4.1 Python 挂载 (setup_web_common)

```python
from pathlib import Path
from fastapi import FastAPI
from web_common.macros import setup_web_common

app = FastAPI()
templates = setup_web_common(
    app,
    template_dir="my_templates",      # 业务模板目录
    static_url_path="/static/web-common"
)
```

**行为**：
1. 挂载 `static/` 到 `/static/web-common`（StaticFiles）
2. 配置 Jinja2 loader：业务模板目录 + 宏目录
3. 返回 `Jinja2Templates` 实例

### 4.2 手动挂载（不用 __init__.py）

```python
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import FileSystemLoader

app.mount("/static/web-common", StaticFiles(directory="static"), name="wc-static")
templates = Jinja2Templates(directory="my_templates")
templates.env.loader = FileSystemLoader(["my_templates", "macros"])
```

### 4.3 模板中使用宏

```jinja2
{% from "layout.html" import base_layout, page_header with context %}
{% from "components.html" import card, stat_card, dashboard_grid, table with context %}

{% call base_layout(
    title="仪表盘",
    brand_name="我的应用",
    brand_icon="🚀",
    active_page="dashboard",
    storage_key="myapp-theme",
    sidebar_items=[
        {"title": "概览", "items": [
            {"id": "dashboard", "label": "仪表盘", "url": "/", "icon": "📊"},
        ]}
    ]
) %}
    {{ page_header(title="仪表盘", subtitle="概览数据") }}
    {% call dashboard_grid() %}
        {{ stat_card(label="总用户", value=1234, variant="primary") }}
    {% endcall %}
{% endcall %}
```

## 5. 组件清单

### 5.1 布局 (layout.html)

| 宏 | 用途 | 关键参数 |
|---|---|---|
| `base_layout` | 完整页面布局（侧边栏 + 顶栏 + Toast 容器） | `title`, `brand_name`, `brand_icon`, `active_page`, `storage_key`, `sidebar_items`, `show_mobile_menu` |
| `page_header` | 页面标题区 | `title`, `subtitle`, `actions` |

### 5.2 通用组件 (components.html)

| 宏 | 用途 | 关键参数 |
|---|---|---|
| `card` | 卡片容器 | `title`, `actions`, `class_` |
| `stat_card` | 统计数字卡片 | `label`, `value`, `variant`, `sub`, `icon` |
| `dashboard_grid` | 统计卡片网格容器 | — |
| `table` | 数据表格 | `columns`, `rows`, `row_actions`, `empty_text` |
| `badge` | 徽章/标签 | `text`, `variant` |
| `progress_bar` | 进度条 | `percent`, `variant`, `label` |
| `chart_container` | 图表容器 | `title`, `height`, `id` |
| `pagination` | 分页 | `current`, `total_pages`, `on_click`, `href_template` |
| `filter_bar` | 筛选栏 | `fields`, `submit_onclick`, `reset_onclick` |
| `info_grid` | 详情信息网格 | `items` |

### 5.3 表单 (forms.html)

| 宏 | 用途 | 关键参数 |
|---|---|---|
| `input` | 文本/数字/日期等输入框 | `name`, `label`, `type`, `value`, `required`, `disabled`, `readonly`, `help_text`, `error` |
| `textarea` | 多行文本域 | `name`, `label`, `value`, `rows`, `help_text` |
| `select` | 下拉选择 | `name`, `label`, `options`, `value`, `placeholder` |
| `button` | 按钮 | `text`, `variant`, `type`, `size`, `url`, `onclick`, `disabled` |
| `form_row` | 多列表单行 | `cols` (2/3/4) |
| `checkbox` | 复选框 | `name`, `label`, `checked` |
| `switch` | 开关切换 | `name`, `label`, `checked` |
| `form_group` | 表单字段组 | `label`, `id`, `help_text`, `error` |

### 5.4 图标 (icons.html)

19+ 内联 SVG 图标，使用 `currentColor` 继承父元素颜色：

| 类别 | 图标 |
|---|---|
| 导航 | `icon_home` `icon_dashboard` `icon_settings` `icon_menu` |
| 操作 | `icon_plus` `icon_check` `icon_x` `icon_edit` `icon_trash` `icon_search` |
| 状态 | `icon_alert` `icon_info` |
| 主题 | `icon_sun` `icon_moon` |
| 文件 | `icon_file` `icon_chart` `icon_user` |
| 方向 | `icon_arrow_left` `icon_arrow_right` |

## 6. JavaScript API

### 6.1 Theme API (theme.js)

```js
// 获取当前主题
Theme.current  // 'light' | 'dark'

// 设置主题
Theme.set('dark')

// 切换主题
Theme.toggle()

// 订阅主题变化（用于图表重新渲染等）
Theme.onChange(function(theme) {
    console.log('主题切换到:', theme);
});
```

**初始化优先级**：localStorage → 系统 `prefers-color-scheme`

**全局变量依赖**：`window.__WEB_COMMON_STORAGE_KEY__`（由 `base_layout` 宏注入）

### 6.2 Toast API (toast.js)

```js
// 基础用法
showToast('操作成功', 'success');

// 命名空间 API
Toast.success('保存成功');
Toast.error('出错了');
Toast.warning('请注意');
Toast.info('提示信息');

// 自定义时长（默认 3000ms）
Toast.success('完成', 5000);
```

**安全**：内部使用 `escapeHtml()` 转义消息内容，防止 XSS。

## 7. CSS 变量与主题定制

通过覆盖 CSS 变量即可定制主题色：

```css
:root {
    --c-primary: #8b5cf6;       /* 主色 */
    --c-primary-l: #a78bfa;     /* 主色浅 */
    --c-primary-d: #7c3aed;     /* 主色深 */
    --sidebar-w: 260px;          /* 侧边栏宽度 */
}
```

深色模式变量在 `[data-theme="dark"]` 选择器下覆盖。

### 7.1 响应式断点

| 断点 | 宽度 | 适配 |
|---|---|---|
| 桌面 | > 1200px | 完整侧边栏 |
| 平板横屏 | ≤ 1200px | 侧边栏收缩 |
| 平板竖屏 | ≤ 1024px | 侧边栏收起 |
| 手机 | ≤ 768px | 汉堡菜单 + 全屏侧边栏 |
| 小屏手机 | ≤ 480px | 进一步压缩间距 |

## 8. 与其他组件的关系

```
web-common (本组件)
    │
    ├── 依赖 ─── Jinja2 (模板引擎)
    │
    ├── 依赖 ─── FastAPI (Web 框架)
    │
    ├── 被引用 ─ L4 业务组件 (通过 setup_web_common 或手动 loader)
    │
    └── 独立 ─── 不依赖其他 L2 组件
```

## 9. 测试覆盖

| 测试文件 | 用例数 | 覆盖点 |
|---|---|---|
| `tests/test_macros.py` | 40+ | 布局宏(9) / 组件宏(13) / 表单宏(10) / 图标宏(19) |
| `tests/test_integration.py` | 12 | FastAPI 路由响应 / 静态资源可访问 / 模板渲染完整性 |

运行测试：

```bash
cd L2-infra/components/web-common
pytest tests/ -v
```

运行 Demo：

```bash
python3 examples/demo_app.py
# 访问 http://localhost:8000
```

## 10. 演进方向

| 方向 | 优先级 | 触发条件 |
|---|---|---|
| 新增更多组件宏（时间线、步骤条、空状态） | 中 | L4 业务需要时 |
| 暗色模式变量完善 | 低 | 用户反馈可读性问题 |
| 组件文档站点 | 低 | L4 组件数量 > 5 个 |
| TypeScript 迁移（theme.js / toast.js） | 低 | JS 逻辑复杂度增长 |
| 无障碍审计 | 中 | 面向公众产品时 |

## 11. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-11 | 基于实际代码重写 DESIGN.md，覆盖 macros + static + examples 三层完整结构 |
