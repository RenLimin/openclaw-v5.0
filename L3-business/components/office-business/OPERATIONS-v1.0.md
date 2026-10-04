# office-business — 操作手册 (OPERATIONS)

> 版本: v1.0 · 日期: 2026-09-28

## 1. 安装与启动

### 1.1 环境依赖

纯 Markdown，无运行时依赖。

### 1.2 安装步骤

```bash
cd L3-business/components/office-business
# 无需安装
```

### 1.3 启动命令

无启动命令，纯模板引用。

### 1.4 健康检查

```bash
# 验证模板完整
ls templates/contract/ templates/report/ templates/proposal/ templates/presentation/
# 验证角色完整
ls roles/business-analyst/ roles/document-engineer/
# 验证索引
cat templates/index.json | python3 -m json.tool
```

## 2. 操作指南

### 2.1 场景一：生成合同

1. 选择 `templates/contract/sales-contract.md`
2. 复制模板内容
3. 替换 `{{变量}}` 占位符
4. 输出最终合同

### 2.2 场景二：生成报告

1. 选择 `templates/report/monthly-report.md`
2. 复制并填充内容
3. 输出报告

### 2.3 场景三：切换 Agent 角色

1. 读取 `roles/business-analyst/IDENTITY.md`
2. 读取 `roles/business-analyst/SOUL.md`
3. 读取 `roles/business-analyst/AGENTS.md`
4. 按角色定义切换人设

## 3. 配置说明

无外部配置。

## 4. 故障排查

### 4.1 模板缺失

- **症状**: 找不到模板文件
- **原因**: 目录结构不正确
- **解决**: 检查 `index.json` 确认模板列表

### 4.2 变量未定义

- **症状**: 变量无法替换
- **原因**: 变量名拼写错误
- **解决**: 参考 `knowledge/variable-system.md`

## 5. FAQ

**Q1: 如何添加新模板？**
A: 在 `templates/` 下创建新文件，更新 `index.json`

**Q2: 如何添加新角色？**
A: 在 `roles/` 下创建新目录，添加三件套

**Q3: 变量系统如何使用？**
A: 模板中使用 `{{变量名}}` 占位符，替换时填充实际值

## 6. 附录

### 6.1 模板清单

- 合同: sales-contract.md / service-contract.md
- 报告: weekly/monthly/quarterly/annual-report.md
- 方案: project-proposal.md / technical-proposal.md
- 演示: project-status.md / meeting-minutes.md

### 6.2 角色清单

- 业务分析师: business-analyst/
- 文档工程师: document-engineer/
