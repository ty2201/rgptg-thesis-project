from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


WIKIDATA_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
PROPERTY_LABELS = {
    "P31": "instance_of",
    "P279": "subclass_of",
    "P361": "part_of",
    "P366": "use",
    "P527": "has_part",
    "P101": "field_of_work",
    "P178": "developer",
    "P921": "main_subject",
    "P2283": "uses",
    "P1269": "facet_of",
}
DEFAULT_PROPERTIES = tuple(PROPERTY_LABELS)


@dataclass(frozen=True)
class WikidataEntity:
    id: str
    name: str
    description: str = ""
    aliases: tuple[str, ...] = ()
    source: str = "wikidata"


@dataclass(frozen=True)
class WikidataRelation:
    head: str
    relation: str
    tail: str
    confidence: float = 1.0
    source: str = "wikidata"


@dataclass(frozen=True)
class WikidataGraph:
    topic_id: str
    topic_name: str
    entities: list[WikidataEntity]
    relations: list[WikidataRelation]

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic_id": self.topic_id,
            "topic_name": self.topic_name,
            "entities": [asdict(item) for item in self.entities],
            "relations": [asdict(item) for item in self.relations],
        }


def fetch_topic_graph(
    topic_id: str = "Q11660",
    limit: int = 120,
    per_property_limit: int = 25,
    properties: tuple[str, ...] | None = None,
) -> WikidataGraph:
    bindings: list[dict[str, Any]] = []
    for property_id in properties or DEFAULT_PROPERTIES:
        bindings.extend(_run_sparql(_build_query(topic_id, property_id, per_property_limit)))
    entity_map: dict[str, WikidataEntity] = {}
    relations: list[WikidataRelation] = []
    topic_name = topic_id

    for row in bindings:
        head_id = _qid(row["head"]["value"])
        tail_id = _qid(row["tail"]["value"])
        relation = _relation_name(row["relation"]["value"])
        head_name = row.get("headLabel", {}).get("value", head_id)
        tail_name = row.get("tailLabel", {}).get("value", tail_id)
        head_desc = row.get("headDescription", {}).get("value", "")
        tail_desc = row.get("tailDescription", {}).get("value", "")
        head_aliases = _split_aliases(row.get("headAltLabel", {}).get("value", ""))
        tail_aliases = _split_aliases(row.get("tailAltLabel", {}).get("value", ""))

        if _weak_label(head_id, head_name) or _weak_label(tail_id, tail_name):
            continue

        if head_id == topic_id:
            topic_name = head_name
        if tail_id == topic_id:
            topic_name = tail_name

        entity_map[head_id] = _merge_entity(entity_map.get(head_id), head_id, head_name, head_desc, head_aliases)
        entity_map[tail_id] = _merge_entity(entity_map.get(tail_id), tail_id, tail_name, tail_desc, tail_aliases)
        relation_item = WikidataRelation(head=head_id, relation=relation, tail=tail_id)
        if relation_item not in relations:
            relations.append(relation_item)

    entities = sorted(entity_map.values(), key=lambda item: item.id)
    return WikidataGraph(topic_id=topic_id, topic_name=topic_name, entities=entities[: limit * 2], relations=relations[:limit])


def save_graph(graph: WikidataGraph, output_path: str | Path) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(graph.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def load_graph(path: str | Path) -> WikidataGraph:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return WikidataGraph(
        topic_id=raw["topic_id"],
        topic_name=raw["topic_name"],
        entities=[WikidataEntity(**_normalize_entity(item)) for item in raw["entities"]],
        relations=[WikidataRelation(**item) for item in raw["relations"]],
    )


def export_cypher(graph: WikidataGraph, output_path: str | Path) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE;",
        "",
    ]
    for entity in graph.entities:
        lines.append(
            "MERGE (e:Entity {id: "
            + _cypher_string(entity.id)
            + "}) SET e.name = "
            + _cypher_string(entity.name)
            + ", e.description = "
            + _cypher_string(entity.description)
            + ", e.aliases = "
            + _cypher_list(entity.aliases)
            + ", e.source = "
            + _cypher_string(entity.source)
            + ";"
        )
    lines.append("")
    for relation in graph.relations:
        rel_type = relation.relation.upper()
        lines.append(
            "MATCH (h:Entity {id: "
            + _cypher_string(relation.head)
            + "}), (t:Entity {id: "
            + _cypher_string(relation.tail)
            + f"}}) MERGE (h)-[r:{rel_type}]->(t) "
            + f"SET r.confidence = {relation.confidence}, r.source = "
            + _cypher_string(relation.source)
            + ";"
        )
    Path(output_path).write_text("\n".join(lines), encoding="utf-8")


def import_to_neo4j(graph: WikidataGraph, uri: str, user: str, password: str) -> None:
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:
        raise ImportError("Please install neo4j first: pip install neo4j") from exc

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            session.run(
                "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS "
                "FOR (e:Entity) REQUIRE e.id IS UNIQUE"
            )
            for entity in graph.entities:
                params = asdict(entity)
                params["aliases"] = list(entity.aliases)
                session.run(
                    """
                    MERGE (e:Entity {id: $id})
                    SET e.name = $name,
                        e.description = $description,
                        e.aliases = $aliases,
                        e.source = $source
                    """,
                    **params,
                )
            for relation in graph.relations:
                rel_type = relation.relation.upper()
                session.run(
                    f"""
                    MATCH (h:Entity {{id: $head}}), (t:Entity {{id: $tail}})
                    MERGE (h)-[r:{rel_type}]->(t)
                    SET r.confidence = $confidence,
                        r.source = $source
                    """,
                    **asdict(relation),
                )
    finally:
        driver.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch a small Wikidata topic graph and import/export it.")
    parser.add_argument("--topic", default="Q11660", help="Wikidata topic QID. Default: Q11660 artificial intelligence.")
    parser.add_argument("--limit", type=int, default=120, help="Maximum relation rows to keep.")
    parser.add_argument("--per-property-limit", type=int, default=25, help="Rows to fetch for each Wikidata property.")
    parser.add_argument("--output", default="data/wikidata_ai_sample.json", help="Output JSON path.")
    parser.add_argument("--cypher", default="outputs/wikidata_ai_import.cypher", help="Output Cypher path.")
    parser.add_argument("--from-json", help="Load an existing Wikidata graph JSON instead of fetching.")
    parser.add_argument("--import-neo4j", action="store_true", help="Import the graph into Neo4j.")
    parser.add_argument("--neo4j-uri", default=os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--neo4j-user", default=os.getenv("NEO4J_USER", "neo4j"))
    parser.add_argument("--neo4j-password", default=os.getenv("NEO4J_PASSWORD"))
    args = parser.parse_args()

    graph = (
        load_graph(args.from_json)
        if args.from_json
        else fetch_topic_graph(args.topic, args.limit, args.per_property_limit)
    )
    save_graph(graph, args.output)
    export_cypher(graph, args.cypher)
    print(
        f"Fetched {len(graph.entities)} entities and {len(graph.relations)} relations "
        f"for {graph.topic_name} ({graph.topic_id})."
    )
    print(f"JSON saved to {args.output}")
    print(f"Cypher saved to {args.cypher}")

    if args.import_neo4j:
        if not args.neo4j_password:
            raise ValueError("Neo4j password is required. Set NEO4J_PASSWORD or pass --neo4j-password.")
        import_to_neo4j(graph, args.neo4j_uri, args.neo4j_user, args.neo4j_password)
        print(f"Imported graph into Neo4j at {args.neo4j_uri}")


def _build_query(topic_id: str, property_id: str, limit: int) -> str:
    topic = f"wd:{topic_id}"
    prop = f"wdt:{property_id}"
    return f"""
    SELECT ?head ?headLabel ?headDescription ?headAltLabel ?relation ?relationLabel ?tail ?tailLabel ?tailDescription ?tailAltLabel WHERE {{
      {{
        VALUES ?head {{ {topic} }}
        VALUES ?relation {{ {prop} }}
        ?head ?relation ?tail .
      }}
      UNION
      {{
        VALUES ?tail {{ {topic} }}
        VALUES ?relation {{ {prop} }}
        ?head ?relation ?tail .
      }}
      UNION
      {{
        VALUES ?root {{ {topic} }}
        VALUES ?relation {{ {prop} }}
        ?head ?relation ?root .
        ?head wdt:P279|wdt:P31 ?tail .
      }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,zh". }}
    }}
    LIMIT {int(limit)}
    """


def _run_sparql(query: str, retries: int = 3) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"query": query, "format": "json"}).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        request = urllib.request.Request(
            WIKIDATA_SPARQL_ENDPOINT,
            data=params,
            headers={
                "Accept": "application/sparql-results+json",
                "User-Agent": "rgptg-wikidata-import/0.1 (educational prototype; thesis KG expansion)",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return payload["results"]["bindings"]
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(min(5 * attempt, 15))
    raise last_error or RuntimeError("Wikidata SPARQL request failed.")


def _qid(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def _safe_relation(label: str) -> str:
    relation = re.sub(r"[^A-Za-z0-9_]+", "_", label.strip().lower()).strip("_")
    return relation or "related_to"


def _relation_name(uri: str) -> str:
    property_id = _qid(uri)
    return PROPERTY_LABELS.get(property_id, _safe_relation(property_id))


def _cypher_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _cypher_list(values: tuple[str, ...]) -> str:
    return json.dumps(list(values), ensure_ascii=False)


def _split_aliases(value: str) -> tuple[str, ...]:
    if not value:
        return ()
    aliases = []
    for item in value.split(", "):
        cleaned = item.strip()
        if cleaned and cleaned not in aliases and not cleaned.startswith("Q"):
            aliases.append(cleaned)
    return tuple(aliases[:8])


def _weak_label(entity_id: str, name: str) -> bool:
    return not name or name == entity_id or re.fullmatch(r"Q\d+", name) is not None


def _merge_entity(
    old: WikidataEntity | None,
    entity_id: str,
    name: str,
    description: str,
    aliases: tuple[str, ...],
) -> WikidataEntity:
    if old is None:
        return WikidataEntity(entity_id, name, description, aliases)
    merged_aliases = tuple(dict.fromkeys([*old.aliases, *aliases]))
    return WikidataEntity(
        id=old.id,
        name=old.name if old.name else name,
        description=old.description if old.description else description,
        aliases=merged_aliases[:8],
        source=old.source,
    )


def _normalize_entity(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    aliases = normalized.get("aliases", ())
    if isinstance(aliases, list):
        aliases = tuple(aliases)
    normalized["aliases"] = aliases
    return normalized


if __name__ == "__main__":
    main()
