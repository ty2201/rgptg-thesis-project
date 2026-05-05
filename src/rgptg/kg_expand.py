from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from .neo4j_optimize import optimize_neo4j, write_report as write_optimize_report
from .wikidata import WikidataGraph, fetch_topic_graph, import_to_neo4j, load_graph, save_graph


DEFAULT_NEO4J_DATA_DIR = Path(r"E:\neo4j-codex\neo4j-5.26.25\data")


def expand_kg(
    topics_path: Path,
    target_bytes: int,
    output_dir: Path,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    neo4j_data_dir: Path,
    per_topic_limit: int,
    per_property_limit: int,
    sleep_seconds: float,
    import_neo4j: bool,
    optimize_after_import: bool,
    domain_json: Path,
    max_topics: int | None,
    properties: tuple[str, ...] | None,
) -> dict[str, Any]:
    topics = json.loads(topics_path.read_text(encoding="utf-8"))
    if max_topics is not None:
        topics = topics[:max_topics]
    output_dir.mkdir(parents=True, exist_ok=True)
    before_bytes = _dir_size(neo4j_data_dir)
    records: list[dict[str, Any]] = []

    for topic in topics:
        current_bytes = _dir_size(neo4j_data_dir)
        if import_neo4j and current_bytes >= target_bytes:
            break
        topic_id = topic["id"]
        topic_name = topic.get("name", topic_id)
        graph_path = output_dir / f"{topic_id}_{_safe_name(topic_name)}.json"
        started = time.perf_counter()
        try:
            if graph_path.exists():
                graph = load_graph(graph_path)
                source = "cache"
            else:
                graph = fetch_topic_graph(
                    topic_id=topic_id,
                    limit=per_topic_limit,
                    per_property_limit=per_property_limit,
                    properties=properties,
                )
                save_graph(graph, graph_path)
                source = "wikidata"
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)

            if import_neo4j:
                import_to_neo4j(graph, neo4j_uri, neo4j_user, neo4j_password)
                after_import_bytes = _dir_size(neo4j_data_dir)
            else:
                after_import_bytes = current_bytes

            records.append(
                {
                    "topic_id": topic_id,
                    "topic_name": topic_name,
                    "source": source,
                    "status": "ok",
                    "entities": len(graph.entities),
                    "relations": len(graph.relations),
                    "json_path": str(graph_path),
                    "elapsed_seconds": round(time.perf_counter() - started, 2),
                    "neo4j_bytes_after": after_import_bytes,
                }
            )
        except Exception as exc:
            records.append(
                {
                    "topic_id": topic_id,
                    "topic_name": topic_name,
                    "source": "error",
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                    "entities": 0,
                    "relations": 0,
                    "json_path": str(graph_path),
                    "elapsed_seconds": round(time.perf_counter() - started, 2),
                    "neo4j_bytes_after": current_bytes,
                }
            )

    optimize_summary = None
    if import_neo4j and optimize_after_import:
        optimize_summary = optimize_neo4j(domain_json, neo4j_uri, neo4j_user, neo4j_password)
        write_optimize_report(optimize_summary, Path("outputs/neo4j_kg_optimization_report.md"))

    after_bytes = _dir_size(neo4j_data_dir)
    summary = {
        "target_bytes": target_bytes,
        "target_mb": round(target_bytes / 1024 / 1024, 2),
        "before_bytes": before_bytes,
        "after_bytes": after_bytes,
        "after_mb": round(after_bytes / 1024 / 1024, 2),
        "added_bytes": max(0, after_bytes - before_bytes),
        "import_neo4j": import_neo4j,
        "topics_processed": len(records),
        "records": records,
        "optimize_summary": optimize_summary,
        "properties": list(properties) if properties else None,
    }
    report_path = Path("outputs/kg_expansion_report.md")
    write_report(summary, report_path)
    Path("outputs/kg_expansion_report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def write_report(summary: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# KG Expansion Report",
        "",
        f"- Target: {summary['target_mb']} MB",
        f"- Neo4j size before: {summary['before_bytes'] / 1024 / 1024:.2f} MB",
        f"- Neo4j size after: {summary['after_mb']} MB",
        f"- Topics processed: {summary['topics_processed']}",
        "",
        "## Processed Topics",
        "",
        "| Topic | Status | Source | Entities | Relations | Neo4j size after | Error |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for item in summary["records"]:
        lines.append(
            f"| {item['topic_name']} ({item['topic_id']}) | {item.get('status', 'ok')} | {item['source']} | "
            f"{item['entities']} | {item['relations']} | "
            f"{item['neo4j_bytes_after'] / 1024 / 1024:.2f} MB | {item.get('error', '')} |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- The expansion is staged and idempotent: cached topic JSON files are reused.",
            "- For thesis experiments, quality and domain relevance matter more than raw graph size.",
            "- Reaching 1GB should be done in batches, with quality audits after each stage.",
        ]
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def parse_size(value: str) -> int:
    normalized = value.strip().lower()
    multipliers = {
        "kb": 1024,
        "mb": 1024**2,
        "gb": 1024**3,
    }
    for suffix, multiplier in multipliers.items():
        if normalized.endswith(suffix):
            return int(float(normalized[: -len(suffix)].strip()) * multiplier)
    return int(float(normalized))


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                continue
    return total


def _safe_name(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")[:48]


def parse_properties(value: str | None) -> tuple[str, ...] | None:
    if not value:
        return None
    properties = tuple(part.strip() for part in value.split(",") if part.strip())
    return properties or None


def main() -> None:
    parser = argparse.ArgumentParser(description="Expand Wikidata-backed KG toward a target Neo4j size.")
    parser.add_argument("--topics", default="examples/kg_expansion_topics.json")
    parser.add_argument("--target-size", default="1GB", help="Target Neo4j data directory size, e.g. 100MB or 1GB.")
    parser.add_argument("--output-dir", default="data/kg_expansion")
    parser.add_argument("--neo4j-uri", default=os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687"))
    parser.add_argument("--neo4j-user", default=os.getenv("NEO4J_USER", "neo4j"))
    parser.add_argument("--neo4j-password", default=os.getenv("NEO4J_PASSWORD"))
    parser.add_argument("--neo4j-data-dir", default=str(DEFAULT_NEO4J_DATA_DIR))
    parser.add_argument("--per-topic-limit", type=int, default=1000)
    parser.add_argument("--per-property-limit", type=int, default=120)
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--max-topics", type=int, help="Only process the first N topics.")
    parser.add_argument(
        "--properties",
        help="Comma-separated Wikidata property IDs to fetch, e.g. P31,P279. Defaults to the built-in set.",
    )
    parser.add_argument("--no-import", action="store_true", help="Only fetch JSON files; do not import Neo4j.")
    parser.add_argument("--no-optimize", action="store_true", help="Skip domain optimization after import.")
    parser.add_argument("--domain-json", default="data/domain_kg.json")
    args = parser.parse_args()

    if not args.no_import and not args.neo4j_password:
        raise ValueError("Set NEO4J_PASSWORD or pass --neo4j-password.")

    summary = expand_kg(
        topics_path=Path(args.topics),
        target_bytes=parse_size(args.target_size),
        output_dir=Path(args.output_dir),
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password or "",
        neo4j_data_dir=Path(args.neo4j_data_dir),
        per_topic_limit=args.per_topic_limit,
        per_property_limit=args.per_property_limit,
        sleep_seconds=args.sleep_seconds,
        import_neo4j=not args.no_import,
        optimize_after_import=not args.no_optimize,
        domain_json=Path(args.domain_json),
        max_topics=args.max_topics,
        properties=parse_properties(args.properties),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("Report saved to outputs/kg_expansion_report.md")


if __name__ == "__main__":
    main()
