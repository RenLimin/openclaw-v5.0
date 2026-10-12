---
title: ONES 研发管理系统总览
description: 邦清 ONES 系统核心能力、三大项目视图（签约/POC/异常）、数据导出方式与 API 接入指南
source: ONES v3.14/v3.15 私有部署 + 实际使用经验
version: 1.0
category: business
dimension: implementation
sub_area: ones
type: knowledge
tags: [ones, project-management, delivery, poc, 签约项目, 异常处置]
last_reviewed: 2026-10-10
---

# ONES 研发管理系统总览

## 系统信息

| 项 | 值 |
|---|---|
| 部署方式 | 私有部署 v3.15.1 |
| 域名 | `ones.bangcle.com` |
| 团队 UUID | `RZxvwUZ8` |
| Rex 的 user UUID | `REccSDPA` |
| 产品手册 | https://docs.ones.cn/wiki/#/team/6mRWUuNv/space/66ANjLmW/page/2Zbe2wjw |
| API 文档 | https://docs.ones.cn/project/open-api-doc/ |
| 本地参考文档 | `~/Downloads/ones/`（数据字典、私有部署手册、SQL说明） |

## 三大核心项目视图（2026 周报系列）

| 视图名称 | filter ID | 用途 | 数据量级 |
|---|---|---|---|
| **2026周报-签约项目统计** | `5wY9X4m8` | 已签约交付项目全量跟踪 | ~16,600 行 / 40 列 |
| **2026周报-POC&提前实施统计** | `KxnjPRY7` | POC、售前、提前实施项目 | ~5,030 行 / 40 列 |
| **2026-签约项目异常处置** | `NWPaa48w` | 异常/风险项目跟踪处置 | ~362 行 / 40 列 |

## 数据获取方式

### 方式一：浏览器自动化导出 CSV（最可靠）
- Skill：`ones-browser-export`
- 原理：`osascript` 控制 Chrome，点击左侧筛选器 → 更多操作 → 导出工作项
- 优点：导出的就是 UI 看到的完整数据，无需猜字段
- 缺点：依赖 Chrome 已登录、有页面加载等待、索引可能变化
- 适用场景：周报/月报全量数据导出

### 方式二：GraphQL API（结构化查询）
- 端点：`POST https://ones.bangcle.com/project/api/project/team/RZxvwUZ8/items/graphql`
- 鉴权：`Ones-Auth-Token` + `Ones-User-Id`
- 参考脚本：`~/Downloads/ones/ones-graphQL.sh`
- 可查询：users / projects / tasks / issueTypes / fields / __schema
- 适用场景：增量查询、单项目详情、字段元数据探索

### 方式三：知识库 SQL 查询
- 参考：`~/Downloads/ones/SQL 使用说明 _ 知识库管理.html`
- 适用场景：知识库内容批量操作

## 核心实体

| 实体 | GraphQL 名 | 关键字段 |
|---|---|---|
| 用户 | `users` | uuid, name, email |
| 项目 | `projects` | uuid, name |
| 工作项 | `tasks` | uuid, summary, assign, status, 自定义字段 |
| 工作项类型 | `issueTypes` | uuid, name, key |
| 字段定义 | `fields` | uuid, name, type, required, options |

## 相关资产

- Skill：`L4-proprietary/skills/ones-browser-export/SKILL.md`
- 导出脚本：`scripts/l4/delivery_center/generators/generate_report_202606.py`
- 月报生成器：`scripts/l4/delivery_center/generators/delivery_report.py`
- 数据目录：`~/.openclaw/data/ones_exports/`

## 使用规范

1. **优先走浏览器导出**做全量数据拉取，API 做增量/查询
2. 不要在代码里硬编码筛选器索引，用**文本匹配**定位链接
3. 导出的 CSV 存 `~/.openclaw/data/ones_exports/`，按日期归档
4. 涉及密码/token 存 SQLite 凭据库，不要写进 markdown
