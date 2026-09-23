"""
Code Triage Configuration Manager

Provides centralized access to code-triage agent configuration.
"""

import os
import asyncio
import logging
from typing import Optional
from pydantic import BaseModel
from sqlalchemy import select

logger = logging.getLogger(__name__)


class CodeTriageConfig(BaseModel):
    """Code triage configuration"""
    enabled: bool
    base_url: str
    timeout_seconds: int
    max_retries: int


async def get_code_triage_config() -> Optional[CodeTriageConfig]:
    """
    Get code-triage configuration.

    Priority:
    1. Environment variable CODE_TRIAGE_ENABLED (for testing/development)
    2. Database configuration (for production with UI)

    Returns None if not configured or disabled.
    """
    # Check environment variable first (for testing without frontend)
    env_enabled = os.getenv("CODE_TRIAGE_ENABLED", "").lower()

    if env_enabled == "false":
        logger.info("Code triaging agent disabled via CODE_TRIAGE_ENABLED environment variable")
        return None

    if env_enabled == "true":
        # Use environment variable configuration
        logger.info("Code triaging agent enabled via CODE_TRIAGE_ENABLED environment variable")
        base_url = os.getenv("CODE_TRIAGE_BASE_URL", "http://code-triage-agent:8002")
        timeout = int(os.getenv("CODE_TRIAGE_TIMEOUT", "180"))
        retries = int(os.getenv("CODE_TRIAGE_MAX_RETRIES", "3"))

        return CodeTriageConfig(
            enabled=True,
            base_url=base_url,
            timeout_seconds=timeout,
            max_retries=retries
        )

    # Fall back to database configuration (for production with UI)
    try:
        from src.server.models.db.app_config import AppConfig
        from src.server.apis_v1.dependencies import async_db_session

        async with async_db_session() as session:
            stmt = select(AppConfig).order_by(AppConfig.id.desc()).limit(1)
            result = await session.execute(stmt)
            config = result.scalar_one_or_none()

            if not config:
                logger.info("No app config found, code triaging agent disabled")
                return None

            if not config.code_triaging_agent_enabled:
                logger.info("Code triaging agent disabled in database")
                return None

            agent_config = config.code_triaging_agent_config or {}

            logger.info("Code triaging agent enabled via database configuration")
            return CodeTriageConfig(
                enabled=True,
                base_url=agent_config.get('base_url', 'http://code-triage-agent:8002'),
                timeout_seconds=agent_config.get('timeout_seconds', 180),
                max_retries=agent_config.get('max_retries', 3)
            )
    except Exception as e:
        logger.error(f"Failed to get code triage config from database: {e}")
        return None


# Cache for performance
_config_cache: Optional[CodeTriageConfig] = None
_cache_lock = asyncio.Lock()


async def get_code_triage_config_cached() -> Optional[CodeTriageConfig]:
    """Get cached config (refreshed on config changes).

    Uses double-check locking pattern to prevent database connection exhaustion
    under concurrent load. Only one coroutine will fetch the config from the
    database, while others wait for the result.
    """
    global _config_cache

    # First check (without lock) - fast path for cached values
    if _config_cache is not None:
        return _config_cache

    # Acquire lock for cache update
    async with _cache_lock:
        # Second check (with lock) - ensure another coroutine didn't populate cache
        if _config_cache is None:
            _config_cache = await get_code_triage_config()

    return _config_cache


def clear_code_triage_config_cache():
    """Clear cache (called when config is updated)"""
    global _config_cache
    _config_cache = None

