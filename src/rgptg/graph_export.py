from __future__ import annotations

from .kg import KnowledgeGraph
from .models import GenerationResult, NodeStatus


def to_mermaid(result: GenerationResult, kg: KnowledgeGraph | None = None) -> str:
    lines = ["flowchart TD"]
    for node in result.nodes:
        label = _label(node.id, node.claim, node.entity_id, kg)
        style = ":::pruned" if node.status == NodeStatus.PRUNED else ""
        lines.append(f'    {node.id}["{label}"]{style}')
    for node in result.nodes:
        for dep in node.depends_on:
            lines.append(f"    {dep} --> {node.id}")
    lines.append("    classDef pruned fill:#f8d7da,stroke:#842029,color:#842029;")
    return "\n".join(lines)


def to_dot(result: GenerationResult, kg: KnowledgeGraph | None = None) -> str:
    lines = ["digraph ThoughtGraph {", "  rankdir=LR;"]
    for node in result.nodes:
        label = _label(node.id, node.claim, node.entity_id, kg)
        color = "#842029" if node.status == NodeStatus.PRUNED else "#333333"
        lines.append(f'  {node.id} [label="{_escape(label)}", color="{color}"];')
    for node in result.nodes:
        for dep in node.depends_on:
            lines.append(f"  {dep} -> {node.id};")
    lines.append("}")
    return "\n".join(lines)


def _label(node_id: str, claim: str, entity_id: str | None, kg: KnowledgeGraph | None) -> str:
    entity = kg.display_name(entity_id) if kg else entity_id or "None"
    short_claim = claim if len(claim) <= 24 else claim[:24] + "..."
    return f"{node_id}: {entity}\\n{short_claim}"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
