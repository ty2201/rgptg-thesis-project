from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from .evaluation import Timer, evaluate_result
from .factory import create_pipeline
from .graph_export import to_mermaid
from .methods import MethodContext, build_methods


def run_experiment(
    input_path: Path,
    output_path: Path | None = None,
    config_path: Path | None = None,
    method_names: list[str] | None = None,
) -> list[dict]:
    pipeline = create_pipeline(config_path)
    context = MethodContext(pipeline=pipeline)
    methods = build_methods(method_names, max_workers=pipeline.scheduler.max_workers)
    rows: list[dict] = []
    for line in input_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        method_results = {}
        for method in methods:
            with Timer() as timer:
                result = method.generate(item["query"], context)
            metrics = evaluate_result(result, timer.elapsed_ms)
            method_results[method.name] = {
                "metrics": metrics.to_dict(),
                "rule_events": [event.__dict__ for event in result.rule_events],
                "final_text": result.final_text,
                "mermaid": to_mermaid(result, pipeline.kg),
            }
        rows.append(
            {
                "id": item.get("id"),
                "query": item["query"],
                "results": method_results,
            }
        )
    if output_path:
        output_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        write_summary_csv(rows, output_path.with_suffix(".summary.csv"))
    return rows


def write_summary_csv(rows: list[dict], output_path: Path) -> None:
    fieldnames = [
        "id",
        "query",
        "method",
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
            for method_name, result in row["results"].items():
                metrics = result["metrics"]
                writer.writerow(
                    {
                        "id": row["id"],
                        "query": row["query"],
                        "method": method_name,
                        "latency_ms": metrics["latency_ms"],
                        "node_count": metrics["node_count"],
                        "dependency_count": metrics["dependency_count"],
                        "pruned_count": metrics["pruned_count"],
                        "evidence_triple_count": metrics["evidence_triple_count"],
                        "evidence_node_ratio": metrics["evidence_node_ratio"],
                        "relation_diversity": metrics["relation_diversity"],
                        "entity_coverage_score": metrics["entity_coverage_score"],
                        "grounding_score": metrics["grounding_score"],
                        "hallucination_risk_score": metrics["hallucination_risk_score"],
                        "graph_structure_score": metrics["graph_structure_score"],
                        "verified_ratio": metrics["verified_ratio"],
                        "parallelizable_ratio": metrics["parallelizable_ratio"],
                        "coverage_score": metrics["coverage_score"],
                        "coherence_score": metrics["coherence_score"],
                        "rule_event_count": len(result["rule_events"]),
                    }
                )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run batch experiments.")
    parser.add_argument("--input", default="examples/tasks.jsonl", help="JSONL task file.")
    parser.add_argument("--output", default="outputs/experiment_results.json", help="Result JSON path.")
    parser.add_argument("--config", help="Path to config JSON.")
    parser.add_argument(
        "--methods",
        default="direct,sot,rule_guided",
        help="Comma-separated methods: direct,sot,rule_guided.",
    )
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    method_names = [item.strip() for item in args.methods.split(",") if item.strip()]
    rows = run_experiment(
        Path(args.input),
        output,
        Path(args.config) if args.config else None,
        method_names,
    )
    print(f"Finished {len(rows)} cases. Results saved to {output}")
    print(f"Summary CSV saved to {output.with_suffix('.summary.csv')}")
    for row in rows:
        print(f"- {row['id']}: {row['query']}")
        for method_name, result in row["results"].items():
            metrics = result["metrics"]
            print(
                f"  {method_name}: latency={metrics['latency_ms']:.2f}ms, "
                f"coverage={metrics['coverage_score']:.2f}, "
                f"coherence={metrics['coherence_score']:.2f}, "
                f"deps={metrics['dependency_count']}"
            )


if __name__ == "__main__":
    main()
