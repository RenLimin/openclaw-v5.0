# forms — 表单组件宏文档

## 概述

`forms.html` 提供了常用表单字段组件宏，快速构建表单。

## `form_group` — 表单字段组

包装标签 + 字段 + 帮助提示 + 错误提示。

### 用法

```jinja2
{% from "macros/forms.html" import form_group %}
{% call form_group(label="用户名", id="username", help_text="请输入 4-16 位字母数字") %}
    <input type="text" id="username" name="username">
{% endcall %}
```

### 参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `label` | string | 否 | 字段标签 |
| `id` | string | 否 | 字段 ID（对应 for 属性） |
| `help_text` | string | 否 | 帮助提示文字 |
| `error` | string | 否 | 错误提示文字（有错误时设置） |

## `input` — 文本输入框

快速创建带标签的文本输入框。

### 用法

```jinja2
{% from "macros/forms.html" import input %}
{{ input(
    name="username",
    label="用户名",
    placeholder="请输入用户名",
    required=true
) }}
```

### 参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | string | 是 | input name 属性 |
| `label` | string | 否 | 字段标签 |
| `value` | string | 否 | 默认值 |
| `type` | string | 否 | input type，默认 `text` |
| `placeholder` | string | 否 | 占位提示文字 |
| `id` | string | 否 | id 属性，默认等于 name |
| `required` | bool | 否 | 是否必填 |
| `disabled` | bool | 否 | 是否禁用 |
| `readonly` | bool | 否 | 是否只读 |
| `help_text` | string | 否 | 帮助提示 |
| `error` | string | 否 | 错误提示 |

## `textarea` — 多行文本域

### 用法

```jinja2
{% from "macros/forms.html" import textarea %}
{{ textarea(
    name="bio",
    label="个人简介",
    placeholder="介绍一下自己",
    rows=5
) }}
```

### 参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | string | 是 | textarea name |
| `label` | string | 否 | 字段标签 |
| `value` | string | 否 | 默认值 |
| `placeholder` | string | 否 | 占位提示 |
| `id` | string | 否 | id，默认等于 name |
| `rows` | int | 否 | 行数，默认 4 |
| `required` | bool | 否 | 必填 |
| `disabled` | bool | 否 | 禁用 |
| `readonly` | bool | 否 | 只读 |
| `help_text` | string | 否 | 帮助提示 |
| `error` | string | 否 | 错误提示 |

## `select` — 下拉选择框

### 用法

```jinja2
{% from "macros/forms.html" import select %}
{{ select(
    name="status",
    label="状态",
    options=[("1", "启用"), ("0", "禁用")],
    value="1",
    required=true
) }}
```

### 参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | string | 是 | select name |
| `label` | string | 否 | 字段标签 |
| `options` | list | 否 | 选项列表 `[(value, label), ...]` 或 `[{"value":"", "label":""}, ...]` |
| `value` | string | 否 | 默认选中值 |
| `id` | string | 否 | id，默认等于 name |
| `placeholder` | string | 否 | 空选项占位文字 |
| `required` | bool | 否 | 必填 |
| `disabled` | bool | 否 | 禁用 |
| `help_text` | string | 否 | 帮助提示 |
| `error` | string | 否 | 错误提示 |

## `button` — 按钮

### 用法

```jinja2
{% from "macros/forms.html" import button %}
{{ button("提交", variant="primary", type="submit") }}
```

### 参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `text` | string | 是 | 按钮文字 |
| `variant` | string | 否 | 样式变体：`primary`/`success`/`warning`/`danger`/`info` |
| `type` | string | 否 | button type，默认 `button` |
| `size` | string | 否 | 尺寸：`sm`/`lg` |
| `id` | string | 否 | id 属性 |
| `name` | string | 否 | name 属性 |
| `value` | string | 否 | value 属性 |
| `disabled` | bool | 否 | 禁用 |
| `onclick` | string | 否 | onclick 脚本 |
| `url` | string | 否 | 如果提供则渲染为 `<a>` 标签而不是 `<button>` |

## `form_row` — 多列表单行

### 用法

```jinja2
{% from "macros/forms.html" import form_row %}
{% call form_row(cols=2) %}
    {{ input(...) }}
    {{ input(...) }}
{% endcall %}
```

### 参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `cols` | int | 否 | 列数，支持 `2`/`3`/`4`，默认 2 |

## `checkbox` — 复选框

### 用法

```jinja2
{% from "macros/forms.html" import checkbox %}
{{ checkbox(
    name="agree",
    label="我已阅读并同意用户协议",
    required=true
) }}
```

### 参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | string | 是 | name 属性 |
| `label` | string | 否 | 标签文字 |
| `checked` | bool | 否 | 是否默认选中 |
| `id` | string | 否 | id，默认等于 name |
| `value` | string | 否 | value，默认 `1` |
| `disabled` | bool | 否 | 禁用 |
| `help_text` | string | 否 | 帮助提示 |

## `switch` — 开关切换

### 用法

```jinja2
{% from "macros/forms.html" import switch %}
{{ switch(
    name="enabled",
    label="启用功能",
    checked=true
) }}
```

### 参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | string | 是 | name 属性 |
| `label` | string | 否 | 标签文字 |
| `checked` | bool | 否 | 是否默认打开 |
| `id` | string | 否 | id，默认等于 name |
| `disabled` | bool | 否 | 禁用 |

## 样式规范

所有表单组件都遵循 Design Tokens 规范：
- 颜色使用 `--c-text-*` / `--c-*` 语义化 token
- 间距使用 `--s-*` token
- 字号使用 `--fs-*` token
- 圆角使用 `--r-*` token
- 支持亮/暗双主题自动适配
