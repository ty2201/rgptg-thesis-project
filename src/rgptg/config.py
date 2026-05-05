from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "mock"
    base_url: str = "https://api.openai.com/v1"
    api_key: str | None = None
    model: str = "gpt-4o-mini"
    timeout: int = 60
    max_tokens: int = 900
    plan_max_tokens: int = 700
    expand_max_tokens: int = 360
    aggregate_max_tokens: int = 700


@dataclass(frozen=True)
class KGConfig:
    provider: str = "json"
    json_path: str = "data/sample_kg.json"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str | None = None
    neo4j_password: str | None = None


@dataclass(frozen=True)
class RuntimeConfig:
    max_workers: int = 4


@dataclass(frozen=True)
class AppConfig:
    llm: LLMConfig
    kg: KGConfig
    runtime: RuntimeConfig


def load_config(path: str | Path | None = None) -> AppConfig:
    raw: dict[str, Any] = {}
    if path:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))

    llm_raw = raw.get("llm", {})
    kg_raw = raw.get("kg", {})
    runtime_raw = raw.get("runtime", {})

    llm = LLMConfig(
        provider=os.getenv("RGPTG_LLM_PROVIDER", llm_raw.get("provider", "mock")),
        base_url=os.getenv("RGPTG_LLM_BASE_URL", llm_raw.get("base_url", "https://api.openai.com/v1")),
        api_key=os.getenv(llm_raw.get("api_key_env", "OPENAI_API_KEY"), llm_raw.get("api_key")),
        model=os.getenv("RGPTG_LLM_MODEL", llm_raw.get("model", "gpt-4o-mini")),
        timeout=int(os.getenv("RGPTG_LLM_TIMEOUT", llm_raw.get("timeout", 60))),
        max_tokens=int(os.getenv("RGPTG_LLM_MAX_TOKENS", llm_raw.get("max_tokens", 900))),
        plan_max_tokens=int(os.getenv("RGPTG_PLAN_MAX_TOKENS", llm_raw.get("plan_max_tokens", 700))),
        expand_max_tokens=int(os.getenv("RGPTG_EXPAND_MAX_TOKENS", llm_raw.get("expand_max_tokens", 360))),
        aggregate_max_tokens=int(os.getenv("RGPTG_AGGREGATE_MAX_TOKENS", llm_raw.get("aggregate_max_tokens", 700))),
    )
    kg = KGConfig(
        provider=os.getenv("RGPTG_KG_PROVIDER", kg_raw.get("provider", "json")),
        json_path=os.getenv("RGPTG_KG_JSON_PATH", kg_raw.get("json_path", "data/sample_kg.json")),
        neo4j_uri=os.getenv("RGPTG_NEO4J_URI", kg_raw.get("neo4j_uri", "bolt://localhost:7687")),
        neo4j_user=os.getenv(kg_raw.get("neo4j_user_env", "NEO4J_USER"), kg_raw.get("neo4j_user")),
        neo4j_password=os.getenv(
            kg_raw.get("neo4j_password_env", "NEO4J_PASSWORD"),
            kg_raw.get("neo4j_password"),
        ),
    )
    runtime = RuntimeConfig(
        max_workers=int(os.getenv("RGPTG_MAX_WORKERS", runtime_raw.get("max_workers", 4)))
    )
    return AppConfig(llm=llm, kg=kg, runtime=runtime)
