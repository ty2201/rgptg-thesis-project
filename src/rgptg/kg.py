from __future__ import annotations

import json
import re
from pathlib import Path

from .models import Entity, KnowledgeTriple


class KnowledgeGraph:
    def __init__(
        self,
        entities: dict[str, Entity],
        triples: list[KnowledgeTriple],
        constraints: list[dict[str, str]],
    ) -> None:
        self.entities = entities
        self.triples = triples
        self.constraints = constraints
        self._alias_index = self._build_alias_index()

    @classmethod
    def from_json(cls, path: str | Path) -> "KnowledgeGraph":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        entities = {
            item["id"]: Entity(
                id=item["id"],
                name=item["name"],
                aliases=tuple(item.get("aliases", [])),
                description=item.get("description", ""),
            )
            for item in raw.get("entities", [])
        }
        triples = [KnowledgeTriple(**item) for item in raw.get("triples", [])]
        return cls(entities, triples, raw.get("constraints", []))

    def link_entities(self, text: str) -> list[Entity]:
        lowered = text.lower()
        found: list[Entity] = []
        for token, entity_id in self._alias_index.items():
            entity = self.entities[entity_id]
            if self._matches_token(token, lowered) and entity not in found:
                found.append(entity)
        return found

    def neighbors(self, entity_id: str, hops: int = 1) -> list[KnowledgeTriple]:
        frontier = {entity_id}
        seen_entities = {entity_id}
        collected: list[KnowledgeTriple] = []
        for _ in range(max(1, hops)):
            next_frontier: set[str] = set()
            for triple in self.triples:
                if triple.head in frontier or triple.tail in frontier:
                    collected.append(triple)
                    if triple.head not in seen_entities:
                        next_frontier.add(triple.head)
                    if triple.tail not in seen_entities:
                        next_frontier.add(triple.tail)
            seen_entities.update(next_frontier)
            frontier = next_frontier
        return [self._with_names(triple) for triple in self._dedupe_triples(collected)]

    def relation_conflicts(self, relation: str | None, evidence: list[KnowledgeTriple]) -> bool:
        if not relation:
            return False
        opposites = {
            item["relation"]: item["opposite"]
            for item in self.constraints
            if item.get("severity") == "hard"
        }
        return any(opposites.get(triple.relation) == relation for triple in evidence)

    def display_name(self, entity_id: str | None) -> str:
        if not entity_id:
            return "unlinked entity"
        return self.entities.get(entity_id, Entity(entity_id, entity_id)).name

    def _with_names(self, triple: KnowledgeTriple) -> KnowledgeTriple:
        return KnowledgeTriple(
            head=triple.head,
            relation=triple.relation,
            tail=triple.tail,
            confidence=triple.confidence,
            head_name=self.display_name(triple.head),
            tail_name=self.display_name(triple.tail),
        )

    def _build_alias_index(self) -> dict[str, str]:
        index: dict[str, str] = {}
        for entity in self.entities.values():
            index.setdefault(entity.name, entity.id)
            index.setdefault(entity.id, entity.id)
            for alias in entity.aliases:
                index.setdefault(alias, entity.id)
        return index

    @staticmethod
    def _matches_token(token: str, lowered_text: str) -> bool:
        token = token.strip()
        if not token:
            return False
        lowered_token = token.lower()
        if re.fullmatch(r"[a-z0-9_.+-]+", lowered_token):
            return re.search(rf"(?<![a-z0-9]){re.escape(lowered_token)}(?![a-z0-9])", lowered_text) is not None
        return lowered_token in lowered_text

    @staticmethod
    def _dedupe_triples(triples: list[KnowledgeTriple]) -> list[KnowledgeTriple]:
        seen: set[tuple[str, str, str]] = set()
        result: list[KnowledgeTriple] = []
        for triple in triples:
            key = (triple.head, triple.relation, triple.tail)
            if key not in seen:
                result.append(triple)
                seen.add(key)
        return result
