# 模板变量体系

## 1. 命名规范

### 1.1 基本原则
- 使用蛇形命名法（全小写 + 下划线分隔）：`project_name`
- 语义清晰，名称即含义：`contract_start_date` 而非 `s_dt`
- 前缀区分类型：
  - `company_`：公司相关
  - `project_`：项目相关
  - `contract_`：合同相关
  - `report_`：报告相关
  - `user_`：用户相关
  - `meta_`：元数据

### 1.2 示例

| 好的命名 | 不好的命名 |
|---|---|
| `project_name` | `pname` / `pn` / `ProjectName` |
| `contract_amount` | `amt` / `contract_amt` / `$` |
| `report_week_start_date` | `start` / `wk_st` |

## 2. 变量类型

| 类型 | 说明 | 示例 |
|---|---|---|
| `string` | 文本字符串 | 项目名称、客户名称、地址 |
| `number` | 数字（整数/小数） | 合同金额、交付数量、百分比 |
| `date` | 日期 | 开始日期、结束日期、签署日期 |
| `list` | 列表（多个字符串/数字） | 交付物列表、项目成员列表 |
| `table` | 二维表格 | 进度表、统计表、清单 |
| `markdown` | Markdown 格式文本 | 项目描述、需求说明、总结 |

## 3. 变量作用域

| 作用域 | 说明 |
|---|---|
| **全局** | 整个文档所有模板都可用 |
| **文档级** | 当前文档可用 |
| **模板级** | 当前模板可用 |
| **段落级** | 当前段落可用 |
| **表格级** | 当前表格可用 |
| **单元格级** | 当前单元格可用 |

## 4. 占位格式

模板中使用双大括号占位：`{{ variable_name }}`

示例：
```markdown
# 项目周报 {{ project_name }} ({{ report_week }})

**报告周期:** {{ report_week_start_date }} ~ {{ report_week_end_date }}
```

## 5. 默认值与必填

变量 frontmatter 中标记 `required: true/false`：
- `required: true`：必须提供值，否则渲染报错
- `required: false`：可留空，使用默认值或不显示

示例 frontmatter：
```yaml
variables:
  - name: project_name
    type: string
    description: 项目名称
    required: true
  - name: project_manager
    type: string
    description: 项目经理姓名
    required: false
    default: 未指定
```

## 6. 条件渲染

支持 `{% if variable %} ... {% endif %}` 条件块：
```
{% if project_manager %}
项目经理：{{ project_manager }}
{% endif %}
```

支持 `{% for item in list %} ... {% endfor %}` 循环：
```
{% for deliverable in deliverable_list %}
- {{ deliverable }}
{% endfor %}
```

*注：条件和循环语法遵循 Jinja2，由 L2 docxtpl 实现*

