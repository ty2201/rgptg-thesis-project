from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass

from .models import GenerationResult, NodeStatus


@dataclass
class EvaluationMetrics:
    latency_ms: float
    node_count: int
    dependency_count: int
    pruned_count: int
    evidence_triple_count: int
    evidence_node_ratio: float
    relation_diversity: float
    entity_coverage_score: float
    grounding_score: float
    hallucination_risk_score: float
    graph_structure_score: float
    verified_ratio: float
    parallelizable_ratio: float
    coverage_score: float
    coherence_score: float

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


class Timer:
    def __enter__(self) -> "Timer":
        self.started = time.perf_counter()
        self.elapsed_ms = 0.0
        return self

    def __exit__(self, *_args) -> None:
        self.elapsed_ms = (time.perf_counter() - self.started) * 1000


def evaluate_result(result: GenerationResult, latency_ms: float) -> EvaluationMetrics:
    nodes = result.nodes
    node_count = len(nodes)
    dependency_count = sum(len(node.depends_on) for node in nodes)
    pruned_count = sum(node.status == NodeStatus.PRUNED for node in nodes)
    evidence_triple_count = sum(len(node.evidence) for node in nodes)
    evidence_node_count = sum(1 for node in nodes if node.evidence)
    relation_diversity = _relation_diversity(result)
    verified_count = sum(node.verified for node in nodes)
    root_count = sum(not node.depends_on for node in nodes if node.status != NodeStatus.PRUNED)
    active_count = max(1, sum(node.status != NodeStatus.PRUNED for node in nodes))

    entity_coverage_score = _entity_coverage_score(result)
    evidence_density = min(1.0, evidence_triple_count / max(1, node_count * 3))
    grounding_score = min(
        1.0,
        evidence_node_count / max(1, node_count) * 0.35
        + verified_count / max(1, node_count) * 0.30
        + evidence_density * 0.20
        + entity_coverage_score * 0.15,
    )
    graph_structure_score = _graph_structure_score(result)

    return EvaluationMetrics(
        latency_ms=latency_ms,
        node_count=node_count,
        dependency_count=dependency_count,
        pruned_count=pruned_count,
        evidence_triple_count=evidence_triple_count,
        evidence_node_ratio=round(evidence_node_count / max(1, node_count), 3),
        relation_diversity=round(relation_diversity, 3),
        entity_coverage_score=round(entity_coverage_score, 3),
        grounding_score=round(grounding_score, 3),
        hallucination_risk_score=round(1 - grounding_score, 3),
        graph_structure_score=round(graph_structure_score, 3),
        verified_ratio=round(verified_count / max(1, node_count), 3),
        parallelizable_ratio=round(root_count / active_count, 3),
        coverage_score=round(_coverage_score(result.query, result.final_text), 3),
        coherence_score=round(_coherence_score(result), 3),
    )


def _coverage_score(query: str, text: str) -> float:
    tokens = _tokens(query)
    if not tokens:
        return 1.0
    matched = sum(1 for token in tokens if token.lower() in text.lower())
    return matched / len(tokens)


def _coherence_score(result: GenerationResult) -> float:
    active_nodes = [node for node in result.nodes if node.status != NodeStatus.PRUNED]
    if not active_nodes:
        return 0.0
    linked = sum(1 for node in active_nodes if node.depends_on or node.verified)
    has_summary = "综合" in result.final_text or "结论" in result.final_text
    base = linked / len(active_nodes)
    return min(1.0, base + (0.15 if has_summary else 0.0))


def _tokens(text: str) -> list[str]:
    latin = re.findall(r"[A-Za-z][A-Za-z0-9_-]+", text)
    chinese = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    return latin + chinese


def _relation_diversity(result: GenerationResult) -> float:
    relations = [triple.relation for node in result.nodes for triple in node.evidence]
    if not relations:
        return 0.0
    return len(set(relations)) / len(relations)


def _entity_coverage_score(result: GenerationResult) -> float:
    names = []
    for node in result.nodes:
        for triple in node.evidence:
            names.extend([triple.head_name, triple.tail_name])
    names = [name for name in dict.fromkeys(names) if name and not name.startswith("Q")]
    if not names:
        return 0.0
    text = result.final_text.lower()
    matched = sum(1 for name in names if name.lower() in text)
    return matched / len(names)


def _graph_structure_score(result: GenerationResult) -> float:
    nodes = result.nodes
    if not nodes:
        return 0.0
    roles = [node.metadata.get("kg_role") for node in nodes]
    has_root = "root_anchor" in roles
    has_branch = "parallel_branch" in roles
    has_aggregate = "aggregation" in roles
    aggregate_nodes = [node for node in nodes if node.metadata.get("kg_role") == "aggregation"]
    aggregate_has_two_inputs = any(len(node.depends_on) >= 2 for node in aggregate_nodes)
    branch_nodes = [node for node in nodes if node.metadata.get("kg_role") == "parallel_branch"]
    branches_reachable_from_root = bool(branch_nodes) and all(
        _has_dependency_path(nodes, node.id, "n1") for node in branch_nodes
    )
    score = sum([has_root, has_branch, has_aggregate, aggregate_has_two_inputs, branches_reachable_from_root]) / 5
    return float(score)


def _has_dependency_path(nodes, start_id: str, target_id: str) -> bool:
    by_id = {node.id: node for node in nodes}
    stack = list(by_id.get(start_id, ()).depends_on if start_id in by_id else [])
    seen = set()
    while stack:
        current = stack.pop()
        if current == target_id:
            return True
        if current in seen:
            continue
        seen.add(current)
        stack.extend(by_id.get(current, ()).depends_on if current in by_id else [])
    return False
