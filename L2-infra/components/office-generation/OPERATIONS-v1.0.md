# office-generation — 操作手册 (OPERATIONS)

> 版本: v1.0 · 日期: 2026-09-28

## 安装与启动

### 环境依赖

- python3
- python-docx
- openpyxl
- xlsxwriter
- pandas
- python-pptx

### 启动命令

```bash
python3 office_generate.py --help
```

### 健康检查

```bash
python3 -c "from office_generate import *; print('OK')"
```

## 操作指南

### 场景一：生成 Word

```bash
python3 L2-infra/components/office-generation/office_generate.py word --data data.json
```

### 场景二：生成 Excel

```bash
python3 L2-infra/components/office-generation/office_generate.py excel --data data.json
```

### 场景三：生成 PPT

```bash
python3 L2-infra/components/office-generation/office_generate.py ppt --data data.json
```

## 配置说明

- Word: python-docx (主力) + docxtpl (模板)
- Excel: openpyxl + xlsxwriter + pandas
- PPT: pptxgenjs + python-pptx

## 故障排查

### 库不可用

- **症状**: 导入错误
- **原因**: 库未安装
- **解决**: pip install 对应库

### 格式错误

- **症状**: 输出文件格式损坏
- **原因**: 数据格式不兼容
- **解决**: 检查输入数据结构
