"""
Tests for Configuration Utilities.

Tests cover:
- get_app_config() - Configuration loading with caching
- clear_all_manager_caches() - Cache clearing
- Environment variable fallbacks
- Database vs environment config modes
"""

import os
import time
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from src.server.models.db.app_config import AppConfig
import src.server.utilities.config as config_module
# Import functions for easier access
get_app_config = config_module.get_app_config
clear_all_manager_caches = config_module.clear_all_manager_caches
load_config_from_db = config_module.load_config_from_db

pytestmark = pytest.mark.asyncio


# Test fixtures

@pytest_asyncio.fixture
async def sample_db_config(db_session):
    """Create sample configuration in database"""
    from src.server.models.api.enums import Severity, LlmProvider, EmbeddingProvider

    # Primary LLM configuration
    primary_llm_config = {
        "api_key": "db-api-key",
        "endpoint_url": "https://db.openai.azure.com/",
        "deployment_name": "gpt-4",
        "api_version": "2024-02-01",
        "price_usd_per_1k_ip_tokens": 0.01,
        "price_usd_per_1k_op_tokens": 0.03
    }

    # Embedding configuration
    embedding_config = {
        "api_key": "db-embedding-key",
        "endpoint_url": "https://db-embedding.openai.azure.com/",
        "deployment_name": "text-embedding-ada-002",
        "api_version": "2024-02-01"
    }

    app_config = AppConfig(
        enabled_severities=[Severity.P1, Severity.P2],
        primary_llm_provider=LlmProvider.AZURE_OPENAI,
        primary_llm_connection_config=primary_llm_config,
        embedding_provider=EmbeddingProvider.AZURE_OPENAI,
        embedding_connection_config=embedding_config,
        code_triaging_agent_enabled=False,
        orchestrator_agents=1,
        chaos_system_enabled=False
    )

    db_session.add(app_config)
    await db_session.commit()
    await db_session.refresh(app_config)

    return app_config


@pytest.fixture
def mock_env_vars():
    """Mock environment variables for testing"""
    env_vars = {
        "CONFIG_DB": "false",
        "AZURE_OPENAI_API_KEY": "env-api-key",
        "AZURE_OPENAI_ENDPOINT": "https://env.openai.azure.com/",
        "AZURE_OPENAI_DEPLOYMENT_NAME": "env-gpt-4",
        "AZURE_OPENAI_API_VERSION": "2024-02-01"
    }

    with patch.dict(os.environ, env_vars, clear=False):
        yield env_vars


# get_app_config tests

async def test_get_app_config_from_database_success(db_session, sample_db_config):
    """Test successful config loading from database"""
    # Clear cache first
    clear_all_manager_caches()

    config = await get_app_config(db_session, use_cache=False)

    assert config is not None
    assert config["llm"] is not None
    assert config["llm"]["mode"] == "AZURE_OPENAI"
    assert config["llm"]["azure_api_key"] == "db-api-key"
    assert config["llm"]["azure_endpoint"] == "https://db.openai.azure.com/"
    assert config["llm"]["azure_deployment"] == "gpt-4"
    assert config["embedding"] is not None
    assert config["embedding"]["azure_api_key"] == "db-embedding-key"


async def test_get_app_config_with_caching(db_session, sample_db_config):
    """Test config caching functionality"""
    # Clear cache first
    clear_all_manager_caches()

    # First call should hit database
    config1 = await get_app_config(db_session, use_cache=True)

    # Mock database to verify second call uses cache
    with patch.object(db_session, 'execute') as mock_execute:
        config2 = await get_app_config(db_session, use_cache=True)

        # Database should not be called on second request
        mock_execute.assert_not_called()

    # Configs should be identical
    assert config1 == config2
    assert config1["llm"]["azure_api_key"] == "db-api-key"


async def test_get_app_config_cache_expiry(db_session, sample_db_config):
    """Test config cache expiry"""
    # Clear cache first
    clear_all_manager_caches()

    # First call
    config1 = await get_app_config(db_session, use_cache=True)

    # Directly manipulate the cache timestamp to simulate expiry
    # Set cache timestamp to be older than cache duration (5 minutes = 300 seconds)
    config_module._cache_timestamp = time.time() - 400  # 400 seconds ago

    # This should hit database again due to expired cache
    config2 = await get_app_config(db_session, use_cache=True)

    assert config1 == config2


async def test_get_app_config_no_cache(db_session, sample_db_config):
    """Test config loading without cache"""
    # Clear cache first
    clear_all_manager_caches()

    # Mock database execute to track calls
    original_execute = db_session.execute
    call_count = 0

    async def mock_execute(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return await original_execute(*args, **kwargs)

    with patch.object(db_session, 'execute', side_effect=mock_execute):
        # Two calls without cache should hit database twice
        config1 = await get_app_config(db_session, use_cache=False)
        config2 = await get_app_config(db_session, use_cache=False)

        assert call_count == 2

    assert config1 == config2


async def test_get_app_config_fallback_to_env(db_session, mock_env_vars):
    """Test fallback to environment variables when CONFIG_DB=false"""
    # Clear cache first
    clear_all_manager_caches()

    # Clear any existing database config to ensure env fallback
    from sqlalchemy import delete
    await db_session.execute(delete(AppConfig))
    await db_session.commit()

    config = await get_app_config(db_session, use_cache=False)

    # Should use environment variables
    assert config["llm"] is not None
    assert config["llm"]["mode"] == "AZURE_OPENAI"
    assert config["llm"]["azure_api_key"] == "env-api-key"
    assert config["llm"]["azure_endpoint"] == "https://env.openai.azure.com/"
    assert config["llm"]["azure_deployment"] == "env-gpt-4"


async def test_get_app_config_database_error_fallback(db_session, mock_env_vars):
    """Test fallback to environment when database error occurs"""
    # Clear cache first
    clear_all_manager_caches()

    # Mock database to raise exception
    with patch.dict(os.environ, {"CONFIG_DB": "false"}):  # Force env fallback mode
        with patch.object(db_session, 'execute') as mock_execute:
            mock_execute.side_effect = Exception("Database connection failed")

            config = await get_app_config(db_session, use_cache=False)

    # Should fallback to environment variables
    assert config["llm"]["azure_api_key"] == "env-api-key"


async def test_get_app_config_no_database_no_env(db_session):
    """Test config loading when no database config and no environment variables"""
    # Clear cache first
    clear_all_manager_caches()

    # Ensure CONFIG_DB is true but no data exists
    with patch.dict(os.environ, {"CONFIG_DB": "true"}, clear=False):
        config = await get_app_config(db_session, use_cache=False)

    # Should return None for missing configurations
    assert config["llm"] is None
    assert config["embedding"] is None


# clear_all_manager_caches tests

def test_clear_all_manager_caches():
    """Test cache clearing functionality"""
    # Set some cache values directly in the module
    config_module._config_cache = {"test": "data"}
    config_module._cache_timestamp = time.time()

    # Clear caches
    clear_all_manager_caches()

    # Verify caches are cleared
    assert config_module._config_cache is None
    assert config_module._cache_timestamp is None


# load_config_from_db tests

async def test_load_config_from_db_success():
    """Test loading config from database without session parameter"""
    # Mock the database session and config
    mock_config = {"deployment": "CUSTOM", "test": "data"}

    with patch('src.server.utilities.config.async_db_session') as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        with patch('src.server.utilities.config.get_app_config') as mock_get_config:
            mock_get_config.return_value = mock_config

            config = await load_config_from_db()

    assert config == mock_config


async def test_load_config_from_db_error():
    """Test loading config from database when error occurs"""
    with patch('src.server.utilities.config.async_db_session') as mock_session_factory:
        mock_session_factory.side_effect = Exception("Database connection failed")

        config = await load_config_from_db()

    assert config is None


# Environment variable processing tests

async def test_get_app_config_env_var_processing(db_session):
    """Test environment variable processing and type conversion"""
    env_vars = {
        "CONFIG_DB": "false",
        "AZURE_OPENAI_API_KEY": "test-key",
        "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com/",
        "AZURE_OPENAI_DEPLOYMENT_NAME": "gpt-4",
        "AZURE_OPENAI_API_VERSION": "2024-02-01",
        "AZURE_EMBEDDING_API_KEY": "embedding-key",
        "AZURE_EMBEDDING_ENDPOINT": "https://embedding.openai.azure.com/",
        "AZURE_EMBEDDING_DEPLOYMENT_NAME": "text-embedding-ada-002",
        "AZURE_EMBEDDING_API_VERSION": "2024-02-01"
    }

    with patch.dict(os.environ, env_vars, clear=False):
        clear_all_manager_caches()

        # Clear any existing database config to ensure env fallback
        from sqlalchemy import delete
        await db_session.execute(delete(AppConfig))
        await db_session.commit()

        config = await get_app_config(db_session, use_cache=False)

    # Verify LLM config
    llm_config = config["llm"]
    assert llm_config is not None
    assert llm_config["azure_api_key"] == "test-key"
    assert llm_config["azure_endpoint"] == "https://test.openai.azure.com/"
    assert llm_config["azure_deployment"] == "gpt-4"

    # Verify embedding config
    embedding_config = config["embedding"]
    assert embedding_config is not None
    assert embedding_config["azure_api_key"] == "embedding-key"
    assert embedding_config["azure_endpoint"] == "https://embedding.openai.azure.com/"
    assert embedding_config["azure_deployment"] == "text-embedding-ada-002"


async def test_get_app_config_partial_env_vars(db_session):
    """Test config loading with partial environment variables"""
    env_vars = {
        "CONFIG_DB": "false",
        "AZURE_OPENAI_API_KEY": "partial-key",
        # Missing other required variables
    }

    with patch.dict(os.environ, env_vars, clear=False):
        clear_all_manager_caches()

        # Clear any existing database config to ensure env fallback
        from sqlalchemy import delete
        await db_session.execute(delete(AppConfig))
        await db_session.commit()

        config = await get_app_config(db_session, use_cache=False)

    # Should return None for incomplete config (missing required fields)
    assert config["llm"] is None  # Missing required endpoint and deployment name
    assert config["embedding"] is None  # Missing required fields


async def test_get_app_config_config_db_true_with_env_fallback(db_session, mock_env_vars):
    """Test CONFIG_DB=true but no fallback to env vars when DB is empty"""
    # Clear cache first
    clear_all_manager_caches()

    # Force CONFIG_DB=true but ensure no database config exists
    with patch.dict(os.environ, {"CONFIG_DB": "true"}):
        config = await get_app_config(db_session, use_cache=False)

    # Should NOT fallback to environment variables when CONFIG_DB=true
    assert config["llm"] is None  # No fallback when CONFIG_DB=true
