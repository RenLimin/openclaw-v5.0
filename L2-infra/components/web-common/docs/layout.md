# layout — 布局宏文档

## 概述

`layout.html` 提供了基础应用布局宏，包含侧边栏、顶部工具栏、响应式适配。

## `base_layout` 基础布局

### 用法

```jinja2
{% from "macros/layout.html" import base_layout with context %}
{% call base_layout(
    title="页面标题",
    active_page="dashboard",
    brand_icon="📊",
    brand_name="我的应用",
    storage_key="myapp-theme"
) %}
    <p>页面内容放在这里</p>
{% endcall %}
```

### 参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `title` | string | 否 | 页面标题，显示在顶部工具栏 |
| `active_page` | string | 否 | 当前激活的侧边栏菜单项 ID |
| `brand_icon` | string | 否 | 品牌图标（emoji 或 HTML） |
| `brand_name` | string | 否 | 品牌名称，显示在侧边栏顶部 |
| `brand_logo` | string | 否 | 品牌 Logo URL，如果提供则替换图标+文字 |
| `storage_key` | string | 否 | localStorage 存储主题的 key，默认 `web-common-theme` |
| `sidebar_items` | list | 否 | 侧边栏菜单项，结构化数据 |
| `extra_head` | string | 否 | 额外 head 内容（CSS/meta） |
| `extra_scripts` | string | 否 | 额外 script 内容 |
| `lang` | string | 否 | HTML lang 属性，默认 `zh-CN` |
| `show_mobile_menu` | bool | 否 | 是否显示移动端菜单按钮，默认 `true` |

### sidebar_items 结构

`sidebar_items` 是一个数组，每个元素是一个 section：

```python
[
    {
        "title": "一级菜单",  # 可以为空
        "items": [
            {
                "id": "dashboard",
                "url": "/dashboard",
                "label": "仪表盘",
                "icon": "📊"
            },
            ...
        ]
    },
    ...
]
```

## `page_header` 页面标题区

### 用法

```jinja2
{% from "macros/layout.html" import page_header %}
{{ page_header(
    title="仪表盘",
    subtitle="概览数据统计",
    actions=[
        {
            "label": "新建",
            "icon": "➕",
            "url": "/create",
            "variant": "primary"
        }
    ]
) }}
```

### 参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `title` | string | 是 | 页面主标题 |
| `subtitle` | string | 否 | 副标题说明 |
| `actions` | list | 否 | 操作按钮列表，每个按钮包含 `label`/`icon`/`url`/`variant`/`size`/`onclick` |

## 响应式断点

使用 Design Tokens 断点体系：

| 断点 | 宽度 | 适配行为 |
|---|---|---|
| `--bp-xl` | ≥ 1200px | 桌面端默认 |
| `--bp-lg` | ≥ 1024px | 小屏笔记本，侧边栏宽度收缩到 200px |
| `--bp-md` | ≥ 768px | 平板竖屏，侧边栏隐藏，点击按钮弹出 |
| `--bp-sm` | ≥ 480px | 手机横屏，单列布局 |
| < 480px | 手机竖屏，紧凑布局 |

## 特性

- ✅ 可折叠侧边栏
- ✅ 可拖拽调整侧边栏宽度（JS 实现，存储到 localStorage）
- ✅ 主题切换内置
- ✅ 响应式适配桌面/平板/手机
- ✅ Toast 容器内置
