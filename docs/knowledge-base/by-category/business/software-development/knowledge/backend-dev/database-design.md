---
title: 数据库设计
description: 关系型与 NoSQL 数据库设计原则、索引策略与迁移管理
source: Martin Fowler; MongoDB Docs; PostgreSQL Official Docs
version: 1.0
category: business
dimension: software-development
sub_area: database
type: knowledge
tags: [database, postgresql, mysql, mongodb, indexing, migration]
xref: [software-development/knowledge/backend-dev/api-design.md]
last_reviewed: 2026-08-27
---

# 数据库设计

## 关系型 vs NoSQL

| 维度 | 关系型（PostgreSQL/MySQL） | NoSQL（MongoDB/Redis） |
|------|---------------------------|------------------------|
| 数据模型 | 表 + 行 + 列，严格 schema | 文档/键值/列族，灵活 schema |
| 事务 | ACID 完整支持 | 有限（MongoDB 4.0+ 多文档事务） |
| 查询 | SQL，复杂关联查询 | API 查询，聚合管道 |
| 扩展 | 垂直扩展为主 | 水平扩展友好 |
| 适用 | 强一致性、复杂关系 | 高吞吐、灵活 schema、缓存 |

## 关系型设计

### 范式与反范式

| 范式 | 目标 | 代价 |
|------|------|------|
| 1NF | 原子性，每列不可再拆 | — |
| 2NF | 消除部分依赖 | — |
| 3NF | 消除传递依赖 | 查询需要更多 JOIN |

**实践**：设计到 3NF，性能热点有意识反范式（冗余字段、宽表）。

### 索引策略

| 索引类型 | 适用场景 |
|----------|----------|
| B-Tree（默认） | 等值查询、范围查询 |
| Hash | 仅等值查询 |
| GIN | JSONB、全文搜索、数组 |
| GiST | 地理空间、范围类型 |
| 复合索引 | 多列联合查询（注意列顺序） |

**最左前缀原则**：复合索引 `(a, b, c)` 可支持 `a`、`(a,b)`、`(a,b,c)` 查询。

### 索引设计原则

1. **WHERE / JOIN / ORDER BY** 中的列建索引
2. **高基数**（唯一值多）的列优先
3. **小索引**优先（整数 < 字符串 < 文本）
4. 避免过多索引（每次写入更新所有索引）
5. `EXPLAIN ANALYZE` 验证执行计划

## 迁移管理

| 策略 | 工具 | 说明 |
|------|------|------|
| 版本化迁移 | Flyway / Prisma Migrate | 每个变更一个迁移文件，有序执行 |
| 扩展/收缩 | 蓝绿迁移 | 先加字段→双写→切读→删旧字段 |
| 零停机 | 分阶段部署 | 兼容旧代码的 schema 变更 |

### 安全变更清单

- [ ] 新增字段带默认值（避免 NOT NULL 无默认值导致写入失败）
- [ ] 大表变更使用 `pt-online-schema-change` 或 `gh-ost`
- [ ] 索引在低峰期创建（`CONCURRENTLY`）
- [ ] 删除字段前确认无代码引用

## Redis 使用模式

| 模式 | 用途 | 注意事项 |
|------|------|----------|
| 缓存 | 热点数据加速 | 缓存失效/穿透/雪崩 |
| 会话存储 | 分布式会话 | TTL 管理 |
| 排行榜 | Sorted Set | 内存占用 |
| 限流 | 滑动窗口计数 | 原子操作（Lua） |
| 消息队列 | List / Stream | 可靠性 vs 延迟权衡 |
| 分布式锁 | SET NX EX | Redlock 算法 |
