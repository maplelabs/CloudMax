"""
Centralized Configuration - Single method to get ALL app configuration from database.
This is the ONLY place where database config is retrieved, then used everywhere else.
Includes caching to avoid repeated database calls.
"""

import logging
import os
import time
from typing import Optional, Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..apis_v1.dependencies import async_db_session
from ..models.db.app_config import AppConfig

logger = logging.getLogger(__name__)

# Global cache for config
_config_cache = None
_cache_timestamp = None
_cache_duration = 300  # 5 minutes


async def get_app_config(db_session: AsyncSession, use_cache: bool = True) -> Dict[str, Any]:
    """
    Get ALL application configuration from database with environment fallback.

    This is the SINGLE method that retrieves all config. Import this and use
    specific values wherever needed.

    Args:
        db_session: Database session
        use_cache: Whether to use cached config (default: True)

    Returns:
        Dictionary containing ALL application configuration
    """
    global _config_cache, _cache_timestamp

    # Check cache first (if enabled)
    if use_cache and _config_cache is not None and _cache_timestamp is not None:
        cache_age = time.time() - _cache_timestamp
        if cache_age < _cache_duration:
            logger.debug(f"Using cached config (age: {cache_age:.1f}s)")
            return _config_cache

    # Get database config
    try:
        result = await db_session.execute(
            select(AppConfig).order_by(AppConfig.updated_at.desc()).limit(1)
        )
        db_config = result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error retrieving config from database: {e}")
        db_config = None

    # Build complete config dictionary
    config = {}

    # ==================== PRIMARY LLM CONFIGURATION ====================
    if db_config and db_config.primary_llm_provider and db_config.primary_llm_connection_config:
        primary_llm_config = db_config.primary_llm_connection_config

        if db_config.primary_llm_provider == "azure-openai":
            config["llm"] = {
                "mode": "AZURE_OPENAI",
                "azure_endpoint": primary_llm_config["endpoint_url"],
                "azure_api_key": primary_llm_config["api_key"],
                "azure_deployment": primary_llm_config["deployment_name"],
                "azure_api_version": primary_llm_config.get("api_version", "2024-02-01"),
                "price_usd_per_1k_ip_tokens": primary_llm_config.get("price_usd_per_1k_ip_tokens", 0),
                "price_usd_per_1k_op_tokens": primary_llm_config.get("price_usd_per_1k_op_tokens", 0)
            }
        elif db_config.primary_llm_provider == "aws-bedrock-claude":
            config["llm"] = {
                "mode": "AWS_BEDROCK",
                "aws_region": primary_llm_config.get("region", "us-east-1"),
                "bedrock_model_id": primary_llm_config.get("model_id", "us.anthropic.claude-sonnet-4-20250514-v1:0"),
                "api_key": primary_llm_config.get("api_key"),
                "price_usd_per_1k_ip_tokens": primary_llm_config.get("price_usd_per_1k_ip_tokens", 0),
                "price_usd_per_1k_op_tokens": primary_llm_config.get("price_usd_per_1k_op_tokens", 0)
            }
        elif db_config.primary_llm_provider == "azure-anthropic":
            config["llm"] = {
                "mode": "AZURE_ANTHROPIC",
                "azure_anthropic_endpoint": primary_llm_config.get("endpoint_url"),
                "api_key": primary_llm_config.get("api_key"),
                "azure_anthropic_model_id": primary_llm_config.get("model_id", "claude-haiku-4-5"),
                "price_usd_per_1k_ip_tokens": primary_llm_config.get("price_usd_per_1k_ip_tokens", 0),
                "price_usd_per_1k_op_tokens": primary_llm_config.get("price_usd_per_1k_op_tokens", 0)
            }
        logger.info(f"Using primary LLM config from database: {config['llm']['mode']}")
    else:
        # Check if we should use database config exclusively
        if should_use_database_config():
            # CONFIG_DB=true but no database LLM config found - return None
            config["llm"] = None
            logger.warning("CONFIG_DB=true but no primary LLM configuration found in database")
        else:
            # CONFIG_DB=false: Fallback to environment variables
            azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
            azure_api_key = os.getenv("AZURE_OPENAI_API_KEY")
            azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
            azure_api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")

            if azure_endpoint and azure_api_key and azure_deployment:
                config["llm"] = {
                    "mode": "AZURE_OPENAI",
                    "azure_endpoint": azure_endpoint,
                    "azure_api_key": azure_api_key,
                    "azure_deployment": azure_deployment,
                    "azure_api_version": azure_api_version,
                    "price_usd_per_1k_ip_tokens": 0,
                    "price_usd_per_1k_op_tokens": 0
                }
                logger.info("Using primary LLM config from environment variables")
            else:
                config["llm"] = None
                logger.warning("No primary LLM configuration found in database or environment variables")

    # ==================== SECONDARY LLM CONFIGURATION ====================
    if db_config and db_config.secondary_llm_provider and db_config.secondary_llm_connection_config:
        secondary_llm_config = db_config.secondary_llm_connection_config

        # Check same_as_primary flag value
        if secondary_llm_config.get("same_as_primary") is True:
            logger.info("Secondary LLM configured as 'same as primary' - using primary LLM config")
            # Use primary LLM config for secondary
            config["secondary_llm"] = config["llm"]
        else:
            logger.info("Secondary LLM configured with custom settings")
            # Use custom secondary config
            if db_config.secondary_llm_provider == "azure-openai":
                config["secondary_llm"] = {
                    "mode": "AZURE_OPENAI",
                    "azure_endpoint": secondary_llm_config.get("endpoint_url"),
                    "azure_api_key": secondary_llm_config.get("api_key"),
                    "azure_deployment": secondary_llm_config.get("deployment_name"),
                    "azure_api_version": secondary_llm_config.get("api_version", "2024-02-01"),
                    "price_usd_per_1k_ip_tokens": secondary_llm_config.get("price_usd_per_1k_ip_tokens", 0),
                    "price_usd_per_1k_op_tokens": secondary_llm_config.get("price_usd_per_1k_op_tokens", 0)
                }
            elif db_config.secondary_llm_provider == "aws-bedrock-claude":
                config["secondary_llm"] = {
                    "mode": "AWS_BEDROCK",
                    "aws_region": secondary_llm_config.get("region", "us-east-1"),
                    "bedrock_model_id": secondary_llm_config.get("model_id",
                                                                 "us.anthropic.claude-sonnet-4-20250514-v1:0"),
                    "api_key": secondary_llm_config.get("api_key"),
                    "price_usd_per_1k_ip_tokens": secondary_llm_config.get("price_usd_per_1k_ip_tokens", 0),
                    "price_usd_per_1k_op_tokens": secondary_llm_config.get("price_usd_per_1k_op_tokens", 0)
                }
            elif db_config.secondary_llm_provider == "azure-anthropic":
                config["secondary_llm"] = {
                    "mode": "AZURE_ANTHROPIC",
                    "azure_anthropic_endpoint": secondary_llm_config.get("endpoint_url"),
                    "api_key": secondary_llm_config.get("api_key"),
                    "azure_anthropic_model_id": secondary_llm_config.get("model_id", "claude-haiku-4-5"),
                    "price_usd_per_1k_ip_tokens": secondary_llm_config.get("price_usd_per_1k_ip_tokens", 0),
                    "price_usd_per_1k_op_tokens": secondary_llm_config.get("price_usd_per_1k_op_tokens", 0)
                }

        if config["secondary_llm"]:
            logger.info(f"Using secondary LLM config from database: {config['secondary_llm']['mode']}")
    else:
        config["secondary_llm"] = None
        logger.info("No secondary LLM configured")

    if db_config and db_config.embedding_provider and db_config.embedding_connection_config:
        embedding_config = db_config.embedding_connection_config
        config["embedding"] = {
            "azure_endpoint": embedding_config["endpoint_url"],
            "azure_api_key": embedding_config["api_key"],
            "azure_deployment": embedding_config["deployment_name"],
            "azure_api_version": embedding_config.get("api_version", "2024-02-01")
        }
        logger.info("Using embedding config from database")
    else:
        # Check if we should use database config exclusively
        if should_use_database_config():
            # CONFIG_DB=true but no database embedding config found - return None
            config["embedding"] = None
            logger.warning("CONFIG_DB=true but no embedding configuration found in database")
        else:
            # CONFIG_DB=false: Fallback to environment variables
            azure_endpoint = os.getenv("AZURE_EMBEDDING_ENDPOINT") or os.getenv("AZURE_OPENAI_ENDPOINT")
            azure_api_key = os.getenv("AZURE_EMBEDDING_API_KEY") or os.getenv("AZURE_OPENAI_API_KEY")
            azure_deployment = os.getenv("AZURE_EMBEDDING_DEPLOYMENT_NAME")
            azure_api_version = os.getenv("AZURE_EMBEDDING_API_VERSION", "2024-02-01")

            if azure_endpoint and azure_api_key and azure_deployment:
                config["embedding"] = {
                    "azure_endpoint": azure_endpoint,
                    "azure_api_key": azure_api_key,
                    "azure_deployment": azure_deployment,
                    "azure_api_version": azure_api_version
                }
                logger.info("Using embedding config from environment variables")
            else:
                config["embedding"] = None
                logger.warning("No embedding configuration found in database or environment variables")

    # ==================== MCP CONFIGURATION (Observability Systems) ====================
    mcp_config = {"grafana_url": None, "jaeger_url": None, "opensearch_url": None, "connections": []}

    if db_config and db_config.mcp_connections:
        mcp_data = db_config.mcp_connections
        if isinstance(mcp_data, dict) and "systems" in mcp_data:
            for system in mcp_data["systems"]:
                system_name = system.get("observability_system")
                if system.get("enabled") and system.get("connection_config", {}).get("endpoint_url"):
                    endpoint_url = system["connection_config"]["endpoint_url"]
                    connection_config = system.get("connection_config", {})

                    if system_name == "grafana":
                        mcp_config["grafana_url"] = endpoint_url
                    elif system_name == "jaeger":
                        mcp_config["jaeger_url"] = endpoint_url
                    elif system_name == "opensearch":
                        mcp_config["opensearch_url"] = endpoint_url
                    elif system_name == "diagnostic":
                        mcp_config["diagnostic_url"] = endpoint_url

                    # Extract mTLS configuration (for observability systems)
                    connection_data = {
                        "system": system_name,
                        "enabled": True,
                        "endpoint_url": endpoint_url,
                        "http_headers": connection_config.get("http_headers", []),
                        "mtls_enabled": connection_config.get("mtls_enabled", False),
                        "ca_cert": connection_config.get("ca_cert"),
                        "client_cert": connection_config.get("client_cert"),
                        "client_key": connection_config.get("client_key")
                    }
                    mcp_config["connections"].append(connection_data)
        logger.info(
            f"Using MCP config from database: {len(mcp_config['connections'])} observability system connections")
    else:
        # Check if we should use database config exclusively
        if should_use_database_config():
            # CONFIG_DB=true but no database MCP config found - use empty config
            logger.warning("CONFIG_DB=true but no MCP configuration found in database - using empty MCP config")
        else:
            # CONFIG_DB=false: Fallback to environment variables
            grafana_url = os.getenv("GRAFANA_MCP_URL")
            jaeger_url = os.getenv("JAEGER_MCP_URL")
            opensearch_url = os.getenv("OPENSEARCH_MCP_URL")
            diagnostic_url = os.getenv("DIAGNOSTIC_MCP_URL")

            if grafana_url:
                mcp_config["grafana_url"] = grafana_url
                mcp_config["connections"].append({
                    "system": "grafana",
                    "enabled": True,
                    "endpoint_url": grafana_url,
                    "http_headers": [],
                    "mtls_enabled": False,
                    "ca_cert": None,
                    "client_cert": None,
                    "client_key": None
                })

            if jaeger_url:
                mcp_config["jaeger_url"] = jaeger_url
                mcp_config["connections"].append({
                    "system": "jaeger",
                    "enabled": True,
                    "endpoint_url": jaeger_url,
                    "http_headers": [],
                    "mtls_enabled": False,
                    "ca_cert": None,
                    "client_cert": None,
                    "client_key": None
                })

            if opensearch_url:
                mcp_config["opensearch_url"] = opensearch_url
                mcp_config["connections"].append({
                    "system": "opensearch",
                    "enabled": True,
                    "endpoint_url": opensearch_url,
                    "http_headers": [],
                    "mtls_enabled": False,
                    "ca_cert": None,
                    "client_cert": None,
                    "client_key": None
                })

            logger.info(
                f"Using MCP config from environment: {len(mcp_config['connections'])} observability system connections")

    config["mcp"] = mcp_config

    # ==================== DIAGNOSTIC MCP SERVERS CONFIGURATION ====================
    diagnostic_mcp_config = {"servers": []}

    if db_config and db_config.diagnostic_mcp_servers:
        diagnostic_data = db_config.diagnostic_mcp_servers
        if isinstance(diagnostic_data, dict) and "servers" in diagnostic_data:
            for server in diagnostic_data["servers"]:
                if server.get("enabled") and server.get("connection_config", {}).get("endpoint_url"):
                    server_name = server.get("name", "")
                    connection_config = server.get("connection_config", {})

                    server_data = {
                        "name": server_name,
                        "enabled": True,
                        "endpoint_url": connection_config.get("endpoint_url"),
                        "http_headers": connection_config.get("http_headers", []),
                        "mtls_enabled": connection_config.get("mtls_enabled", False),
                        "ca_cert": connection_config.get("ca_cert"),
                        "client_cert": connection_config.get("client_cert"),
                        "client_key": connection_config.get("client_key")
                    }
                    diagnostic_mcp_config["servers"].append(server_data)
        logger.info(f"Using diagnostic MCP config from database: {len(diagnostic_mcp_config['servers'])} server(s)")
    else:
        # Check if we should use database config exclusively
        if should_use_database_config():
            # CONFIG_DB=true but no database diagnostic MCP config found - use empty config
            logger.warning(
                "CONFIG_DB=true but no diagnostic MCP configuration found in database - using empty diagnostic MCP config")
        else:
            # CONFIG_DB=false: Fallback to environment variable (single server for backward compatibility)
            diagnostic_url = os.getenv("DIAGNOSTIC_MCP_URL")
            if diagnostic_url:
                diagnostic_mcp_config["servers"].append({
                    "name": "Diagnostic",
                    "enabled": True,
                    "endpoint_url": diagnostic_url,
                    "http_headers": [],
                    "mtls_enabled": False,
                    "ca_cert": None,
                    "client_cert": None,
                    "client_key": None
                })
                logger.info("Using diagnostic MCP config from DIAGNOSTIC_MCP_URL environment variable")

    config["diagnostic_mcp"] = diagnostic_mcp_config

    if (db_config and
            db_config.code_triaging_agent_enabled and
            db_config.code_triaging_agent_config):

        agent_config = db_config.code_triaging_agent_config
        config["code_triaging"] = {
            "enabled": True,
            "base_url": agent_config.get("base_url"),
            "api_key": agent_config.get("api_key"),
            "timeout_seconds": agent_config.get("timeout_seconds", 30),
            "max_retries": agent_config.get("max_retries", 3),
            "notes": agent_config.get("notes", "")
        }
        logger.info("Using code triaging config from database")
    else:
        config["code_triaging"] = {
            "enabled": False,
            "base_url": None,
            "api_key": None,
            "timeout_seconds": 30,
            "max_retries": 3,
            "notes": ""
        }

    # ==================== CHAOS SYSTEM CONFIGURATION ====================
    if db_config:
        config["chaos_system"] = {
            "enabled": db_config.chaos_system_enabled if hasattr(db_config, 'chaos_system_enabled') else False
        }
    else:
        config["chaos_system"] = {
            "enabled": False
        }

    # ==================== AUTOMATIC TRIAGE CONFIGURATION ====================
    if db_config:
        config["automatic_triage"] = db_config.automatic_triage if hasattr(db_config, 'automatic_triage') else True
    else:
        config["automatic_triage"] = True

    # ==================== ALERT GROUPING CONFIGURATION ====================
    if db_config:
        config["alert_grouping_enabled"] = db_config.alert_grouping_enabled if hasattr(db_config, 'alert_grouping_enabled') else True
    else:
        config["alert_grouping_enabled"] = True

    # Cache the config
    if use_cache:
        _config_cache = config
        _cache_timestamp = time.time()
        logger.debug("Config cached successfully")

    return config


def should_use_database_config() -> bool:
    """
    Check if database configuration should be used based on environment variable.

    Returns:
        bool: True by default (database config), False only if explicitly disabled
    """
    config_db = os.getenv("CONFIG_DB", "true").lower()
    return config_db in ("true", "1", "yes", "on")


def clear_config_cache():
    """
    Clear the configuration cache to force fresh config loading.
    Call this when configuration is updated in the database.
    """
    global _config_cache, _cache_timestamp
    _config_cache = None
    _cache_timestamp = None
    logger.info("Configuration cache cleared - next config request will reload from database")


def is_secondary_llm_same_as_primary(secondary_llm_config: dict) -> bool:
    """
    Check if secondary LLM is configured as 'same as primary'.

    Args:
        secondary_llm_config: Secondary LLM configuration JSONB from database

    Returns:
        bool: True if secondary LLM is configured as same as primary, False otherwise
    """
    if not secondary_llm_config:
        return False

    # Flag only exists when same_as_primary is true
    return secondary_llm_config.get("same_as_primary", False)


async def load_config_from_db() -> Optional[Dict[str, Any]]:
    """
    Async wrapper to load configuration from database without requiring a session parameter.

    This is a convenience function that creates its own database session and calls get_app_config().
    Use this when you need to load config from outside the FastAPI request context.

    Returns:
        Dictionary containing application configuration, or None if no database connection
    """
    try:
        # Create a database session using the session factory directly
        async with async_db_session() as db_session:
            config = await get_app_config(db_session)
            return config
    except Exception as e:
        logger.error(f"Failed to load config from database: {e}")
        return None


async def has_enabled_diagnostic_mcp_servers() -> bool:
    """
    Check if there are any enabled diagnostic MCP servers in the configuration.

    This function loads the configuration from the database and checks if at least
    one diagnostic MCP server is enabled. It's used to determine whether the
    Diagnostic Tests Agent should be included in the orchestrator.

    Returns:
        bool: True if at least one diagnostic MCP server is enabled, False otherwise
              (including when configuration is missing or empty)
    """
    try:
        config = await load_config_from_db()

        if not config:
            logger.debug("No configuration loaded - no diagnostic MCP servers available")
            return False

        diagnostic_mcp = config.get("diagnostic_mcp")
        if not diagnostic_mcp or not isinstance(diagnostic_mcp, dict):
            logger.debug("No diagnostic_mcp configuration found")
            return False

        servers = diagnostic_mcp.get("servers", [])
        if not servers:
            logger.debug("No diagnostic MCP servers configured")
            return False

        # Check if any server is enabled
        enabled_servers = [s for s in servers if s.get("enabled", False)]

        if enabled_servers:
            logger.info(f"Found {len(enabled_servers)} enabled diagnostic MCP server(s)")
            return True
        else:
            logger.info("No enabled diagnostic MCP servers found")
            return False

    except Exception as e:
        logger.error(f"Error checking for enabled diagnostic MCP servers: {e}")
        return False


async def is_chaos_system_enabled() -> bool:
    """
    Check if chaos system is enabled in the database configuration.

    Returns:
        bool: True if chaos system is enabled, False otherwise
    """
    try:
        # Create a database session using the session factory directly
        async with async_db_session() as db_session:
            config = await get_app_config(db_session)
            return config.get("chaos_system", {}).get("enabled", False)
    except Exception:
        logger.exception(f"Failed to load config from database")
        return False


def process_secondary_llm_config(primary_llm_config: dict, secondary_llm_config: dict) -> tuple:
    """
    Process secondary LLM configuration based on same_as_primary flag.
    Now stores the same_as_primary flag in the database JSONB field.

    Args:
        primary_llm_config: Primary LLM configuration dict
        secondary_llm_config: Secondary LLM configuration dict with same_as_primary flag

    Returns:
        tuple: (secondary_llm_provider, secondary_llm_connection_config) or (None, None) if not configured
    """
    # If no secondary LLM config provided, return None
    if not secondary_llm_config:
        return None, None

    if secondary_llm_config.get("same_as_primary", True):
        # Store ONLY the flag when same as primary
        return primary_llm_config.get("llm_type"), {
            "same_as_primary": True
        }
    else:
        # Store custom config WITH the flag set to false
        if not secondary_llm_config.get("llm_config"):
            raise ValueError("Secondary LLM configuration is required when same_as_primary=False")

        llm_config = secondary_llm_config["llm_config"]
        provider = llm_config.get("llm_type")

        if provider == "azure-openai":
            return "azure-openai", {
                "same_as_primary": False,
                "llm_type": "azure-openai",
                "endpoint_url": llm_config["endpoint_url"],
                "api_key": llm_config["api_key"],
                "deployment_name": llm_config["deployment_name"],
                "api_version": llm_config.get("api_version", "2024-02-01"),
                "price_usd_per_1k_op_tokens": llm_config.get("price_usd_per_1k_op_tokens", 0),
                "price_usd_per_1k_ip_tokens": llm_config.get("price_usd_per_1k_ip_tokens", 0)
            }
        elif provider == "aws-bedrock-claude":
            return "aws-bedrock-claude", {
                "same_as_primary": False,
                "llm_type": "aws-bedrock-claude",
                "region": llm_config.get("region", "us-east-1"),
                "model_id": llm_config.get("model_id", "us.anthropic.claude-sonnet-4-20250514-v1:0"),
                "api_key": llm_config.get("api_key"),
                "aws_access_key_id": llm_config.get("aws_access_key_id"),
                "aws_secret_access_key": llm_config.get("aws_secret_access_key"),
                "price_usd_per_1k_op_tokens": llm_config.get("price_usd_per_1k_op_tokens", 0),
                "price_usd_per_1k_ip_tokens": llm_config.get("price_usd_per_1k_ip_tokens", 0)
            }
        elif provider == "azure-anthropic":
            return "azure-anthropic", {
                "same_as_primary": False,
                "llm_type": "azure-anthropic",
                "endpoint_url": llm_config.get("endpoint_url"),
                "api_key": llm_config.get("api_key"),
                "model_id": llm_config.get("model_id", "claude-haiku-4-5"),
                "price_usd_per_1k_op_tokens": llm_config.get("price_usd_per_1k_op_tokens", 0),
                "price_usd_per_1k_ip_tokens": llm_config.get("price_usd_per_1k_ip_tokens", 0)
            }
        else:
            raise ValueError(f"Unsupported secondary LLM provider: {provider}")


def clear_all_manager_caches():
    """
    Clear all manager caches to force reinitialization with new configuration.
    Call this when configuration is updated in the database.
    """
    global _config_cache, _cache_timestamp

    # Clear config cache
    _config_cache = None
    _cache_timestamp = None
    logger.info("Configuration cache cleared")

    from .embedding_manager import clear_embedding_manager_cache
    from .llm_manager import clear_llm_manager_cache

    # Clear manager caches
    try:
        clear_embedding_manager_cache()
    except ImportError:
        logger.warning("Could not import embedding manager cache clear function")

    try:
        clear_llm_manager_cache()
    except ImportError:
        logger.warning("Could not import LLM manager cache clear function")

    logger.info("All manager caches cleared - components will reinitialize with new config")


async def is_automatic_triage_enabled() -> bool:
    """
    Check if automatic triage is enabled in the database configuration.

    When automatic triage is enabled, triage jobs are automatically created
    for new alerts received via webhooks. When disabled, alerts are still
    stored but no triage jobs are created.

    Returns:
        bool: True if automatic triage is enabled, False otherwise
    """
    try:
        # Create a database session using the session factory directly
        async with async_db_session() as db_session:
            # IMPORTANT: use_cache=False to ensure feature flags are always fresh
            # Feature flags must take effect immediately when changed via Setup UI
            config = await get_app_config(db_session, use_cache=False)
            return config.get("automatic_triage", True)
    except Exception:
        logger.exception(f"Failed to load config from database")
        return False


async def is_alert_grouping_enabled() -> bool:
    """
    Check if alert grouping is enabled in the database configuration.

    When alert grouping is enabled, incoming alerts are processed by background
    workers for intelligent grouping and correlation. When disabled, alerts are
    triaged individually (if automatic_triage is enabled).

    Returns:
        bool: True if alert grouping is enabled, False otherwise
    """
    try:
        # Create a database session using the session factory directly
        async with async_db_session() as db_session:
            # IMPORTANT: use_cache=False to ensure feature flags are always fresh
            # Feature flags must take effect immediately when changed via Setup UI
            config = await get_app_config(db_session, use_cache=False)
            return config.get("alert_grouping_enabled", True)
    except Exception:
        logger.exception(f"Failed to load alert grouping config from database")
        return True  # Default to enabled
