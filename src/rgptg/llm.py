from __future__ import annotations

from abc import ABC, abstractmethod

from .models import KnowledgeTriple, ThoughtNode


class LLMClient(ABC):
    @abstractmethod
    def plan(self, query: str, evidence: list[KnowledgeTriple]) -> list[ThoughtNode]:
        """Create structured thought nodes from a query and KG evidence."""

    @abstractmethod
    def expand(self, query: str, node: ThoughtNode, context: dict[str, str]) -> str:
        """Generate a detailed paragraph for one node."""

    @abstractmethod
    def aggregate(self, query: str, nodes: list[ThoughtNode]) -> str:
        """Merge node outputs into final text."""


class MockLLMClient(LLMClient):
    """Deterministic local generator used when no external LLM is configured."""

    def plan(self, query: str, evidence: list[KnowledgeTriple]) -> list[ThoughtNode]:
        if evidence:
            return self._evidence_guided_plan(query, evidence)
        nodes: list[ThoughtNode] = [
            ThoughtNode(
                id="n1",
                claim="明确任务类型与生成目标，判断是否适合启用并行骨架生成。",
                entity_id="sot",
                relation="uses",
                confidence=0.86,
                verified=True,
            ),
            ThoughtNode(
                id="n2",
                claim="利用知识图谱检索相关事实，降低事实幻觉和关键分支遗漏。",
                entity_id="kg",
                relation="reduces",
                depends_on=["n1"],
                confidence=0.88,
                verified=True,
            ),
            ThoughtNode(
                id="n3",
                claim="将骨架节点组织为思维图，显式标注强逻辑依赖。",
                entity_id="got",
                relation="models",
                depends_on=["n1"],
                confidence=0.84,
                verified=True,
            ),
            ThoughtNode(
                id="n4",
                claim="对违反知识图谱强约束的分支执行剪枝或低置信度标记。",
                entity_id="verification",
                relation="reduces",
                depends_on=["n2", "n3"],
                confidence=0.81,
                verified=True,
            ),
            ThoughtNode(
                id="n5",
                claim="聚合并行生成的分支，统一术语并补充段落间逻辑桥梁。",
                entity_id="dependency",
                relation="supports",
                depends_on=["n2", "n3", "n4"],
                confidence=0.78,
                verified=False,
            ),
        ]
        if any(marker in query for marker in ("证明", "推理", "数学", "依赖", "逻辑")):
            nodes.append(
                ThoughtNode(
                    id="n6",
                    claim="对强逻辑链条保留串行执行，避免纯并行破坏推理连续性。",
                    entity_id="cot",
                    relation="strong_at",
                    depends_on=["n3"],
                    confidence=0.83,
                    verified=True,
                )
            )
        return nodes

    def _evidence_guided_plan(self, query: str, evidence: list[KnowledgeTriple]) -> list[ThoughtNode]:
        nodes = [
            ThoughtNode(
                id="n1",
                claim="根据用户问题完成语义锚定，并将问题中的核心概念链接到知识图谱实体。",
                entity_id=evidence[0].head,
                relation=evidence[0].relation,
                confidence=0.9,
                verified=True,
                evidence=[evidence[0]],
            )
        ]
        for index, triple in enumerate(evidence[:4], start=2):
            nodes.append(
                ThoughtNode(
                    id=f"n{index}",
                    claim=(
                        f"利用知识图谱事实 {triple.head}-{triple.relation}-{triple.tail} "
                        "约束分支生成，减少无证据扩展。"
                    ),
                    entity_id=triple.head,
                    relation=triple.relation,
                    depends_on=["n1"],
                    confidence=max(0.7, triple.confidence),
                    verified=True,
                    evidence=[triple],
                )
            )
        nodes.append(
            ThoughtNode(
                id=f"n{len(nodes) + 1}",
                claim="综合 KG 证据分支，统一实体术语并形成最终回答。",
                entity_id=evidence[0].tail,
                relation="aggregate",
                depends_on=[node.id for node in nodes[1:]] or ["n1"],
                confidence=0.82,
                verified=False,
            )
        )
        return nodes

    def expand(self, query: str, node: ThoughtNode, context: dict[str, str]) -> str:
        dependency_text = ""
        if node.depends_on:
            ready = [context[item] for item in node.depends_on if item in context]
            if ready:
                dependency_text = "在前置结论基础上，"
        evidence_text = "; ".join(
            f"{item.head_name or item.head}-{item.relation}-{item.tail_name or item.tail}"
            for item in node.evidence[:2]
        )
        if evidence_text:
            evidence_text = f" 关联证据包括：{evidence_text}。"
        return f"{dependency_text}{node.claim}{evidence_text}该步骤服务于查询“{query}”，并为最终答案提供结构化支撑。"

    def aggregate(self, query: str, nodes: list[ThoughtNode]) -> str:
        usable = [node for node in nodes if node.content]
        lines = [f"问题：{query}", "", "生成结果："]
        for index, node in enumerate(usable, start=1):
            lines.append(f"{index}. {node.content}")
        lines.append("")
        has_evidence = any(node.evidence for node in usable)
        if has_evidence:
            lines.append(
                "综合来看，规则引导的并行文本生成会先检索与问题相关的知识图谱证据，"
                "再按事实关系和逻辑依赖组织分支，最后聚合为更有依据的回答。"
            )
        else:
            lines.append(
                "综合来看，规则引导的并行文本生成会先拆分问题，再展开各个分支，"
                "最后合并为结构清晰的回答。"
            )
        return "\n".join(lines)
