from __future__ import annotations

import re
from collections import Counter

from .kg import KnowledgeGraph
from .models import KnowledgeTriple, ThoughtNode


PARALLEL_RELATIONS = {
    "instance_of",
    "subclass_of",
    "use",
    "uses",
    "has_part",
    "part_of",
    "field_of_work",
    "main_subject",
    "facet_of",
    "models",
    "improves",
    "strong_at",
    "weak_at",
}

CHAIN_RELATIONS = {
    "causes",
    "depends_on",
    "has_risk",
    "requires",
    "reduces",
    "supports",
}

QUERY_COMPLEXITY_MARKERS = {
    "分析",
    "比较",
    "为什么",
    "如何",
    "怎么",
    "流程",
    "影响",
    "风险",
    "优化",
    "提升",
    "区别",
    "关系",
    "原因",
    "compare",
    "why",
    "how",
    "process",
    "impact",
    "risk",
    "optimize",
    "improve",
    "relationship",
}


class KGGraphBuilder:
    """Build a KG-guided thought DAG before text expansion.

    The builder no longer assumes the fixed n1/n2/n3/n4 shape. It uses the
    question and retrieved KG relations to choose a variable number of evidence
    nodes, then turns relation chains such as A -> B -> C into DAG edges.
    """

    def __init__(
        self,
        kg: KnowledgeGraph,
        min_branches: int = 1,
        max_branches: int = 5,
    ) -> None:
        self.kg = kg
        self.min_branches = min_branches
        self.max_branches = max_branches

    def build(self, query: str, evidence: list[KnowledgeTriple]) -> list[ThoughtNode]:
        if not evidence:
            return []

        branch_count = self._target_branch_count(query, evidence)
        selected = self._select_evidence(query, evidence, branch_count)
        if not selected:
            return []

        root_entity = self._root_entity(selected)
        root_name = self.kg.display_name(root_entity)
        root = ThoughtNode(
            id="n1",
            claim=f"将问题锚定到知识图谱核心实体“{root_name}”，并以检索到的关系事实生成后续 DAG 节点。",
            entity_id=root_entity,
            relation="semantic_anchor",
            confidence=0.92,
            verified=True,
            evidence=selected[:1],
            metadata={
                "kg_role": "root_anchor",
                "branch_target": len(selected),
                "selection_reason": "query_and_relation_guided",
            },
        )

        branches: list[ThoughtNode] = []
        for index, triple in enumerate(selected, start=2):
            head = triple.head_name or self.kg.display_name(triple.head)
            tail = triple.tail_name or self.kg.display_name(triple.tail)
            branches.append(
                ThoughtNode(
                    id=f"n{index}",
                    claim=f"依据 KG 关系“{head} -[{triple.relation}]-> {tail}”生成一个证据节点。",
                    entity_id=triple.head,
                    relation=triple.relation,
                    depends_on=["n1"],
                    confidence=max(0.72, triple.confidence),
                    verified=True,
                    evidence=[triple],
                    metadata={
                        "kg_role": "parallel_branch",
                        "source_relation": triple.relation,
                        "source_head": triple.head,
                        "source_tail": triple.tail,
                    },
                )
            )

        self._add_kg_chain_dependencies(branches)
        terminal_branch_ids = self._terminal_branch_ids(branches)
        aggregate = ThoughtNode(
            id=f"n{len(branches) + 2}",
            claim="聚合 KG-DAG 中的终端证据节点，统一术语、消解分支差异，并形成面向问题的综合结论。",
            entity_id=root_entity,
            relation="kg_guided_aggregate",
            depends_on=terminal_branch_ids,
            confidence=0.84,
            verified=False,
            evidence=selected,
            metadata={
                "kg_role": "aggregation",
                "aggregates": terminal_branch_ids,
                "dynamic_branch_count": len(branches),
            },
        )
        return [root, *branches, aggregate]

    def _target_branch_count(self, query: str, evidence: list[KnowledgeTriple]) -> int:
        relation_count = len({triple.relation for triple in evidence})
        entity_count = len({item for triple in evidence for item in (triple.head, triple.tail)})
        complexity_bonus = self._query_complexity(query)
        raw_target = max(self.min_branches, relation_count + complexity_bonus)
        if entity_count <= 2:
            raw_target = min(raw_target, 2)
        return max(self.min_branches, min(self.max_branches, len(evidence), raw_target))

    def _select_evidence(
        self,
        query: str,
        evidence: list[KnowledgeTriple],
        target_count: int,
    ) -> list[KnowledgeTriple]:
        query_tokens = self._tokens(query)
        scored = [
            (
                self._score_triple(triple, query_tokens),
                -index,
                triple,
            )
            for index, triple in enumerate(evidence)
        ]
        scored.sort(reverse=True, key=lambda item: (item[0], item[1]))

        selected: list[KnowledgeTriple] = []
        seen_edges: set[tuple[str, str, str]] = set()
        relation_counter: Counter[str] = Counter()
        for _score, _index, triple in scored:
            edge_key = (triple.head, triple.relation, triple.tail)
            if edge_key in seen_edges:
                continue
            if relation_counter[triple.relation] and self._has_unused_relation(scored, selected):
                continue
            selected.append(triple)
            seen_edges.add(edge_key)
            relation_counter[triple.relation] += 1
            if len(selected) >= target_count:
                return selected

        for _score, _index, triple in scored:
            if triple not in selected:
                selected.append(triple)
            if len(selected) >= target_count:
                break
        return selected

    def _score_triple(self, triple: KnowledgeTriple, query_tokens: set[str]) -> float:
        label = " ".join(
            [
                triple.head,
                triple.tail,
                triple.head_name,
                triple.tail_name,
                triple.relation,
            ]
        ).lower()
        overlap = sum(1 for token in query_tokens if token in label)
        relation_weight = 0.25 if triple.relation in CHAIN_RELATIONS else 0.15
        if triple.relation in PARALLEL_RELATIONS:
            relation_weight += 0.1
        return triple.confidence + overlap * 0.22 + relation_weight

    def _has_unused_relation(
        self,
        scored: list[tuple[float, int, KnowledgeTriple]],
        selected: list[KnowledgeTriple],
    ) -> bool:
        selected_relations = {triple.relation for triple in selected}
        return any(triple.relation not in selected_relations for _score, _index, triple in scored)

    def _add_kg_chain_dependencies(self, branches: list[ThoughtNode]) -> None:
        for node in branches:
            triple = node.evidence[0]
            if triple.relation not in CHAIN_RELATIONS:
                continue
            for candidate in branches:
                if candidate.id == node.id:
                    continue
                candidate_triple = candidate.evidence[0]
                if candidate_triple.tail == triple.head and self._can_depend(node, candidate, branches):
                    node.depends_on = [dep for dep in node.depends_on if dep != "n1"]
                    node.depends_on.append(candidate.id)
                    break

    def _can_depend(self, node: ThoughtNode, candidate: ThoughtNode, branches: list[ThoughtNode]) -> bool:
        graph = {branch.id: set(branch.depends_on) for branch in branches}
        graph.setdefault(node.id, set()).add(candidate.id)
        return not self._has_path(graph, candidate.id, node.id)

    def _terminal_branch_ids(self, branches: list[ThoughtNode]) -> list[str]:
        depended_on = {dep for node in branches for dep in node.depends_on if dep != "n1"}
        terminal = [node.id for node in branches if node.id not in depended_on]
        return terminal or [node.id for node in branches]

    def _root_entity(self, evidence: list[KnowledgeTriple]) -> str:
        endpoints = Counter()
        for triple in evidence:
            endpoints[triple.head] += 1
            endpoints[triple.tail] += 1
        return endpoints.most_common(1)[0][0]

    def _query_complexity(self, query: str) -> int:
        marker_bonus = sum(1 for marker in QUERY_COMPLEXITY_MARKERS if marker.lower() in query.lower())
        separator_bonus = len(re.findall(r"[，,；;、?？]", query)) // 2
        length_bonus = min(2, len(query) // 45)
        return min(2, marker_bonus // 2 + separator_bonus + length_bonus)

    @staticmethod
    def _tokens(text: str) -> set[str]:
        latin = re.findall(r"[A-Za-z][A-Za-z0-9_-]+", text.lower())
        chinese = re.findall(r"[\u4e00-\u9fff]{2,}", text)
        return set(latin + chinese)

    @staticmethod
    def _has_path(graph: dict[str, set[str]], start: str, target: str) -> bool:
        stack = list(graph.get(start, set()))
        seen: set[str] = set()
        while stack:
            current = stack.pop()
            if current == target:
                return True
            if current in seen:
                continue
            seen.add(current)
            stack.extend(graph.get(current, set()))
        return False
