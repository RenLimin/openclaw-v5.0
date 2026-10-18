"""
GraphRAG module for L2 AI KB
Add knowledge graph relation enhancement to hybrid retrieval
"""
from typing import List, Dict, Optional, Tuple, Set
from .db import AIKB


class GraphRAG:
    def __init__(self, kb: AIKB):
        self.kb = kb

    def add_relation(self, subject_type: str, subject_id: int,
                     relation_type: str, object_type: str, object_id: int,
                     metadata: Optional[str] = None, permissions: Optional[str] = None) -> int:
        """Add a relation between two entities"""
        now = self.kb.get_now()
        cursor = self.kb.execute("""
        INSERT INTO kb_relation (subject_type, subject_id, relation_type, object_type, object_id,
                               metadata, permissions, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (subject_type, subject_id, relation_type, object_type, object_id,
              metadata, permissions, now))
        self.kb.commit()
        return cursor.lastrowid

    def get_relations(self, subject_type: str, subject_id: int,
                      relation_type: Optional[str] = None) -> List[Dict]:
        """Get all relations for a subject entity"""
        if relation_type:
            cursor = self.kb.execute("""
            SELECT * FROM kb_relation
            WHERE subject_type = ? AND subject_id = ? AND relation_type = ?
            """, (subject_type, subject_id, relation_type))
        else:
            cursor = self.kb.execute("""
            SELECT * FROM kb_relation
            WHERE subject_type = ? AND subject_id = ?
            """, (subject_type, subject_id))
        results = []
        for row in cursor.fetchall():
            # Get the object entity info
            obj = self.kb.get_entity(row['object_id'])
            results.append({
                'relation': dict(row),
                'object': dict(obj) if obj else None
            })
        return results

    def expand_related_entities(self, start_entity_id: int, max_depth: int = 2) -> Set[int]:
        """Expand all related entities starting from a given entity, up to max_depth"""
        visited = set()
        queue = [(start_entity_id, 0)]
        visited.add(start_entity_id)

        while queue:
            entity_id, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            # Get all outgoing relations
            cursor = self.kb.execute("""
            SELECT object_id FROM kb_relation WHERE subject_id = ?
            """, (entity_id,))
            for (obj_id,) in cursor.fetchall():
                if obj_id not in visited:
                    visited.add(obj_id)
                    queue.append((obj_id, depth + 1))
            # Get all incoming relations (reverse)
            cursor = self.kb.execute("""
            SELECT subject_id FROM kb_relation WHERE object_id = ?
            """, (entity_id,))
            for (subj_id,) in cursor.fetchall():
                if subj_id not in visited:
                    visited.add(subj_id)
                    queue.append((subj_id, depth + 1))
        return visited

    def graph_enhanced_search(self, domain_id: int, query: str,
                             start_entity_name: Optional[str] = None,
                             max_related: int = 10, top_k: int = 5,
                             include_expired: bool = False) -> List[Dict]:
        """Graph enhanced hybrid search:
        1. If start_entity_name provided, expand related entities from it
        2. Do hybrid search only within expanded subgraph
        3. Return enhanced results
        """
        from .search import HybridSearch

        related_ids = set()
        if start_entity_name:
            entities = self.kb.find_entities_by_name(domain_id, start_entity_name, limit=1, include_expired=include_expired)
            if entities:
                start_id = entities[0]['id']
                related_ids = self.expand_related_entities(start_id, max_depth=2)
                related_ids.add(start_id)

        # Do normal hybrid search
        hs = HybridSearch(self.kb, domain_id, include_expired=include_expired)
        all_results = hs.search(query, top_k=top_k * 3)

        # Filter results if we have related entities
        if related_ids:
            filtered = []
            for res in all_results:
                entity_id = res['entity']['id']
                if entity_id in related_ids:
                    # Skip expired entities unless explicitly included
                    if not include_expired and res['entity']['status'] == 'expired':
                        continue
                    filtered.append(res)
            # If not enough, add back some from all results
            if len(filtered) < top_k:
                existing = set(r['chunk']['id'] for r in filtered)
                for res in all_results:
                    if res['chunk']['id'] not in existing:
                        if not include_expired and res['entity']['status'] == 'expired':
                            continue
                        filtered.append(res)
                        if len(filtered) >= top_k:
                            break
            return filtered[:top_k]
        else:
            return all_results[:top_k]

    def extract_entities_and_relations(self, text: str, llm_client) -> List[Dict]:
        """Use LLM to extract entities and relations from text.
        Caller provides llm_client that accepts prompt and returns structured output.
        This is a placeholder, actual implementation depends on your LLM setup.
        """
        prompt = f"""
        Extract all entities and relationships from the following text:

        Text: {text[:2000]}

        Output format (JSON):
        {{
          "entities": [
            {{"name": "Entity Name", "type": "entity_type", "family": "optional_family"}}
          ],
          "relations": [
            {{
              "subject_name": "Subject Name",
              "subject_type": "subject_type",
              "relation_type": "relation_type",
              "object_name": "Object Name",
              "object_type": "object_type"
            }}
          ]
        }}
        """
        # Caller handles LLM inference
        return llm_client(prompt)

