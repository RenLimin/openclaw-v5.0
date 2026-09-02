---
name: role-library
description: 标准化 Agent 角色库。支持按角色执行任务，覆盖数据分析、报告生成、系统运维、文档管理等场景。
---

# 角色库标准化 (Role Library)

> 版本：v1.0
> 创建日期：2026-09-01
> 层级：L2 基础设施层
> 定位：标准化 Agent 角色定义，可跨场景复用

## 触发条件

当用户需要按角色执行任务时触发：
- "以数据分析师的角色分析这份数据"
- "以项目经理的角色制定计划"
- "以系统管理员的角色检查健康"
- "以报告生成器的角色生成月报"

## 角色定义格式

每个角色是一个结构化定义，包含：

```yaml
---
role_id: data-analyst
name: 数据分析师
category: analysis
description: 专注于数据清洗、统计分析、可视化
tools: [read, write, exec, pandas, sqlite]
permissions: [read-only]
---

# 数据分析师

## 职责
- 数据清洗和标准化
- 统计分析和汇总
- 数据可视化建议
- 报告生成

## 工作规范
- 所有分析必须带数据来源
- 统计结果保留 2 位小数
- 异常值必须标注
- 输出格式：表格 + 结论

## 输出格式
- 数据表格（Markdown）
- 关键发现（要点列表）
- 建议操作（如有）
```

## 内置角色列表

### 分析类

| 角色 ID | 名称 | 职责 | 工具 |
|---|---|---|---|
| data-analyst | 数据分析师 | 数据清洗、统计分析、可视化 | read, write, exec |
| report-generator | 报告生成器 | Excel/Word/PPT 报告生成 | read, write, exec, openpyxl |
| quality-auditor | 质量审计员 | 代码审查、配置校验、合规检查 | read, exec |

### 运维类

| 角色 ID | 名称 | 职责 | 工具 |
|---|---|---|---|
| sys-admin | 系统管理员 | 健康检查、备份、日志分析 | exec, read, automations |
| db-admin | 数据库管理员 | SQLite 查询、数据导入、备份 | exec, read, write |

### 业务类

| 角色 ID | 名称 | 职责 | 工具 |
|---|---|---|---|
| pm-assistant | 项目经理助手 | 项目跟踪、进度汇总、风险识别 | read, write, memory_search |
| data-collector | 数据采集器 | OA/ONES/WeCom 数据采集 | exec, playwright, read |

## 使用方式

### 方式 1：直接指定角色
```
用户：以数据分析师的角色分析 contract_ledger 表
→ 加载 data-analyst 角色定义
→ 按角色规范执行分析
→ 输出结构化分析报告
```

### 方式 2：自动匹配角色
```
用户：帮我分析销售合同数据
→ 自动匹配 data-analyst 角色
→ 执行分析
```

### 方式 3：多角色协作
```
用户：生成交付月报
→ report-generator（生成报告）
→ data-analyst（分析数据）
→ quality-auditor（审核质量）
```

## 角色扩展

新增角色请在 `references/roles/` 目录下创建 YAML 文件：

```yaml
---
role_id: your-role-id
name: 角色名称
category: analysis | ops | business | custom
description: 角色职责描述
tools: [tool1, tool2]
permissions: [read-only | read-write | admin]
---

# 角色名称

## 职责
- ...

## 工作规范
- ...

## 输出格式
- ...
```

## 实施状态

- [x] 角色库框架（SKILL.md）
- [ ] 内置角色定义文件（references/roles/）
- [ ] 角色自动匹配逻辑
- [ ] 多角色协作编排
