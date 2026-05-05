from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from ..llm import LLMClient
from ..models import KnowledgeTriple, ThoughtNode
from ..prompts import AGGREGATION_PROMPT, EXPANSION_PROMPT, SKELETON_PROMPT


@dataclass
class LLMCallLog:
    stage: str
    elapsed_ms: float
    prompt_chars: int
    output_chars: int
    attempt: int


class OpenAICompatibleClient(LLMClient):
    """Minimal adapter for OpenAI-compatible chat completion endpoints.

    It intentionally uses only the Python standard library. If the remote model
    does not return valid JSON for planning, a clear ValueError is raised.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: int = 60,
        max_tokens: int = 900,
        stage_max_tokens: dict[str, int] | None = None,
        retries: int = 1,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.stage_max_tokens = stage_max_tokens or {}
        self.retries = retries
        self.call_logs: list[LLMCallLog] = []

    def plan(self, query: str, evidence: list[KnowledgeTriple]) -> list[ThoughtNode]:
        prompt = SKELETON_PROMPT.format(query=query, evidence=self._format_evidence(evidence))
        text = self._chat(prompt, stage="plan")
        try:
            raw_payload = json.loads(_strip_code_fence(text))
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM planning response is not valid JSON: {text[:300]}") from exc
        raw_nodes = raw_payload["nodes"] if isinstance(raw_payload, dict) and "nodes" in raw_payload else raw_payload
        return [_coerce_node(item) for item in raw_nodes]

    def expand(self, query: str, node: ThoughtNode, context: dict[str, str]) -> str:
        prompt = EXPANSION_PROMPT.format(
            query=query,
            node=json.dumps(node.__dict__, ensure_ascii=False, default=str),
            context=json.dumps(context, ensure_ascii=False),
            evidence=self._format_evidence(node.evidence),
        )
        return self._chat(prompt, stage=f"expand:{node.id}")

    def aggregate(self, query: str, nodes: list[ThoughtNode]) -> str:
        contents = "\n\n".join(f"{node.id}: {node.content}" for node in nodes)
        prompt = AGGREGATION_PROMPT.format(query=query, contents=contents)
        return self._chat(prompt, stage="aggregate")

    def _chat(self, prompt: str, stage: str) -> str:
        max_tokens = self._max_tokens_for_stage(stage)
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 2):
            started = time.perf_counter()
            request = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = json.loads(response.read().decode("utf-8"))
                text = raw["choices"][0]["message"]["content"]
                elapsed = (time.perf_counter() - started) * 1000
                self.call_logs.append(
                    LLMCallLog(
                        stage=stage,
                        elapsed_ms=round(elapsed, 2),
                        prompt_chars=len(prompt),
                        output_chars=len(text),
                        attempt=attempt,
                    )
                )
                return text
            except urllib.error.URLError as exc:
                last_error = exc
                if attempt <= self.retries:
                    time.sleep(min(2 * attempt, 5))
        raise RuntimeError(f"LLM request failed after retries: {last_error}")

    @staticmethod
    def _format_evidence(evidence: list[KnowledgeTriple]) -> str:
        if not evidence:
            return "[]"
        return json.dumps(
            [
                {
                    "head": item.head,
                    "head_name": item.head_name,
                    "relation": item.relation,
                    "tail": item.tail,
                    "tail_name": item.tail_name,
                    "confidence": item.confidence,
                }
                for item in evidence
            ],
            ensure_ascii=False,
            indent=2,
        )

    def _max_tokens_for_stage(self, stage: str) -> int:
        if stage.startswith("expand:"):
            return self.stage_max_tokens.get("expand", self.max_tokens)
        return self.stage_max_tokens.get(stage, self.max_tokens)


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped


def _coerce_node(item: dict) -> ThoughtNode:
    return ThoughtNode(
        id=str(item.get("id", "n1")),
        claim=str(item.get("claim", "")),
        entity_id=item.get("entity_id"),
        relation=item.get("relation"),
        depends_on=list(item.get("depends_on") or []),
        confidence=float(item.get("confidence", 0.7)),
        verified=bool(item.get("verified", False)),
    )
