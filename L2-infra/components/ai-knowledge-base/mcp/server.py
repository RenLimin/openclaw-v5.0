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

# P5.1 wrapper fields stripped when a dynamic propose tool flattens
# action params into the tool's top-level arguments.
_PROPOSE_WRAPPER_FIELDS = frozenset({
    "object_refs", "caller_id", "caller_kind",
    "rationale", "idempotency_key", "snapshot",
})


class KBMCPHandler:
    """
    MCP-compatible tool handler. Provides tool descriptors (list_tools)
    and tool invocation (call_tool) matching the MCP protocol shape.
    """

    def __init__(self, db_path: str, instance_code: str = "default"):
        self.db_path = db_path
        self.instance_code = instance_code
        self._service: Optional[AIKBService] = None
        self._ont_services: Optional[Dict[str, Any]] = None

    def _get_service(self) -> AIKBService:
        if self._service is None:
            self._service = AIKBService(self.db_path, self.instance_code)
        return self._service

    # --- MCP protocol: tools ---

    def _get_ontology_services(self) -> Dict[str, Any]:
        """Lazily build ontology services against db_path / instance domain.

        Returns dict with kb / registry(gate closed) / identity / proposals /
        decisions. Structure registry is read-only at runtime.
        """
        if self._ont_services is None:
            from ai_kb.db import AIKB
            from ai_kb.ontology import (
                ActionRegistry,
                AssemblyGate,
                IdentityService,
                ProposalService,
            )
            from ai_kb.ontology.decision import DecisionService

            kb = AIKB(self.db_path)
            kb.connect()
            kb.init_ontology_tables()
            # 运行期：gate 保持关闭，register_* 一律拒绝
            registry = ActionRegistry(kb, gate=AssemblyGate(open_by_default=False))
            identity = IdentityService(kb)
            decisions = DecisionService(kb)
            proposals = ProposalService(kb, registry, decisions=decisions)
            self._ont_services = {
                "kb": kb,
                "registry": registry,
                "identity": identity,
                "proposals": proposals,
                "decisions": decisions,
            }
        return self._ont_services

    # --- MCP protocol: tools ---

    def list_tools(self) -> List[Dict[str, Any]]:
        """Return MCP tool descriptors (name, description, inputSchema).

        = static KB tools + static six ontology tools (backward compatible)
        + dynamic enumeration from ont_action_type / ont_function_def
          (P5.1, §3.2): active actions -> ont_propose_<name>, deterministic
        active functions -> ont_compute_<name>. Tool names are globally
        unique: duplicates raise ValueError (fail-fast at enumeration).
        """
        tools = list(AIKBService.mcp_tools())
        tools.extend(self.ontology_tool_descriptors())
        tools.extend(self._dynamic_ontology_tools())
        seen: set[str] = set()
        duplicates: List[str] = []
        for descriptor in tools:
            name = descriptor["name"]
            if name in seen:
                duplicates.append(name)
            seen.add(name)
        if duplicates:
            raise ValueError(
                f"MCP tool name conflict(s): {sorted(set(duplicates))}"
            )
        return tools

    def _dynamic_ontology_tools(self) -> List[Dict[str, Any]]:
        """P5.1: enumerate action/function registry rows into tool descriptors.

        Runtime read-only: uses the registry built by
        _get_ontology_services() whose AssemblyGate stays closed. Only
        propose_*/compute_* tools are ever generated here; commit remains
        internal to ProposalService (§7 invariant 2).
        """
        ont = self._get_ontology_services()
        registry = ont["registry"]

        tools: List[Dict[str, Any]] = []
        for action in registry.list_actions(self.instance_code):
            if action.get("status") != "active":
                continue
            params_schema = action.get("params_schema") or {}
            properties = dict((params_schema.get("properties") or {}))
            required = list(params_schema.get("required") or [])
            properties.update({
                "object_refs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Operational object references this proposal targets.",
                },
                "caller_id": {"type": "string"},
                "caller_kind": {"type": "string", "enum": ["human", "agent"]},
                "rationale": {"type": "string"},
                "idempotency_key": {"type": "string"},
            })
            if "object_refs" not in required:
                required.append("object_refs")
            target = action.get("writeback_target")
            target_note = (
                f" writeback target: {target}." if target else " no external writeback target."
            )
            tools.append({
                "name": f"ont_propose_{action['name']}",
                "category": "propose_",
                "description": (
                    f"Propose action {action['name']!r} on object type "
                    f"{action.get('object_type')!r}: creates a pending "
                    f"proposal (target snapshot only, zero writes)."
                    f"{target_note} Commit happens only via human review."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            })

        for fn in registry.list_functions(self.instance_code):
            if fn.get("status") != "active" or int(fn.get("deterministic") or 0) != 1:
                continue
            io_schema = fn.get("io_schema") or {}
            tools.append({
                "name": f"ont_compute_{fn['name']}",
                "category": "compute_",
                "description": (
                    f"Run deterministic function {fn['name']!r} "
                    f"(kind={fn.get('kind')!r}). Advice only, zero writes."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": dict(io_schema.get("properties") or {}),
                    "required": list(io_schema.get("required") or []),
                },
            })
        return tools

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

        if tool.startswith("ont_"):
            return self._call_ontology_tool(tool, arguments)

        return {"error": f"Unknown tool: {tool_name}"}

    def _call_ontology_tool(self, tool: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch the six ontology tools (§4 three-way classification).

        Hard constraint: no execute_*/write_*/commit_* tool exists; commit is
        triggered only inside ProposalService via review/auto policy.
        """
        import json as _json

        ont = self._get_ontology_services()
        registry = ont["registry"]
        identity = ont["identity"]
        proposals = ont["proposals"]

        if tool == "ont_query_object":
            # query_: resolve + object read, ABAC filtered
            identity_id = identity.resolve(
                arguments["source_system"], arguments["source_key"]
            )
            if identity_id is None:
                return {"found": False}
            row = ont["kb"].execute(
                "SELECT * FROM ont_identity WHERE id = ?", (identity_id,)
            ).fetchone()
            obj = dict(row)
            obj["metadata"] = _safe_json_obj(obj.get("metadata"))
            caller_attrs = arguments.get("caller_attrs") or {
                "user_id": arguments.get("caller_id", "anonymous"),
                "role": "viewer",
                "clearance": "internal",
            }
            from ai_kb.permissions import PermissionChecker

            perms = None
            if isinstance(obj["metadata"], dict):
                perms = obj["metadata"].get("permissions")
            if isinstance(perms, (dict, list)):
                perms = _json.dumps(perms, ensure_ascii=False)
            if not PermissionChecker(ont["kb"]).can_access_doc(caller_attrs, perms):
                return {"found": True, "allowed": False, "error": "access denied"}
            obj["found"] = True
            obj["allowed"] = True
            return obj

        if tool == "ont_compute_risk":
            # compute_: run bound function, advice only, zero writes
            fn = registry.get_function(self.instance_code, arguments["function"])
            if fn is None:
                return {"error": f"function not found: {arguments['function']}"}
            from ai_kb.ontology.actions import load_handler

            handler = load_handler(fn["handler_ref"])
            result = handler(
                arguments.get("snapshot", {}), arguments.get("params", {})
            )
            return {"function": arguments["function"], "result": result}

        if tool == "ont_propose_action":
            # propose_: pending + snapshot only
            return proposals.propose_action(
                self.instance_code,
                arguments["action"],
                arguments["object_refs"],
                arguments.get("params", {}),
                caller_id=arguments.get("caller_id", "agent"),
                caller_kind=arguments.get("caller_kind", "agent"),
                rationale=arguments.get("rationale"),
                idempotency_key=arguments.get("idempotency_key"),
            )

        if tool == "ont_list_actions":
            # query_: tool discovery
            return {"actions": registry.list_actions(self.instance_code)}

        if tool == "ont_get_proposal":
            # query_: status lookup
            try:
                return proposals.get(int(arguments["proposal_id"]))
            except ValueError as exc:
                return {"error": str(exc)}

        if tool == "ont_review_proposal":
            # propose_(human): only human role; commit happens internally
            return proposals.review(
                int(arguments["proposal_id"]),
                arguments["decision"],
                arguments.get("reviewer", "human"),
                reviewer_kind=arguments.get("reviewer_kind", "human"),
                auto_commit=arguments.get("auto_commit", True),
            )

        # P5.1: dynamic dispatch for ont_propose_<name> / ont_compute_<name>
        if tool.startswith("ont_propose_"):
            name = tool[len("ont_propose_"):]
            return proposals.propose_action(
                self.instance_code,
                name,
                arguments["object_refs"],
                arguments.get("params", {k: v for k, v in arguments.items()
                                        if k not in _PROPOSE_WRAPPER_FIELDS}),
                caller_id=arguments.get("caller_id", "agent"),
                caller_kind=arguments.get("caller_kind", "agent"),
                rationale=arguments.get("rationale"),
                idempotency_key=arguments.get("idempotency_key"),
            )

        if tool.startswith("ont_compute_"):
            name = tool[len("ont_compute_"):]
            fn = registry.get_function(self.instance_code, name)
            if fn is None:
                return {"error": f"function not found: {name}"}
            from ai_kb.ontology.actions import load_handler

            handler = load_handler(fn["handler_ref"])
            # Advice only, zero writes: handlers read snapshot/params.
            result = handler(
                arguments.get("snapshot", {}),
                arguments.get("params", arguments),
            )
            return {"function": name, "result": result}

        return {"error": f"Unknown ontology tool: {tool}"}

    @staticmethod
    def ontology_tool_descriptors() -> List[Dict[str, Any]]:
        """MCP descriptors for the six ontology tools (§4).

        Each descriptor carries "category": query_ | compute_ | propose_.
        """
        return [
            {
                "name": "ont_query_object",
                "category": "query_",
                "description": "Resolve and read an operational object (ABAC filtered). Read-only.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "source_system": {"type": "string"},
                        "source_key": {"type": "string"},
                        "caller_id": {"type": "string"},
                        "caller_attrs": {"type": "object"},
                    },
                    "required": ["source_system", "source_key"],
                },
            },
            {
                "name": "ont_compute_risk",
                "category": "compute_",
                "description": "Run a registered risk/compute function. Advice only, zero writes.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "function": {"type": "string"},
                        "snapshot": {"type": "object"},
                        "params": {"type": "object"},
                    },
                    "required": ["function"],
                },
            },
            {
                "name": "ont_propose_action",
                "category": "propose_",
                "description": "Propose an action: creates a pending proposal with target snapshot only.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string"},
                        "object_refs": {"type": "array", "items": {"type": "string"}},
                        "params": {"type": "object"},
                        "caller_id": {"type": "string"},
                        "caller_kind": {"type": "string", "enum": ["human", "agent"]},
                        "rationale": {"type": "string"},
                        "idempotency_key": {"type": "string"},
                    },
                    "required": ["action", "object_refs"],
                },
            },
            {
                "name": "ont_list_actions",
                "category": "query_",
                "description": "List registered action types (tool discovery). Read-only.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "ont_get_proposal",
                "category": "query_",
                "description": "Get proposal status/detail. Read-only.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"proposal_id": {"type": "integer"}},
                    "required": ["proposal_id"],
                },
            },
            {
                "name": "ont_review_proposal",
                "category": "propose_",
                "description": "Human review (approve/reject) a validated proposal. Internal commit only.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "proposal_id": {"type": "integer"},
                        "decision": {"type": "string", "enum": ["approve", "reject"]},
                        "reviewer": {"type": "string"},
                        "reviewer_kind": {"type": "string", "enum": ["human", "agent"]},
                        "auto_commit": {"type": "boolean", "default": True},
                    },
                    "required": ["proposal_id", "decision"],
                },
            },
        ]

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
        if self._ont_services is not None:
            self._ont_services["kb"].close()
            self._ont_services = None
        if self._service:
            self._service.close()
            self._service = None


def _safe_json_obj(value: Any) -> Any:
    """Best-effort JSON parse for stored text fields (MCP response shaping)."""
    if value is None or not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value
