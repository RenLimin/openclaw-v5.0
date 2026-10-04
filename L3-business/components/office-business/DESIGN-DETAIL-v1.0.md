# 办公业务组件 — 详细设计

> 组件：office-business (L3)
> 版本：v1.0
> 日期：2026-09-03

## 1. 概述

办公业务组件的详细设计，包含合同、方案、报告、演示模板和角色定义。

## 2. 接口契约

### 2.1 模板接口

| 接口 | 方法 | 输入 | 输出 |
|---|---|---|---|
| render_template | POST | template_name, variables | rendered_doc |
| list_templates | GET | category | templates |
| validate_variables | POST | template_name, variables | validation |

### 2.2 角色接口

| 接口 | 方法 | 输入 | 输出 |
|---|---|---|---|
| get_role_config | GET | role_name | config |
| list_roles | GET | category | roles |

## 3. 数据模型

### 3.1 模板模型

```python
@dataclass
class Template:
    name: str
    category: TemplateCategory
    variables: List[str]
    template_path: str
    output_format: str
```

### 3.2 角色模型

```python
@dataclass
class Role:
    name: str
    category: str
    permissions: List[str]
    default_model: str
    system_prompt: str
```

## 4. 技术方案

### 4.1 模板系统

- 合同模板：销售合同、服务合同
- 方案模板：项目方案、技术方案
- 报告模板：周报、月报、季报、年报
- 演示模板：项目状态、会议纪要

### 4.2 角色系统

- 业务分析师
- 文档工程师
- 项目经理
- 技术专家

### 4.3 变量系统

模板变量定义、验证和渲染机制。

## 5. 依赖关系

- L2 Office 文档生成
- L2 知识库
- L2 模板宏

## 6. 测试方案

- 单元测试：模板渲染
- 集成测试：变量验证
- E2E 测试：完整文档生成
