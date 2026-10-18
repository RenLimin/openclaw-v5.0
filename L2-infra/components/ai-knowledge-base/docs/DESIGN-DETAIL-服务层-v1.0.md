# AI 知识库 - 服务化与接口详细设计 v1.0

> L2 Infrastructure Component · ai-knowledge-base
> 版本：v1.0 · 状态：Draft
> 最后更新：2026-10-18

---

## 1. 设计目标

1. **Agent 无关**：不绑定任何 Agent 框架，所有功能通过标准协议暴露
2. **多接口形态**：REST API / MCP Server / CLI / Python SDK 四种接入方式
3. **接口一致性**：不同接口形态的功能、参数、返回格式保持一致
4. **可观测性**：完整的健康检查、监控指标、审计日志
5. **高可用**：无状态服务设计，支持水平扩展
6. **向后兼容**：API 版本化，旧版本接口平滑过渡

---

## 2. 服务架构

### 2.1 分层架构

```
┌───────────────────────────────────────────────────────────┐
│                    API Gateway (可选)                      │
│              认证 · 限流 · 路由 · 日志                     │
└───────────────────────────┬───────────────────────────────┘
                            │
┌───────────────────────────▼───────────────────────────────┐
│                      API Layer                            │
│  ┌─────────┐  ┌──────────┐  ┌──────┐  ┌────────────────┐ │
│  │ REST API│  │MCP Server│  │ CLI │  │  Python SDK    │ │
│  └────┬────┘  └────┬─────┘  └──┬───┘  └───────┬────────┘ │
│       └──────────┬──┴───────────┘──────────────┘          │
│                  ▼                                         │
│           Service Layer (业务编排)                         │
└───────────────────┬───────────────────────────────────────┘
                    │
┌───────────────────▼───────────────────────────────────────┐
│                    Core Engine                             │
│  检索引擎 · 接入流水线 · 知识管理 · 反馈系统 · 模板引擎   │
└───────────────────┬───────────────────────────────────────┘
                    │
┌───────────────────▼───────────────────────────────────────┐
│                   Storage Layer                            │
│        关系数据库 · 向量索引 · 文件存储                    │
└───────────────────────────────────────────────────────────┘
```

### 2.2 服务层模块

| 服务 | 职责 | 核心方法 |
|---|---|---|
| KBInstanceService | 知识库实例管理 | 创建/删除/列出/配置实例 |
| IngestionService | 文档接入 | 导入/上传/扫描/任务状态查询 |
| RetrievalService | 检索查询 | query/search/explain |
| EntityService | 实体管理 | CRUD / 列表 / 分类移动 |
| DocumentService | 文档管理 | CRUD / 版本 / 重新解析 |
| GraphService | 知识图谱 | 关系管理 / 图查询 / 扩展 |
| FeedbackService | 反馈管理 | 提交/统计/审核/处理 |
| TemplateService | 模板管理 | 模板CRUD / 实例化 |
| AdminService | 管理后台 | 统计 / 健康检查 / 配置 |
| AuditService | 审计日志 | 查询 / 导出 |

---

## 3. REST API 设计

### 3.1 基础规范

- **协议**：HTTPS / HTTP
- **数据格式**：JSON (UTF-8)
- **版本策略**：URL 路径版本化（`/api/v1/...`）
- **认证**：API Key / JWT Token（可配置）
- **分页**：`?page=1&page_size=20`，返回 `total` / `page` / `page_size`
- **错误码**：HTTP 状态码 + 业务错误码 + 消息

### 3.2 统一响应格式

```json
{
  "code": 0,
  "message": "success",
  "data": { /* 业务数据 */ },
  "request_id": "uuid-string",
  "timestamp": 1700000000
}
```

### 3.3 错误码规范

| HTTP 状态码 | 业务码范围 | 说明 |
|---|---|---|
| 200 | 0 | 成功 |
| 400 | 1000-1999 | 请求参数错误 |
| 401 | 2000-2099 | 认证失败 |
| 403 | 2100-2199 | 权限不足 |
| 404 | 3000-3099 | 资源不存在 |
| 409 | 4000-4099 | 资源冲突 |
| 429 | 5000-5099 | 限流 |
| 500 | 9000-9999 | 服务器内部错误 |

### 3.4 接口清单

#### 知识库实例管理

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/instances` | 创建知识库实例 |
| GET | `/api/v1/instances` | 列出所有实例 |
| GET | `/api/v1/instances/{code}` | 获取实例详情 |
| PUT | `/api/v1/instances/{code}` | 更新实例配置 |
| DELETE | `/api/v1/instances/{code}` | 删除实例 |
| GET | `/api/v1/instances/{code}/stats` | 获取实例统计信息 |

#### 文档接入

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/instances/{code}/ingest/upload` | 上传单个文件并导入 |
| POST | `/api/v1/instances/{code}/ingest/scan` | 扫描指定目录导入 |
| GET | `/api/v1/instances/{code}/ingest/tasks` | 列出导入任务 |
| GET | `/api/v1/instances/{code}/ingest/tasks/{task_id}` | 获取任务详情 |
| POST | `/api/v1/instances/{code}/ingest/tasks/{task_id}/cancel` | 取消任务 |
| GET | `/api/v1/instances/{code}/ingest/report` | 获取批量导入报告 |

#### 检索查询

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/instances/{code}/query` | 知识库查询（返回答案+来源） |
| POST | `/api/v1/instances/{code}/search` | 纯检索（只返回chunk结果） |
| POST | `/api/v1/instances/{code}/search/explain` | 检索解释模式（详细过程） |
| GET | `/api/v1/instances/{code}/entities` | 实体列表 |
| GET | `/api/v1/instances/{code}/entities/{id}` | 实体详情 |
| GET | `/api/v1/instances/{code}/entities/{id}/docs` | 实体的文档列表 |

#### 实体管理

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/instances/{code}/entities` | 创建实体 |
| PUT | `/api/v1/instances/{code}/entities/{id}` | 更新实体 |
| DELETE | `/api/v1/instances/{code}/entities/{id}` | 删除实体 |
| POST | `/api/v1/instances/{code}/entities/batch-update-status` | 批量更新状态 |
| POST | `/api/v1/instances/{code}/entities/{id}/expire` | 标记实体过期 |

#### 文档管理

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/instances/{code}/docs` | 文档列表 |
| GET | `/api/v1/instances/{code}/docs/{id}` | 文档详情 |
| GET | `/api/v1/instances/{code}/docs/{id}/chunks` | 文档切片列表 |
| GET | `/api/v1/instances/{code}/docs/{id}/versions` | 文档版本历史 |
| POST | `/api/v1/instances/{code}/docs/{id}/reparse` | 重新解析文档 |
| DELETE | `/api/v1/instances/{code}/docs/{id}` | 删除文档 |

#### 知识图谱

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/instances/{code}/relations` | 创建关系 |
| DELETE | `/api/v1/instances/{code}/relations/{id}` | 删除关系 |
| GET | `/api/v1/instances/{code}/entities/{id}/relations` | 实体的所有关系 |
| POST | `/api/v1/instances/{code}/graph/expand` | 图谱扩展查询 |
| POST | `/api/v1/instances/{code}/graph/search` | 图谱增强检索 |

#### 反馈系统

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/instances/{code}/feedback` | 提交反馈 |
| GET | `/api/v1/instances/{code}/feedback` | 反馈列表 |
| GET | `/api/v1/instances/{code}/feedback/stats` | 反馈统计 |
| GET | `/api/v1/instances/{code}/feedback/low-score` | 低评分知识列表 |
| POST | `/api/v1/instances/{code}/feedback/{id}/resolve` | 处理反馈 |

#### 分类管理

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/instances/{code}/collections` | 分类树 |
| POST | `/api/v1/instances/{code}/collections` | 创建分类 |
| PUT | `/api/v1/instances/{code}/collections/{id}` | 更新分类 |
| DELETE | `/api/v1/instances/{code}/collections/{id}` | 删除分类 |

#### 模板管理

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/templates` | 列出所有模板 |
| GET | `/api/v1/templates/{code}` | 模板详情 |
| POST | `/api/v1/templates` | 创建模板 |
| PUT | `/api/v1/templates/{code}` | 更新模板 |
| DELETE | `/api/v1/templates/{code}` | 删除模板 |
| POST | `/api/v1/templates/{code}/instantiate` | 基于模板创建实例 |

#### 系统管理

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| GET | `/health/detailed` | 详细健康状态 |
| GET | `/api/v1/admin/metrics` | 服务指标 |
| GET | `/api/v1/admin/audit-logs` | 审计日志查询 |

---

## 4. MCP Server 设计

### 4.1 设计原则

- 完全兼容 MCP (Model Context Protocol) 规范
- 工具描述清晰，输入 Schema 完整
- 支持通过 MCP 进行查询、反馈、管理等操作
- 权限与 REST API 共用同一套鉴权体系

### 4.2 MCP 工具清单

| 工具名 | 说明 |
|---|---|
| `kb_query` | 查询知识库，返回带来源的答案 |
| `kb_search` | 纯检索，返回结构化chunk结果 |
| `kb_list_entities` | 列出所有实体 |
| `kb_get_entity` | 获取实体详情 |
| `kb_get_entity_docs` | 获取实体的所有文档 |
| `kb_add_feedback` | 提交用户反馈 |
| `kb_get_entity_feedback_stats` | 获取实体反馈统计 |
| `kb_list_low_score_knowledge` | 列出低评分知识 |
| `kb_mark_entity_expired` | 标记实体过期 |
| `kb_batch_update_entity_status` | 批量更新实体状态 |
| `kb_list_collections` | 列出分类树 |
| `kb_stats` | 获取知识库统计信息 |
| `kb_list_templates` | 列出可用模板 |
| `kb_create_instance` | 基于模板创建实例 |

### 4.3 资源暴露

MCP 资源（Resources）：
- `kb://{instance-code}/entities/{id}` — 实体详情
- `kb://{instance-code}/docs/{id}` — 文档全文
- `kb://{instance-code}/stats` — 统计信息

---

## 5. CLI 设计

### 5.1 命令结构

```bash
ai-kb [全局选项] <命令> [子命令] [参数]

# 实例管理
ai-kb instance create <code> --name <名称> --template <模板名>
ai-kb instance list
ai-kb instance show <code>
ai-kb instance delete <code>
ai-kb instance stats <code>

# 文档导入
ai-kb ingest upload <code> <file_path>
ai-kb ingest scan <code> <dir_path>
ai-kb ingest tasks <code>
ai-kb ingest status <code> <task_id>

# 检索查询
ai-kb query <code> "查询问题" [--top-k 5] [--markdown]
ai-kb search <code> "关键词" [--top-k 10]
ai-kb search explain <code> "关键词"

# 实体管理
ai-kb entity list <code> [--collection <id>] [--status active]
ai-kb entity show <code> <entity_id>
ai-kb entity expire <code> <entity_id>
ai-kb entity batch-update-status <code> --ids 1,2,3 --status expired

# 反馈
ai-kb feedback submit <code> --query "问题" --type useful
ai-kb feedback list <code>
ai-kb feedback stats <code>
ai-kb feedback low-score <code> [--threshold 1]

# 模板
ai-kb template list
ai-kb template show <code>
ai-kb template create --config <yaml文件>
ai-kb template delete <code>

# 系统
ai-kb health
ai-kb version
ai-kb serve [--host 0.0.0.0] [--port 8000]  # 启动服务
```

### 5.2 全局选项

- `--config <path>`：配置文件路径
- `--db-path <path>`：直接指定数据库路径（不通过实例名）
- `--format <json|table|markdown>`：输出格式
- `--verbose` / `-v`：详细输出
- `--quiet` / `-q`：静默模式，只输出结果

---

## 6. Python SDK 设计

### 6.1 核心类

```python
class AIKBClient:
    """AI 知识库客户端（支持远程HTTP和本地直连两种模式）"""
    
    # 两种模式
    # 1. 远程模式: AIKBClient(base_url="http://localhost:8000", api_key="xxx")
    # 2. 本地模式: AIKBClient(local_db_path="/path/to/kb.db", domain_code="product-kb")
    
    def __init__(self, base_url: str = None, api_key: str = None,
                 local_db_path: str = None, domain_code: str = None):
        ...

    # --- 检索 ---
    def query(self, question: str, top_k: int = 5, 
              use_graph: bool = False, include_expired: bool = False) -> QueryResult:
        ...
    
    def search(self, query: str, top_k: int = 10) -> List[ChunkResult]:
        ...
    
    # --- 实体 ---
    def list_entities(self, **filters) -> List[Entity]:
        ...
    
    def get_entity(self, entity_id: int) -> Entity:
        ...
    
    def mark_entity_expired(self, entity_id: int) -> bool:
        ...
    
    # --- 反馈 ---
    def add_feedback(self, query_text: str, feedback_type: str, **kwargs) -> int:
        ...
    
    def get_feedback_stats(self, entity_id: int = None, doc_id: int = None) -> Dict:
        ...
    
    def list_low_score_knowledge(self, threshold: int = 1) -> List:
        ...
    
    # --- 模板与实例 ---
    @staticmethod
    def create_instance(template_code: str, instance_code: str, **kwargs) -> AIKBClient:
        """基于模板创建新实例并返回客户端"""
        ...
```

### 6.2 设计特点

- **双模式**：支持 HTTP 远程调用和本地直连，接口完全一致
- **类型提示**：完整的 Type Hints，支持 IDE 补全
- **异常体系**：自定义异常类，统一错误处理
- **自动重试**：网络请求失败自动重试（指数退避）
- **缓存**：可选本地缓存，减少重复请求

---

## 7. 认证与授权

### 7.1 认证方式

| 方式 | 适用场景 | 配置 |
|---|---|---|
| API Key | 服务间调用、MCP | `auth.api_keys: [key1, key2]` |
| JWT Token | 用户登录场景 | `auth.jwt.secret: xxx` |
| 无认证 | 本地/内网部署 | `auth.enabled: false` |

### 7.2 权限模型

复用 ABAC 权限模型（参见权限模块设计）：
- 用户属性：role / department / clearance / user_id
- 资源属性（文档/切片级）：allowed_roles / allowed_departments / clearance_level
- 权限判断在检索时执行，不是返回后再过滤

---

## 8. 可观测性

### 8.1 健康检查

`GET /health` 返回：

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime_seconds": 86400,
  "components": {
    "database": "healthy",
    "embedding": "healthy",
    "storage": "healthy"
  }
}
```

### 8.2 监控指标（Metrics）

| 指标类型 | 指标名 | 说明 |
|---|---|---|
| 检索 | `kb_query_total` | 查询总次数（counter） |
| 检索 | `kb_query_duration_seconds` | 查询耗时分布（histogram） |
| 检索 | `kb_query_result_count` | 每次查询返回结果数（histogram） |
| 检索 | `kb_query_cache_hit_total` | 缓存命中次数（counter） |
| 接入 | `kb_ingest_total` | 导入文件总数（counter） |
| 接入 | `kb_ingest_duration_seconds` | 导入耗时（histogram） |
| 接入 | `kb_ingest_failed_total` | 导入失败次数（counter） |
| 系统 | `kb_entities_total` | 实体总数（gauge） |
| 系统 | `kb_docs_total` | 文档总数（gauge） |
| 系统 | `kb_chunks_total` | 切片总数（gauge） |

### 8.3 审计日志

所有操作记录审计日志，支持：
- 按时间范围查询
- 按用户查询
- 按操作类型查询
- 按对象查询
- 导出为 CSV / JSON

---

## 9. 部署设计

### 9.1 单机部署

```bash
# 直接运行
ai-kb serve --host 0.0.0.0 --port 8000

# 配置文件
ai-kb serve --config /etc/ai-kb/config.yaml
```

### 9.2 Docker 部署

```dockerfile
# Dockerfile 示例
FROM python:3.11-slim
RUN pip install ai-kb[all]
EXPOSE 8000
CMD ["ai-kb", "serve", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker run -d \
  -p 8000:8000 \
  -v /path/to/data:/data \
  -e AI_KB_DATA_DIR=/data \
  ai-kb:latest
```

### 9.3 配置管理

**配置优先级**（从高到低）：
1. 命令行参数
2. 环境变量（`AI_KB_` 前缀）
3. 配置文件（YAML）
4. 默认值

**核心配置项**：

```yaml
server:
  host: 0.0.0.0
  port: 8000
  workers: 4

auth:
  enabled: false
  api_keys: []
  jwt:
    secret: ""

database:
  type: sqlite          # sqlite / postgres
  path: ./data/ai-kb.db
  # postgres 配置
  # host: localhost
  # port: 5432
  # user: ai_kb
  # password: xxx
  # database: ai_kb

embedding:
  provider: local       # local / openai / volcengine / tongyi
  model: embeddinggemma-300m
  api_key: ""
  endpoint: ""
  batch_size: 32

storage:
  type: local           # local / s3 / minio
  path: ./data/docs
  # s3 配置
  # bucket: ai-kb-docs
  # endpoint: ""

retrieval:
  default_top_k: 5
  min_similarity: 0.3
  channels:
    entity: { enabled: true, weight: 1.2 }
    fts: { enabled: true, weight: 1.0 }
    vector: { enabled: true, weight: 0.9 }
    graph: { enabled: false, weight: 0.8 }
  rerank:
    enabled: false
    model: ""

logging:
  level: info
  format: json
  file: ./logs/ai-kb.log
```

