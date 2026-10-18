"""
Knowledge extractor: automatically extract entities and relations from text
Supports:
  - Rule-based entity extraction based on pattern matching
  - Dictionary-based entity matching
  - Relation extraction based on dependency parsing (optional if stanza installed)
  - Auto build knowledge graph with entities and relations
"""
import re
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass

from ai_kb.db import AIKB


@dataclass
class ExtractedEntity:
    """Extracted entity from text"""
    name: str
    entity_type: str
    start: int  # start char position
    end: int    # end char position
    aliases: List[str] = None
    confidence: float = 1.0


@dataclass
class ExtractedRelation:
    """Extracted relation between two entities"""
    subject: ExtractedEntity
    predicate: str
    object: ExtractedEntity
    confidence: float = 1.0
    context: str = ""


class KnowledgeExtractor:
    """
    Extract entities and relations from text, auto build knowledge graph.
    Rule + dictionary based, optionally uses stanza for relation extraction.
    """

    def __init__(self, domain_patterns: Dict[str, str] = None, dictionary: Dict[str, List[str]] = None):
        """
        Initialize knowledge extractor.
        Args:
            domain_patterns: regex patterns for entity types: {type: pattern}
            dictionary: {entity_type: [list_of_entity_names]} for dictionary matching
        """
        self.domain_patterns = domain_patterns or {}
        self.dictionary = dictionary or {}
        self._stanza_nlp = None

    @property
    def stanza_nlp(self):
        """Lazy load stanza NLP pipeline"""
        if self._stanza_nlp is None:
            try:
                import stanza
                stanza.download('en')
                self._stanza_nlp = stanza.Pipeline(lang='en', processors='tokenize,lemma,pos,depparse')
            except ImportError:
                self._stanza_nlp = None
        return self._stanza_nlp

    def extract_entities(self, text: str) -> List[ExtractedEntity]:
        """Extract entities from text using patterns and dictionary matching"""
        entities = []

        # 1. Pattern-based extraction
        for entity_type, pattern in self.domain_patterns.items():
            matches = list(re.finditer(pattern, text, re.IGNORECASE))
            for match in matches:
                entities.append(ExtractedEntity(
                    name=match.group(0).strip(),
                    entity_type=entity_type,
                    start=match.start(),
                    end=match.end(),
                    confidence=0.9
                ))

        # 2. Dictionary-based exact matching
        for entity_type, names in self.dictionary.items():
            for name in names:
                pattern = re.compile(r'\b' + re.escape(name) + r'\b', re.IGNORECASE)
                matches = list(pattern.finditer(text))
                for match in matches:
                    # Skip if already covered by a higher confidence entity
                    overlap = any(
                        e.start <= match.start() <= e.end or
                        match.start() <= e.start <= match.end()
                        for e in entities
                    )
                    if not overlap:
                        entities.append(ExtractedEntity(
                            name=match.group(0).strip(),
                            entity_type=entity_type,
                            start=match.start(),
                            end=match.end(),
                            confidence=1.0
                        ))

        # Sort by start position
        entities.sort(key=lambda e: e.start)
        return entities

    def extract_relations(
        self,
        text: str,
        entities: List[ExtractedEntity]
    ) -> List[ExtractedRelation]:
        """Extract relations between entities. Use stanza if available, else rule-based."""
        relations = []

        if len(entities) < 2:
            return relations

        nlp = self.stanza_nlp
        if nlp is not None:
            # Use stanza dependency parsing for relation extraction
            relations = self._extract_relations_stanza(text, entities)
        else:
            # Simple rule-based: adjacent entities in same sentence
            relations = self._extract_relations_rule(text, entities)

        return relations

    def _extract_relations_rule(
        self,
        text: str,
        entities: List[ExtractedEntity]
    ) -> List[ExtractedRelation]:
        """Simple rule-based relation extraction: co-occurrence in same sentence"""
        relations = []
        sentences = re.split(r'(?<=[。！？!?\n])', text)

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # Find entities in this sentence
            entities_in_sent = [
                e for e in entities
                if sentence[e.start - sentence.start:e.end - sentence.start]
            ]
            # Pairwise all combinations
            for i in range(len(entities_in_sent)):
                for j in range(i+1, len(entities_in_sent)):
                    subj = entities_in_sent[i]
                    obj = entities_in_sent[j]
                    # Relation predicate is "related_to" as default
                    relations.append(ExtractedRelation(
                        subject=subj,
                        predicate="related_to",
                        object=obj,
                        context=sentence,
                        confidence=0.5
                    ))
        return relations

    def _extract_relations_stanza(
        self,
        text: str,
        entities: List[ExtractedEntity]
    ) -> List[ExtractedRelation]:
        """Stanza-based relation extraction using dependency parsing"""
        import stanza
        relations = []
        doc = self.stanza_nlp(text)

        # Map entities to tokens
        entity_token_map: Dict[int, ExtractedEntity] = {}
        for sent in doc.sentences:
            for token in sent.tokens:
                for entity in entities:
                    if token.start_char >= entity.start and token.end_char <= entity.end:
                        entity_token_map[token.id] = entity

        # Find subject-verb-object triples
        for sent in doc.sentences:
            # Find root verb
            root = None
            for word in sent.words:
                if word.deprel == "root":
                    root = word
                    break
            if root is None:
                continue

            # Find subject and object
            subj_word = None
            obj_word = None
            for word in sent.words:
                if word.head == root.id and word.deprel in ("nsubj", "nsubj:pass"):
                    subj_word = word
                if word.head == root.id and word.deprel in ("obj", "obj:pass"):
                    obj_word = word

            if subj_word is not None and obj_word is not None:
                subj_entity = entity_token_map.get(subj_word.id)
                obj_entity = entity_token_map.get(obj_word.id)
                if subj_entity and obj_entity:
                    relations.append(ExtractedRelation(
                        subject=subj_entity,
                        predicate=root.lemma,
                        object=obj_entity,
                        context=sent.text,
                        confidence=0.8
                    ))

        return relations

    def add_to_knowledge_graph(
        self,
        kb: AIKB,
        domain_id: int,
        text: str,
        doc_id: int
    ) -> Tuple[List[int], List[int]]:
        """
        Auto extract entities and relations and add to knowledge graph in AIKB.
        Returns: (entity_ids, relation_ids)
        """
        entities = self.extract_entities(text)
        relations = self.extract_relations(text, entities)

        entity_ids: List[int] = []
        # Add entities
        for ent in entities:
            code = f"{ent.entity_type}_{hash(ent.name.lower())}"
            entity_id = kb.get_or_create_entity(
                domain_id=domain_id,
                entity_type=ent.entity_type,
                name=ent.name,
                code=code,
                aliases=ent.aliases
            )
            entity_ids.append(entity_id)

        relation_ids: List[int] = []
        # Add relations
        for rel in relations:
            # Find entity ids for subject and object
            # FIXME: map extracted entities to db ids
            # For now, we rely on the order being the same
            # This needs improvement
            try:
                subj_idx = entities.index(rel.subject)
                obj_idx = entities.index(rel.object)
                subj_id = entity_ids[subj_idx]
                obj_id = entity_ids[obj_idx]
                rid = kb.add_relation(
                    subject_id=subj_id,
                    relation_type=rel.predicate,
                    object_id=obj_id,
                    confidence=rel.confidence
                )
                relation_ids.append(rid)
            except ValueError:
                continue

        return entity_ids, relation_ids
