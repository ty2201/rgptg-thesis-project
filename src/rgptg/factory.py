from __future__ import annotations

from pathlib import Path

from .adapters.openai_compatible import OpenAICompatibleClient
from .adapters.neo4j_kg import Neo4jKnowledgeGraph
from .config import AppConfig, load_config
from .kg import KnowledgeGraph
from .llm import LLMClient, MockLLMClient
from .pipeline import GenerationPipeline


def create_pipeline(config_path: str | Path | None = None) -> GenerationPipeline:
    config = load_config(config_path)
    kg = _create_kg(config)
    llm = _create_llm(config)
    return GenerationPipeline(kg=kg, llm=llm, max_workers=config.runtime.max_workers)


def _create_kg(config: AppConfig) -> KnowledgeGraph:
    if config.kg.provider == "json":
        root = Path(__file__).resolve().parents[2]
        path = Path(config.kg.json_path)
        if not path.is_absolute():
            path = root / path
        return KnowledgeGraph.from_json(path)
    if config.kg.provider == "neo4j":
        if not config.kg.neo4j_user or not config.kg.neo4j_password:
            raise ValueError("Neo4j provider requires user and password.")
        return Neo4jKnowledgeGraph.connect(
            uri=config.kg.neo4j_uri,
            user=config.kg.neo4j_user,
            password=config.kg.neo4j_password,
        )
    raise ValueError(f"Unsupported KG provider: {config.kg.provider}")


def _create_llm(config: AppConfig) -> LLMClient:
    if config.llm.provider == "mock":
        return MockLLMClient()
    if config.llm.provider in {"openai_compatible", "openai"}:
        if not config.llm.api_key:
            raise ValueError("OpenAI-compatible provider requires an API key.")
        return OpenAICompatibleClient(
            base_url=config.llm.base_url,
            api_key=config.llm.api_key,
            model=config.llm.model,
            timeout=config.llm.timeout,
            max_tokens=config.llm.max_tokens,
            stage_max_tokens={
                "plan": config.llm.plan_max_tokens,
                "expand": config.llm.expand_max_tokens,
                "aggregate": config.llm.aggregate_max_tokens,
            },
            retries=1,
        )
    raise ValueError(f"Unsupported LLM provider: {config.llm.provider}")
