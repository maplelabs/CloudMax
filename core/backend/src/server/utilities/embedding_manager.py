"""
Embedding Manager - Centralized embedding configuration and instance management
Provides singleton-like access to Azure OpenAI embedding instances throughout the application.
Supports loading configuration from database or environment variables.
"""

import asyncio
import logging
import os
from functools import lru_cache
from typing import Optional, Dict, Any

from langchain_openai import AzureOpenAIEmbeddings

from .config import load_config_from_db
from .config import should_use_database_config

logger = logging.getLogger(__name__)


class EmbeddingManager:
    """
    Centralized Embedding Manager for the application.
    Can load configuration from database or fallback to environment variables.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the Embedding Manager with configuration.

        Args:
            config: Configuration dictionary. If None, uses CONFIG_DB flag to determine source.
        """
        self._embedding_model = None
        self.config = config

        if config:
            self._load_from_config(config)
        else:
            # Load based on CONFIG_DB flag
            if should_use_database_config():
                self._load_from_database()
            else:
                self._load_from_environment()

        self._initialize_embedding_model()

    def _load_from_database(self):
        """Load configuration from database."""

        try:

            # Check if we're already in an event loop
            try:
                # If we're in an async context, we can't create a new loop
                asyncio.get_running_loop()
                logger.error(
                    "Cannot load database config synchronously from within async context. Use get_embedding_manager_async() instead.")
                raise ValueError(
                    "Cannot load database config synchronously from within async context. Use get_embedding_manager_async() instead.")
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
                raise ValueError(
                    "CONFIG_DB=true but no database configuration found. Please configure the application through the UI or set CONFIG_DB=false to use environment variables.")

            # Extract embedding config - same as _load_from_config but from DB
            embedding_config = config.get("embedding", {})

            self.azure_endpoint = embedding_config.get("azure_endpoint")
            self.azure_api_key = embedding_config.get("azure_api_key")
            self.azure_api_version = embedding_config.get("azure_api_version", "2024-02-01")
            self.azure_deployment = embedding_config.get("azure_deployment", "text-embedding-3-large")

            if not self.azure_endpoint or not self.azure_api_key:
                raise ValueError(
                    "Azure OpenAI Embedding configuration missing required fields: azure_endpoint, azure_api_key")

        except Exception as e:
            raise ValueError(f"Failed to load Embedding configuration from database: {e}")

    def _load_from_config(self, config: Dict[str, Any]):
        """Load Embedding configuration from database config dictionary"""
        embedding_config = config.get("embedding")

        # Check if embedding config is None (CONFIG_DB=true but no database config)
        if embedding_config is None:
            raise ValueError(
                "CONFIG_DB=true but no embedding configuration found in database. Please configure embedding settings through the UI or set CONFIG_DB=false to use environment variables.")

        self.azure_endpoint = embedding_config.get("azure_endpoint")
        self.azure_api_key = embedding_config.get("azure_api_key")
        self.azure_api_version = embedding_config.get("azure_api_version", "2024-02-01")
        self.azure_deployment = embedding_config.get("azure_deployment", "text-embedding-3-large")

        if not self.azure_endpoint or not self.azure_api_key:
            raise ValueError(
                "Azure OpenAI Embedding configuration missing required fields: azure_endpoint, azure_api_key")

        logger.info(f"EmbeddingManager loaded configuration from database")

    def _load_from_environment(self):
        """
        Load environment variables (fallback)
        """
        # Validate required environment variables
        self.azure_endpoint = os.getenv("AZURE_OPENAI_EMBEDDING_ENDPOINT")
        self.azure_api_key = os.getenv("AZURE_OPENAI_API_KEY")
        self.azure_api_version = os.getenv(
            "AZURE_OPENAI_EMBEDDING_API_VERSION", "2024-02-01"
        )
        self.azure_deployment = os.getenv(
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME", "text-embedding-3-large"
        )

        if not self.azure_endpoint or not self.azure_api_key:
            raise ValueError(
                "Azure OpenAI Embedding configuration missing. Please set AZURE_OPENAI_EMBEDDING_ENDPOINT "
                "and AZURE_OPENAI_API_KEY in your .env file. "
                "See AZURE_SETUP.md for detailed setup instructions."
            )

        logger.info(f"EmbeddingManager loaded configuration from environment")

    def _initialize_embedding_model(self):
        """
        Initialize the Azure OpenAI Embeddings instance.
        """
        try:
            self._embedding_model = AzureOpenAIEmbeddings(
                azure_endpoint=self.azure_endpoint,
                api_key=self.azure_api_key,
                api_version=self.azure_api_version,
                azure_deployment=self.azure_deployment,
                chunk_size=1000,  # Process embeddings in batches
                dimensions=1536,
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize Azure OpenAI Embeddings: {str(e)}"
            )

    def get_embedding_model(self):
        """
        Get the initialized embeddings instance.
        """
        return self._embedding_model

    def get_config(self):
        """
        Get the Azure OpenAI embedding configuration.
        """
        return {
            "azure_endpoint": self.azure_endpoint,
            "azure_api_key": self.azure_api_key,
            "azure_api_version": self.azure_api_version,
            "azure_deployment": self.azure_deployment,
        }


@lru_cache(maxsize=1)
def _get_embedding_manager():
    """
    Create and cache a single EmbeddingManager instance.
    Thread-safe singleton pattern using lru_cache.
    """
    return EmbeddingManager()


def get_embedding_manager():
    """
    Get the Embedding Manager from singleton cache, initializing if needed.
    """
    return _get_embedding_manager()


def clear_embedding_manager_cache():
    """
    Clear the embedding manager cache to force reinitialization with new config.
    Call this when configuration is updated.
    """
    _get_embedding_manager.cache_clear()
    logger.info("Embedding manager cache cleared - will reinitialize with new config on next access")


async def get_embedding_manager_async() -> EmbeddingManager:
    """
    Get EmbeddingManager instance asynchronously with database configuration.

    This version loads configuration from the database asynchronously, avoiding
    event loop conflicts in FastAPI contexts.

    Returns:
        EmbeddingManager instance
    """
    config = None
    if should_use_database_config():
        # Load config from database asynchronously
        config = await load_config_from_db()
        if not config:
            raise ValueError(
                "CONFIG_DB=true but no database configuration found. Please configure the application through the UI or set CONFIG_DB=false to use environment variables.")

    return EmbeddingManager(config=config)


def get_embedding_model():
    """
    Convenience function to get the embeddings instance.
    """
    return get_embedding_manager().get_embedding_model()
