from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

from .adapters.neo4j_kg import Neo4jKnowledgeGraph
from .evaluation import Timer, evaluate_result
from .kg import KnowledgeGraph
from .llm import MockLLMClient
from .pipeline import GenerationPipeline


def run_kg_ablation(output_path: Path) -> list[dict]:
    tasks = [
        "知识图谱如何降低 SoT 并行生成中的幻觉",
        "比较 SoT 与 CoT 在数学推理任务中的差异",
        "How does artificial intelligence relate to AlphaFold and AI applications?",
        "Explain why artificial intelligence systems need verified knowledge sources.",
    ]
    scenarios = _build_scenarios()
    rows: list[dict] = []
    for task in tasks:
        for name, kg in scenarios.items():
            pipeline = GenerationPipeline(kg=kg, llm=MockLLMClient(), max_workers=4)
            with Timer() as timer:
                result = pipeline.generate(task)
            metrics = evaluate_result(result, timer.elapsed_ms)
            rows.append(
                {
                    "task": task,
                    "scenario": name,
                    **metrics.to_dict(),
                    "rule_event_count": len(result.rule_events),
                    "final_text": result.final_text,
                }
            )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(rows, output_path.with_suffix(".csv"))
    _write_markdown_report(rows, output_path.with_suffix(".md"))
    return rows


def _build_scenarios() -> dict[str, KnowledgeGraph]:
    root = Path(__file__).resolve().parents[2]
    scenarios = {
        "no_kg": KnowledgeGraph(entities={}, triples=[], constraints=[]),
        "sample_kg": KnowledgeGraph.from_json(root / "data" / "sample_kg.json"),
    }
    password = os.getenv("NEO4J_PASSWORD")
    if not password:
        return scenarios
    try:
        scenarios["neo4j_wikidata"] = Neo4jKnowledgeGraph.connect(
            uri=os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687"),
            user=os.getenv("NEO4J_USER", "neo4j"),
            password=password,
        )
    except Exception:
        pass
    return scenarios


def _write_csv(rows: list[dict], output_path: Path) -> None:
    fieldnames = [
        "task",
        "scenario",
        "latency_ms",
        "node_count",
        "dependency_count",
        "pruned_count",
        "evidence_triple_count",
        "evidence_node_ratio",
        "relation_diversity",
        "entity_coverage_score",
        "grounding_score",
        "hallucination_risk_score",
        "graph_structure_score",
        "verified_ratio",
        "parallelizable_ratio",
        "coverage_score",
        "coherence_score",
        "rule_event_count",
    ]
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in fieldnames})


def _write_markdown_report(rows: list[dict], output_path: Path) -> None:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["scenario"], []).append(row)

    lines = ["# KG Ablation Report", ""]
    lines.append("| Scenario | Avg evidence triples | Avg relation diversity | Avg grounding | Avg hallucination risk | Avg verified ratio |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for scenario, items in grouped.items():
        lines.append(
            f"| {scenario} | {_avg(items, 'evidence_triple_count'):.2f} | "
            f"{_avg(items, 'relation_diversity'):.2f} | "
            f"{_avg(items, 'grounding_score'):.2f} | "
            f"{_avg(items, 'hallucination_risk_score'):.2f} | "
            f"{_avg(items, 'verified_ratio'):.2f} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `no_kg` removes external knowledge while keeping the same generation pipeline.",
            "- `sample_kg` uses the prototype KG about SoT, CoT, GoT, KG, and verification.",
            "- `neo4j_wikidata` uses the imported Wikidata AI subgraph when Neo4j is reachable.",
            "- Higher evidence and verified ratios indicate that generation branches are more strongly grounded by KG facts.",
        ]
    )
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _avg(items: list[dict], key: str) -> float:
    return sum(float(item[key]) for item in items) / max(1, len(items))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run KG ablation verification.")
    parser.add_argument("--output", default="outputs/kg_ablation_results.json")
    args = parser.parse_args()
    rows = run_kg_ablation(Path(args.output))
    scenarios = sorted({row["scenario"] for row in rows})
    print(f"Finished KG ablation for scenarios: {', '.join(scenarios)}")
    print(f"Results saved to {args.output}")
    print(f"CSV saved to {Path(args.output).with_suffix('.csv')}")
    print(f"Report saved to {Path(args.output).with_suffix('.md')}")


if __name__ == "__main__":
    main()
