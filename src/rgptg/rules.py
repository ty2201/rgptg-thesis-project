from __future__ import annotations

from .kg import KnowledgeGraph
from .models import NodeStatus, RuleEvent, ThoughtNode


class RuleEngine:
    def __init__(self, kg: KnowledgeGraph, min_confidence: float = 0.55) -> None:
        self.kg = kg
        self.min_confidence = min_confidence

    def apply(self, nodes: list[ThoughtNode]) -> tuple[list[ThoughtNode], list[RuleEvent]]:
        events: list[RuleEvent] = []
        self._attach_evidence(nodes)
        self._mark_low_confidence(nodes, events)
        self._prune_conflicts(nodes, events)
        self._add_implicit_dependencies(nodes, events)
        return nodes, events

    def _attach_evidence(self, nodes: list[ThoughtNode]) -> None:
        for node in nodes:
            if node.entity_id:
                node.evidence = self.kg.neighbors(node.entity_id, hops=1)

    def _mark_low_confidence(self, nodes: list[ThoughtNode], events: list[RuleEvent]) -> None:
        for node in nodes:
            if node.confidence < self.min_confidence:
                node.status = NodeStatus.LOW_CONFIDENCE
                events.append(
                    RuleEvent(
                        rule="confidence_threshold",
                        node_id=node.id,
                        action="downgrade",
                        reason=f"confidence {node.confidence:.2f} < {self.min_confidence:.2f}",
                    )
                )

    def _prune_conflicts(self, nodes: list[ThoughtNode], events: list[RuleEvent]) -> None:
        for node in nodes:
            if self.kg.relation_conflicts(node.relation, node.evidence):
                node.status = NodeStatus.PRUNED
                events.append(
                    RuleEvent(
                        rule="kg_hard_constraint",
                        node_id=node.id,
                        action="prune",
                        reason="node relation conflicts with hard KG constraint",
                    )
                )

    def _add_implicit_dependencies(self, nodes: list[ThoughtNode], events: list[RuleEvent]) -> None:
        by_entity = {node.entity_id: node for node in nodes if node.entity_id}
        by_id = {node.id: node for node in nodes}
        for node in nodes:
            if node.status == NodeStatus.PRUNED:
                continue
            for triple in node.evidence:
                if triple.tail != node.entity_id:
                    continue
                candidate = by_entity.get(triple.head)
                if (
                    candidate
                    and candidate.id != node.id
                    and candidate.id not in node.depends_on
                    and not self._has_path(by_id, candidate.id, node.id)
                ):
                    node.depends_on.append(candidate.id)
                    events.append(
                        RuleEvent(
                            rule="implicit_dependency",
                            node_id=node.id,
                            action="add_dependency",
                            reason=f"{node.entity_id} is linked with {candidate.entity_id} by {triple.relation}",
                        )
                    )

    def _has_path(self, by_id: dict[str, ThoughtNode], start_id: str, target_id: str) -> bool:
        stack = [start_id]
        seen: set[str] = set()
        while stack:
            current = stack.pop()
            if current == target_id:
                return True
            if current in seen:
                continue
            seen.add(current)
            stack.extend(by_id.get(current, ThoughtNode(current, "")).depends_on)
        return False
