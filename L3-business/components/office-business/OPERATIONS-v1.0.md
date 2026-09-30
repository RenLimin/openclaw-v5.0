# OPERATIONS-v1.0 — L3 企业办公模板库 (office-business)

> 层级：L3 业务通用能力
> 版本：v1.0
> 创建：2026-09-29

## 1. 前置依赖

| 依赖 | 说明 | 安装/获取 |
|---|---|---|
| L2 office-generation | 模板生成能力 | 已内置 |
| Microsoft Office / LibreOffice | 打开编辑模板 | 官方获取 |

## 2. 使用方式

### 2.1 获取模板

```bash
# 查看分类
ls L3-business/components/office-business/templates/
```

### 2.2 基于模板创建

1. 复制对应模板到工作目录
2. 重命名为项目/业务需要的文件名
3. 打开编辑，替换占位内容（`[占位名称]`格式）

### 2.3 占位符说明

| 占位符 | 替换内容 |
|---|---|
| `[项目名称]` | 当前项目名称 |
| `[版本]` | 当前文档版本 |
| `[日期]` | 创建日期 |
| `[作者]` | 文档作者 |
| `[公司LOGO]` | 企业 Logo 占位 |

## 3. 目录结构

```
office-business/
├── PRD-v1.0.md          # 产品需求
├── OPERATIONS-v1.0.md  # 本手册
├── DESIGN.md            # 设计说明
└── templates/           # 模板文件
    ├── business/        # 业务文档
    │   ├── contract.docx
    │   ├── financial_report.xlsx
    │   └── ...
    └── common/         # 通用办公
        ├── meeting_minutes.docx
        ├── weekly_report.docx
        └── ...
```

## 4. 故障排查

| 问题 | 原因 | 解决 |
|---|---|---|
| 模板打不开 | 版本不兼容 | 使用对应 Office 版本保存 |
| 样式错乱 | 不同软件渲染差异 | 使用 Microsoft Office 编辑 |

## 5. 版本更新记录

| 版本 | 日期 | 更新内容 |
|---|---|---|
| v1.0 | 2026-09-29 | 初始版本，需求定义 |
---
