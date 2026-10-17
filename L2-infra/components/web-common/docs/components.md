# components — 通用组件宏文档

## 概述

`components.html` 提供了常用 UI 组件：卡片、表格、徽章、按钮、统计卡片、进度条、模态框、Toast、时间线等。

## 卡片 `card`

### 用法

```jinja2
{% from "macros/components.html" import card %}
{% call card(title="基本信息", actions=[...]) %}
  <p>卡片内容</p>
{% endcall %}
```

### 参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `title` | string | 否 | 卡片标题 |
| `actions` | list | 否 | 操作按钮，同表单 `page_header` actions |

## 表格 `table`

### 用法

```jinja2
{% from "macros/components.html" import table_header, table_row %}
<div class="table-wrapper">
  <table class="table">
    <thead>
      <tr>
        {{ table_header("ID") }}
        {{ table_header("名称") }}
        {{ table_header("状态") }}
        {{ table_header("操作") }}
      </tr>
    </thead>
    <tbody>
      {% for item in items %}
        <tr>
          {{ table_cell(item.id) }}
          {{ table_cell(item.name) }}
          {{ table_cell(badge(item.status)) }}
          {{ table_cell(actions(...)) }}
        </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
```

### 宏

- `table_header(text)` — 表头单元格
- `table_cell(content, align="left")` — 表格内容单元格，align 支持 `left`/`right`/`center`

## 徽章 `badge`

### 用法

```jinja2
{% from "macros/components.html" import badge %}
{{ badge("已通过", variant="success") }}
```

### 参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `text` | string | 是 | 徽章文字 |
| `variant` | string | 否 | 变体：`success`/`warning`/`danger`/`error`/`info`/`primary`/`muted`，默认 `muted` |

## 按钮 `btn`

同 `forms.html` 的 `button` 宏，这里重新导出，使用方法一致。

## 统计卡片网格 `dashboard_grid` + `stat_card`

### 用法

```jinja2
{% from "macros/components.html" import dashboard_grid, stat_card %}
{% call dashboard_grid() %}
  {{ stat_card(label="总用户数", value="1,234", variant="primary") }}
  {{ stat_card(label="今日新增", value="+56", variant="success") }}
  {{ stat_card(label="待处理", value="12", variant="warning") }}
  {{ stat_card(label="错误数", value="3", variant="danger") }}
{% endcall %}
```

### 参数

- `stat_card(label, value, variant="")` — `variant` 支持 `primary`/`success`/`warning`/`danger`/`info`

## 进度条 `progress_bar`

### 用法

```jinja2
{% from "macros/components.html" import progress_bar %}
{{ progress_bar(percent=75, label="完成进度", variant="primary") }}
```

### 参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `percent` | float | 是 | 完成百分比 0-100 |
| `label` | string | 否 | 标签文字 |
| `variant` | string | 否 | 颜色变体：`primary`/`success`/`warning`/`danger`，默认 `primary` |

## 信息网格 `info_grid` 详情页展示

### 用法

```jinja2
{% from "macros/components.html" import info_grid, info_item %}
{% call info_grid() %}
  {{ info_item("创建时间", "2026-10-01") }}
  {{ info_item("状态", badge("已发布")) }}
  {{ info_item("负责人", "张三") }}
{% endcall %}
```

## 模态框 `modal`

### 用法

```jinja2
{% from "macros/components.html" import modal %}
{% call modal(title="确认删除") %}
  <p>确定要删除这条记录吗？</p>
  <div class="modal-actions">
    {{ button("取消", onclick="closeModal()") }}
    {{ button("确认删除", variant="danger", onclick="doDelete()") }}
  </div>
{% endcall %}
```

### 参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `title` | string | 否 | 模态框标题 |

## 时间线 `timeline`

### 用法

```jinja2
{% from "macros/components.html" import timeline, timeline_item %}
{% call timeline() %}
  {{ timeline_item(
      title="创建项目",
      meta="2026-10-01 10:00",
      comment="由 Rex 创建",
      status="completed"
  ) }}
  {{ timeline_item(
      title="审核通过",
      meta="2026-10-02 14:30",
      comment="审批通过，准备发布",
      status="active"
  ) }}
{% endcall %}
```

### 参数 - `timeline_item`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `title` | string | 是 | 事件标题 |
| `meta` | string | 否 | 元信息（时间/操作人） |
| `comment` | string | 否 | 评论/说明 |
| `status` | string | 否 | 状态：`completed`/`active`/`rejected`，影响点颜色 |

## 所有组件特性

- ✅ 全部使用 Design Tokens
- ✅ 支持亮/暗双主题自动适配
- ✅ 响应式布局，手机/平板都能正常显示
- ✅ 语义化 HTML 结构
- ✅ 一致的间距、颜色、字号规范
