from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path

from .adapters.neo4j_kg import Neo4jKnowledgeGraph
from .kg import KnowledgeGraph


def audit_kg(kg: KnowledgeGraph) -> dict:
    entity_count = len(kg.entities)
    relation_count = len(kg.triples)
    relation_counts = Counter(triple.relation for triple in kg.triples)
    alias_count = sum(len(entity.aliases) for entity in kg.entities.values())
    entities_with_aliases = sum(1 for entity in kg.entities.values() if entity.aliases)
    weak_labels = sum(1 for entity in kg.entities.values() if entity.name == entity.id or entity.name.startswith("Q"))
    described = sum(1 for entity in kg.entities.values() if getattr(entity, "description", ""))

    return {
        "entity_count": entity_count,
        "relation_count": relation_count,
        "relation_type_count": len(relation_counts),
        "relation_counts": dict(relation_counts.most_common()),
        "alias_count": alias_count,
        "alias_coverage": round(entities_with_aliases / max(1, entity_count), 3),
        "description_coverage": round(described / max(1, entity_count), 3),
        "weak_label_ratio": round(weak_labels / max(1, entity_count), 3),
        "avg_degree": round(relation_count * 2 / max(1, entity_count), 3),
    }


def write_report(stats: dict, output_path: Path) -> None:
    lines = [
        "# Knowledge Graph Quality Report",
        "",
        f"- Entities: {stats['entity_count']}",
        f"- Relations: {stats['relation_count']}",
        f"- Relation types: {stats['relation_type_count']}",
        f"- Alias coverage: {stats['alias_coverage']}",
        f"- Description coverage: {stats['description_coverage']}",
        f"- Weak label ratio: {stats['weak_label_ratio']}",
        f"- Average degree: {stats['avg_degree']}",
        "",
        "## Relation Distribution",
        "",
        "| Relation | Count |",
        "| --- | ---: |",
    ]
    for relation, count in stats["relation_counts"].items():
        lines.append(f"| {relation} | {count} |")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit KG quality.")
    parser.add_argument("--source", choices=["json", "neo4j"], default="neo4j")
    parser.add_argument("--json-path", default="data/wikidata_ai_sample.json")
    parser.add_argument("--output", default="outputs/kg_quality_report.md")
    args = parser.parse_args()

    if args.source == "neo4j":
        password = os.getenv("NEO4J_PASSWORD")
        if not password:
            raise ValueError("Set NEO4J_PASSWORD before auditing Neo4j.")
        kg = Neo4jKnowledgeGraph.connect(
            os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687"),
            os.getenv("NEO4J_USER", "neo4j"),
            password,
        )
    else:
        raw = json.loads(Path(args.json_path).read_text(encoding="utf-8"))
        converted = {
            "entities": [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "aliases": item.get("aliases", []),
                    "description": item.get("description", ""),
                }
                for item in raw["entities"]
            ],
            "triples": [
                {
                    "head": item["head"],
                    "relation": item["relation"],
                    "tail": item["tail"],
                    "confidence": item.get("confidence", 1.0),
                }
                for item in raw["relations"]
            ],
            "constraints": [],
        }
        tmp = Path("outputs/.kg_quality_tmp.json")
        tmp.write_text(json.dumps(converted, ensure_ascii=False), encoding="utf-8")
        kg = KnowledgeGraph.from_json(tmp)
    stats = audit_kg(kg)
    write_report(stats, Path(args.output))
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"Report saved to {args.output}")


if __name__ == "__main__":
    main()
