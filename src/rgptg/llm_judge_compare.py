from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

from .adapters.neo4j_kg import Neo4jKnowledgeGraph
from .adapters.openai_compatible import OpenAICompatibleClient
from .evaluation import evaluate_result
from .kg import KnowledgeGraph
from .methods import MethodContext, SkeletonOfThoughtMethod
from .pipeline import GenerationPipeline


DEFAULT_QUERY = "Explain how AlphaFold changed protein structure prediction and what limitations remain."


def run_compare(
    query: str,
    base_url: str,
    api_key: str,
    model: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    output_path: Path,
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for name, kg, method in [
        ("plain_sot", KnowledgeGraph(entities={}, triples=[], constraints=[]), "sot"),
        ("optimized_neo4j", Neo4jKnowledgeGraph.connect(neo4j_uri, neo4j_user, neo4j_password), "rule_guided"),
    ]:
        llm = OpenAICompatibleClient(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout=60,
            max_tokens=700,
            stage_max_tokens={"plan": 500, "expand": 320, "aggregate": 600},
            retries=1,
        )
        pipeline = GenerationPipeline(kg=kg, llm=llm, max_workers=1)
        started = time.perf_counter()
        if method == "sot":
            result = SkeletonOfThoughtMethod(max_workers=1).generate(query, MethodContext(pipeline=pipeline))
        else:
            result = pipeline.generate_with_options(query, max_nodes=5, skip_aggregate=False)
        elapsed_ms = (time.perf_counter() - started) * 1000
        metrics = evaluate_result(result, elapsed_ms).to_dict()
        results[name] = {
            "metrics": metrics,
            "final_text": result.final_text,
            "node_count": len(result.nodes),
            "dependency_count": sum(len(node.depends_on) for node in result.nodes),
            "evidence_count": result.metadata.get("evidence_count", 0),
            "nodes": [
                {
                    "id": node.id,
                    "claim": node.claim,
                    "depends_on": node.depends_on,
                    "evidence": [
                        {
                            "head": item.head_name or item.head,
                            "relation": item.relation,
                            "tail": item.tail_name or item.tail,
                        }
                        for item in node.evidence
                    ],
                }
                for node in result.nodes
            ],
            "llm_call_logs": [log.__dict__ for log in llm.call_logs],
        }

    judge = _judge(
        query=query,
        answer_a=results["plain_sot"]["final_text"],
        answer_b=results["optimized_neo4j"]["final_text"],
        base_url=base_url,
        api_key=api_key,
        model=model,
    )
    payload = {
        "query": query,
        "mapping": {"A": "plain_sot", "B": "optimized_neo4j"},
        "results": results,
        "judge": judge,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(payload, output_path.with_suffix(".md"))
    return payload


def _judge(
    query: str,
    answer_a: str,
    answer_b: str,
    base_url: str,
    api_key: str,
    model: str,
) -> str:
    prompt = f"""
You are an impartial evaluator. Compare two answers to the same user question.

Question:
{query}

Answer A:
{answer_a}

Answer B:
{answer_b}

Evaluate on factuality, relevance, structure, clarity, and usefulness.
Return concise JSON with this schema:
{{
  "scores": {{
    "A": {{"factuality": 1-10, "relevance": 1-10, "structure": 1-10, "clarity": 1-10, "usefulness": 1-10}},
    "B": {{"factuality": 1-10, "relevance": 1-10, "structure": 1-10, "clarity": 1-10, "usefulness": 1-10}}
  }},
  "winner": "A or B or tie",
  "reason": "brief reason"
}}
"""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 600,
    }
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = json.loads(response.read().decode("utf-8"))
    return raw["choices"][0]["message"]["content"]


def _write_markdown(payload: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# LLM Judge Comparison",
        "",
        f"Question: {payload['query']}",
        "",
        "## Automatic Metrics",
        "",
        "| Scenario | Nodes | Dependencies | Evidence | Grounding | Hallucination risk |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, item in payload["results"].items():
        metrics = item["metrics"]
        lines.append(
            f"| {name} | {item['node_count']} | {item['dependency_count']} | "
            f"{item['evidence_count']} | {metrics['grounding_score']} | "
            f"{metrics['hallucination_risk_score']} |"
        )
    lines.extend(["", "## LLM Judge", "", "```json", payload["judge"].strip(), "```"])
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare no-KG and optimized Neo4j answers with an LLM judge.")
    parser.add_argument("query", nargs="?", default=DEFAULT_QUERY)
    parser.add_argument("--output", default="outputs/llm_judge_ai_general_compare.json")
    parser.add_argument("--base-url", default=os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"))
    parser.add_argument("--api-key", default=os.getenv("DASHSCOPE_API_KEY"))
    parser.add_argument("--model", default=os.getenv("DASHSCOPE_MODEL", "qwen-plus"))
    parser.add_argument("--neo4j-uri", default=os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687"))
    parser.add_argument("--neo4j-user", default=os.getenv("NEO4J_USER", "neo4j"))
    parser.add_argument("--neo4j-password", default=os.getenv("NEO4J_PASSWORD"))
    args = parser.parse_args()

    if not args.api_key:
        raise ValueError("Set DASHSCOPE_API_KEY or pass --api-key.")
    if not args.neo4j_password:
        raise ValueError("Set NEO4J_PASSWORD or pass --neo4j-password.")

    payload = run_compare(
        query=args.query,
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
        output_path=Path(args.output),
    )
    print(json.dumps({"output": args.output, "judge": payload["judge"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
