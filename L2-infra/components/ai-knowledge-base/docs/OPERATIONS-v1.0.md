# AI 知识库 - 运维操作手册 v1.0

> L2 Infrastructure Component · ai-knowledge-base
> 版本：v1.0 · 状态：Draft
> 最后更新：2026-10-18

---

## 1. 系统概述

AI 知识库是一个通用的企业级知识管理引擎，支持多格式文档接入、混合检索、知识图谱、风险防护等能力。本手册涵盖安装、配置、日常运维、故障排查等内容。

### 1.1 组件架构

```
AI KB Service
├── API Layer (REST / MCP / CLI / SDK)
├── Service Layer (检索 / 接入 / 管理 / 反馈 / 模板)
├── Core Engine (数据模型 / 检索引擎 / 风险防护)
└── Storage (关系数据库 + 向量索引 + 文件存储)
```

### 1.2 默认端口与路径

| 项目 | 默认值 | 说明 |
|---|---|---|
| HTTP 端口 | 8000 | REST API 服务端口 |
| MCP 端口 | 通过 stdio 或 SSE | MCP 协议通信 |
| 数据目录 | `./data` | 数据库和索引文件 |
| 文档目录 | `./data/docs` | 原始文档存储 |
| 日志文件 | `./logs/ai-kb.log` | 运行日志 |
| 配置文件 | `./config.yaml` | 服务配置 |

---

## 2. 安装部署

### 2.1 环境要求

| 项目 | 最低要求 | 推荐配置 |
|---|---|---|
| CPU | 2 核 | 4 核以上 |
| 内存 | 4 GB | 8 GB 以上（含本地 Embedding 模型） |
| 磁盘 | 10 GB | 50 GB 以上（取决于知识库规模） |
| 操作系统 | macOS 12+ / Linux x86_64/arm64 / Windows 10+ | Linux 生产环境 |
| Python | 3.11+ | 3.11+ |

### 2.2 安装方式

#### 方式一：pip 安装（推荐）

```bash
# 安装基础版（SQLite + 本地 Embedding）
pip install ai-kb

# 安装完整版（含所有可选依赖）
pip install ai-kb[all]

# 验证安装
ai-kb --version
```

#### 方式二：Docker 部署

```bash
# 拉取镜像
docker pull ai-kb/ai-kb:latest

# 启动服务
docker run -d \
  --name ai-kb \
  -p 8000:8000 \
  -v /path/to/data:/app/data \
  -v /path/to/config.yaml:/app/config.yaml \
  ai-kb/ai-kb:latest

# 查看状态
docker ps | grep ai-kb
docker logs ai-kb
```

#### 方式三：源码运行

```bash
# 克隆代码
git clone <repo-url>
cd ai-knowledge-base

# 安装依赖
pip install -e ".[all]"

# 初始化配置
cp config.example.yaml config.yaml

# 启动服务
ai-kb serve --config config.yaml
```

### 2.3 快速启动

```bash
# 1. 创建一个测试知识库实例
ai-kb instance create test-kb --name "测试知识库" --template generic-doc-kb

# 2. 导入一些文档
ai-kb ingest scan test-kb ./sample-docs/

# 3. 测试查询
ai-kb query test-kb "什么是AI知识库"

# 4. 启动 API 服务
ai-kb serve --host 0.0.0.0 --port 8000

# 5. 健康检查
curl http://localhost:8000/health
```

---

## 3. 配置说明

### 3.1 配置文件结构

```yaml
# 服务配置
server:
  host: 0.0.0.0
  port: 8000
  workers: 4
  reload: false

# 认证配置
auth:
  enabled: false
  api_keys: []
  jwt:
    secret: ""
    algorithm: HS256
    expire_hours: 24

# 数据库配置
database:
  type: sqlite                # sqlite / postgres
  path: ./data/ai-kb.db
  # postgres 配置
  # host: localhost
  # port: 5432
  # user: ai_kb
  # password: ""
  # database: ai_kb
  # ssl_mode: disable

# Embedding 配置
embedding:
  provider: local             # local / openai / volcengine / tongyi
  model: embeddinggemma-300m
  api_key: ""
  endpoint: ""
  batch_size: 32
  max_retries: 3
  timeout: 30

# 文件存储配置
storage:
  type: local                 # local / s3 / minio
  path: ./data/docs
  # s3/minio 配置
  # bucket: ai-kb-docs
  # endpoint: ""
  # access_key: ""
  # secret_key: ""
  # region: us-east-1

# 检索配置
retrieval:
  default_top_k: 5
  min_similarity: 0.3
  query_cache:
    enabled: true
    ttl_seconds: 3600
  channels:
    entity:
      enabled: true
      weight: 1.2
      top_k: 10
    fts:
      enabled: true
      weight: 1.0
      top_k: 20
    vector:
      enabled: true
      weight: 0.9
      top_k: 20
    graph:
      enabled: false
      weight: 0.8
      max_depth: 2
      top_k: 10
  fusion_method: weighted_sum
  rerank:
    enabled: false
    model: ""
    top_n: 20

# 风险防护配置
guardrails:
  input:
    pii_detection:
      enabled: true
      types: [phone, id_card, email, bank_card, api_key]
      action: mask
    quality_check:
      enabled: true
      min_word_count: 50
      min_quality_score: 0.3
    injection_detection:
      enabled: true
      action: block
  
  retrieval:
    permission_filter:
      enabled: true
      mode: strict
    expired_filter:
      enabled: true
    similarity_threshold:
      enabled: true
      min_score: 0.3
    prompt_injection:
      enabled: true
      action: reject
  
  output:
    pii_rescan:
      enabled: true
    scope_check:
      enabled: true
  
  system:
    rate_limit:
      enabled: true
      per_minute: 100
      per_hour: 1000
    audit_log:
      enabled: true
      retention_days: 90
    circuit_breaker:
      enabled: true
      error_rate_threshold: 0.3
      cooldown_seconds: 300

# 切片配置
chunking:
  strategy: section
  max_tokens: 512
  min_tokens: 50
  overlap_tokens: 64
  preserve_tables: true
  preserve_code: true

# 日志配置
logging:
  level: info                 # debug / info / warning / error
  format: json                # json / text
  file: ./logs/ai-kb.log
  max_size: 100MB
  max_backups: 10
  max_age: 30
```

### 3.2 环境变量配置

所有配置项都可以通过环境变量覆盖，前缀 `AI_KB_`，大写加下划线：

```bash
AI_KB_SERVER_PORT=8080
AI_KB_AUTH_ENABLED=true
AI_KB_DATABASE_TYPE=postgres
AI_KB_EMBEDDING_PROVIDER=openai
AI_KB_EMBEDDING_API_KEY=sk-xxx
```

优先级：命令行参数 > 环境变量 > 配置文件 > 默认值

---

## 4. 日常运维操作

### 4.1 实例管理

```bash
# 列出所有实例
ai-kb instance list

# 创建实例（基于模板）
ai-kb instance create <code> --name <名称> --template <模板名>

# 查看实例详情
ai-kb instance show <code>

# 查看实例统计
ai-kb instance stats <code>

# 删除实例（危险操作，需确认）
ai-kb instance delete <code> --yes-i-know-what-i-am-doing
```

### 4.2 文档导入

```bash
# 扫描目录批量导入
ai-kb ingest scan <instance-code> <目录路径>

# 上传单个文件
ai-kb ingest upload <instance-code> <文件路径>

# 查看导入任务列表
ai-kb ingest tasks <instance-code>

# 查看任务详情
ai-kb ingest status <instance-code> <task_id>

# 取消任务
ai-kb ingest cancel <instance-code> <task_id>

# 重新解析单个文档
ai-kb doc reparse <instance-code> <doc_id>
```

### 4.3 知识管理

```bash
# 列出实体
ai-kb entity list <instance-code> [--collection <id>] [--status active]

# 查看实体详情
ai-kb entity show <instance-code> <entity_id>

# 标记实体过期
ai-kb entity expire <instance-code> <entity_id>

# 批量更新实体状态
ai-kb entity batch-update-status <instance-code> --ids 1,2,3 --status expired

# 列出文档
ai-kb doc list <instance-code>

# 查看文档版本历史
ai-kb doc versions <instance-code> <doc_id>

# 删除文档
ai-kb doc delete <instance-code> <doc_id>
```

### 4.4 反馈管理

```bash
# 查看反馈列表
ai-kb feedback list <instance-code>

# 查看反馈统计
ai-kb feedback stats <instance-code>

# 列出低评分知识
ai-kb feedback low-score <instance-code> --threshold 1

# 处理反馈
ai-kb feedback resolve <instance-code> <feedback_id> --note "已修正"
```

### 4.5 模板管理

```bash
# 列出所有模板
ai-kb template list

# 查看模板详情
ai-kb template show <code>

# 从 YAML 文件创建模板
ai-kb template create --file template.yaml

# 删除模板
ai-kb template delete <code>
```

### 4.6 索引维护

```bash
# 重建 FTS 索引
ai-kb index rebuild-fts <instance-code>

# 重建向量索引
ai-kb index rebuild-vector <instance-code>

# 优化索引（减少碎片化）
ai-kb index optimize <instance-code>

# 验证索引完整性
ai-kb index verify <instance-code>
```

### 4.7 备份与恢复

```bash
# 全量备份（数据库 + 文档）
ai-kb backup <instance-code> --output /path/to/backup/

# 只备份数据库
ai-kb backup <instance-code> --db-only --output /path/to/backup.db

# 从备份恢复
ai-kb restore <instance-code> --from /path/to/backup/

# 定时备份（cron 示例）
# 每天凌晨 2 点备份
# 0 2 * * * /usr/local/bin/ai-kb backup my-kb --output /data/backups/ --rotate 30
```

---

## 5. 监控与告警

### 5.1 健康检查

```bash
# 简单健康检查
curl http://localhost:8000/health

# 详细健康状态
curl http://localhost:8000/health/detailed
```

健康检查项：
- 数据库连接状态
- Embedding 服务可用性
- 文件存储可用性
- 磁盘空间
- 内存使用

### 5.2 关键指标

| 指标 | 正常范围 | 告警阈值 | 说明 |
|---|---|---|---|
| 查询响应时间 P95 | < 500ms | > 1s | 检索性能 |
| 查询成功率 | > 99% | < 95% | 服务质量 |
| 导入成功率 | > 95% | < 80% | 接入质量 |
| 缓存命中率 | > 30% | < 10% | 缓存效率 |
| 磁盘使用率 | < 70% | > 85% | 存储容量 |
| 内存使用率 | < 80% | > 90% | 内存压力 |
| 错误率 | < 1% | > 5% | 系统稳定性 |

### 5.3 日志查询

```bash
# 实时查看日志
tail -f ./logs/ai-kb.log

# 查询错误日志
grep '"level":"error"' ./logs/ai-kb.log

# 按请求ID追踪
grep '"request_id":"xxx"' ./logs/ai-kb.log

# 查询慢查询
grep '"duration_ms":[5-9][0-9]\{2,\}' ./logs/ai-kb.log
```

---

## 6. 故障排查

### 6.1 服务无法启动

| 可能原因 | 排查方法 | 解决方案 |
|---|---|---|
| 端口被占用 | `lsof -i :8000` | 换端口或停掉占用进程 |
| 数据库文件损坏 | 查看启动日志中的数据库错误 | 从备份恢复 |
| 配置文件错误 | 查看启动日志中的配置解析错误 | 修正配置文件格式 |
| 权限不足 | 检查数据目录权限 | `chmod -R 755 data/` |
| 依赖缺失 | 查看 ImportError | `pip install ai-kb[all]` |

### 6.2 查询速度慢

| 可能原因 | 排查方法 | 解决方案 |
|---|---|---|
| 数据量太大 | `ai-kb instance stats` 查看切片数 | 升级到向量索引/增加内存 |
| 索引碎片 | `ai-kb index verify` | `ai-kb index optimize` |
| Embedding 调用慢 | 查看日志中的 embedding 耗时 | 切换更快的模型 / 增加缓存 |
| 磁盘 IO 瓶颈 | `iostat` 查看磁盘使用率 | 换 SSD / 增加内存缓存 |

### 6.3 导入失败

| 现象 | 可能原因 | 解决方案 |
|---|---|---|
| 所有文档都失败 | 解析器依赖缺失 | 安装对应格式的解析库 |
| 个别文档失败 | 文档损坏 / 加密 / 格式特殊 | 检查具体错误信息，手动处理 |
| 导入到一半卡住 | 某个大文档处理超时 | 增加超时时间 / 单独导入该文档 |
| 内存溢出 | 文档太大或批量太大 | 减小 batch_size，增加内存 |

### 6.4 查询结果不准确

| 现象 | 可能原因 | 解决方案 |
|---|---|---|
| 搜不到已知内容 | 文档未正确解析 / 分词问题 | 检查文档解析状态，尝试换关键词 |
| 结果不相关 | 相似度太低 / 检索策略问题 | 提高相似度阈值，调整通道权重 |
| 过期内容还出现 | 未正确标记过期 / 过滤未生效 | 检查实体 status 字段，确认过滤开启 |
| 越权内容能看到 | 权限配置错误 / 权限过滤未启用 | 检查权限配置，确认 guardrails 开启 |

### 6.5 数据恢复

```bash
# 场景1：误删文档，从备份恢复
ai-kb restore my-kb --from /path/to/backup/ --only-docs

# 场景2：数据库损坏，重建索引
ai-kb index rebuild-fts my-kb
ai-kb index rebuild-vector my-kb

# 场景3：实例误删
# 1. 从最近备份恢复数据库
# 2. 恢复文档文件
# 3. 验证完整性
ai-kb index verify my-kb
```

---

## 7. 安全运维

### 7.1 安全检查清单

- [ ] 认证已启用（非内网部署）
- [ ] API Key 定期轮换
- [ ] HTTPS 已配置
- [ ] 敏感数据已脱敏
- [ ] 审计日志已开启并定期归档
- [ ] 权限配置正确（最小权限原则）
- [ ] 输入注入防护已开启
- [ ] 输出脱敏已开启
- [ ] 备份已加密
- [ ] 定期安全审计

### 7.2 应急响应

**发现安全事件时**：

1. **立即响应**
   - 确认事件类型和影响范围
   - 暂停相关服务（如数据泄漏风险）
   - 保留现场（日志、数据库快照）

2. **评估影响**
   - 哪些数据受影响
   - 影响多少用户
   - 是否需要通知用户

3. **处置措施**
   - 阻断攻击路径
   - 修复漏洞
   - 清理受污染数据
   - 恢复服务

4. **事后复盘**
   - 根因分析
   - 更新防护规则
   - 完善应急预案
   - 记录归档

---

## 8. 升级指南

### 8.1 版本升级

```bash
# 1. 备份所有数据（重要！）
ai-kb backup my-kb --output /path/to/pre-upgrade-backup/

# 2. 停止服务
docker stop ai-kb
# 或
pkill -f "ai-kb serve"

# 3. 升级软件
pip install --upgrade ai-kb
# 或
docker pull ai-kb/ai-kb:latest

# 4. 执行数据库迁移
ai-kb db migrate

# 5. 验证升级
ai-kb --version
ai-kb db verify

# 6. 重启服务
ai-kb serve --config config.yaml
# 或
docker start ai-kb

# 7. 验证功能
curl http://localhost:8000/health
ai-kb query my-kb "测试查询"
```

### 8.2 回滚

如果升级失败：

```bash
# 1. 停止服务
docker stop ai-kb

# 2. 恢复数据
ai-kb restore my-kb --from /path/to/pre-upgrade-backup/

# 3. 回滚软件版本
pip install ai-kb==<旧版本号>
# 或
docker rollback ai-kb

# 4. 重启服务
ai-kb serve --config config.yaml
```

### 8.3 存储后端迁移

#### SQLite → PostgreSQL

```bash
# 1. 备份 SQLite 数据
ai-kb backup my-kb --db-only --output backup.db

# 2. 修改配置为 PostgreSQL
# 编辑 config.yaml，设置 database.type = postgres

# 3. 初始化 PostgreSQL 数据库
ai-kb db init

# 4. 导入数据
ai-kb db import-from-sqlite backup.db

# 5. 验证
ai-kb db verify
```

