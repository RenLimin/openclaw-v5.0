"""
MCP (Model Context Protocol) Server for AI Knowledge Base
Exposes KB operations as MCP tools, compatible with MCP spec.
Any AI Agent (Claude, Codex, etc.) can register these tools directly.

Usage:
    from mcp.server import KBMCPHandler
    handler = KBMCPHandler(db_path)
    tools = handler.list_tools()          # MCP tool descriptors
    result = handler.call_tool("kb_query", {"question": "..."})
"""
import json
import os
from typing import Dict, Any, List, Optional

from ai_kb.api import AIKBService


class KBMCPHandler:
    """
    MCP-compatible tool handler. Provides tool descriptors (list_tools)
    and tool invocation (call_tool) matching the MCP protocol shape.
    """

    def __init__(self, db_path: str, instance_code: str = "default"):
        self.db_path = db_path
        self.instance_code = instance_code
        self._service: Optional[AIKBService] = None

    def _get_service(self) -> AIKBService:
        if self._service is None:
            self._service = AIKBService(self.db_path, self.instance_code)
        return self._service

    # --- MCP protocol: tools ---

    def list_tools(self) -> List[Dict[str, Any]]:
        """Return MCP tool descriptors (name, description, inputSchema)"""
        return AIKBService.mcp_tools()

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke an MCP tool by name with arguments"""
        svc = self._get_service()
        tool = tool_name.lower()

        if tool == "kb_query":
            return svc.query(
                question=arguments["question"],
                top_k=arguments.get("top_k", 5),
                use_graph=arguments.get("use_graph", False),
                start_entity=arguments.get("start_entity"),
                format=arguments.get("format", "markdown"),
                include_expired=arguments.get("include_expired", False),
            )
        if tool == "kb_search":
            # Pure retrieval, returns structured chunks
            from ai_kb.search import HybridSearch
            svc_kb = svc.kb
            domain_id = svc.domain_id
            hs = HybridSearch(svc_kb, domain_id, include_expired=arguments.get("include_expired", False))
            return {"results": hs.search(arguments["query"], top_k=arguments.get("top_k", 10))}
        if tool == "kb_list_entities":
            return {"entities": svc.list_entities(
                collection_id=arguments.get("collection_id"),
                status=arguments.get("status"),
            )}
        if tool == "kb_get_entity":
            entity = svc.get_entity(arguments["entity_id"])
            if not entity:
                return {"error": "Entity not found"}
            return {"entity": entity}
        if tool == "kb_get_entity_docs":
            return {"docs": svc.get_entity_docs(arguments["entity_id"])}
        if tool == "kb_add_feedback":
            return svc.add_feedback(
                query_text=arguments["query_text"],
                feedback_type=arguments["feedback_type"],
                answer_text=arguments.get("answer_text"),
                feedback_comment=arguments.get("feedback_comment"),
                entity_id=arguments.get("entity_id"),
                doc_id=arguments.get("doc_id"),
                chunk_id=arguments.get("chunk_id"),
                user_id=arguments.get("user_id"),
            )
        if tool == "kb_get_entity_feedback_stats":
            return svc.get_entity_feedback_stats(arguments["entity_id"])
        if tool == "kb_list_low_score_knowledge":
            return {"items": svc.list_low_score_knowledge(arguments.get("threshold", 1))}
        if tool == "kb_mark_entity_expired":
            return svc.mark_entity_expired(arguments["entity_id"])
        if tool == "kb_batch_update_entity_status":
            return svc.batch_update_entity_status(arguments["entity_ids"], arguments["status"])
        if tool == "kb_stats":
            return svc.stats(arguments.get("include_expired", False))
        if tool == "kb_list_templates":
            from ai_kb.template import TemplateManager
            tm = TemplateManager(svc.kb)
            return {"templates": [t.to_dict() for t in tm.list_templates()]}
        if tool == "kb_create_instance":
            return svc.kb.get_or_create_domain(arguments["name"], arguments["code"])

        return {"error": f"Unknown tool: {tool_name}"}

    # --- MCP protocol: resources ---

    def read_resource(self, uri: str) -> Optional[Dict[str, Any]]:
        """Read an MCP resource: kb://{instance}/{type}/{id}"""
        # Format: kb://{instance-code}/entities/{id} | docs/{id} | stats
        parts = uri.replace("kb://", "").split("/")
        if len(parts) < 2:
            return None
        svc = self._get_service()
        if parts[0] != self.instance_code:
            return None
        if parts[1] == "stats":
            return {"uri": uri, "data": svc.stats()}
        if len(parts) < 3:
            return None
        obj_type, obj_id = parts[1], int(parts[2])
        if obj_type == "entities":
            return {"uri": uri, "data": svc.get_entity(obj_id)}
        if obj_type == "docs":
            return {"uri": uri, "data": svc.get_entity_docs(obj_id)}
        return None

    def close(self):
        if self._service:
            self._service.close()
            self._service = None
