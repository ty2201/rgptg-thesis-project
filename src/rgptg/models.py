from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NodeStatus(str, Enum):
    READY = "ready"
    PRUNED = "pruned"
    LOW_CONFIDENCE = "low_confidence"
    DONE = "done"


@dataclass(frozen=True)
class Entity:
    id: str
    name: str
    aliases: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class KnowledgeTriple:
    head: str
    relation: str
    tail: str
    confidence: float = 1.0
    head_name: str = ""
    tail_name: str = ""


@dataclass
class ThoughtNode:
    id: str
    claim: str
    entity_id: str | None = None
    relation: str | None = None
    depends_on: list[str] = field(default_factory=list)
    confidence: float = 0.7
    verified: bool = False
    status: NodeStatus = NodeStatus.READY
    evidence: list[KnowledgeTriple] = field(default_factory=list)
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleEvent:
    rule: str
    node_id: str
    action: str
    reason: str


@dataclass
class GenerationResult:
    query: str
    nodes: list[ThoughtNode]
    rule_events: list[RuleEvent]
    final_text: str
    metadata: dict[str, Any] = field(default_factory=dict)
