"""
Template system for AI KB: define KB structure and behavior, instantiate quickly
"""
import yaml
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from .db import AIKB


@dataclass
class Template:
    """KB template definition"""
    template_id: str
    name: str
    version: str
    description: Optional[str]
    author: Optional[str]
    category: Optional[str]
    config: Dict[str, Any]

    @classmethod
    def from_yaml(cls, template_id: str, yaml_content: str) -> 'Template':
        """Load template from YAML"""
        data = yaml.safe_load(yaml_content)
        return cls(
            template_id=template_id,
            name=data.get('name', template_id),
            version=data.get('version', '1.0.0'),
            description=data.get('description'),
            author=data.get('author'),
            category=data.get('category'),
            config=data
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "template_id": self.template_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "category": self.category,
            "config": self.config
        }

    def to_yaml(self) -> str:
        return yaml.dump(self.config, default_flow_style=False)



# --- Built-in templates (design doc §5) ---

BUILTIN_TEMPLATES: Dict[str, str] = {
    "generic-doc-kb": """
name: 通用文档知识库
version: 1.0.0
description: 最基础的模板，适合通用文档管理
author: ai-knowledge-base
category: general
entity_types:
  - Document
retrieval:
  entity_weight: 0.3
  fts_weight: 0.35
  vector_weight: 0.35
categories: []
""",
    "product-kb": """
name: 产品知识库
version: 1.0.0
description: 面向产品型企业的知识库模板
author: ai-knowledge-base
category: business
entity_types:
  - Product
  - Solution
  - Whitepaper
retrieval:
  entity_weight: 0.5
  fts_weight: 0.25
  vector_weight: 0.25
categories:
  - name: 产品线
    children:
      - name: 核心产品
      - name: 解决方案
      - name: 白皮书
""",
    "tech-doc-kb": """
name: 技术文档库
version: 1.0.0
description: 面向技术团队的知识库模板
author: ai-knowledge-base
category: engineering
entity_types:
  - Document
  - API
  - Component
retrieval:
  entity_weight: 0.2
  fts_weight: 0.4
  vector_weight: 0.4
categories:
  - name: 架构设计
  - name: 接口文档
  - name: 运维手册
""",
}


class TemplateManager:
    """Manage KB templates"""

    def __init__(self, db: AIKB):
        self.db = db
        self.ensure_builtin_templates()

    def ensure_builtin_templates(self) -> int:
        """Register built-in templates if missing. Returns number created."""
        created = 0
        for tid, yaml_content in BUILTIN_TEMPLATES.items():
            if self.get_template(tid) is None:
                tpl = Template.from_yaml(tid, yaml_content)
                self.save_template(tpl)
                created += 1
        return created

    def save_template(self, template: Template) -> int:
        """Save or update template in database"""
        config_yaml = template.to_yaml()
        return self.db.save_template(
            template.template_id,
            template.name,
            template.version,
            template.description,
            template.author,
            template.category,
            config_yaml
        )

    def get_template(self, template_id: str) -> Optional[Template]:
        """Get template by id"""
        cursor = self.db.execute("SELECT * FROM kb_template WHERE template_id = ?", (template_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return Template(
            template_id=row['template_id'],
            name=row['name'],
            version=row['version'],
            description=row['description'],
            author=row['author'],
            category=row['category'],
            config=yaml.safe_load(row['config_yaml'])
        )

    def list_templates(self, category: Optional[str] = None) -> List[Template]:
        """List all templates"""
        if category:
            cursor = self.db.execute("SELECT * FROM kb_template WHERE category = ? ORDER BY name", (category,))
        else:
            cursor = self.db.execute("SELECT * FROM kb_template ORDER BY name")
        templates = []
        for row in cursor.fetchall():
            templates.append(Template(
                template_id=row['template_id'],
                name=row['name'],
                version=row['version'],
                description=row['description'],
                author=row['author'],
                category=row['category'],
                config=yaml.safe_load(row['config_yaml'])
            ))
        return templates

    def create_instance_from_template(self,
                                     template_id: str,
                                     instance_code: str,
                                     instance_name: str,
                                     instance_description: Optional[str] = None,
                                     overrides: Optional[Dict[str, Any]] = None) -> int:
        """
        Create a new KB instance from template.
        Returns domain_id of the new instance.
        """
        template = self.get_template(template_id)
        if not template:
            raise ValueError(f"Template {template_id} not found")

        # Create domain
        domain_id = self.db.get_or_create_domain(
            name=instance_name,
            code=instance_code,
            description=instance_description or template.description or ""
        )

        # Create categories from template
        config = template.config
        if 'categories' in config:
            self._create_categories(domain_id, config['categories'])

        # TODO: create default permissions, roles
        return domain_id

    def _create_categories(self, domain_id: int, categories: List[Dict], parent_id: Optional[int] = None):
        """Recursively create category tree"""
        for cat in categories:
            collection_id = self.db.get_or_create_collection(
                domain_id=domain_id,
                name=cat['name'],
                parent_id=parent_id
            )
            if 'children' in cat and cat['children']:
                self._create_categories(domain_id, cat['children'], collection_id)
