"""知识点领域模型。

CISSP 八大域 + 树形层级结构。
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import Field

from base.base_model import TenantModel


class CISSPDomain(str, Enum):
    """CISSP 八大知识域（2021 CBK）。"""
    SECURITY_RISK_MANAGEMENT = "security_risk_management"
    ASSET_SECURITY = "asset_security"
    SECURITY_ARCHITECTURE = "security_architecture"
    COMMUNICATION_NETWORK_SECURITY = "communication_network_security"
    IDENTITY_ACCESS_MANAGEMENT = "identity_access_management"
    SECURITY_ASSESSMENT_TESTING = "security_assessment_testing"
    SECURITY_OPERATIONS = "security_operations"
    SOFTWARE_DEVELOPMENT_SECURITY = "software_development_security"


class KnowledgeLevel(str, Enum):
    """掌握程度。"""
    NOT_STARTED = "not_started"   # 未开始
    FAMILIAR = "familiar"         # 了解
    UNDERSTAND = "understand"     # 理解
    PROFICIENT = "proficient"     # 熟练
    EXPERT = "expert"             # 精通


class KnowledgePoint(TenantModel):
    """知识点聚合根 — 树形层级结构。

    支持多级目录（如：域 → 章节 → 知识点），通过 parent_id 构成树。
    """

    # ── 基本信息 ────────────────────────────────────────────────
    title: str
    description: str = ""
    content: str = ""            # 知识点详细内容（Markdown）

    # ── 分类 ────────────────────────────────────────────────────
    domain: Optional[CISSPDomain] = None  # 所属 CISSP 域
    category: str = "general"    # 分类标签（自定义）

    # ── 树形结构 ────────────────────────────────────────────────
    parent_id: Optional[str] = None       # 父节点 ID，None 表示根节点
    path: str = ""                        # 层级路径，如 "root/chapter1/topicA"
    depth: int = 0                        # 层级深度（0 为根）
    sort_order: int = 0                   # 同级排序

    # ── 掌握程度 ────────────────────────────────────────────────
    level: KnowledgeLevel = KnowledgeLevel.NOT_STARTED

    # ── 统计 ────────────────────────────────────────────────────
    view_count: int = 0
    note_count: int = 0
    quiz_count: int = 0

    tags: List[str] = Field(default_factory=list)
    is_leaf: bool = True         # 是否叶子节点

    # ── 方法 ────────────────────────────────────────────────────

    def update_level(self, level: KnowledgeLevel) -> None:
        """更新掌握程度。"""
        self.level = level

    def increment_view(self) -> None:
        """浏览次数 +1。"""
        self.view_count += 1

    def is_root(self) -> bool:
        """是否根节点。"""
        return self.parent_id is None or self.depth == 0

    def is_descendant_of(self, ancestor_path: str) -> bool:
        """判断是否是某个节点的后代。"""
        if not self.path:
            return False
        return self.path.startswith(ancestor_path + "/") or self.path == ancestor_path
