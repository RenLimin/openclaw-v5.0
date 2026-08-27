---
title: 数据迁移
description: ETL 流程、数据校验、回滚计划与零停机迁移
source: Data Migration Best Practices; AWS DMS Docs
version: 1.0
category: business
dimension: implementation
sub_area: data-migration
type: knowledge
tags: [data-migration, etl, validation, rollback, zero-downtime]
last_reviewed: 2026-08-27
---

# 数据迁移

## ETL 流程

| 阶段 | 活动 |
|------|------|
| Extract | 从源系统抽取数据 |
| Transform | 清洗、转换、映射 |
| Load | 写入目标系统 |
| Validate | 数据完整性校验 |

## 迁移策略

| 策略 | 说明 | 适用 |
|------|------|------|
| Big Bang | 一次性全量迁移 | 小数据量、可停机 |
| 增量迁移 | 分批迁移 | 大数据量 |
| 双写 | 新旧系统同时写入 | 零停机 |
| CDC | 变更数据捕获 | 实时同步 |

## 数据校验

| 维度 | 方法 |
|------|------|
| 完整性 | 记录数对比 |
| 准确性 | 抽样逐条对比 |
| 一致性 | 关联关系校验 |
| 唯一性 | 主键/唯一索引检查 |

## 回滚计划

1. **备份**：迁移前全量备份
2. **检查点**：每批次迁移后验证
3. **回滚脚本**：预先生成回退 SQL
4. **验证窗口**：回滚后数据完整性确认

## 零停机迁移

```
旧系统（读写）→ 双写阶段 → 新系统（读验证）→ 新系统（读写）→ 旧系统下线
```
