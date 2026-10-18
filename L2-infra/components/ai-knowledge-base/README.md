# AI Knowledge Base (ai-knowledge-base)

> L2 Infrastructure Component · 企业级 AI 知识库 — 跨 Agent 可复制、多格式接入、混合检索、强制来源引用

## 特性

- **多格式文档接入**：MD / TXT / HTML / CSV / JSON / Word / Excel / PPT / PDF / 图片 OCR
- **智能切片**：章节切片 + 固定大小切片 + 重叠上下文
- **质量检测**：内容质量评分 + PII 检测脱敏（手机号/身份证/邮箱/银行卡/API Key）
- **四类存储**：关系表 + SQLite FTS5 全文索引 + 向量索引 + 知识图谱（GraphRAG）
- **混合检索**：实体精确匹配 + FTS 关键词 + 向量相似度，多路召回 + 融合排序
- **强制来源引用**：每个回答必须附原始文档来源（文件名+类型+原文片段+置信度）
- **ABAC 权限**：文档级权限，检索时过滤（非应用层）
- **四种接入**：REST API / MCP Server / CLI / Python SDK
- **审计日志**：所有操作可追溯
- **模板实例化**：基于模板一键创建新知识库

## 快速开始

```bash
# 1. 创建实例（脚本自动初始化数据库 + 目录 + 配置）
bash scripts/init_kb.sh my-kb

# 2. 启动 REST API 服务
python3 -m api.server --host 0.0.0.0 --port 8000
# 或
python3 ai-kb serve --host 0.0.0.0 --port 8000

# 3. 上传文档
curl -X POST http://127.0.0.1:8000/api/v1/instances/my-kb/ingest/upload \
  -F "file=@docs/product.md"

# 4. 查询（带来源引用）
curl -X POST http://127.0.0.1:8000/api/v1/instances/my-kb/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"APP加固有什么功能","top_k":5,"format":"markdown"}'
```

## CLI

```bash
ai-kb instance create <code> --name "名称"        # 创建实例
ai-kb ingest upload <code> <file>                # 上传文档
ai-kb ingest scan <code> <dir>                   # 扫描目录批量导入
ai-kb query <code> "问题" --top-k 5 --markdown   # 查询（带来源）
ai-kb entity list <code>                         # 实体列表
ai-kb feedback submit <code> --query "问题" --type useful  # 反馈
ai-kb health                                     # 健康检查
ai-kb serve --host 0.0.0.0 --port 8000           # 启动服务
```

## REST API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| GET | `/api/v1/instances` | 实例列表 |
| POST | `/api/v1/instances` | 创建实例 |
| POST | `/api/v1/instances/{code}/query` | 查询（带来源引用） |
| POST | `/api/v1/instances/{code}/ingest/upload` | 上传文档 |
| POST | `/api/v1/instances/{code}/ingest/scan` | 目录扫描导入 |
| GET | `/api/v1/instances/{code}/entities` | 实体列表 |
| POST | `/api/v1/instances/{code}/feedback` | 提交反馈 |
| GET | `/api/v1/instances/{code}/stats` | 实例统计 |
| GET | `/api/v1/mcp/tools` | MCP 工具描述符 |

## MCP 接入（其他 Agent 使用）

```python
from mcp.server import KBMCPHandler
handler = KBMCPHandler("./data/ai-kb.db", "my-kb")
tools = handler.list_tools()                      # 工具描述符
result = handler.call_tool("kb_query", {"question": "..."})
```

## 架构

```
接入层: parsers/ (MD/TXT/HTML/CSV/JSON/Word/Excel/PPT/PDF/OCR)
        ↓
处理层: chunker/ (章节+固定切片) → quality/ (质量+PII脱敏) → ingestion/ (流水线)
        ↓
存储层: db.py (SQLite) — entity / doc_asset / doc_chunk / kb_relation / FTS5
        embedding.py (向量) / graphrag.py (知识图谱)
        ↓
检索层: retrieval/ — entity_search + fts_search + vector_search → fusion
        ↓
服务层: api/ (REST) + mcp/ (MCP) + cli/ (CLI) + guardrails/ (风险防护)
```

## 文档

- `docs/PRD-v1.0.md` — 产品需求
- `docs/DESIGN-OUTLINE-v1.0.md` — 总体设计
- `docs/DESIGN-DETAIL-*.md` — 详细设计（数据模型/接入层/检索层/服务层/风险防护/模板化）
- `docs/OPERATIONS-v1.0.md` — 运维手册
- `docs/IMPLEMENTATION-PLAN-v1.0.md` — 实施计划

## 测试

```bash
python3 -m pytest tests/ -v
```

---

## Agent 资产：Bangcle 产品专家

基于本知识库构建的产品专家 Agent 资产（`agents/bangcle-product-expert/`）：

| 资产 | 说明 |
|---|---|
| `SYSTEM_PROMPT.md` | Agent 系统提示词（强制来源引用/禁止编造/上下文管理） |
| `TOOLS.md` | MCP 工具对接说明 |
| `config.json` | Agent 运行配置（实例/MCP端点/检索参数） |
| `knowledge/` | 产品知识源文档（APP加固/渠道监测/威胁情报） |
| `scripts/init_instance.sh` | 创建 bangcle-products 实例（product-kb 模板） |
| `scripts/import_knowledge.sh` | 批量导入产品知识 |
| `tests/e2e_verify.py` | E2E 验证（18 项检查） |

快速启用：

```bash
# 1. 创建实例
bash agents/bangcle-product-expert/scripts/init_instance.sh

# 2. 导入知识
bash agents/bangcle-product-expert/scripts/import_knowledge.sh

# 3. E2E 验证
python3 agents/bangcle-product-expert/tests/e2e_verify.py
```
