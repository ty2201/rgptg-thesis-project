from __future__ import annotations

from pathlib import Path

from .kg import KnowledgeGraph
from .kg_graph_builder import KGGraphBuilder
from .llm import LLMClient, MockLLMClient
from .models import GenerationResult, NodeStatus, ThoughtNode
from .rules import RuleEngine
from .scheduler import DAGScheduler


KG_PRIORITY_QUERY_TERMS = {
    "verify",
    "verification",
    "evidence",
    "grounding",
    "grounded",
    "hallucination",
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
    ) -> GenerationResult:
        evidence = self._initial_evidence(query)
        kg_strategy = self._select_kg_strategy(query, evidence, use_kg_graph_builder, adaptive_kg)
        nodes = self.graph_builder.build(query, evidence) if kg_strategy == "kg_dag" else []
        if not nodes:
            nodes = self.llm.plan(query, evidence)
            if kg_strategy == "kg_dag":
                kg_strategy = "llm_plan_fallback"
        if max_nodes is not None:
            nodes = self._limit_nodes(nodes, max_nodes)
        nodes, events = self.rules.apply(nodes)
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
    ) -> str:
        if not use_kg_graph_builder:
            return "llm_plan_no_kg_graph"
        if not evidence:
            return "llm_plan_no_evidence"
        if not adaptive_kg:
            return "kg_dag"

        relation_count = len({triple.relation for triple in evidence})
        entity_count = len({item for triple in evidence for item in (triple.head, triple.tail)})
        query_lower = query.lower()
        is_kg_priority_query = any(term in query_lower for term in KG_PRIORITY_QUERY_TERMS)

        if len(evidence) >= 6 and relation_count >= 2:
            return "kg_dag"
        if is_kg_priority_query and len(evidence) >= 3 and entity_count >= 3:
            return "kg_dag"
        return "llm_plan_weak_kg"

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
