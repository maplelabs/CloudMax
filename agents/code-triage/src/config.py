"""Configuration and environment setup"""

import os
import logging
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from the code-triage-agent's local .env, if present.
# This avoids accidentally picking up the monorepo root .env when running from
# different working directories.
BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

# LLM Mode Configuration - determines which LLM provider to use
LLM_MODE = os.getenv("LLM_MODE", "AWS_BEDROCK").upper()

# AWS Bedrock Configuration
BEDROCK_API_KEY = os.getenv("BEDROCK_API_KEY", "")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
BEDROCK_MODEL_ID = os.getenv(
    "BEDROCK_MODEL_ID",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0"
)
BEDROCK_MAX_TOKENS = int(os.getenv("BEDROCK_MAX_TOKENS", "4096"))
BEDROCK_TEMPERATURE = float(os.getenv("BEDROCK_TEMPERATURE", "0.1"))

# Azure Anthropic Configuration
AZURE_ANTHROPIC_ENDPOINT = os.getenv("AZURE_ANTHROPIC_ENDPOINT", "")
AZURE_ANTHROPIC_API_KEY = os.getenv("AZURE_ANTHROPIC_API_KEY", "")
AZURE_ANTHROPIC_MODEL_ID = os.getenv("AZURE_ANTHROPIC_MODEL_ID", "claude-haiku-4-5")
AZURE_ANTHROPIC_MAX_TOKENS = int(os.getenv("AZURE_ANTHROPIC_MAX_TOKENS", "4096"))
AZURE_ANTHROPIC_TEMPERATURE = float(os.getenv("AZURE_ANTHROPIC_TEMPERATURE", "0.1"))

# GitHub MCP Configuration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_MCP_URL = os.getenv("GITHUB_MCP_URL", "https://api.githubcopilot.com/mcp/x/repos/readonly")

# Agent Configuration
ORCHESTRATOR_PORT = int(os.getenv("ORCHESTRATOR_PORT", "8002"))

# Logging Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Our own modules: allow INFO/DEBUG as controlled by LOG_LEVEL
logging.getLogger("src.mcp_tools").setLevel(logging.DEBUG)
logging.getLogger("src.agents.middlewares.cache_monitor").setLevel(logging.DEBUG)

# Third-party libraries: reduce noisy INFO logs to WARNING by default
logging.getLogger("botocore.tokens").setLevel(logging.WARNING)
logging.getLogger("langchain_aws.llms.bedrock").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("mcp.client.streamable_http").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def validate_config():
    """Validate required configuration

    Raises:
        ValueError: If any required environment variables are missing

    Returns:
        bool: True if all required configuration is valid
    """
    errors = []

    # Validate LLM configuration based on mode
    if LLM_MODE == "AWS_BEDROCK":
        if not BEDROCK_API_KEY:
            errors.append("BEDROCK_API_KEY is required when LLM_MODE=AWS_BEDROCK")
    elif LLM_MODE == "AZURE_ANTHROPIC":
        if not AZURE_ANTHROPIC_ENDPOINT:
            errors.append("AZURE_ANTHROPIC_ENDPOINT is required when LLM_MODE=AZURE_ANTHROPIC")
        if not AZURE_ANTHROPIC_API_KEY:
            errors.append("AZURE_ANTHROPIC_API_KEY is required when LLM_MODE=AZURE_ANTHROPIC")
    else:
        errors.append(f"Invalid LLM_MODE: {LLM_MODE}. Must be 'AWS_BEDROCK' or 'AZURE_ANTHROPIC'")

    if not GITHUB_TOKEN:
        errors.append("GITHUB_TOKEN is required but not set")

    if errors:
        error_message = "Configuration validation failed:\n" + "\n".join(f"  - {err}" for err in errors)
        logger.error(error_message)
        raise ValueError(error_message)

    logger.info("Configuration validation successful (LLM_MODE=%s)", LLM_MODE)
    return True

