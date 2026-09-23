"""
LLM Manager - Centralized LLM configuration and instance management
Provides singleton-like access to LLM instances throughout the application.
Supports Azure OpenAI, AWS Bedrock with Claude models, and Azure Anthropic (Claude on Azure AI Foundry).
"""

import asyncio
import logging
import os
from functools import lru_cache
from typing import Optional, Dict, Any

import boto3
from botocore.config import Config
from langchain_anthropic import ChatAnthropic
from langchain_aws import ChatBedrock
from langchain_openai import AzureChatOpenAI

from .config import load_config_from_db
from .config import should_use_database_config

logger = logging.getLogger(__name__)


class LLMManager:
    """
    Centralized LLM Manager for the application.
    Can load configuration from database or fallback to environment variables.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the LLM Manager with configuration.

        Args:
            config: Configuration dictionary. If None, uses CONFIG_DB flag to determine source.
        """
        self._llm = None
        self.config = config

        # Initialize price fields
        self.price_usd_per_1k_ip_tokens = 0
        self.price_usd_per_1k_op_tokens = 0

        if config:
            self._load_from_config(config)
        else:
            # Load based on CONFIG_DB flag
            if should_use_database_config():
                self._load_from_database()
            else:
                self._load_from_environment()

        self._initialize_llm()

    def _load_from_database(self):
        """Load configuration from database."""
        try:

            # Check if we're already in an event loop
            try:
                # If we're in an async context, we can't create a new loop
                asyncio.get_running_loop()
                logger.error("Cannot load database config synchronously from within async context. "
                             "Use get_llm_async() instead.")
                raise ValueError("Cannot load database config synchronously from within async context. "
                                 "Use get_llm_async() instead.")
            except RuntimeError:
                # No running loop, safe to create one
                pass

            # Get database config
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                config = loop.run_until_complete(load_config_from_db())
            finally:
                loop.close()

            if not config:
                raise ValueError("CONFIG_DB=true but no database configuration found. "
                                 "Please configure the application through the UI or "
                                 "set CONFIG_DB=false to use environment variables.")

            # Extract LLM config - same as _load_from_config but from DB
            llm_config = config.get("llm", {})
            mode = llm_config.get("mode", "").upper()

            # Extract price fields
            self.price_usd_per_1k_ip_tokens = llm_config.get("price_usd_per_1k_ip_tokens", 0)
            self.price_usd_per_1k_op_tokens = llm_config.get("price_usd_per_1k_op_tokens", 0)

            if mode == "AZURE_OPENAI":
                self.llm_mode = "AZURE_OPENAI"
                self.azure_endpoint = llm_config.get("azure_endpoint")
                self.azure_api_key = llm_config.get("azure_api_key")
                self.azure_api_version = llm_config.get("azure_api_version", "2024-02-15-preview")
                self.azure_deployment = llm_config.get("azure_deployment", "gpt-4")

                if not self.azure_endpoint or not self.azure_api_key:
                    raise ValueError("Azure OpenAI configuration missing required fields: endpoint_url, api_key")

            elif mode == "AWS_BEDROCK":
                self.llm_mode = "AWS_BEDROCK"
                self.aws_region = llm_config.get("aws_region", "us-east-1")
                self.bedrock_model_id = llm_config.get("bedrock_model_id", "us.anthropic.claude-sonnet-4-20250514-v1:0")
                self.aws_bedrock_bearer_token = llm_config.get("api_key")
                self.aws_profile = llm_config.get("aws_profile")
                self.aws_access_key_id = llm_config.get("aws_access_key_id")
                self.aws_secret_access_key = llm_config.get("aws_secret_access_key")

            elif mode == "AZURE_ANTHROPIC":
                self.llm_mode = "AZURE_ANTHROPIC"
                self.azure_anthropic_endpoint = llm_config.get("azure_anthropic_endpoint")
                self.azure_anthropic_api_key = llm_config.get("api_key")
                self.azure_anthropic_model_id = llm_config.get("azure_anthropic_model_id", "claude-haiku-4-5")

                if not self.azure_anthropic_endpoint or not self.azure_anthropic_api_key:
                    raise ValueError("Azure Anthropic configuration missing required fields: endpoint, api_key")

            else:
                raise ValueError(f"Unsupported LLM mode in database config: {mode}")

        except Exception as e:
            raise ValueError(f"Failed to load LLM configuration from database: {e}")

    def _load_from_config(self, config: Dict[str, Any]):
        """Load configuration from config dictionary"""
        llm_config = config.get("llm")

        # Check if LLM config is None (CONFIG_DB=true but no database config)
        if llm_config is None:
            raise ValueError("CONFIG_DB=true but no LLM configuration found in database. "
                             "Please configure LLM settings through the UI or "
                             "set CONFIG_DB=false to use environment variables.")

        mode = llm_config.get("mode", "").upper()

        # Extract price fields
        self.price_usd_per_1k_ip_tokens = llm_config.get("price_usd_per_1k_ip_tokens", 0)
        self.price_usd_per_1k_op_tokens = llm_config.get("price_usd_per_1k_op_tokens", 0)

        if mode == "AZURE_OPENAI":
            self.llm_mode = "AZURE_OPENAI"
            self.azure_endpoint = llm_config.get("azure_endpoint")
            self.azure_api_key = llm_config.get("azure_api_key")
            self.azure_api_version = llm_config.get("azure_api_version", "2024-02-15-preview")
            self.azure_deployment = llm_config.get("azure_deployment", "gpt-4")

            if not self.azure_endpoint or not self.azure_api_key:
                raise ValueError("Azure OpenAI configuration missing required fields: endpoint_url, api_key")

        elif mode == "AWS_BEDROCK":
            self.llm_mode = "AWS_BEDROCK"
            self.aws_region = llm_config.get("aws_region", "us-east-1")
            self.bedrock_model_id = llm_config.get("bedrock_model_id", "us.anthropic.claude-sonnet-4-20250514-v1:0")
            self.aws_bedrock_bearer_token = llm_config.get("api_key")  # Bearer token from database
            self.aws_profile = llm_config.get("aws_profile")
            self.aws_access_key_id = llm_config.get("aws_access_key_id")
            self.aws_secret_access_key = llm_config.get("aws_secret_access_key")

        elif mode == "AZURE_ANTHROPIC":
            self.llm_mode = "AZURE_ANTHROPIC"
            self.azure_anthropic_endpoint = llm_config.get("azure_anthropic_endpoint")
            self.azure_anthropic_api_key = llm_config.get("api_key")
            self.azure_anthropic_model_id = llm_config.get("azure_anthropic_model_id", "claude-haiku-4-5")

            if not self.azure_anthropic_endpoint or not self.azure_anthropic_api_key:
                raise ValueError("Azure Anthropic configuration missing required fields: endpoint, api_key")

        else:
            raise ValueError(f"Unsupported LLM mode in database config: {mode}")

        logger.info(f"LLMManager loaded configuration from database: {self.llm_mode}")

    def _load_from_environment(self):
        """
        Load environment variables based on LLM mode (fallback)
        """
        self.llm_mode = os.getenv("LLM_MODE", "AZURE_OPENAI").upper()

        # Load price configuration from environment
        self.price_usd_per_1k_ip_tokens = float(os.getenv("PRICE_USD_PER_1K_IP_TOKENS", "0"))
        self.price_usd_per_1k_op_tokens = float(os.getenv("PRICE_USD_PER_1K_OP_TOKENS", "0"))

        if self.llm_mode == "AZURE_OPENAI":
            # Azure OpenAI configuration
            self.azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
            self.azure_api_key = os.getenv("AZURE_OPENAI_API_KEY")
            self.azure_api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
            self.azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4")

            if not self.azure_endpoint or not self.azure_api_key:
                raise ValueError(
                    "Azure OpenAI configuration missing. Please set AZURE_OPENAI_ENDPOINT "
                    "and AZURE_OPENAI_API_KEY in your .env file. "
                    "See AZURE_SETUP.md for detailed setup instructions."
                )

        elif self.llm_mode == "AWS_BEDROCK":

            if os.getenv("AWS_BEARER_TOKEN_BEDROCK"):
                self.aws_bedrock_bearer_token = os.getenv("AWS_BEARER_TOKEN_BEDROCK")

            # AWS Bedrock configuration
            self.aws_profile = os.getenv("AWS_PROFILE")
            self.aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
            self.aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
            self.aws_region = os.getenv("AWS_REGION", "us-east-1")
            # Cross-region inference profiles (us.anthropic.*) provide better availability
            # and can handle traffic bursts by routing across multiple regions
            self.bedrock_model_id = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0")

            # Validate AWS authentication - either profile or keys must be provided
            if (not self.aws_bedrock_bearer_token and not self.aws_profile and
                    (not self.aws_access_key_id or not self.aws_secret_access_key)):
                raise ValueError(
                    "AWS authentication missing. Please set either AWS_BEARER_TOKEN_BEDROCK or AWS_PROFILE or "
                    "both AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in your .env file."
                )

        elif self.llm_mode == "AZURE_ANTHROPIC":
            # Azure Anthropic (Claude on Azure AI Foundry) configuration
            self.azure_anthropic_endpoint = os.getenv("AZURE_ANTHROPIC_ENDPOINT")
            self.azure_anthropic_api_key = os.getenv("AZURE_ANTHROPIC_API_KEY")
            self.azure_anthropic_model_id = os.getenv("AZURE_ANTHROPIC_MODEL_ID", "claude-haiku-4-5")

            if not self.azure_anthropic_endpoint or not self.azure_anthropic_api_key:
                raise ValueError(
                    "Azure Anthropic configuration missing. Please set AZURE_ANTHROPIC_ENDPOINT "
                    "and AZURE_ANTHROPIC_API_KEY in your .env file."
                )

        else:
            raise ValueError(
                f"Invalid LLM_MODE: {self.llm_mode}. Must be 'AZURE_OPENAI', 'AWS_BEDROCK', or 'AZURE_ANTHROPIC'")

        logger.info(f"LLMManager loaded configuration from environment: {self.llm_mode}")

    def _initialize_llm(self):
        """
        Initialize the LLM instance based on the selected mode.
        """
        try:
            if self.llm_mode == "AZURE_OPENAI":

                self._llm = AzureChatOpenAI(
                    azure_endpoint=self.azure_endpoint,
                    api_key=self.azure_api_key,
                    api_version=self.azure_api_version,
                    azure_deployment=self.azure_deployment,
                )

            elif self.llm_mode == "AZURE_ANTHROPIC":
                # Azure Anthropic (Claude on Azure AI Foundry) configuration
                # Use the endpoint URL directly (e.g., https://resource.services.ai.azure.com/anthropic/v1/messages)
                # Strip trailing /v1/messages if present, as ChatAnthropic adds it automatically
                base_url = self.azure_anthropic_endpoint.rstrip("/")
                if base_url.endswith("/v1/messages"):
                    base_url = base_url[:-len("/v1/messages")]
                elif base_url.endswith("/v1"):
                    base_url = base_url[:-len("/v1")]

                self._llm = ChatAnthropic(
                    model=self.azure_anthropic_model_id,
                    base_url=base_url,
                    api_key=self.azure_anthropic_api_key,
                    default_headers={"anthropic-version": "2023-06-01"},
                    max_tokens=16384,
                    temperature=0,
                    max_retries=3,  # Retry on rate limits (429) and transient errors with exponential backoff
                )
                logger.info(
                    f"Initialized ChatAnthropic for Azure AI Foundry with model {self.azure_anthropic_model_id} at {base_url} with 3 retries")

            elif self.llm_mode == "AWS_BEDROCK":

                # Configure AWS credentials - prefer profile over keys
                bedrock_kwargs = {
                    "model_id": self.bedrock_model_id,
                    "region_name": self.aws_region,
                    "temperature": 0,
                    "max_tokens": 16384
                }

                if self.aws_bedrock_bearer_token:

                    os.environ['AWS_BEARER_TOKEN_BEDROCK'] = self.aws_bedrock_bearer_token

                    # Configure Bedrock client with production timeouts
                    bedrock_config = Config(
                        read_timeout=120,  # 2 minutes for model inference
                        connect_timeout=60,  # 1 minute for connection
                        retries={
                            'max_attempts': 3,
                            'mode': 'adaptive'
                        }
                    )

                    bedrock_client = boto3.client(
                        service_name="bedrock-runtime",
                        region_name=self.aws_region,
                        config=bedrock_config
                    )

                    bedrock_kwargs['client'] = bedrock_client

                elif self.aws_profile:
                    # Use AWS profile for authentication with production timeouts
                    bedrock_config = Config(
                        read_timeout=120,  # 2 minutes for model inference
                        connect_timeout=60,  # 1 minute for connection
                        retries={
                            'max_attempts': 3,
                            'mode': 'adaptive'
                        }
                    )

                    bedrock_client = boto3.client(
                        service_name="bedrock-runtime",
                        region_name=self.aws_region,
                        config=bedrock_config
                    )

                    bedrock_kwargs['client'] = bedrock_client
                    bedrock_kwargs["credentials_profile_name"] = self.aws_profile

                else:
                    # Use explicit credentials with production timeouts
                    bedrock_config = Config(
                        read_timeout=120,  # 2 minutes for model inference
                        connect_timeout=60,  # 1 minute for connection
                        retries={
                            'max_attempts': 3,
                            'mode': 'adaptive'
                        }
                    )

                    bedrock_client = boto3.client(
                        service_name="bedrock-runtime",
                        region_name=self.aws_region,
                        config=bedrock_config
                    )

                    bedrock_kwargs['client'] = bedrock_client

                self._llm = ChatBedrock(**bedrock_kwargs)
                logger.info(f"Initialized ChatBedrock with 120s read timeout and adaptive retry policy")

        except Exception as e:

            raise RuntimeError(f"Failed to initialize {self.llm_mode} LLM: {str(e)}")

    def get_llm(self):
        """
        Get the initialized LLM instance with retry logic for rate limits.

        Applies LangChain's RunnableRetry with exponential backoff and jitter
        to handle rate limit errors (429) and other transient failures.

        Retry timing:
        - 1st retry: 5-10 seconds
        - 2nd retry: 7.5-12.5 seconds
        - 3rd retry: 11.25-16.25 seconds
        - And so on up to 10 retries with max 60 second delays
        """
        return self._llm

    def get_config(self):
        """
        Get the LLM configuration based on the selected mode.
        """
        if self.llm_mode == "AZURE_OPENAI":

            return {
                "mode": self.llm_mode,
                "azure_endpoint": self.azure_endpoint,
                "azure_api_version": self.azure_api_version,
                "azure_deployment": self.azure_deployment
            }

        elif self.llm_mode == "AZURE_ANTHROPIC":

            return {
                "mode": self.llm_mode,
                "azure_anthropic_endpoint": self.azure_anthropic_endpoint,
                "azure_anthropic_model_id": self.azure_anthropic_model_id
            }

        else:

            config = {
                "mode": self.llm_mode,
                "aws_region": self.aws_region,
                "bedrock_model_id": self.bedrock_model_id
            }

            if self.aws_profile:
                config["aws_profile"] = self.aws_profile
            else:
                config["auth_method"] = "environment_variables"

            return config

    def get_price(self) -> dict:
        """
        Get LLM pricing configuration.

        Returns:
            Dictionary with 'input' and 'output' price per 1000 tokens in USD.
            Example: {"input": 0.01, "output": 0.03}
        """
        return {
            "input": self.price_usd_per_1k_ip_tokens,
            "output": self.price_usd_per_1k_op_tokens
        }


@lru_cache(maxsize=1)
def _get_llm_manager():
    """
    Create and cache a single LLMManager instance.
    Thread-safe singleton pattern using lru_cache.
    """
    return LLMManager()


def get_llm():
    """
    Get the LLM instance from the singleton LLMManager.

    This function provides efficient, thread-safe access to the LLM instance
    with connection pooling benefits. The LLMManager is created only once
    and reused across all calls.

    Returns:
        LangChain LLM instance with retry logic applied
    """
    return _get_llm_manager().get_llm()


def clear_llm_manager_cache():
    """
    Clear the LLM manager cache to force reinitialization with new config.
    Call this when configuration is updated.
    """
    _get_llm_manager.cache_clear()
    logger.info("LLM manager cache cleared - will reinitialize with new config on next access")


async def get_llm_async():
    """
    Get primary LLM instance asynchronously with database configuration.

    This version loads configuration from the database asynchronously, avoiding
    event loop conflicts in FastAPI contexts.

    Returns:
        Primary LLM instance (ChatOpenAI or ChatBedrock) for triage and complex operations
    """
    config = None
    if should_use_database_config():
        # Load config from database asynchronously
        config = await load_config_from_db()
        if not config:
            raise ValueError(
                "CONFIG_DB=true but no database configuration found. Please configure the application through the UI or set CONFIG_DB=false to use environment variables.")

    llm_manager = LLMManager(config=config)
    return llm_manager.get_llm()


async def get_primary_llm_async():
    """
    Get primary LLM instance asynchronously - alias for get_llm_async for clarity.

    Returns:
        Primary LLM instance for triage, orchestrator, and complex reasoning operations
    """
    return await get_llm_async()


def get_prompt_caching_middleware(llm_mode: str):
    """
    Get the appropriate prompt caching middleware based on LLM provider.

    This is the single source of truth for prompt caching middleware selection.
    Returns a middleware object (or None) that can be used in two ways:
    1. Passed to create_agent() via middleware parameter (universal approach)
    2. Used with llm.with_middleware() for providers that support it

    Prompt caching reduces token costs by ~70% by caching static parts of prompts
    (system prompts and tool definitions) that don't change between calls.

    Args:
        llm_mode: LLM provider mode ("AZURE_OPENAI", "AWS_BEDROCK", or "AZURE_ANTHROPIC")

    Returns:
        Middleware instance or None if not applicable/not supported
    """
    if llm_mode == "AZURE_OPENAI":
        # Azure OpenAI has automatic prompt caching enabled by default
        # No middleware needed - caching happens transparently
        logger.info("Azure OpenAI detected - using automatic prompt caching (no middleware needed)")
        return None

    elif llm_mode == "AWS_BEDROCK":
        # AWS Bedrock requires explicit prompt caching middleware
        try:
            from langchain_aws.middleware.prompt_caching import BedrockPromptCachingMiddleware
            logger.info("AWS Bedrock detected - returning BedrockPromptCachingMiddleware with 1-hour TTL")
            return BedrockPromptCachingMiddleware(ttl="1h")
        except ImportError as e:
            logger.warning(f"Failed to import BedrockPromptCachingMiddleware: {e}. Proceeding without caching.")
            return None

    elif llm_mode == "AZURE_ANTHROPIC":
        # Azure Anthropic requires explicit prompt caching middleware
        try:
            from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware
            logger.info("Azure Anthropic detected - returning AnthropicPromptCachingMiddleware with 1-hour TTL")
            return AnthropicPromptCachingMiddleware(ttl="1h")
        except ImportError as e:
            logger.warning(f"Failed to import AnthropicPromptCachingMiddleware: {e}. Proceeding without caching.")
            return None

    else:
        logger.warning(f"Unknown LLM mode '{llm_mode}' - proceeding without prompt caching")
        return None


def wrap_llm_with_caching(llm, llm_mode: str):
    """
    Wrap LLM instance with prompt caching middleware based on provider.

    This function uses get_prompt_caching_middleware() to get the middleware,
    then applies it appropriately based on LLM provider capabilities.

    Note: Only use this for direct LLM wrapping (e.g., secondary LLM, RAG).
    For agents using create_agent(), use get_prompt_caching_middleware() directly
    and pass the middleware to create_agent()'s middleware parameter.

    Args:
        llm: LangChain LLM instance to wrap
        llm_mode: LLM provider mode ("AZURE_OPENAI", "AWS_BEDROCK", or "AZURE_ANTHROPIC")

    Returns:
        LLM instance wrapped with appropriate caching middleware, or original LLM if no caching needed
    """
    middleware = get_prompt_caching_middleware(llm_mode)

    if middleware is None:
        return llm

    # Try to wrap using .with_middleware() if the LLM supports it
    # This works for ChatBedrockConverse but not ChatAnthropic
    if hasattr(llm, 'with_middleware'):
        try:
            return llm.with_middleware([middleware])
        except Exception as e:
            logger.warning(f"Failed to apply middleware via with_middleware(): {e}. Returning unwrapped LLM.")
            return llm
    else:
        # LLM doesn't support .with_middleware() (e.g., ChatAnthropic)
        # For these cases, the middleware should be passed to create_agent() instead
        logger.warning(f"LLM {type(llm).__name__} doesn't support .with_middleware(). "
                      f"For agents, pass middleware to create_agent() instead.")
        return llm


async def get_secondary_llm_async():
    """
    Get secondary LLM instance asynchronously for evaluation and RAG operations with prompt caching.

    If no secondary LLM is configured, falls back to primary LLM.
    Applies prompt caching middleware to reduce costs for evaluation and RAG operations.

    Returns:
        Secondary LLM instance (ChatOpenAI or ChatBedrock) with caching middleware for evaluation and RAG
    """
    config = None
    if should_use_database_config():
        # Load config from database asynchronously
        config = await load_config_from_db()
        if not config:
            raise ValueError(
                "CONFIG_DB=true but no database configuration found. "
                "Please configure the application through the UI or set CONFIG_DB=false to use environment variables."
            )

    # Check if secondary LLM is configured
    if config and config.get("secondary_llm"):
        # Create LLM manager with secondary config
        secondary_config = {
            "llm": config["secondary_llm"]
        }
        llm_manager = LLMManager(config=secondary_config)
        llm = llm_manager.get_llm()
        llm_mode = llm_manager.llm_mode

        # Apply prompt caching to secondary LLM
        llm_with_caching = wrap_llm_with_caching(llm, llm_mode)
        logger.info(f"Secondary LLM initialized with caching support (mode: {llm_mode})")
        return llm_with_caching
    else:
        # Fall back to primary LLM
        logger.info("No secondary LLM configured, using primary LLM for evaluation/RAG operations")
        primary_llm = await get_llm_async()

        # Get primary LLM mode for caching
        primary_config = config if config else None
        primary_llm_manager = LLMManager(config=primary_config)
        primary_llm_mode = primary_llm_manager.llm_mode

        # Apply caching to primary LLM when used as secondary
        llm_with_caching = wrap_llm_with_caching(primary_llm, primary_llm_mode)
        logger.info(f"Using primary LLM as secondary with caching (mode: {primary_llm_mode})")
        return llm_with_caching


async def get_primary_llm_price() -> dict:
    """
    Get primary LLM pricing configuration.

    Returns:
        Dictionary with 'input' and 'output' price per 1000 tokens in USD.
        Example: {"input": 0.01, "output": 0.03}
    """
    config = None
    if should_use_database_config():
        # Load config from database asynchronously
        config = await load_config_from_db()
        if not config:
            raise ValueError(
                "CONFIG_DB=true but no database configuration found. Please configure the application through the UI or set CONFIG_DB=false to use environment variables.")

    llm_manager = LLMManager(config=config)
    return llm_manager.get_price()


async def get_secondary_llm_price() -> dict:
    """
    Get secondary LLM pricing configuration.

    If no secondary LLM is configured, falls back to primary LLM prices.

    Returns:
        Dictionary with 'input' and 'output' price per 1000 tokens in USD.
        Example: {"input": 0.005, "output": 0.015}
    """
    config = None
    if should_use_database_config():
        config = await load_config_from_db()
        if not config:
            raise ValueError(
                "CONFIG_DB=true but no database configuration found. "
                "Please configure the application through the UI or set CONFIG_DB=false to use environment variables."
            )

    # Check if secondary LLM is configured
    if config and config.get("secondary_llm"):
        secondary_config = {
            "llm": config["secondary_llm"]
        }
        llm_manager = LLMManager(config=secondary_config)
        return llm_manager.get_price()
    else:
        # Fall back to primary LLM prices
        return await get_primary_llm_price()
