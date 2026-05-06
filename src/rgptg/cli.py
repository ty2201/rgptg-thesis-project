from __future__ import annotations

import argparse
import json

from .factory import create_pipeline
from .graph_export import to_dot, to_mermaid


def main() -> None:
    parser = argparse.ArgumentParser(description="Rule-guided parallel text generation demo.")
    parser.add_argument("query", help="User query to answer.")
    parser.add_argument("--config", help="Path to config JSON.")
    parser.add_argument("--json", action="store_true", help="Print structured JSON instead of text.")
    parser.add_argument("--mermaid", action="store_true", help="Print Mermaid graph.")
    parser.add_argument("--dot", action="store_true", help="Print Graphviz DOT graph.")
    parser.add_argument("--max-nodes", type=int, help="Limit planned nodes before expansion.")
    parser.add_argument("--skip-aggregate", action="store_true", help="Skip final LLM aggregation.")
    parser.add_argument("--no-kg-graph-builder", action="store_true", help="Disable KG-guided DAG construction.")
    parser.add_argument("--no-adaptive-kg", action="store_true", help="Force KG-DAG whenever KG evidence exists.")
    parser.add_argument("--min-kg-relevance-score", type=float, default=0.70)
    parser.add_argument("--min-kg-overlap", type=float, default=0.08)
    args = parser.parse_args()

    pipeline = create_pipeline(args.config)
    result = pipeline.generate_with_options(
        args.query,
        max_nodes=args.max_nodes,
        skip_aggregate=args.skip_aggregate,
        use_kg_graph_builder=not args.no_kg_graph_builder,
        adaptive_kg=not args.no_adaptive_kg,
        min_kg_relevance_score=args.min_kg_relevance_score,
        min_kg_overlap=args.min_kg_overlap,
    )
    if args.mermaid:
        print(to_mermaid(result, pipeline.kg))
        return
    if args.dot:
        print(to_dot(result, pipeline.kg))
        return
    if args.json:
        print(
            json.dumps(
                {
                    "query": result.query,
                    "nodes": [
                        {
                            "id": node.id,
                            "claim": node.claim,
                            "entity_id": node.entity_id,
                            "depends_on": node.depends_on,
                            "status": node.status.value,
                            "confidence": node.confidence,
                            "content": node.content,
                        }
                        for node in result.nodes
                    ],
                    "rule_events": [event.__dict__ for event in result.rule_events],
                    "final_text": result.final_text,
                    "metadata": result.metadata,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    print("=== Rule Events ===")
    if not result.rule_events:
        print("No rule event.")
    for event in result.rule_events:
        print(f"- [{event.rule}] {event.node_id}: {event.action} - {event.reason}")
    print()
    print("=== Final Text ===")
    print(result.final_text)
    if result.metadata.get("llm_call_logs"):
        print()
        print("=== LLM Calls ===")
        for log in result.metadata["llm_call_logs"]:
            print(
                f"- {log['stage']}: {log['elapsed_ms']}ms, "
                f"prompt={log['prompt_chars']}, output={log['output_chars']}, attempt={log['attempt']}"
            )


if __name__ == "__main__":
    main()
