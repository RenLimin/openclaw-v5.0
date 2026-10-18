# MCP 工具对接说明 — Bangcle 产品专家 Agent

> 版本：v1.0 · 2026-10-18
> 对接：AI 知识库 MCP Server（实例：bangcle-products）

---

## 1. 连接配置

MCP Server 端点（由 AI 知识库服务提供）：

```
http://<host>:<port>/mcp
```

Agent 框架配置示例（Claude Code settings.json）：

```json
{
  "mcpServers": {
    "bangcle-product-kb": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

---

## 2. 工具清单

### 2.1 kb_query（核心工具）

查询知识库，返回带来源引用的结果。

```json
{
  "name": "kb_query",
  "description": "Query the Bangcle product knowledge base and get results with source references. Always use this tool to get product information before answering.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "question": { "type": "string", "description": "用户问题" },
      "top_k": { "type": "integer", "description": "返回结果数", "default": 5 },
      "format": { "type": "string", "description": "输出格式", "default": "json" },
      "include_expired": { "type": "boolean", "description": "是否包含过期知识", "default": false }
    },
    "required": ["question"]
  }
}
```

**返回结构**：

```json
{
  "query": "APP加固有什么功能",
  "answer": "...",
  "sources": [
    {
      "entity": { "name": "APP加固产品说明", "id": 1 },
      "doc_asset": { "file_name": "产品-APP加固.md", "doc_type": "document" },
      "chunk": { "text": "...", "chunk_index": 0 }
    }
  ],
  "source_count": 1,
  "confidence": "medium",
  "markdown": "..."
}
```

### 2.2 kb_add_feedback（反馈收集）

```json
{
  "name": "kb_add_feedback",
  "description": "Submit user feedback after answer.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query_text": { "type": "string", "description": "原始查询" },
      "feedback_type": { "type": "string", "description": "useful / not_useful" },
      "entity_id": { "type": "integer", "description": "来源实体 ID" },
      "doc_id": { "type": "integer", "description": "来源文档 ID" },
      "user_id": { "type": "string", "description": "用户标识" }
    },
    "required": ["query_text", "feedback_type"]
  }
}
```

### 2.3 kb_stats（实例统计）

```json
{
  "name": "kb_stats",
  "description": "Get statistics about the product knowledge base.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "domain_code": { "type": "string", "description": "实例 code" }
    },
    "required": ["domain_code"]
  }
}
```

### 2.4 其他可用工具

| 工具 | 用途 |
|---|---|
| `kb_list_entities` | 列出实体 |
| `kb_get_entity` | 获取实体详情 |
| `kb_get_entity_docs` | 获取实体文档 |
| `kb_list_low_score_knowledge` | 低评分知识（质量巡检） |
| `kb_get_entity_feedback_stats` | 实体反馈统计 |

---

## 3. 调用规则

1. **查询必调**：回答任何产品问题前必须先调用 `kb_query`
2. **反馈必报**：用户明确评价后调用 `kb_add_feedback`
3. **失败降级**：工具调用失败时告知用户「知识库服务暂时不可用」，不编造答案
