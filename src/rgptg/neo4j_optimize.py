from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any


NOISE_DESCRIPTION_PATTERNS = [
    "film",
    "television",
    "tv series",
    "video game",
    "album",
    "song",
    "novel",
    "fictional",
    "character",
    "episode",
]


def optimize_neo4j(
    domain_json: Path,
    uri: str,
    user: str,
    password: str,
) -> dict[str, Any]:
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:
        raise ImportError("Please install neo4j first: pip install -r requirements-optional.txt") from exc

    domain = json.loads(domain_json.read_text(encoding="utf-8"))
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            before = _stats(session)
            session.run("CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE")
            session.run("CREATE INDEX entity_domain_score IF NOT EXISTS FOR (e:Entity) ON (e.domain_score)")
            session.run("CREATE INDEX entity_source IF NOT EXISTS FOR (e:Entity) ON (e.source)")
            session.run("MATCH (e:Entity) SET e.domain_score = coalesce(e.domain_score, 0.0)")
            session.run(
                """
                MATCH (e:Entity)
                WHERE any(pattern IN $patterns WHERE toLower(coalesce(e.description, "")) CONTAINS pattern)
                SET e.noise = true,
                    e.domain_score = CASE
                        WHEN coalesce(e.domain_score, 0.0) < 0.2 THEN -0.3
                        ELSE e.domain_score
                    END
                """,
                patterns=NOISE_DESCRIPTION_PATTERNS,
            )
            session.run(
                """
                MATCH (e:Entity)
                WHERE toLower(coalesce(e.name, "")) CONTAINS "artificial intelligence"
                   OR toLower(coalesce(e.description, "")) CONTAINS "artificial intelligence"
                   OR toLower(coalesce(e.description, "")) CONTAINS "machine learning"
                   OR toLower(coalesce(e.description, "")) CONTAINS "knowledge representation"
                   OR toLower(coalesce(e.description, "")) CONTAINS "reasoning"
                SET e.domain_score = CASE
                        WHEN coalesce(e.domain_score, 0.0) < 0.35 THEN 0.35
                        ELSE e.domain_score
                    END
                """,
            )

            for entity in domain["entities"]:
                session.run(
                    """
                    MERGE (e:Entity {id: $id})
                    SET e:DomainEntity,
                        e.name = $name,
                        e.description = $description,
                        e.aliases = $aliases,
                        e.source = "domain_seed",
                        e.domain_score = 1.0,
                        e.noise = false
                    """,
                    id=entity["id"],
                    name=entity["name"],
                    description=entity.get("description", ""),
                    aliases=entity.get("aliases", []),
                )

            for triple in domain["triples"]:
                rel_type = _safe_rel_type(triple["relation"])
                session.run(
                    f"""
                    MATCH (h:Entity {{id: $head}}), (t:Entity {{id: $tail}})
                    MERGE (h)-[r:{rel_type}]->(t)
                    SET r.confidence = $confidence,
                        r.kg_weight = $kg_weight,
                        r.source = "domain_seed",
                        r.evidence_role = "domain_core"
                    """,
                    head=triple["head"],
                    tail=triple["tail"],
                    confidence=float(triple.get("confidence", 1.0)),
                    kg_weight=round(float(triple.get("confidence", 1.0)) * 1.35, 3),
                )

            _link_wikidata_ai(session)
            session.run(
                """
                MATCH (:DomainEntity)-[r]->(:DomainEntity)
                SET r.domain_core = true
                """
            )
            after = _stats(session)
            relation_distribution = session.run(
                """
                MATCH (:Entity)-[r]->(:Entity)
                RETURN type(r) AS relation, count(r) AS count
                ORDER BY count DESC, relation
                LIMIT 20
                """
            )
            top_relations = {row["relation"].lower(): row["count"] for row in relation_distribution}
            domain_paths = session.run(
                """
                MATCH (h:DomainEntity)-[r]->(t:DomainEntity)
                RETURN h.id AS head, type(r) AS relation, t.id AS tail, r.kg_weight AS weight
                ORDER BY weight DESC, head, tail
                LIMIT 12
                """
            )
            top_domain_paths = [
                {
                    "head": row["head"],
                    "relation": row["relation"].lower(),
                    "tail": row["tail"],
                    "weight": row["weight"],
                }
                for row in domain_paths
            ]
    finally:
        driver.close()

    return {
        "before": before,
        "after": after,
        "added_entities": after["domain_entity_count"] - before["domain_entity_count"],
        "top_relations": top_relations,
        "top_domain_paths": top_domain_paths,
    }


def write_report(summary: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Neo4j KG Optimization Report",
        "",
        "## Summary",
        "",
        "| Metric | Before | After |",
        "| --- | ---: | ---: |",
    ]
    for key in [
        "entity_count",
        "relation_count",
        "domain_entity_count",
        "domain_relation_count",
        "noise_entity_count",
    ]:
        lines.append(f"| {key} | {summary['before'][key]} | {summary['after'][key]} |")

    lines.extend(["", "## Top Relations", "", "| Relation | Count |", "| --- | ---: |"])
    for relation, count in summary["top_relations"].items():
        lines.append(f"| {relation} | {count} |")

    lines.extend(["", "## Top Domain Paths", "", "| Head | Relation | Tail | Weight |", "| --- | --- | --- | ---: |"])
    for path in summary["top_domain_paths"]:
        lines.append(f"| {path['head']} | {path['relation']} | {path['tail']} | {path['weight']} |")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _stats(session) -> dict[str, int]:
    row = session.run(
        """
        MATCH (e:Entity)
        OPTIONAL MATCH (:Entity)-[r]->(:Entity)
        RETURN count(DISTINCT e) AS entity_count,
               count(DISTINCT r) AS relation_count,
               count(DISTINCT CASE WHEN e:DomainEntity THEN e END) AS domain_entity_count,
               count(DISTINCT CASE WHEN coalesce(e.noise, false) THEN e END) AS noise_entity_count
        """
    ).single()
    domain_rel = session.run(
        """
        MATCH (:DomainEntity)-[r]->(:DomainEntity)
        RETURN count(r) AS count
        """
    ).single()
    return {
        "entity_count": int(row["entity_count"]),
        "relation_count": int(row["relation_count"]),
        "domain_entity_count": int(row["domain_entity_count"]),
        "domain_relation_count": int(domain_rel["count"]),
        "noise_entity_count": int(row["noise_entity_count"]),
    }


def _link_wikidata_ai(session) -> None:
    session.run(
        """
        MATCH (ai:Entity {id: "artificial_intelligence"})
        OPTIONAL MATCH (wd:Entity {id: "Q11660"})
        FOREACH (_ IN CASE WHEN wd IS NULL THEN [] ELSE [1] END |
            MERGE (ai)-[r:SAME_AS]->(wd)
            SET r.confidence = 0.99,
                r.kg_weight = 1.25,
                r.source = "domain_alignment"
        )
        """
    )


def _safe_rel_type(relation: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_]+", "_", relation.upper()).strip("_")
    return value or "RELATED_TO"


def main() -> None:
    parser = argparse.ArgumentParser(description="Optimize Neo4j KG for rule-guided parallel text generation.")
    parser.add_argument("--domain-json", default="data/domain_kg.json")
    parser.add_argument("--neo4j-uri", default=os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687"))
    parser.add_argument("--neo4j-user", default=os.getenv("NEO4J_USER", "neo4j"))
    parser.add_argument("--neo4j-password", default=os.getenv("NEO4J_PASSWORD"))
    parser.add_argument("--report", default="outputs/neo4j_kg_optimization_report.md")
    args = parser.parse_args()

    if not args.neo4j_password:
        raise ValueError("Neo4j password is required. Set NEO4J_PASSWORD or pass --neo4j-password.")

    summary = optimize_neo4j(
        domain_json=Path(args.domain_json),
        uri=args.neo4j_uri,
        user=args.neo4j_user,
        password=args.neo4j_password,
    )
    write_report(summary, Path(args.report))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Report saved to {args.report}")


if __name__ == "__main__":
    main()
