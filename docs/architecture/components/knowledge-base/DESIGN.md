# 知识库能力组件设计

> ADR-003 阶段 2 工具链。同时是阶段 3 自建系统的解析内核（§4.4 子能力 1~4：解析/索引/检索/关联）。
>
> **不是自建系统**。本组件是 CLI 工具链，Markdown 是永久单一来源（ADR-003 §4.3）。
> 自建系统（服务层：DB + Web 渲染）是阶段三的事，见 EXP-20260823-008。

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 组件类 | 知识库能力 |
| 实现 | `scripts/kb_index.py` |
| ADR | ADR-010 (知识库工具链组件) |
| 状态 | 已建设 (2026-08-23) |
| 验证 | pre-commit 第 3 段（阻塞性错误拒绝提交）|

## 2. 设计约束

1. **只读，不反向写**（ADR-003 §4.3 核心原则）。唯一例外：INDEX.md 标记区（标记外手写保留）。
2. **可重建**。所有索引/视图都是 Markdown 的派生，可全量或增量 reindex。
3. **schema 容错，不卡内容**。已有内容漂移通过 --validate 的 drift 段报告，输出归一化但不报错。工具不能比内容更严格。
4. **幂等**。`--emit-index` 再跑一次结果不变。
5. **CI 友好**。`--validate` 异常退出码，被 pre-commit 集成。

## 3. 子命令

```
kb_index.py --validate              # schema 校验（pre-commit 集成）
            --stats                 # 三维分布统计（layer×stage×category）
            --query layer=L2 stage=manage tag=cron  # 三维交叉查询
            --tags                  # tag 聚合
            --xref                  # 交叉引用图 + 孤岛/断链检测
            --emit-index            # 重生 INDEX.md 派生小节（幂等）
            --json                  # 全量结构化输出
```

## 4. 数据模型

### 4.1 合法值（ADR-002）

| 字段 | 合法值 |
|---|---|
| layer | L1, L2, L3, L4 |
| stage | design, develop, manage |
| category | industry-practice, theoretical-knowledge, project-experience |

### 4.2 schema 归一化

已发现的漂移（均被工具归一，不报错）：

| 规范键 | 别名 | 发现时间 |
|---|---|---|
| `layers` | `layer` | 2026-08-23 |
| `category` | `kind` | 2026-08-23 |
| `type: experience` | `type: experience-card` | 2026-08-23 |

### 4.3 输出格式

`--json` 输出 `Doc` 对象，含：

```
path, doc_id, doc_type, title, date, status,
layers, stage, category, tags, related, body_refs, links,
is_template, errors, drift, refs (派生: related + body_refs 去重)
```

## 5. 契约

### 5.1 输入

- `docs/knowledge-base/` — Markdown 文件，需含 frontmatter
- frontmatter 缺失的导航页（INDEX、README）不查 schema

### 5.2 输出

- stdout（`--stats`、`--query`、`--tags`、`--xref`）
- `docs/knowledge-base/INDEX.md` 标记区（`--emit-index`）
- stderr（`--validate` 错误信息）

### 5.3 阻塞性错误（退出码 1）

| 错误 | 原因 |
|---|---|
| 非法 layer | 值不在 L1/L2/L3/L4 |
| 非法 stage | 值不在 design/develop/manage |
| 非法 category | 值不在 industry-practice/theoretical-knowledge/project-experience |
| 重复 ID | 同一 id 出现多次 |
| 缺 title | 非导航页缺少 title |
| YAML 解析失败 | frontmatter 格式错误 |
| frontmatter 非映射 | 不是 dict 结构 |

### 5.4 警告（退出码 0，仅提醒）

- 缺 id、缺 layers、缺 stage、缺 category、断链、失效相对链接、schema 漂移

## 6. 演进方向

| 方向 | 优先级 | 条件 |
|---|---|---|
| 全文搜索集成 | 低 | 篇数 > 200 或 `--query` 不再够用 |
| 自建系统（服务层） | 暂缓 | ADR-003 §4.2 触发条件 ≥2 个达成 |
| git 集成（diff-aware 索引） | 低 | 工具链稳定后 |

## 7. 验证

- `--validate` 已被 pre-commit 第 3 段集成
- 幂等性：`--emit-index` 重复运行输出不变
- 实测阻断：`layers: [L9]` + `stage: nonsense` 的文档被 commit 拒绝
- 首跑发现 34 个问题（修后全部通过）