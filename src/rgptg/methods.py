from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .llm import LLMClient
from .models import GenerationResult, NodeStatus, ThoughtNode
from .pipeline import GenerationPipeline
from .scheduler import DAGScheduler


@dataclass(frozen=True)
class MethodContext:
    pipeline: GenerationPipeline


class GenerationMethod(ABC):
    name: str

    @abstractmethod
    def generate(self, query: str, context: MethodContext) -> GenerationResult:
        """Run one generation strategy."""


class DirectGenerationMethod(GenerationMethod):
    name = "direct"

    def generate(self, query: str, context: MethodContext) -> GenerationResult:
        llm = context.pipeline.llm
        node = ThoughtNode(
            id="d1",
            claim="直接围绕用户问题生成完整回答，不进行显式骨架规划和并行调度。",
            confidence=0.65,
            verified=False,
        )
        node.content = llm.expand(query, node, {})
        node.status = NodeStatus.DONE
        final_text = llm.aggregate(query, [node])
        return GenerationResult(query=query, nodes=[node], rule_events=[], final_text=final_text)


class SkeletonOfThoughtMethod(GenerationMethod):
    name = "sot"

    def __init__(self, max_workers: int = 4) -> None:
        self.scheduler = DAGScheduler(max_workers=max_workers)

    def generate(self, query: str, context: MethodContext) -> GenerationResult:
        llm = context.pipeline.llm
        nodes = _plain_sot_nodes(llm, query)
        nodes = self.scheduler.run(nodes, lambda node, ctx: llm.expand(query, node, ctx))
        final_text = llm.aggregate(query, [node for node in nodes if node.status == NodeStatus.DONE])
        return GenerationResult(query=query, nodes=nodes, rule_events=[], final_text=final_text)


class RuleGuidedMethod(GenerationMethod):
    name = "rule_guided"

    def generate(self, query: str, context: MethodContext) -> GenerationResult:
        return context.pipeline.generate(query)


def build_methods(names: list[str] | None = None, max_workers: int = 4) -> list[GenerationMethod]:
    registry: dict[str, GenerationMethod] = {
        "direct": DirectGenerationMethod(),
        "sot": SkeletonOfThoughtMethod(max_workers=max_workers),
        "rule_guided": RuleGuidedMethod(),
    }
    selected = names or ["direct", "sot", "rule_guided"]
    unknown = [name for name in selected if name not in registry]
    if unknown:
        raise ValueError(f"Unknown generation methods: {', '.join(unknown)}")
    return [registry[name] for name in selected]


def _plain_sot_nodes(llm: LLMClient, query: str) -> list[ThoughtNode]:
    nodes = llm.plan(query, evidence=[])
    for index, node in enumerate(nodes, start=1):
        node.id = f"s{index}"
        node.depends_on = []
        node.evidence = []
        node.verified = False
        node.status = NodeStatus.READY
    return nodes
