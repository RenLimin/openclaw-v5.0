# 🧩 Web Common — L2 通用 Web UI 组件库

> 抽离 L4 业务组件中重复的 Web UI 模式，做成可复用的 Jinja2 宏 + CSS + JS 库。

## 特性

- 🎨 **设计语言统一**：侧边栏布局 + 深浅双主题 + 一致的视觉规范
- 🧱 **组件化**：Jinja2 宏封装，参数化配置，不用复制大段 HTML
- 🚀 **零依赖**：仅依赖 Jinja2 + FastAPI，无额外前端框架
- 📱 **响应式**：4 档断点（1200 / 1024 / 768 / 480），移动端友好
- ♿ **无障碍**：语义化 HTML + ARIA label + `prefers-reduced-motion` 支持

## 目录结构

```
web-common/
├── README.md                    # 本文档
├── macros/                      # Jinja2 宏
│   ├── __init__.py              # Python 封装 + FastAPI 挂载工具
│   ├── layout.html              # 基础布局宏（侧边栏 + 页头）
│   ├── components.html          # 通用组件宏（卡片/表格/徽章/进度条/分页...）
│   ├── forms.html               # 表单宏（输入/选择/文本域/按钮/开关...）
│   └── icons.html               # 图标宏（内联 SVG，19+ 常用图标）
├── static/
│   ├── css/
│   │   ├── base.css             # 重置 + CSS 变量（深浅主题）+ 工具类
│   │   ├── layout.css           # 侧边栏布局 + 响应式
│   │   ├── components.css       # 卡片/表格/按钮/徽章/分页/模态框...
│   │   └── forms.css            # 表单样式
│   └── js/
│       ├── theme.js             # 主题切换（localStorage + 系统跟随）
│       └── toast.js             # Toast 消息提示
├── tests/
│   ├── test_macros.py           # 宏渲染测试（40+ 用例）
│   └── test_integration.py      # 集成测试（FastAPI + 资源完整性）
└── examples/
    └── demo_app.py              # 最小 FastAPI Demo（4 个演示页面）
```

## 快速开始

### 1. 挂载到 FastAPI

```python
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import FileSystemLoader

app = FastAPI()

# 宏和静态资源目录
WEB_COMMON = Path("path/to/web-common")
MACROS_DIR = WEB_COMMON / "macros"
STATIC_DIR = WEB_COMMON / "static"
MY_TEMPLATES = Path("my_templates")

# 挂载静态资源
app.mount("/static/web-common", StaticFiles(directory=str(STATIC_DIR)), name="wc-static")

# 配置 Jinja2：业务模板 + 宏目录
templates = Jinja2Templates(directory=str(MY_TEMPLATES))
templates.env.loader = FileSystemLoader([str(MY_TEMPLATES), str(MACROS_DIR)])
```

### 2. 写页面模板

```jinja2
{# my_templates/dashboard.html #}
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
            {"id": "list", "label": "列表", "url": "/list", "icon": "📋"},
        ]}
    ]
) %}
    {{ page_header(title="仪表盘", subtitle="概览数据", actions=[
        {"label": "新建", "url": "/new", "variant": "primary", "icon": "➕"}
    ]) }}

    {% call dashboard_grid() %}
        {{ stat_card(label="总用户", value=1234, variant="primary", sub="本月 +12%") }}
        {{ stat_card(label="订单数", value=567, variant="success") }}
    {% endcall %}

    {% call card(title="最近订单") %}
        {{ table(
            columns=[
                {"key": "id", "label": "ID"},
                {"key": "name", "label": "名称"},
                {"key": "amount", "label": "金额", "align": "right", "num": true}
            ],
            rows=orders
        ) }}
    {% endcall %}
{% endcall %}
```

### 3. 写路由

```python
@app.get("/")
async def dashboard(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "orders": [...]}
    )
```

## 组件清单

### 布局 (layout.html)

| 宏 | 用途 | 关键参数 |
|---|---|---|
| `base_layout` | 完整页面布局（侧边栏 + 顶栏 + Toast） | `title`, `brand_name`, `sidebar_items`, `active_page`, `storage_key` |
| `page_header` | 页面标题区 | `title`, `subtitle`, `actions` |

### 通用组件 (components.html)

| 宏 | 用途 | 关键参数 |
|---|---|---|
| `card` | 卡片容器 | `title`, `actions` |
| `stat_card` | 统计数字卡片 | `label`, `value`, `variant`, `sub` |
| `dashboard_grid` | 统计卡片网格 | — |
| `table` | 数据表格 | `columns`, `rows`, `row_actions`, `empty_text` |
| `badge` | 徽章/标签 | `text`, `variant` |
| `progress_bar` | 进度条 | `percent`, `variant`, `label` |
| `chart_container` | 图表容器 | `title`, `height`, `id` |
| `pagination` | 分页 | `current`, `total_pages`, `on_click`, `href_template` |
| `filter_bar` | 筛选栏 | `fields`, `submit_onclick`, `reset_onclick` |
| `info_grid` | 详情信息网格 | `items` |

### 表单 (forms.html)

| 宏 | 用途 | 关键参数 |
|---|---|---|
| `input` | 文本/数字/日期等输入框 | `name`, `label`, `type`, `value`, `required` |
| `textarea` | 多行文本域 | `name`, `label`, `value`, `rows` |
| `select` | 下拉选择 | `name`, `label`, `options`, `value` |
| `button` | 按钮 | `text`, `variant`, `type`, `size`, `url` |
| `form_row` | 多列表单行 | `cols` (2/3/4) |
| `checkbox` | 复选框 | `name`, `label`, `checked` |
| `switch` | 开关切换 | `name`, `label`, `checked` |

### 图标 (icons.html)

19+ 内联 SVG 图标，用 `currentColor` 继承父元素颜色：

`icon_home` `icon_dashboard` `icon_settings` `icon_menu` `icon_plus` `icon_check` `icon_x` `icon_edit` `icon_trash` `icon_search` `icon_alert` `icon_info` `icon_sun` `icon_moon` `icon_file` `icon_chart` `icon_user` `icon_arrow_left` `icon_arrow_right`

用法：`{{ icon_home(size=20) }}`

## JavaScript API

### Theme (theme.js)

```js
// 获取当前主题
Theme.current  // 'light' | 'dark'

// 设置主题
Theme.set('dark')

// 切换主题
Theme.toggle()

// 订阅主题变化（用于图表等需要重新渲染的场景）
Theme.onChange(function(theme) {
    console.log('主题切换到:', theme);
});
```

### Toast (toast.js)

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

## CSS 变量 / 主题定制

通过覆盖 CSS 变量即可定制主题色：

```css
:root {
    --c-primary: #8b5cf6;    /* 紫色主色 */
    --c-primary-l: #a78bfa;
    --c-primary-d: #7c3aed;
    --sidebar-w: 260px;       /* 侧边栏宽度 */
}
```

深色模式变量在 `[data-theme="dark"]` 选择器下覆盖。

## 运行 Demo

```bash
cd web-common
python examples/demo_app.py
# 访问 http://localhost:8000
```

## 运行测试

```bash
cd web-common
pytest tests/ -v
```

测试覆盖：
- ✅ 布局宏渲染（9 个用例）
- ✅ 组件宏渲染（13 个用例）
- ✅ 表单宏渲染（10 个用例）
- ✅ 图标宏（19 个用例）
- ✅ 集成测试（12 个用例）

## 设计原则

1. **零依赖**：仅 Jinja2 + FastAPI，不引入 React/Vue 等前端框架
2. **CSS 变量驱动**：主题、间距、圆角全部通过 CSS 变量配置，易定制
3. **宏即组件**：每个宏是独立的 UI 单元，参数化配置，不复制 HTML
4. **渐进增强**：基础功能纯 HTML+CSS，JS 只做增强（主题切换、Toast）
5. **可被 import**：宏目录加入 Jinja2 loader 即可使用，无需 copy 代码

## 迁移指南（L4 组件接入）

对于已有独立 Web UI 的 L4 组件，迁移步骤：

1. **替换 base.html**：删掉自有 base.html，改用 `base_layout` 宏
2. **替换 CSS**：删掉自有 style.css，改用 web-common 的 4 个 CSS 文件
3. **替换 JS**：主题切换和 Toast 改用 web-common 的 JS
4. **逐步替换页面组件**：card/table/form 等逐步换成宏调用
5. **保留业务特有样式**：业务专属样式写在独立 CSS 文件中追加引入

## License

与项目整体一致。
