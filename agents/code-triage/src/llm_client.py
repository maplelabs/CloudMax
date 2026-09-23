"""Multi-provider LLM client helper using LangChain.

Supports both AWS Bedrock and Azure Anthropic based on LLM_MODE configuration.
- AWS Bedrock: 120s read timeout, 60s connect timeout, 3 max retries
- Azure Anthropic: Direct API connection to Azure AI Foundry

Prompt caching reduces token costs by ~70% by caching static parts of prompts
(system prompts and tool definitions) that don't change between calls.
"""

import logging
import os

import boto3
from botocore.config import Config
from langchain_aws import ChatBedrockConverse
from langchain_anthropic import ChatAnthropic

from src.config import (
    LLM_MODE,
    BEDROCK_API_KEY,
    AWS_REGION,
    BEDROCK_MODEL_ID,
    AZURE_ANTHROPIC_ENDPOINT,
    AZURE_ANTHROPIC_API_KEY,
    AZURE_ANTHROPIC_MODEL_ID,
)

logger = logging.getLogger(__name__)


def get_llm(temperature: float = 0.1, max_tokens: int = 2000):
    """Return a configured LLM instance based on LLM_MODE configuration.

    Args:
        temperature: Sampling temperature for the model.
        max_tokens: Maximum tokens to generate in a single call.

    Returns:
        LangChain LLM instance (ChatBedrockConverse or ChatAnthropic)

    Raises:
        ValueError: If LLM_MODE is invalid or required configuration is missing
    """

    if LLM_MODE == "AWS_BEDROCK":
        return _get_bedrock_llm(temperature, max_tokens)
    elif LLM_MODE == "AZURE_ANTHROPIC":
        return _get_azure_anthropic_llm(temperature, max_tokens)
    else:
        raise ValueError(
            f"Invalid LLM_MODE: {LLM_MODE}. Must be 'AWS_BEDROCK' or 'AZURE_ANTHROPIC'"
        )


def _get_bedrock_llm(temperature: float = 0.1, max_tokens: int = 2000):
    """Return a configured ChatBedrockConverse LLM instance.

    Configuration matches backend's production settings:
    - Read timeout: 120s (2 minutes for model inference)
    - Connect timeout: 60s (1 minute for connection)
    - Retries: 3 max attempts with adaptive mode (exponential backoff)

    Uses ChatBedrockConverse which supports the Converse API and structured outputs
    via response_format parameter (required for create_agent with structured output).
    """

    # Set bearer token via environment (boto3 will pick it up)
    os.environ["AWS_BEARER_TOKEN_BEDROCK"] = BEDROCK_API_KEY

    # Configure Bedrock client with production timeouts and retry policy
    bedrock_config = Config(
        read_timeout=120,  # 2 minutes for model inference
        connect_timeout=60,  # 1 minute for connection
        retries={"max_attempts": 3, "mode": "adaptive"},  # Adaptive retry with exponential backoff
    )

    # Create boto3 client with the production configuration
    bedrock_client = boto3.client(
        service_name="bedrock-runtime",
        region_name=AWS_REGION,
        config=bedrock_config,
    )

    # Initialize ChatBedrockConverse with the configured client
    llm = ChatBedrockConverse(
        model=BEDROCK_MODEL_ID,
        region_name=AWS_REGION,
        client=bedrock_client,  # Use configured client with timeouts and retries
        temperature=temperature,
        max_tokens=max_tokens,
        credentials_profile_name=None,  # Don't use AWS profile, rely on bearer token
    )

    logger.info(
        "Initialized ChatBedrockConverse: %s (temp=%s, max_tokens=%s) with 120s timeout and 3 retries",
        BEDROCK_MODEL_ID,
        temperature,
        max_tokens,
    )
    return llm


def _get_azure_anthropic_llm(temperature: float = 0.1, max_tokens: int = 2000):
    """Return a configured ChatAnthropic LLM instance for Azure AI Foundry.

    Connects to Azure AI Foundry's Anthropic endpoint with proper configuration.
    The endpoint URL is processed to ensure correct format (ChatAnthropic adds
    /v1/messages automatically).
    """

    if not AZURE_ANTHROPIC_ENDPOINT:
        raise ValueError(
            "AZURE_ANTHROPIC_ENDPOINT is required when LLM_MODE=AZURE_ANTHROPIC. "
            "Please set it in your .env file."
        )

    if not AZURE_ANTHROPIC_API_KEY:
        raise ValueError(
            "AZURE_ANTHROPIC_API_KEY is required when LLM_MODE=AZURE_ANTHROPIC. "
            "Please set it in your .env file."
        )

    # Strip trailing slashes and /v1/messages path if present
    # ChatAnthropic will add these automatically
    base_url = AZURE_ANTHROPIC_ENDPOINT.rstrip("/")
    if base_url.endswith("/v1/messages"):
        base_url = base_url[: -len("/v1/messages")]
    elif base_url.endswith("/v1"):
        base_url = base_url[: -len("/v1")]

    # Create ChatAnthropic instance configured for Azure AI Foundry
    llm = ChatAnthropic(
        model=AZURE_ANTHROPIC_MODEL_ID,
        base_url=base_url,
        api_key=AZURE_ANTHROPIC_API_KEY,
        default_headers={"anthropic-version": "2023-06-01"},
        max_tokens=max_tokens,
        temperature=temperature,
    )

    logger.info(
        "Initialized ChatAnthropic for Azure AI Foundry: %s (temp=%s, max_tokens=%s, endpoint=%s)",
        AZURE_ANTHROPIC_MODEL_ID,
        temperature,
        max_tokens,
        base_url,
    )
    return llm


def get_prompt_caching_middleware():
    """
    Get the appropriate prompt caching middleware based on LLM provider.

    Prompt caching reduces token costs by ~70% by caching static parts of prompts
    (system prompts and tool definitions) that don't change between calls.

    Returns:
        Middleware instance or None if not applicable/not supported
    """
    if LLM_MODE == "AWS_BEDROCK":
        # AWS Bedrock requires explicit prompt caching middleware
        try:
            from langchain_aws.middleware.prompt_caching import BedrockPromptCachingMiddleware
            logger.info("AWS Bedrock detected - returning BedrockPromptCachingMiddleware with 1-hour TTL")
            return BedrockPromptCachingMiddleware(ttl="1h")
        except ImportError as e:
            logger.warning(f"Failed to import BedrockPromptCachingMiddleware: {e}. Proceeding without caching.")
            return None

    elif LLM_MODE == "AZURE_ANTHROPIC":
        # Azure Anthropic requires explicit prompt caching middleware
        try:
            from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware
            logger.info("Azure Anthropic detected - returning AnthropicPromptCachingMiddleware with 1-hour TTL")
            return AnthropicPromptCachingMiddleware(ttl="1h")
        except ImportError as e:
            logger.warning(f"Failed to import AnthropicPromptCachingMiddleware: {e}. Proceeding without caching.")
            return None

    else:
        logger.warning(f"Unknown LLM mode '{LLM_MODE}' - proceeding without prompt caching")
        return None
