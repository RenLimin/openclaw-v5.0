"""
Enterprise AI Knowledge Base
L2 Infrastructure Component · Generic KB for any domain
"""
__version__ = "1.0.0"

from .db import AIKB
from .search import HybridSearch
from .api import AIKBService
from .graphrag import GraphRAG
from .permissions import PermissionChecker
from .audit import AuditLogger
from .template import TemplateManager

__all__ = [
    "AIKB",
    "HybridSearch",
    "AIKBService",
    "GraphRAG",
    "PermissionChecker",
    "AuditLogger",
    "TemplateManager",
]
