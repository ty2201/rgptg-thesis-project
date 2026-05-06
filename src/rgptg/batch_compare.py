from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .adapters.neo4j_kg import Neo4jKnowledgeGraph
from .adapters.openai_compatible import OpenAICompatibleClient
from .evaluation import evaluate_result
from .kg import KnowledgeGraph
from .llm import LLMClient, MockLLMClient
from .methods import MethodContext, SkeletonOfThoughtMethod
from .pipeline import GenerationPipeline


def run_batch(
    input_path: Path,
    output_path: Path,
    use_real_llm: bool,
    judge_limit: int,
    limit: int | None,
    base_url: str,
    api_key: str | None,
    model: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str | None,
    kg_json: Path | None,
    min_kg_relevance_score: float,
    min_kg_overlap: float,
) -> list[dict[str, Any]]:
    tasks = _load_tasks(input_path)
    if limit is not None:
        tasks = tasks[:limit]
    if kg_json is not None:
        optimized_kg = KnowledgeGraph.from_json(kg_json)
        optimized_method_name = "optimized_json_kg"
    else:
        if not neo4j_password:
            raise ValueError("Set NEO4J_PASSWORD or pass --neo4j-password.")
        optimized_kg = Neo4jKnowledgeGraph.connect(neo4j_uri, neo4j_user, neo4j_password)
        optimized_method_name = "optimized_neo4j"
    rows: list[dict[str, Any]] = []
    judge_used = 0

    for task in tasks:
        task_results = {}
        for method_name, kg, mode in [
            ("plain_sot", KnowledgeGraph(entities={}, triples=[], constraints=[]), "sot"),
            (optimized_method_name, optimized_kg, "rule_guided"),
        ]:
            llm = _build_llm(use_real_llm, base_url, api_key, model)
            pipeline = GenerationPipeline(kg=kg, llm=llm, max_workers=1 if use_real_llm else 4)
            started = time.perf_counter()
            if mode == "sot":
                result = SkeletonOfThoughtMethod(max_workers=1 if use_real_llm else 4).generate(
                    task["query"],
                    MethodContext(pipeline=pipeline),
                )
            else:
                result = pipeline.generate_with_options(
                    task["query"],
                    max_nodes=5,
                    skip_aggregate=False,
                    min_kg_relevance_score=min_kg_relevance_score,
                    min_kg_overlap=min_kg_overlap,
                )
            elapsed_ms = (time.perf_counter() - started) * 1000
            metrics = evaluate_result(result, elapsed_ms).to_dict()
            row = {
                "id": task["id"],
                "category": task["category"],
                "query": task["query"],
                "method": method_name,
                **metrics,
                "rule_event_count": len(result.rule_events),
                "kg_strategy": result.metadata.get("kg_strategy", ""),
                "kg_relevance_score": result.metadata.get("kg_relevance_score", ""),
                "kg_relevance_reason": result.metadata.get("kg_relevance_reason", ""),
                "final_text": result.final_text,
            }
            rows.append(row)
            task_results[method_name] = row

        if api_key and judge_used < judge_limit:
            judge = _judge(
                query=task["query"],
                answer_a=task_results["plain_sot"]["final_text"],
                answer_b=task_results[optimized_method_name]["final_text"],
                base_url=base_url,
                api_key=api_key,
                model=model,
            )
            judge_used += 1
            parsed = _parse_judge(judge)
            for method_name, label in [("plain_sot", "A"), (optimized_method_name, "B")]:
                target = next(
                    item
                    for item in reversed(rows)
                    if item["id"] == task["id"] and item["method"] == method_name
                )
                scores = parsed.get("scores", {}).get(label, {})
                target["judge_raw"] = judge
                target["judge_winner"] = parsed.get("winner", "")
                target["judge_reason"] = parsed.get("reason", "")
                target["judge_label"] = label
                target["judge_score_avg"] = _avg_score(scores)
                for score_key in ["factuality", "relevance", "structure", "clarity", "usefulness"]:
                    target[f"judge_{score_key}"] = scores.get(score_key, "")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(rows, output_path.with_suffix(".csv"))
    _write_markdown(rows, output_path.with_suffix(".md"), use_real_llm, judge_limit)
    return rows


def _load_tasks(path: Path) -> list[dict[str, str]]:
    tasks = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        tasks.append(
            {
                "id": str(item["id"]),
                "category": str(item["category"]),
                "query": str(item["query"]),
            }
        )
    return tasks


def _build_llm(use_real_llm: bool, base_url: str, api_key: str | None, model: str) -> LLMClient:
    if not use_real_llm:
        return MockLLMClient()
    if not api_key:
        raise ValueError("Real LLM mode requires DASHSCOPE_API_KEY or --api-key.")
    return OpenAICompatibleClient(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout=60,
        max_tokens=700,
        stage_max_tokens={"plan": 500, "expand": 320, "aggregate": 600},
        retries=1,
    )


def _judge(query: str, answer_a: str, answer_b: str, base_url: str, api_key: str, model: str) -> str:
    prompt = f"""
You are an impartial evaluator. Compare two answers to the same user question.
A is plain Skeleton-of-Thought without KG. B is KG-guided DAG generation.

Question:
{query}

Answer A:
{answer_a}

Answer B:
{answer_b}

Evaluate factuality, relevance, structure, clarity, and usefulness.
Return concise JSON only:
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
        "max_tokens": 500,
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


def _parse_judge(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return {"winner": "", "scores": {}, "reason": stripped}


def _avg_score(scores: dict[str, Any]) -> float:
    values = [float(value) for value in scores.values() if isinstance(value, int | float)]
    return round(sum(values) / max(1, len(values)), 3)


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "id",
        "category",
        "query",
        "method",
        "latency_ms",
        "node_count",
        "dependency_count",
        "evidence_triple_count",
        "evidence_node_ratio",
        "relation_diversity",
        "grounding_score",
        "hallucination_risk_score",
        "graph_structure_score",
        "verified_ratio",
        "coherence_score",
        "rule_event_count",
        "kg_strategy",
        "kg_relevance_score",
        "kg_relevance_reason",
        "judge_label",
        "judge_winner",
        "judge_score_avg",
        "judge_factuality",
        "judge_relevance",
        "judge_structure",
        "judge_clarity",
        "judge_usefulness",
        "judge_reason",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _write_markdown(rows: list[dict[str, Any]], path: Path, use_real_llm: bool, judge_limit: int) -> None:
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["category"], row["method"])].append(row)

    lines = [
        "# Batch Experiment Results",
        "",
        f"- Generation mode: {'real LLM' if use_real_llm else 'mock LLM'}",
        f"- Judge samples: {judge_limit}",
        "- A: plain_sot",
        "- B: optimized KG method",
        "",
        "## Category Averages",
        "",
        "| Category | Method | Cases | Grounding | Hallucination risk | Graph structure | Dependencies | Evidence triples | Coherence | Judge avg |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for (category, method), items in sorted(grouped.items()):
        lines.append(
            f"| {category} | {method} | {len(items)} | "
            f"{_avg(items, 'grounding_score'):.3f} | "
            f"{_avg(items, 'hallucination_risk_score'):.3f} | "
            f"{_avg(items, 'graph_structure_score'):.3f} | "
            f"{_avg(items, 'dependency_count'):.2f} | "
            f"{_avg(items, 'evidence_triple_count'):.2f} | "
            f"{_avg(items, 'coherence_score'):.3f} | "
            f"{_avg_optional(items, 'judge_score_avg')} |"
        )

    lines.extend(["", "## Judge Win Counts", ""])
    wins = Counter()
    judged_ids = set()
    for row in rows:
        winner = row.get("judge_winner")
        if not winner or row["id"] in judged_ids:
            continue
        judged_ids.add(row["id"])
        wins[winner] += 1
    lines.append("| Winner | Count |")
    lines.append("| --- | ---: |")
    for winner, count in sorted(wins.items()):
        lines.append(f"| {winner} | {count} |")

    lines.extend(["", "## Per Case Metrics", ""])
    lines.append(
        "| ID | Category | Method | Grounding | Risk | Graph | Deps | Evidence | "
        "Judge avg | Fact | Rel | Struct | Clarity | Useful | Winner |"
    )
    lines.append("| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |")
    for row in rows:
        lines.append(
            f"| {row['id']} | {row['category']} | {row['method']} | "
            f"{row['grounding_score']} | {row['hallucination_risk_score']} | "
            f"{row['graph_structure_score']} | {row['dependency_count']} | "
            f"{row['evidence_triple_count']} | {row.get('judge_score_avg', '')} | "
            f"{row.get('judge_factuality', '')} | {row.get('judge_relevance', '')} | "
            f"{row.get('judge_structure', '')} | {row.get('judge_clarity', '')} | "
            f"{row.get('judge_usefulness', '')} | {row.get('judge_winner', '')} |"
        )

    lines.extend(["", "## Per Question Pair View", ""])
    lines.append(
        "| ID | Category | Query | Plain internal | KG internal | Plain external | KG external | Winner | Judge reason |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    by_id: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        by_id[row["id"]][row["method"]] = row
    for task_id, methods in sorted(by_id.items()):
        plain = methods.get("plain_sot", {})
        kg = next((value for key, value in methods.items() if key.startswith("optimized_")), {})
        source = plain or kg
        lines.append(
            f"| {task_id} | {source.get('category', '')} | {_cell(source.get('query', ''))} | "
            f"{_internal_cell(plain)} | {_internal_cell(kg)} | "
            f"{_external_cell(plain)} | {_external_cell(kg)} | "
            f"{plain.get('judge_winner') or kg.get('judge_winner', '')} | "
            f"{_cell(plain.get('judge_reason') or kg.get('judge_reason', ''))} |"
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def _avg(items: list[dict[str, Any]], key: str) -> float:
    return sum(float(item.get(key, 0.0)) for item in items) / max(1, len(items))


def _avg_optional(items: list[dict[str, Any]], key: str) -> str:
    values = [float(item[key]) for item in items if item.get(key) not in {"", None}]
    if not values:
        return ""
    return f"{sum(values) / len(values):.3f}"


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def _internal_cell(row: dict[str, Any]) -> str:
    if not row:
        return ""
    return _cell(
        "ground="
        f"{row.get('grounding_score', '')}; risk={row.get('hallucination_risk_score', '')}; "
        f"graph={row.get('graph_structure_score', '')}; deps={row.get('dependency_count', '')}; "
        f"evidence={row.get('evidence_triple_count', '')}; coherence={row.get('coherence_score', '')}"
    )


def _external_cell(row: dict[str, Any]) -> str:
    if not row:
        return ""
    if not row.get("judge_score_avg"):
        return ""
    return _cell(
        "avg="
        f"{row.get('judge_score_avg', '')}; fact={row.get('judge_factuality', '')}; "
        f"rel={row.get('judge_relevance', '')}; struct={row.get('judge_structure', '')}; "
        f"clarity={row.get('judge_clarity', '')}; useful={row.get('judge_usefulness', '')}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch compare plain SoT and optimized Neo4j KG-DAG.")
    parser.add_argument("--input", default="examples/batch_eval_tasks.jsonl")
    parser.add_argument("--output", default="outputs/batch_compare_results.json")
    parser.add_argument("--real-llm", action="store_true", help="Use the configured real LLM for generation.")
    parser.add_argument("--judge-limit", type=int, default=0, help="Number of cases to judge with LLM.")
    parser.add_argument("--limit", type=int, help="Limit the number of cases from the input file.")
    parser.add_argument("--base-url", default=os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"))
    parser.add_argument("--api-key", default=os.getenv("DASHSCOPE_API_KEY"))
    parser.add_argument("--model", default=os.getenv("DASHSCOPE_MODEL", "qwen-plus"))
    parser.add_argument("--neo4j-uri", default=os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687"))
    parser.add_argument("--neo4j-user", default=os.getenv("NEO4J_USER", "neo4j"))
    parser.add_argument("--neo4j-password", default=os.getenv("NEO4J_PASSWORD"))
    parser.add_argument("--kg-json", type=Path, help="Use a local JSON knowledge graph instead of Neo4j.")
    parser.add_argument("--min-kg-relevance-score", type=float, default=0.70)
    parser.add_argument("--min-kg-overlap", type=float, default=0.08)
    args = parser.parse_args()

    rows = run_batch(
        input_path=Path(args.input),
        output_path=Path(args.output),
        use_real_llm=args.real_llm,
        judge_limit=args.judge_limit,
        limit=args.limit,
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
        kg_json=args.kg_json,
        min_kg_relevance_score=args.min_kg_relevance_score,
        min_kg_overlap=args.min_kg_overlap,
    )
    print(f"Finished {len(rows)} rows. JSON: {args.output}")
    print(f"CSV: {Path(args.output).with_suffix('.csv')}")
    print(f"Markdown: {Path(args.output).with_suffix('.md')}")


if __name__ == "__main__":
    main()
