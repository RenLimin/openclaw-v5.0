# web-common — 操作手册 (OPERATIONS)

> 版本: v1.0 · 日期: 2026-09-28

## 安装与启动

### 环境依赖

- python3（示例应用）

### 启动命令

```bash
# 示例应用
cd examples && python3 app.py
```

### 健康检查

```bash
# 验证静态资源
ls L2-infra/components/web-common/static/
```

## 操作指南

### 场景一：使用模板宏

```python
from macros import render
output = render("template.html", {"key": "value"})
```

### 场景二：引用静态资源

```html
<link rel="stylesheet" href="static/css/style.css">
```

### 场景三：运行示例

```bash
cd L2-infra/components/web-common/examples
python3 app.py
```

## 配置说明

- 宏: Jinja2 语法
- 静态资源: CSS + JS

## 故障排查

### 宏渲染失败

- **症状**: 模板报错
- **原因**: 变量未定义
- **解决**: 检查传入的变量
