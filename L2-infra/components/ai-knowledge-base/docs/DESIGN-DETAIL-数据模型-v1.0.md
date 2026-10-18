# AI 知识库 - 数据模型详细设计 v1.0

> L2 Infrastructure Component · ai-knowledge-base
> 版本：v1.0 · 状态：Draft
> 最后更新：2026-10-18

---

## 1. 设计原则

### 1.1 数据模型原则

1. **分层组织**：domain → collection → entity → doc → chunk 五级结构，每级都有独立 ID 和外键关联
2. **显式关联**：所有关联关系通过外键或关系表存储，不存在隐式关联
3. **可扩展属性**：结构化属性用 `entity_attr` 键值对存储，支持不修改表结构扩展字段
4. **全链路审计**：所有变更记录 `created_at` 和 `updated_at`，关键操作有独立审计日志表
5. **向后兼容**：新增字段和表通过 migration 升级，不破坏已有数据
6. **状态驱动**：所有核心实体都有 `status` 字段，支持生命周期管理

---

## 2. ER 图概览

```
domain (1) ──→ (N) collection (1) ──→ (N) entity
                                      │
                                      ├──→ (N) entity_attr (属性键值对)
                                      ├──→ (N) doc_asset (文档资产)
                                      │         │
                                      │         └──→ (N) doc_chunk (文档切片 + 向量)
                                      │
                                      └──→ (N) kb_relation (知识图谱关系，多对多)

kb_feedback (用户反馈) ──→ entity / doc_asset / doc_chunk (多对一，可选关联)

kb_audit_log (审计日志) ──→ 全表操作记录

kb_template (知识库模板) ──→ domain (模板 → 实例 一对多)
```

---

## 3. 表结构详细设计

### 3.1 domain（知识库域）

顶级隔离单元，一个 domain 就是一个独立的知识库实例。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 域ID |
| name | TEXT | NOT NULL | 域名称（如"Bangcle产品知识库"） |
| code | TEXT | UNIQUE NOT NULL | 域编码（唯一标识，如"bangcle-product"） |
| description | TEXT | | 域描述 |
| template_id | INTEGER | REFERENCES kb_template(id) | 关联的模板ID（可选） |
| config | TEXT | | JSON 格式的实例配置 |
| status | TEXT | | 状态：active / archived / deleted |
| created_at | DATETIME | | 创建时间 |
| updated_at | DATETIME | | 更新时间 |

### 3.2 collection（知识分类）

域内的树形分类结构，支持多级嵌套。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 分类ID |
| domain_id | INTEGER | NOT NULL REFERENCES domain(id) | 所属域ID |
| name | TEXT | NOT NULL | 分类名称 |
| parent_id | INTEGER | REFERENCES collection(id) | 父分类ID（NULL为顶级） |
| sort_order | INTEGER | DEFAULT 0 | 排序权重 |
| metadata | TEXT | | JSON 扩展属性 |
| created_at | DATETIME | | 创建时间 |
| updated_at | DATETIME | | 更新时间 |

**索引**：`(domain_id, parent_id, name)` 唯一索引

### 3.3 entity（知识实体）

知识的核心载体，一个实体代表一个业务对象（产品、合同、文档、概念等）。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 实体ID |
| domain_id | INTEGER | NOT NULL REFERENCES domain(id) | 所属域ID |
| collection_id | INTEGER | REFERENCES collection(id) | 所属分类ID |
| entity_type | TEXT | NOT NULL | 实体类型：product / solution / document / concept 等 |
| family | TEXT | | 实体族（用于同族回退） |
| name | TEXT | NOT NULL | 实体名称 |
| aliases | TEXT | | 别名（JSON数组字符串，FTS索引） |
| code | TEXT | UNIQUE | 业务编码（如产品SKU） |
| version_latest | TEXT | | 最新版本号 |
| status | TEXT | | 生命周期状态：<br>draft / review / published / expired / archived |
| summary | TEXT | | 实体摘要 |
| tags | TEXT | | 标签（JSON数组） |
| metadata | TEXT | | JSON 扩展属性 |
| quality_score | REAL | | 质量评分（0-10，基于反馈计算） |
| view_count | INTEGER | DEFAULT 0 | 访问次数 |
| created_at | DATETIME | | 创建时间 |
| updated_at | DATETIME | | 更新时间 |
| published_at | DATETIME | | 发布时间 |
| expired_at | DATETIME | | 过期时间（自动过期用） |

**索引**：
- `(domain_id, status)` — 按域和状态查询
- `(domain_id, entity_type)` — 按类型筛选
- `(collection_id)` — 按分类查询
- FTS5 虚拟表 `entity_fts(name, aliases)` — 全文检索

### 3.4 entity_attr（实体属性）

实体的结构化属性键值对存储，支持不修改表结构扩展任意字段。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 属性ID |
| entity_id | INTEGER | NOT NULL REFERENCES entity(id) | 实体ID |
| attr_key | TEXT | NOT NULL | 属性名 |
| attr_value | TEXT | | 属性值 |
| attr_type | TEXT | | 类型：text / number / boolean / date / json |
| is_searchable | INTEGER | DEFAULT 1 | 是否可被检索（是否加入FTS） |
| sort_order | INTEGER | DEFAULT 0 | 显示排序 |
| created_at | DATETIME | | 创建时间 |
| updated_at | DATETIME | | 更新时间 |

**索引**：`(entity_id, attr_key)` 唯一索引

### 3.5 doc_asset（文档资产）

关联到实体的原始文档资产。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 文档ID |
| entity_id | INTEGER | NOT NULL REFERENCES entity(id) | 所属实体ID |
| doc_type | TEXT | NOT NULL | 文档类型：spec / whitepaper / manual / price / etc. |
| original_path | TEXT | NOT NULL | 原始文件路径 |
| relative_path | TEXT | | 相对知识库根的路径 |
| file_name | TEXT | NOT NULL | 文件名 |
| file_size | INTEGER | | 文件大小（字节） |
| version | TEXT | | 文档版本 |
| format | TEXT | NOT NULL | 文件格式：pdf / docx / xlsx / pptx / md / html / txt / etc. |
| md5 | TEXT | | 文件MD5（用于去重） |
| content_hash | TEXT | | 内容指纹（用于增量更新检测） |
| parse_status | TEXT | | 解析状态：success / partial / failed / pending |
| parse_error | TEXT | | 解析错误信息 |
| permissions | TEXT | | 权限配置JSON（ABAC） |
| language | TEXT | | 文档语言：zh / en / etc. |
| word_count | INTEGER | | 文档字数 |
| page_count | INTEGER | | 文档页数（PDF/PPT/Word） |
| created_at | DATETIME | | 创建时间 |
| updated_at | DATETIME | | 更新时间 |
| parsed_at | DATETIME | | 解析完成时间 |

**索引**：
- `(entity_id, doc_type)` — 按实体和类型查询
- `(md5)` — 去重查询
- `(parse_status)` — 按解析状态筛选

### 3.6 doc_chunk（文档切片）

文档切分后的最小知识单元，存储文本和向量。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 切片ID |
| doc_id | INTEGER | NOT NULL REFERENCES doc_asset(id) | 所属文档ID |
| chunk_index | INTEGER | NOT NULL | 切片在文档中的序号 |
| title | TEXT | | 切片标题（章节标题） |
| section_path | TEXT | | 章节路径，如 "1.2.3 功能介绍" |
| text | TEXT | NOT NULL | 切片文本内容 |
| token_count | INTEGER | | token 数量 |
| embedding | BLOB | | 向量嵌入（二进制存储） |
| embedding_model | TEXT | | 使用的 embedding 模型标识 |
| permissions | TEXT | | 权限配置（覆盖文档级） |
| created_at | DATETIME | | 创建时间 |
| updated_at | DATETIME | | 更新时间 |

**索引**：
- `(doc_id, chunk_index)` — 按文档和序号查询
- FTS5 虚拟表 `chunk_fts(text)` — 全文检索

### 3.7 kb_relation（知识图谱关系）

任意两个节点之间的关系，构建知识图谱。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 关系ID |
| subject_type | TEXT | NOT NULL | 主语类型：entity / doc / chunk / collection |
| subject_id | INTEGER | NOT NULL | 主语ID |
| relation_type | TEXT | NOT NULL | 关系类型：<br>belongs_to / has_part / depends_on / <br>references / similar_to / replaces / etc. |
| object_type | TEXT | NOT NULL | 宾语类型 |
| object_id | INTEGER | NOT NULL | 宾语ID |
| weight | REAL | DEFAULT 1.0 | 关系权重（0-1） |
| direction | TEXT | DEFAULT undirected | 方向：directed / undirected / reverse |
| metadata | TEXT | | JSON 扩展属性 |
| permissions | TEXT | | 权限配置 |
| source | TEXT | | 关系来源：auto_extract / manual / import |
| confidence | REAL | | 置信度（自动抽取的关系有置信度） |
| created_at | DATETIME | | 创建时间 |

**索引**：
- `(subject_type, subject_id, relation_type)` — 正向查询
- `(object_type, object_id, relation_type)` — 反向查询

### 3.8 kb_feedback（用户反馈）

用户对查询/答案的有效性反馈。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 反馈ID |
| domain_id | INTEGER | NOT NULL REFERENCES domain(id) | 所属域ID |
| query_text | TEXT | NOT NULL | 用户查询文本 |
| answer_text | TEXT | | 答案文本 |
| feedback_type | TEXT | NOT NULL | 反馈类型：<br>useful / not_useful / incorrect / outdated |
| feedback_comment | TEXT | | 用户自由文本反馈 |
| entity_id | INTEGER | REFERENCES entity(id) | 关联实体ID（可选） |
| doc_id | INTEGER | REFERENCES doc_asset(id) | 关联文档ID（可选） |
| chunk_id | INTEGER | REFERENCES doc_chunk(id) | 关联切片ID（可选） |
| user_id | TEXT | | 反馈用户ID |
| user_role | TEXT | | 反馈用户角色 |
| session_id | TEXT | | 会话ID（用于关联上下文） |
| metadata | TEXT | | JSON 扩展属性 |
| resolved | INTEGER | DEFAULT 0 | 是否已处理 |
| resolution_note | TEXT | | 处理备注 |
| resolved_at | DATETIME | | 处理时间 |
| resolved_by | TEXT | | 处理人 |
| created_at | DATETIME | NOT NULL | 创建时间 |

**索引**：
- `(domain_id, feedback_type)` — 按域和类型统计
- `(entity_id)` — 按实体统计
- `(doc_id)` — 按文档统计
- `(resolved, created_at)` — 未处理反馈列表

### 3.9 kb_audit_log（审计日志）

所有操作的审计记录。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 日志ID |
| domain_id | INTEGER | REFERENCES domain(id) | 所属域ID |
| action | TEXT | NOT NULL | 操作类型：<br>query / insert / update / delete / import / export / config_change |
| target_type | TEXT | | 操作对象类型：entity / doc / chunk / relation / config |
| target_id | INTEGER | | 操作对象ID |
| user_id | TEXT | | 操作用户ID |
| user_ip | TEXT | | 操作IP |
| detail | TEXT | | 操作详情JSON |
| result | TEXT | | 操作结果：success / failed / partial |
| error_msg | TEXT | | 错误信息 |
| duration_ms | INTEGER | | 耗时（毫秒） |
| created_at | DATETIME | NOT NULL | 操作时间 |

**索引**：
- `(domain_id, action, created_at)` — 按域+操作+时间查询
- `(target_type, target_id)` — 按对象查询变更历史
- `(user_id, created_at)` — 按用户查询操作历史

### 3.10 kb_template（知识库模板）

知识库模板定义，用于快速实例化。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 模板ID |
| name | TEXT | NOT NULL | 模板名称 |
| code | TEXT | UNIQUE NOT NULL | 模板编码 |
| description | TEXT | | 模板描述 |
| version | TEXT | | 模板版本 |
| entity_types | TEXT | | JSON：实体类型定义 |
| categories | TEXT | | JSON：分类规则定义 |
| search_config | TEXT | | JSON：检索配置 |
| permission_template | TEXT | | JSON：权限模板 |
| import_rules | TEXT | | JSON：导入规则 |
| metadata | TEXT | | JSON 扩展属性 |
| is_builtin | INTEGER | DEFAULT 0 | 是否内置模板 |
| status | TEXT | | 状态：draft / active / deprecated |
| created_at | DATETIME | | 创建时间 |
| updated_at | DATETIME | | 更新时间 |

### 3.11 doc_version（文档版本历史）

文档的版本历史记录。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 版本ID |
| doc_id | INTEGER | NOT NULL REFERENCES doc_asset(id) | 文档ID |
| version | TEXT | NOT NULL | 版本号 |
| change_log | TEXT | | 变更说明 |
| content_hash | TEXT | | 版本内容指纹 |
| file_path | TEXT | | 该版本文件存储路径 |
| created_by | TEXT | | 创建人 |
| is_current | INTEGER | DEFAULT 0 | 是否当前版本 |
| created_at | DATETIME | | 版本创建时间 |

**索引**：`(doc_id, version)` 唯一索引

---

## 4. 数据库迁移机制

### 4.1 版本化迁移

- 每个数据库版本对应一个 migration 脚本
- 启动时检查数据库版本，自动执行未执行的 migration
- migration 顺序执行，支持失败回滚（对支持DDL事务的数据库）

### 4.2 Migration 编号规则

```
V001__initial_schema.sql       — 初始建表
V002__add_feedback_table.sql   — 新增反馈表
V003__add_quality_score.sql    — 实体质量分数字段
...
```

### 4.3 版本记录表

```sql
CREATE TABLE IF NOT EXISTS kb_schema_version (
    version INTEGER PRIMARY KEY,
    name TEXT,
    applied_at DATETIME,
    checksum TEXT
);
```

---

## 5. 不同存储后端适配

### 5.1 SQLite → PostgreSQL 迁移

| 特性 | SQLite | PostgreSQL |
|---|---|---|
| 自增ID | AUTOINCREMENT | SERIAL / BIGSERIAL |
| JSON 字段 | TEXT 存储 | JSONB 原生类型 |
| FTS | FTS5 内置 | tsvector + GIN索引 |
| 向量 | BLOB + NumPy 计算 | pgvector 扩展 / 独立向量库 |
| 并发 | 单写多读 | MVCC 高并发 |
| 全文索引 | FTS5 虚拟表 | GIN索引 + to_tsvector |

### 5.2 数据访问层抽象

通过统一的 Repository 接口隔离存储差异：

```python
class KBRepository(ABC):
    # Entity operations
    @abstractmethod
    def create_entity(self, entity: Entity) -> int: ...
    
    @abstractmethod
    def get_entity(self, entity_id: int) -> Optional[Entity]: ...
    
    @abstractmethod
    def search_entities(self, query: SearchQuery) -> List[Entity]: ...
    
    # Chunk operations
    @abstractmethod
    def hybrid_search_chunks(self, query: str, top_k: int) -> List[ChunkResult]: ...
    
    # ... 其他操作
```

**实现类**：
- `SQLiteKBRepository` — 默认实现，零依赖
- `PostgresKBRepository` — 生产级实现，高性能

---

## 6. 索引设计原则

### 6.1 索引策略

1. **主键索引**：所有表都有自增主键，默认B-Tree索引
2. **外键索引**：所有外键字段都建索引，加速关联查询
3. **全文索引**：实体名称/别名、切片文本使用 FTS5 全文索引
4. **向量索引**：切片 embedding 使用向量索引（NumPy暴力计算 / HNSW / IVF）
5. **组合索引**：针对高频查询场景建立组合索引，遵循最左前缀原则

### 6.2 索引维护

- 增量更新：文档导入时实时更新索引
- 定期优化：FTS索引定期 `optimize`，向量索引定期重建
- 重建工具：提供完整重建索引的命令，应对索引损坏

---

## 7. 数据一致性保障

### 7.1 事务边界

- 文档导入：单个文档的解析+切片+入库在一个事务中，失败全部回滚
- 批量导入：每个文档独立事务，单个失败不影响其他
- 状态变更：实体状态变更 + 版本记录 + 审计日志在同一事务

### 7.2 数据完整性

- 外键约束：所有关联关系都有外键约束（SQLite需开启 `PRAGMA foreign_keys = ON`）
- 唯一约束：业务编码、文件名+版本等有唯一约束
- 非空约束：关键字段 NOT NULL 约束

### 7.3 备份与恢复

- 全量备份：定时 `VACUUM` + 备份整个数据库文件
- 增量备份：WAL 模式下的增量备份
- 验证机制：备份后自动校验完整性

