import unittest
from pathlib import Path

from rgptg.adapters.openai_compatible import _strip_code_fence
from rgptg.config import load_config
from rgptg.evaluation import evaluate_result
from rgptg.experiment import run_experiment, write_summary_csv
from rgptg.graph_export import to_dot, to_mermaid
from rgptg.kg import KnowledgeGraph
from rgptg.kg_ablation import run_kg_ablation
from rgptg.kg_graph_builder import KGGraphBuilder
from rgptg.kg_quality import audit_kg
from rgptg.methods import MethodContext, build_methods
from rgptg.models import Entity, KnowledgeTriple
from rgptg.pipeline import GenerationPipeline
from rgptg.wikidata import WikidataEntity, WikidataGraph, WikidataRelation, export_cypher


class PipelineTest(unittest.TestCase):
    def test_pipeline_generates_final_text(self):
        result = GenerationPipeline.from_sample().generate("知识图谱如何降低 SoT 并行生成中的幻觉")

        self.assertIn("规则引导", result.final_text)
        self.assertTrue(any(node.content for node in result.nodes))
        self.assertTrue(all(node.status.value in {"done", "pruned", "low_confidence"} for node in result.nodes))

    def test_reasoning_query_adds_serial_node(self):
        result = GenerationPipeline.from_sample().generate("比较 SoT 与 CoT 在数学推理任务中的差异")

        self.assertTrue(any(node.evidence for node in result.nodes))
        self.assertTrue(any(node.depends_on for node in result.nodes))

    def test_graph_export_contains_edges(self):
        pipeline = GenerationPipeline.from_sample()
        result = pipeline.generate("说明 GoT 如何帮助构建并行文本生成中的逻辑依赖")

        mermaid = to_mermaid(result, pipeline.kg)
        dot = to_dot(result, pipeline.kg)

        self.assertIn("flowchart TD", mermaid)
        self.assertIn("-->", mermaid)
        self.assertIn("digraph ThoughtGraph", dot)

    def test_evaluation_metrics(self):
        result = GenerationPipeline.from_sample().generate("知识图谱如何降低 SoT 并行生成中的幻觉")

        metrics = evaluate_result(result, latency_ms=12.5)

        self.assertEqual(metrics.latency_ms, 12.5)
        self.assertGreater(metrics.node_count, 0)
        self.assertGreaterEqual(metrics.coherence_score, 0)
        self.assertLessEqual(metrics.coherence_score, 1)

    def test_config_defaults_to_mock(self):
        config = load_config()

        self.assertEqual(config.llm.provider, "mock")
        self.assertEqual(config.kg.provider, "json")

    def test_strip_code_fence(self):
        payload = "```json\n[{\"id\": \"n1\"}]\n```"

        self.assertEqual(_strip_code_fence(payload), '[{"id": "n1"}]')

    def test_all_methods_generate(self):
        pipeline = GenerationPipeline.from_sample()
        context = MethodContext(pipeline=pipeline)

        results = {
            method.name: method.generate("比较 SoT 与 CoT 在推理任务中的差异", context)
            for method in build_methods(max_workers=2)
        }

        self.assertEqual(set(results), {"direct", "sot", "rule_guided"})
        self.assertTrue(all(result.final_text for result in results.values()))

    def test_experiment_outputs_method_results(self):
        rows = run_experiment(
            input_path=Path("examples/tasks.jsonl"),
            method_names=["direct", "rule_guided"],
        )

        self.assertTrue(rows)
        self.assertIn("direct", rows[0]["results"])
        self.assertIn("rule_guided", rows[0]["results"])

    def test_summary_csv_writer(self):
        rows = run_experiment(
            input_path=Path("examples/tasks.jsonl"),
            method_names=["direct"],
        )
        output = Path("outputs/test_summary.csv")

        write_summary_csv(rows, output)

        self.assertTrue(output.exists())
        self.assertIn("coherence_score", output.read_text(encoding="utf-8-sig"))

    def test_wikidata_cypher_export(self):
        graph = WikidataGraph(
            topic_id="Q11660",
            topic_name="artificial intelligence",
            entities=[
                WikidataEntity("Q11660", "artificial intelligence"),
                WikidataEntity("Q1", "example"),
            ],
            relations=[WikidataRelation("Q11660", "subclass_of", "Q1")],
        )
        output = Path("outputs/test_wikidata.cypher")

        export_cypher(graph, output)

        text = output.read_text(encoding="utf-8")
        self.assertIn("MERGE (e:Entity", text)
        self.assertIn("SUBCLASS_OF", text)

    def test_kg_ablation_runs(self):
        output = Path("outputs/test_kg_ablation.json")

        rows = run_kg_ablation(output)

        self.assertTrue(output.exists())
        self.assertTrue(any(row["scenario"] == "no_kg" for row in rows))
        self.assertTrue(any(row["scenario"] == "sample_kg" for row in rows))

    def test_kg_quality_audit(self):
        stats = audit_kg(GenerationPipeline.from_sample().kg)

        self.assertGreater(stats["entity_count"], 0)
        self.assertIn("relation_counts", stats)

    def test_kg_graph_builder_creates_dynamic_aggregate_shape(self):
        pipeline = GenerationPipeline.from_sample()
        evidence = pipeline.kg.neighbors("kg", hops=1)
        nodes = KGGraphBuilder(pipeline.kg, max_branches=5).build(
            "知识图谱如何降低幻觉并优化并行文本生成？",
            evidence,
        )

        self.assertEqual(nodes[0].metadata["kg_role"], "root_anchor")
        self.assertEqual(nodes[-1].metadata["kg_role"], "aggregation")
        self.assertGreaterEqual(len(nodes), 4)
        self.assertLessEqual(len(nodes), 7)
        self.assertTrue(any(node.metadata.get("kg_role") == "parallel_branch" for node in nodes))
        self.assertTrue(set(nodes[-1].depends_on).issubset({node.id for node in nodes[1:-1]}))

    def test_kg_graph_builder_uses_chain_dependencies(self):
        pipeline = GenerationPipeline.from_sample()
        evidence = pipeline.kg.neighbors("kg", hops=1) + pipeline.kg.neighbors("verification", hops=1)
        nodes = KGGraphBuilder(pipeline.kg, max_branches=5).build(
            "知识图谱如何通过验证降低幻觉并优化并行文本生成？",
            evidence,
        )

        branch_nodes = [node for node in nodes if node.metadata.get("kg_role") == "parallel_branch"]
        chained = [node for node in branch_nodes if node.depends_on and "n1" not in node.depends_on]

        self.assertTrue(chained)
        self.assertGreater(len(nodes), 4)

    def test_kg_graph_builder_improves_structure_score(self):
        result = GenerationPipeline.from_sample().generate_with_options(
            "How can KG reduce hallucination and support verification in parallel text generation?",
            max_nodes=5,
            skip_aggregate=True,
        )
        metrics = evaluate_result(result, latency_ms=1.0)

        self.assertEqual(metrics.graph_structure_score, 1.0)

    def test_kg_graph_builder_single_evidence_keeps_minimal_dag(self):
        pipeline = GenerationPipeline.from_sample()
        evidence = [
            KnowledgeTriple(
                head="kg",
                relation="reduces",
                tail="hallucination",
                confidence=0.86,
                head_name="Knowledge Graph",
                tail_name="Hallucination",
            )
        ]

        nodes = KGGraphBuilder(pipeline.kg).build("知识图谱如何降低幻觉？", evidence)

        self.assertEqual(
            [node.metadata["kg_role"] for node in nodes],
            ["root_anchor", "parallel_branch", "aggregation"],
        )
        self.assertEqual(nodes[-1].depends_on, ["n2"])

    def test_short_alias_requires_word_boundary(self):
        kg = KnowledgeGraph(
            entities={
                "ai": Entity("ai", "Artificial Intelligence", ("AI",)),
                "mu": Entity("mu", "Machine Unlearning", ("MU",)),
            },
            triples=[],
            constraints=[],
        )

        linked = kg.link_entities("Why must an AI system verify evidence?")

        self.assertEqual([entity.id for entity in linked], ["ai"])

    def test_adaptive_kg_falls_back_on_weak_general_evidence(self):
        kg = KnowledgeGraph(
            entities={
                "alpha": Entity("alpha", "AlphaFold", ("AlphaFold",)),
                "ai": Entity("ai", "Artificial Intelligence", ("AI",)),
            },
            triples=[
                KnowledgeTriple(
                    head="alpha",
                    relation="instance_of",
                    tail="ai",
                    confidence=0.9,
                )
            ],
            constraints=[],
        )
        result = GenerationPipeline(kg).generate_with_options(
            "Explain how AlphaFold changed protein structure prediction.",
            skip_aggregate=True,
        )

        self.assertEqual(result.metadata["kg_strategy"], "llm_plan_weak_kg")
        self.assertLess(result.metadata["kg_relevance_score"], result.metadata["min_kg_relevance_score"])
        self.assertFalse(any(node.metadata.get("kg_role") == "aggregation" for node in result.nodes))
        self.assertFalse(any(node.evidence for node in result.nodes))

    def test_adaptive_kg_uses_dag_for_strong_dependency_evidence(self):
        kg = KnowledgeGraph(
            entities={
                "ai": Entity("ai", "Artificial Intelligence", ("AI",)),
                "verification": Entity("verification", "Verification", ("verify", "evidence")),
                "hallucination": Entity("hallucination", "Hallucination", ("hallucination",)),
                "aggregation": Entity("aggregation", "Aggregation", ("aggregation",)),
            },
            triples=[
                KnowledgeTriple("ai", "requires", "verification", 0.9),
                KnowledgeTriple("verification", "reduces", "hallucination", 0.9),
                KnowledgeTriple("aggregation", "uses", "verification", 0.85),
            ],
            constraints=[],
        )
        result = GenerationPipeline(kg).generate_with_options(
            "Why must an AI system verify evidence before aggregation?",
            skip_aggregate=True,
        )

        self.assertEqual(result.metadata["kg_strategy"], "kg_dag")
        self.assertGreaterEqual(result.metadata["kg_relevance_score"], result.metadata["min_kg_relevance_score"])
        self.assertTrue(any(node.metadata.get("kg_role") == "aggregation" for node in result.nodes))

    def test_adaptive_kg_threshold_can_force_plain_fallback(self):
        kg = KnowledgeGraph(
            entities={
                "kg": Entity("kg", "Knowledge Graph", ("knowledge graph", "KG")),
                "rag": Entity("rag", "Retrieval-Augmented Generation", ("RAG",)),
                "evidence": Entity("evidence", "Evidence", ("evidence",)),
            },
            triples=[
                KnowledgeTriple("kg", "supports", "rag", 0.9),
                KnowledgeTriple("rag", "uses", "evidence", 0.9),
                KnowledgeTriple("kg", "provides", "evidence", 0.85),
            ],
            constraints=[],
        )
        result = GenerationPipeline(kg).generate_with_options(
            "Explain how knowledge graphs support RAG with evidence.",
            skip_aggregate=True,
            min_kg_relevance_score=1.01,
        )

        self.assertEqual(result.metadata["kg_strategy"], "llm_plan_weak_kg")
        self.assertFalse(any(node.evidence for node in result.nodes))


if __name__ == "__main__":
    unittest.main()

