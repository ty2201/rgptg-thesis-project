from __future__ import annotations

import argparse
import json
from pathlib import Path

from .evaluation import Timer, evaluate_result
from .factory import create_pipeline


def run_real_llm(
    query: str,
    config_path: Path,
    output_path: Path,
    max_nodes: int = 3,
    skip_aggregate: bool = False,
    use_kg_graph_builder: bool = True,
) -> dict:
    pipeline = create_pipeline(config_path)
    with Timer() as timer:
        result = pipeline.generate_with_options(
            query,
            max_nodes=max_nodes,
            skip_aggregate=skip_aggregate,
            use_kg_graph_builder=use_kg_graph_builder,
        )
    metrics = evaluate_result(result, timer.elapsed_ms).to_dict()
    payload = {
        "query": query,
        "metrics": metrics,
        "nodes": [
            {
                "id": node.id,
                "claim": node.claim,
                "entity_id": node.entity_id,
                "relation": node.relation,
                "depends_on": node.depends_on,
                "confidence": node.confidence,
                "verified": node.verified,
                "evidence": [
                    {
                        "head": triple.head_name or triple.head,
                        "relation": triple.relation,
                        "tail": triple.tail_name or triple.tail,
                    }
                    for triple in node.evidence[:5]
                ],
                "content": node.content,
            }
            for node in result.nodes
        ],
        "rule_events": [event.__dict__ for event in result.rule_events],
        "final_text": result.final_text,
        "metadata": result.metadata,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(payload, output_path.with_suffix(".md"))
    return payload


def _write_markdown(payload: dict, output_path: Path) -> None:
    metrics = payload["metrics"]
    lines = [
        "# Real LLM Full Pipeline Run",
        "",
        f"Query: {payload['query']}",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key, value in metrics.items():
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "## LLM Calls", ""])
    for log in payload["metadata"].get("llm_call_logs", []):
        lines.append(
            f"- `{log['stage']}`: {log['elapsed_ms']}ms, "
            f"prompt={log['prompt_chars']}, output={log['output_chars']}, attempt={log['attempt']}"
        )
    lines.extend(["", "## Nodes", ""])
    for node in payload["nodes"]:
        lines.append(f"### {node['id']}: {node['claim']}")
        lines.append(f"- confidence: {node['confidence']}")
        lines.append(f"- verified: {node['verified']}")
        if node["evidence"]:
            lines.append("- evidence:")
            for triple in node["evidence"]:
                lines.append(f"  - {triple['head']} -[{triple['relation']}]-> {triple['tail']}")
        lines.append("")
        lines.append(node["content"])
        lines.append("")
    lines.extend(["## Final Text", "", payload["final_text"]])
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a stable real-LLM full pipeline.")
    parser.add_argument("query")
    parser.add_argument("--config", default="config.dashscope.example.json")
    parser.add_argument("--output", default="outputs/real_llm_full_run.json")
    parser.add_argument("--max-nodes", type=int, default=3)
    parser.add_argument("--skip-aggregate", action="store_true")
    parser.add_argument("--no-kg-graph-builder", action="store_true")
    args = parser.parse_args()
    payload = run_real_llm(
        query=args.query,
        config_path=Path(args.config),
        output_path=Path(args.output),
        max_nodes=args.max_nodes,
        skip_aggregate=args.skip_aggregate,
        use_kg_graph_builder=not args.no_kg_graph_builder,
    )
    print(f"Saved JSON to {args.output}")
    print(f"Saved report to {Path(args.output).with_suffix('.md')}")
    print(f"Final text chars: {len(payload['final_text'])}")
    for log in payload["metadata"].get("llm_call_logs", []):
        print(f"- {log['stage']}: {log['elapsed_ms']}ms")


if __name__ == "__main__":
    main()
