from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .kg import KnowledgeGraph
from .kg_graph_builder import KGGraphBuilder
from .llm import LLMClient, MockLLMClient
from .models import KnowledgeTriple
from .models import GenerationResult, NodeStatus, ThoughtNode
from .rules import RuleEngine
from .scheduler import DAGScheduler


KG_PRIORITY_QUERY_TERMS = {
    "verify",
    "verification",
    "fact checking",
    "evidence",
    "source",
    "source attribution",
    "provenance",
    "retrieval",
    "entity linking",
    "grounding",
    "grounded",
    "groundedness",
    "hallucination",
    "contradiction",
    "conflict",
    "dependency",
    "dependencies",
    "aggregate",
    "aggregation",
    "knowledge graph",
    "kg",
    "检索",
    "证据",
    "验证",
    "校验",
    "幻觉",
    "依赖",
    "聚合",
    "知识图谱",
}


@dataclass(frozen=True)
class KGStrategyDecision:
    strategy: str
    score: float
    reason: str


class GenerationPipeline:
    def __init__(
        self,
        kg: KnowledgeGraph,
        llm: LLMClient | None = None,
        max_workers: int = 4,
    ) -> None:
        self.kg = kg
        self.llm = llm or MockLLMClient()
        self.rules = RuleEngine(kg)
        self.scheduler = DAGScheduler(max_workers=max_workers)
        self.graph_builder = KGGraphBuilder(kg)

    @classmethod
    def from_sample(cls) -> "GenerationPipeline":
        root = Path(__file__).resolve().parents[2]
        return cls(KnowledgeGraph.from_json(root / "data" / "sample_kg.json"))

    def generate(self, query: str) -> GenerationResult:
        return self.generate_with_options(query)

    def generate_with_options(
        self,
        query: str,
        max_nodes: int | None = None,
        skip_aggregate: bool = False,
        use_kg_graph_builder: bool = True,
        adaptive_kg: bool = True,
        min_kg_relevance_score: float = 0.70,
        min_kg_overlap: float = 0.08,
    ) -> GenerationResult:
        evidence = self._initial_evidence(query)
        decision = self._select_kg_strategy(
            query,
            evidence,
            use_kg_graph_builder,
            adaptive_kg,
            min_kg_relevance_score,
            min_kg_overlap,
        )
        kg_strategy = decision.strategy
        nodes = self.graph_builder.build(query, evidence) if kg_strategy == "kg_dag" else []
        if not nodes:
            plan_evidence = evidence if kg_strategy == "llm_plan_no_kg_graph" else []
            nodes = self.llm.plan(query, plan_evidence)
            if kg_strategy == "kg_dag":
                kg_strategy = "llm_plan_fallback"
        if max_nodes is not None:
            nodes = self._limit_nodes(nodes, max_nodes)
        rules = self.rules if kg_strategy in {"kg_dag", "llm_plan_no_kg_graph"} else RuleEngine(
            KnowledgeGraph(entities={}, triples=[], constraints=[])
        )
        nodes, events = rules.apply(nodes)
        nodes = self.scheduler.run(nodes, lambda node, context: self.llm.expand(query, node, context))
        done_nodes = self._ordered_done_nodes(nodes)
        final_text = self._fallback_aggregate(query, done_nodes) if skip_aggregate else self.llm.aggregate(query, done_nodes)
        return GenerationResult(
            query=query,
            nodes=nodes,
            rule_events=events,
            final_text=final_text,
            metadata={
                "evidence_count": len(evidence),
                "max_nodes": max_nodes,
                "skip_aggregate": skip_aggregate,
                "use_kg_graph_builder": use_kg_graph_builder,
                "adaptive_kg": adaptive_kg,
                "kg_strategy": kg_strategy,
                "kg_relevance_score": decision.score,
                "kg_relevance_reason": decision.reason,
                "min_kg_relevance_score": min_kg_relevance_score,
                "min_kg_overlap": min_kg_overlap,
                "relation_type_count": len({triple.relation for triple in evidence}),
                "llm_call_logs": [log.__dict__ for log in getattr(self.llm, "call_logs", [])],
            },
        )

    def _initial_evidence(self, query: str):
        entities = self.kg.link_entities(query)
        evidence = []
        for entity in entities:
            evidence.extend(self.kg.neighbors(entity.id, hops=1))
        return evidence

    def _select_kg_strategy(
        self,
        query: str,
        evidence,
        use_kg_graph_builder: bool,
        adaptive_kg: bool,
        min_kg_relevance_score: float,
        min_kg_overlap: float,
    ) -> KGStrategyDecision:
        if not use_kg_graph_builder:
            return KGStrategyDecision("llm_plan_no_kg_graph", 0.0, "kg_graph_builder_disabled")
        if not evidence:
            return KGStrategyDecision("llm_plan_no_evidence", 0.0, "no_linked_kg_evidence")
        if not adaptive_kg:
            return KGStrategyDecision("kg_dag", 1.0, "adaptive_gate_disabled")

        relation_count = len({triple.relation for triple in evidence})
        entity_count = len({item for triple in evidence for item in (triple.head, triple.tail)})
        query_lower = query.lower()
        is_kg_priority_query = any(term in query_lower for term in KG_PRIORITY_QUERY_TERMS)
        relevance_score, overlap_ratio = self._kg_relevance_score(query, evidence, is_kg_priority_query)

        enough_structure = len(evidence) >= 3 and relation_count >= 2 and entity_count >= 3
        sparse_general_evidence = (
            not is_kg_priority_query
            and len(evidence) < 6
            and relevance_score < max(min_kg_relevance_score + 0.12, 0.72)
        )
        if (
            enough_structure
            and relevance_score >= min_kg_relevance_score
            and (overlap_ratio >= min_kg_overlap or is_kg_priority_query)
            and not sparse_general_evidence
        ):
            return KGStrategyDecision(
                "kg_dag",
                relevance_score,
                f"score={relevance_score:.3f}, overlap={overlap_ratio:.3f}, evidence={len(evidence)}, relations={relation_count}",
            )
        return KGStrategyDecision(
            "llm_plan_weak_kg",
            relevance_score,
            f"weak_kg(score={relevance_score:.3f}, overlap={overlap_ratio:.3f}, evidence={len(evidence)}, relations={relation_count})",
        )

    def _kg_relevance_score(
        self,
        query: str,
        evidence: list[KnowledgeTriple],
        is_kg_priority_query: bool,
    ) -> tuple[float, float]:
        query_tokens = self._tokens(query)
        evidence_tokens = self._evidence_tokens(evidence)
        if query_tokens:
            overlap_ratio = len(query_tokens & evidence_tokens) / len(query_tokens)
        else:
            overlap_ratio = 0.0

        relation_count = len({triple.relation for triple in evidence})
        entity_count = len({item for triple in evidence for item in (triple.head, triple.tail)})
        avg_confidence = sum(triple.confidence for triple in evidence) / max(1, len(evidence))

        evidence_score = min(1.0, len(evidence) / 12)
        relation_score = min(1.0, relation_count / 4)
        entity_score = min(1.0, entity_count / 8)
        confidence_score = min(1.0, max(0.0, avg_confidence))
        overlap_score = min(1.0, overlap_ratio / 0.35)
        priority_bonus = 0.12 if is_kg_priority_query else 0.0

        score = (
            overlap_score * 0.35
            + evidence_score * 0.18
            + relation_score * 0.18
            + entity_score * 0.14
            + confidence_score * 0.15
            + priority_bonus
        )
        return min(1.0, round(score, 3)), round(overlap_ratio, 3)

    @staticmethod
    def _tokens(text: str) -> set[str]:
        latin = re.findall(r"[A-Za-z][A-Za-z0-9_-]+", text.lower())
        chinese = re.findall(r"[\u4e00-\u9fff]{2,}", text)
        return set(latin + chinese)

    def _evidence_tokens(self, evidence: list[KnowledgeTriple]) -> set[str]:
        text = " ".join(
            " ".join(
                [
                    triple.head,
                    triple.tail,
                    triple.head_name or self.kg.display_name(triple.head),
                    triple.tail_name or self.kg.display_name(triple.tail),
                    triple.relation,
                ]
            )
            for triple in evidence
        )
        return self._tokens(text.replace("_", " "))

    @staticmethod
    def _ordered_done_nodes(nodes: list[ThoughtNode]) -> list[ThoughtNode]:
        return [node for node in nodes if node.status == NodeStatus.DONE]

    @staticmethod
    def _limit_nodes(nodes: list[ThoughtNode], max_nodes: int) -> list[ThoughtNode]:
        if max_nodes <= 0:
            return []
        if (
            len(nodes) > max_nodes
            and max_nodes >= 3
            and nodes[-1].metadata.get("kg_role") == "aggregation"
        ):
            kept = [*nodes[: max_nodes - 1], nodes[-1]]
        else:
            kept = nodes[:max_nodes]
        kept_ids = {node.id for node in kept}
        for node in kept:
            node.depends_on = [dep for dep in node.depends_on if dep in kept_ids]
        aggregate_nodes = [node for node in kept if node.metadata.get("kg_role") == "aggregation"]
        if aggregate_nodes:
            aggregate = aggregate_nodes[-1]
            branch_ids = [
                node.id for node in kept if node.metadata.get("kg_role") == "parallel_branch"
            ]
            if not aggregate.depends_on and branch_ids:
                aggregate.depends_on = branch_ids
        return kept

    @staticmethod
    def _fallback_aggregate(query: str, nodes: list[ThoughtNode]) -> str:
        lines = [f"问题：{query}", "", "生成结果："]
        for index, node in enumerate(nodes, start=1):
            lines.append(f"{index}. {node.content}")
        return "\n".join(lines)
