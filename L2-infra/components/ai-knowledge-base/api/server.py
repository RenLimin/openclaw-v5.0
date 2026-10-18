"""
FastAPI server for AI Knowledge Base
REST API exposing all KB operations
"""
import os
import json
from typing import List, Dict, Optional, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Body, UploadFile, File
from pydantic import BaseModel

from ai_kb.db import AIKB
from ai_kb.api import AIKBService
from ai_kb.ingestion import IngestionPipeline

app = FastAPI(
    title="AI Knowledge Base API",
    description="Enterprise AI Knowledge Base - Agent-independent, portable, multi-format document ingestion + hybrid retrieval",
    version="1.0.0"
)

# Global service registry: instance_code -> AIKBService
_service_registry: Dict[str, AIKBService] = {}
_db_path: str = ""


# === Request/Response models ===

class QueryRequest(BaseModel):
    question: str
    top_k: int = 5
    use_graph: bool = False
    start_entity: Optional[str] = None
    format: str = "markdown"
    include_expired: bool = False
    user_attrs: Optional[Dict[str, Any]] = None


class FeedbackRequest(BaseModel):
    query_text: str
    feedback_type: str  # useful / not_useful / incorrect
    answer_text: Optional[str] = None
    feedback_comment: Optional[str] = None
    entity_id: Optional[int] = None
    doc_id: Optional[int] = None
    chunk_id: Optional[int] = None
    user_id: Optional[str] = None


class BatchStatusRequest(BaseModel):
    entity_ids: List[int]
    status: str


class InstanceCreateRequest(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    template: str = "generic-doc-kb"


# === Helpers ===

def _get_service(instance_code: str) -> AIKBService:
    if instance_code not in _service_registry:
        raise HTTPException(status_code=404, detail=f"Instance {instance_code} not found or not loaded")
    return _service_registry[instance_code]


def _load_instances(db_path: str):
    """Load all domains as services"""
    kb = AIKB(db_path)
    kb.connect()
    domains = kb.get_all_domains()
    kb.close()
    for domain in domains:
        try:
            _service_registry[domain['code']] = AIKBService(db_path, domain['code'])
        except Exception as e:
            print(f"Warning: failed to load instance {domain['code']}: {e}")


# === Instance management ===

@app.get("/health")
def health():
    """Health check"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "instances_loaded": len(_service_registry),
        "instances": list(_service_registry.keys())
    }


@app.get("/api/v1/instances")
def list_instances():
    """List all loaded instances"""
    return {
        "instances": [
            {"code": code, "service": service.domain_code}
            for code, service in _service_registry.items()
        ]
    }


@app.post("/api/v1/instances")
def create_instance(req: InstanceCreateRequest):
    """Create a new KB instance"""
    global _db_path
    kb = AIKB(_db_path)
    kb.init_db()
    try:
        domain_id = kb.get_or_create_domain(req.name, req.code, req.description)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    kb.close()

    # Load service
    service = AIKBService(_db_path, req.code)
    _service_registry[req.code] = service
    return {
        "status": "success",
        "code": req.code,
        "domain_id": domain_id
    }


@app.get("/api/v1/instances/{instance_code}/stats")
def instance_stats(instance_code: str, include_expired: bool = False):
    """Get instance statistics"""
    service = _get_service(instance_code)
    return service.stats(include_expired)


# === Query ===

@app.post("/api/v1/instances/{instance_code}/query")
def query_kb(instance_code: str, req: QueryRequest):
    """Query the knowledge base"""
    service = _get_service(instance_code)
    try:
        return service.query(
            question=req.question,
            top_k=req.top_k,
            use_graph=req.use_graph,
            start_entity=req.start_entity,
            format=req.format,
            include_expired=req.include_expired
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Ingestion ===

@app.post("/api/v1/instances/{instance_code}/ingest/upload")
async def ingest_upload(instance_code: str, file: UploadFile = File(...)):
    """Upload and ingest a single file"""
    service = _get_service(instance_code)
    kb = service.kb

    # Save to temp file
    tmp_path = f"/tmp/kb_upload_{file.filename}"
    with open(tmp_path, "wb") as f:
        content = await file.read()
        f.write(content)

    pipeline = IngestionPipeline(kb)
    result = pipeline.ingest_single_file(service.domain_id, tmp_path)
    os.unlink(tmp_path)

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or "Ingestion failed")

    return {
        "status": "success",
        "doc_id": result.doc_id,
        "chunks_created": result.chunks_created,
        "quality_score": result.quality_score,
        "issues": result.issues,
        "pii_masked_count": len(result.pii_masked)
    }


@app.post("/api/v1/instances/{instance_code}/ingest/scan")
def ingest_scan(instance_code: str, dir_path: str = Body(..., embed=True)):
    """Scan a directory and ingest all supported files"""
    service = _get_service(instance_code)
    kb = service.kb
    pipeline = IngestionPipeline(kb)
    result = pipeline.scan_directory(service.domain_id, dir_path)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


# === Entities ===

@app.get("/api/v1/instances/{instance_code}/entities")
def list_entities(instance_code: str, collection_id: Optional[int] = None, status: Optional[str] = None):
    """List entities"""
    service = _get_service(instance_code)
    return service.list_entities(collection_id, status)


@app.get("/api/v1/instances/{instance_code}/entities/{entity_id}")
def get_entity(instance_code: str, entity_id: int):
    """Get entity detail"""
    service = _get_service(instance_code)
    entity = service.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


@app.post("/api/v1/instances/{instance_code}/entities/{entity_id}/expire")
def expire_entity(instance_code: str, entity_id: int):
    """Mark entity as expired"""
    service = _get_service(instance_code)
    return service.mark_entity_expired(entity_id)


@app.post("/api/v1/instances/{instance_code}/entities/batch-update-status")
def batch_update_status(instance_code: str, req: BatchStatusRequest):
    """Batch update entity status"""
    service = _get_service(instance_code)
    return service.batch_update_entity_status(req.entity_ids, req.status)


# === Feedback ===

@app.post("/api/v1/instances/{instance_code}/feedback")
def add_feedback(instance_code: str, req: FeedbackRequest):
    """Add feedback"""
    service = _get_service(instance_code)
    return service.add_feedback(
        query_text=req.query_text,
        feedback_type=req.feedback_type,
        answer_text=req.answer_text,
        feedback_comment=req.feedback_comment,
        entity_id=req.entity_id,
        doc_id=req.doc_id,
        chunk_id=req.chunk_id,
        user_id=req.user_id
    )


@app.get("/api/v1/instances/{instance_code}/feedback/stats/{entity_id}")
def feedback_stats(instance_code: str, entity_id: int):
    """Get feedback stats for an entity"""
    service = _get_service(instance_code)
    return service.get_entity_feedback_stats(entity_id)


@app.get("/api/v1/instances/{instance_code}/feedback/low-score")
def low_score_knowledge(instance_code: str, threshold: int = 1):
    """List low-score knowledge"""
    service = _get_service(instance_code)
    return service.list_low_score_knowledge(threshold)


# === MCP tools endpoint (JSON-RPC style) ===

@app.get("/api/v1/mcp/tools")
def mcp_tools():
    """List all MCP tool descriptors"""
    return AIKBService.mcp_tools()


def run_server(host: str = "0.0.0.0", port: int = 8000, config: str = ""):
    """Run the server"""
    import uvicorn

    global _db_path
    # Parse config file (YAML)
    if config and os.path.exists(config):
        try:
            import yaml
            with open(config, 'r') as f:
                cfg = yaml.safe_load(f)
            db_path = cfg.get('database', {}).get('path', './data/ai-kb.db')
            _db_path = db_path
        except Exception as e:
            print(f"Warning: failed to parse config {config}: {e}")
            _db_path = "./data/ai-kb.db"
    else:
        _db_path = "./data/ai-kb.db"

    # Ensure DB exists and init
    os.makedirs(os.path.dirname(_db_path) or '.', exist_ok=True)
    kb = AIKB(_db_path)
    kb.init_db()
    kb.close()

    # Load existing instances
    _load_instances(_db_path)
    print(f"AI KB server started at http://{host}:{port} (db: {_db_path})")
    print(f"Loaded instances: {list(_service_registry.keys())}")

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
