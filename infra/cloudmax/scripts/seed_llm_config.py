"""
One-off seed: populate CloudMax's AppConfig.primary_llm_provider /
primary_llm_connection_config (Azure Anthropic) and
AppConfig.embedding_provider / embedding_connection_config
(Azure OpenAI embeddings) so these don't have to be configured by hand
through the Settings UI after every demo deploy.

Run inside the cloudmax-backend container (has DATABASE_URL + all the
app's own models already available on PYTHONPATH=/app), so this reuses the
exact same SQLAlchemy models/Pydantic config shapes the running app itself
uses -- no hand-written SQL, no enum-type guessing.

ALL values (including both API keys) are read from this process's own
environment -- nothing is hardcoded here and nothing is passed as a CLI
argument (which would risk appearing in `docker inspect`/process-list
output). The caller (see demo-create.yml's "Seed CloudMax LLM/Embedding
config" step) is responsible for populating these env vars from
non-secret repo Variables (endpoint URLs, model/deployment IDs, price per
1k tokens, API version) and Key Vault secrets (the two API keys, fetched
via the VM's own managed identity -- never passed through GitHub Actions).

Required env vars:
  LLM_ENDPOINT_URL, LLM_API_KEY, LLM_MODEL_ID,
  LLM_PRICE_PER_1K_INPUT_TOKENS, LLM_PRICE_PER_1K_OUTPUT_TOKENS
  EMBEDDING_API_KEY, EMBEDDING_ENDPOINT_URL, EMBEDDING_DEPLOYMENT_NAME,
  EMBEDDING_API_VERSION

Idempotent: overwrites only the primary LLM / embedding fields on the
latest AppConfig row (or creates one if none exists yet), leaving every
other field (MCP connections, severities, etc.) untouched.
"""
import asyncio
import os

from sqlalchemy import select

from src.server.apis_v1.dependencies import async_db_session
from src.server.models.db.app_config import AppConfig
from src.server.models.api.enums import Severity, LlmProvider, EmbeddingProvider

REQUIRED_VARS = [
    "LLM_ENDPOINT_URL", "LLM_API_KEY", "LLM_MODEL_ID",
    "LLM_PRICE_PER_1K_INPUT_TOKENS", "LLM_PRICE_PER_1K_OUTPUT_TOKENS",
    "EMBEDDING_API_KEY", "EMBEDDING_ENDPOINT_URL", "EMBEDDING_DEPLOYMENT_NAME",
    "EMBEDDING_API_VERSION",
]


def _require_env():
    missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
    if missing:
        raise SystemExit(f"Missing required env var(s): {', '.join(missing)}")


def primary_llm_connection_config():
    return {
        "llm_type": LlmProvider.AZURE_ANTHROPIC.value,
        "endpoint_url": os.environ["LLM_ENDPOINT_URL"],
        "api_key": os.environ["LLM_API_KEY"],
        "model_id": os.environ["LLM_MODEL_ID"],
        "price_usd_per_1k_ip_tokens": float(os.environ["LLM_PRICE_PER_1K_INPUT_TOKENS"]),
        "price_usd_per_1k_op_tokens": float(os.environ["LLM_PRICE_PER_1K_OUTPUT_TOKENS"]),
    }


def embedding_connection_config():
    return {
        "embedding_type": EmbeddingProvider.AZURE_OPENAI.value,
        "api_key": os.environ["EMBEDDING_API_KEY"],
        "endpoint_url": os.environ["EMBEDDING_ENDPOINT_URL"],
        "deployment_name": os.environ["EMBEDDING_DEPLOYMENT_NAME"],
        "api_version": os.environ["EMBEDDING_API_VERSION"],
    }


async def main():
    _require_env()

    async with async_db_session() as session:
        result = await session.execute(
            select(AppConfig).order_by(AppConfig.id.desc()).limit(1)
        )
        config = result.scalar_one_or_none()

        if config:
            config.primary_llm_provider = LlmProvider.AZURE_ANTHROPIC
            config.primary_llm_connection_config = primary_llm_connection_config()
            config.embedding_provider = EmbeddingProvider.AZURE_OPENAI
            config.embedding_connection_config = embedding_connection_config()
            print(f"Updated existing AppConfig (id={config.id}) with primary LLM + embedding config.")
        else:
            config = AppConfig(
                enabled_severities=[Severity.P1],
                primary_llm_provider=LlmProvider.AZURE_ANTHROPIC,
                primary_llm_connection_config=primary_llm_connection_config(),
                embedding_provider=EmbeddingProvider.AZURE_OPENAI,
                embedding_connection_config=embedding_connection_config(),
                code_triaging_agent_enabled=False,
                orchestrator_agents=1,
                chaos_system_enabled=False,
                automatic_triage=True,
                alert_grouping_enabled=True,
            )
            session.add(config)
            print("No existing AppConfig found -- created a new one with primary LLM + embedding config.")

        await session.commit()


asyncio.run(main())
print("Done.")
