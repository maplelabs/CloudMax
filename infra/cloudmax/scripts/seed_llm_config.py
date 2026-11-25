"""
One-off seed: populate CloudMax's AppConfig.primary_llm_provider /
primary_llm_connection_config and AppConfig.embedding_provider /
embedding_connection_config so these don't have to be configured by hand
through the Settings UI after every demo deploy.

Run inside the cloudmax-backend container (has DATABASE_URL + all the
app's own models already available on PYTHONPATH=/app), so this reuses the
exact same SQLAlchemy models/Pydantic config shapes the running app itself
uses -- no hand-written SQL, no enum-type guessing.

ALL values (including both API keys) are read from this process's own
environment -- nothing is hardcoded here and nothing is passed as a CLI
argument (which would risk appearing in `docker inspect`/process-list
output). The caller (see demo-create.yml's "Seed CloudMax LLM/Embedding
config" step) populates these env vars from non-secret repo Variables
(provider selection, endpoint URLs, model/deployment IDs, price per 1k
tokens, API version) and repo Secrets (the two API keys).

Required env vars (always):
  LLM_PROVIDER            one of: azure-anthropic, azure-openai, aws-bedrock-claude
  LLM_API_KEY             (ignored/optional for aws-bedrock-claude, which still calls it api_key)
  LLM_MODEL_ID            used as model_id (anthropic/bedrock) or deployment_name (azure-openai)
  LLM_PRICE_PER_1K_INPUT_TOKENS
  LLM_PRICE_PER_1K_OUTPUT_TOKENS
  EMBEDDING_LLM_PROVIDER  must be: azure-openai (the only embedding provider CloudMax supports)
  EMBEDDING_API_KEY
  EMBEDDING_ENDPOINT_URL
  EMBEDDING_DEPLOYMENT_NAME
  EMBEDDING_API_VERSION

Conditionally required:
  LLM_ENDPOINT_URL  required for azure-anthropic / azure-openai
  LLM_API_VERSION   optional for azure-openai (falls back to CloudMax's own default)
  LLM_REGION        required for aws-bedrock-claude

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

LLM_PROVIDER_BUILDERS = {}
VALID_LLM_PROVIDERS = {p.value for p in LlmProvider}
VALID_EMBEDDING_PROVIDERS = {p.value for p in EmbeddingProvider}


def _env(name, required=True, default=None):
    val = os.environ.get(name, default)
    if required and not val:
        raise SystemExit(f"Missing required env var: {name}")
    return val


def build_primary_llm_connection_config(provider: str) -> dict:
    api_key = _env("LLM_API_KEY")
    price_in = float(_env("LLM_PRICE_PER_1K_INPUT_TOKENS"))
    price_out = float(_env("LLM_PRICE_PER_1K_OUTPUT_TOKENS"))

    if provider == LlmProvider.AZURE_ANTHROPIC.value:
        return {
            "llm_type": provider,
            "endpoint_url": _env("LLM_ENDPOINT_URL"),
            "api_key": api_key,
            "model_id": _env("LLM_MODEL_ID"),
            "price_usd_per_1k_ip_tokens": price_in,
            "price_usd_per_1k_op_tokens": price_out,
        }
    if provider == LlmProvider.AZURE_OPENAI.value:
        return {
            "llm_type": provider,
            "api_key": api_key,
            "endpoint_url": _env("LLM_ENDPOINT_URL"),
            "deployment_name": _env("LLM_MODEL_ID"),
            "api_version": _env("LLM_API_VERSION", required=False, default="2024-02-01"),
            "price_usd_per_1k_ip_tokens": price_in,
            "price_usd_per_1k_op_tokens": price_out,
        }
    if provider == LlmProvider.AWS_BEDROCK_CLAUDE.value:
        return {
            "llm_type": provider,
            "api_key": api_key,
            "region": _env("LLM_REGION"),
            "model_id": _env("LLM_MODEL_ID"),
            "price_usd_per_1k_ip_tokens": price_in,
            "price_usd_per_1k_op_tokens": price_out,
        }
    raise SystemExit(f"Unsupported LLM_PROVIDER '{provider}' -- expected one of {sorted(VALID_LLM_PROVIDERS)}")


def build_embedding_connection_config(provider: str) -> dict:
    if provider != EmbeddingProvider.AZURE_OPENAI.value:
        raise SystemExit(
            f"Unsupported EMBEDDING_LLM_PROVIDER '{provider}' -- expected one of {sorted(VALID_EMBEDDING_PROVIDERS)}"
        )
    return {
        "embedding_type": provider,
        "api_key": _env("EMBEDDING_API_KEY"),
        "endpoint_url": _env("EMBEDDING_ENDPOINT_URL"),
        "deployment_name": _env("EMBEDDING_DEPLOYMENT_NAME"),
        "api_version": _env("EMBEDDING_API_VERSION"),
    }


async def main():
    llm_provider = _env("LLM_PROVIDER")
    embedding_provider = _env("EMBEDDING_LLM_PROVIDER")

    if llm_provider not in VALID_LLM_PROVIDERS:
        raise SystemExit(f"Invalid LLM_PROVIDER '{llm_provider}' -- expected one of {sorted(VALID_LLM_PROVIDERS)}")
    if embedding_provider not in VALID_EMBEDDING_PROVIDERS:
        raise SystemExit(
            f"Invalid EMBEDDING_LLM_PROVIDER '{embedding_provider}' -- expected one of {sorted(VALID_EMBEDDING_PROVIDERS)}"
        )

    primary_llm_connection_config = build_primary_llm_connection_config(llm_provider)
    embedding_connection_config = build_embedding_connection_config(embedding_provider)

    async with async_db_session() as session:
        result = await session.execute(
            select(AppConfig).order_by(AppConfig.id.desc()).limit(1)
        )
        config = result.scalar_one_or_none()

        if config:
            config.primary_llm_provider = LlmProvider(llm_provider)
            config.primary_llm_connection_config = primary_llm_connection_config
            config.embedding_provider = EmbeddingProvider(embedding_provider)
            config.embedding_connection_config = embedding_connection_config
            print(f"Updated existing AppConfig (id={config.id}) with primary LLM + embedding config.")
        else:
            config = AppConfig(
                enabled_severities=[Severity.P1],
                primary_llm_provider=LlmProvider(llm_provider),
                primary_llm_connection_config=primary_llm_connection_config,
                embedding_provider=EmbeddingProvider(embedding_provider),
                embedding_connection_config=embedding_connection_config,
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
