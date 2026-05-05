from __future__ import annotations

from ..kg import KnowledgeGraph
from ..models import Entity, KnowledgeTriple


class Neo4jKnowledgeGraph(KnowledgeGraph):
    """Load a small in-memory KG snapshot from Neo4j.

    Expected graph shape:
    - Entity nodes have labels that include `Entity`
    - Entity nodes provide `id`, `name`, and optional `aliases`
    - Relationships between Entity nodes represent KG relations
    """

    @classmethod
    def connect(
        cls,
        uri: str,
        user: str,
        password: str,
        limit: int = 1000,
    ) -> "Neo4jKnowledgeGraph":
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise ImportError(
                "Neo4j adapter requires the optional dependency `neo4j`. "
                "Install it with: pip install -r requirements-optional.txt"
            ) from exc

        driver = GraphDatabase.driver(uri, auth=(user, password))
        try:
            with driver.session() as session:
                entity_rows = session.run(
                    """
                    MATCH (e:Entity)
                    RETURN e.id AS id, e.name AS name, e.aliases AS aliases,
                           e.description AS description
                    ORDER BY coalesce(e.domain_score, 0.0) DESC,
                             coalesce(e.noise, false) ASC,
                             e.id
                    LIMIT $limit
                    """,
                    limit=limit,
                )
                entities = {
                    row["id"]: Entity(
                        id=row["id"],
                        name=row["name"] or row["id"],
                        aliases=tuple(row["aliases"] or []),
                        description=row["description"] or "",
                    )
                    for row in entity_rows
                    if row["id"]
                }
                triple_rows = session.run(
                    """
                    MATCH (h:Entity)-[r]->(t:Entity)
                    RETURN h.id AS head, type(r) AS relation, t.id AS tail,
                           coalesce(r.confidence, 1.0) AS confidence
                    ORDER BY coalesce(r.kg_weight, r.confidence, 1.0) DESC,
                             coalesce(h.domain_score, 0.0) + coalesce(t.domain_score, 0.0) DESC,
                             type(r)
                    LIMIT $limit
                    """,
                    limit=limit,
                )
                triples = [
                    KnowledgeTriple(
                        head=row["head"],
                        relation=row["relation"].lower(),
                        tail=row["tail"],
                        confidence=float(row["confidence"]),
                        head_name=entities.get(row["head"], Entity(row["head"], row["head"])).name,
                        tail_name=entities.get(row["tail"], Entity(row["tail"], row["tail"])).name,
                    )
                    for row in triple_rows
                ]
        finally:
            driver.close()
        return cls(entities=entities, triples=triples, constraints=[])
