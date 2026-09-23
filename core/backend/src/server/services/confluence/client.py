"""
Confluence client creation and management
"""
import asyncio
import logging
from typing import Callable

from atlassian import Confluence
from fastapi import HTTPException

from .constants import CONFLUENCE_API_TIMEOUT, confluence_executor

logger = logging.getLogger(__name__)


async def _run_in_executor(func: Callable, *args, **kwargs) -> any:
    """Run a synchronous function in the Confluence executor.

    Supports both positional and keyword arguments.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(confluence_executor, lambda: func(*args, **kwargs))


def get_confluence_client(config: dict) -> Confluence:
    """
    Create Confluence API client from configuration.

    Args:
        config: Dictionary with 'base_url', 'username', 'api_token'

    Returns:
        Configured Confluence client instance
    """
    return Confluence(
        url=config['base_url'],
        username=config['username'],
        password=config['api_token'],  # API token used as password
        cloud=True,
        timeout=CONFLUENCE_API_TIMEOUT
    )


async def validate_confluence_config(config: dict) -> dict:
    """
    Validate Confluence configuration by testing connection.

    Args:
        config: Dictionary with base_url, username, api_token

    Returns:
        dict: {"status": "success", "user": "display_name"}

    Raises:
        HTTPException: If validation fails
    """
    client = get_confluence_client(config)
    logger.info(f"Testing Confluence connection to {config.get('base_url')}")

    try:
        display_name = await _run_in_executor(_validate_connection, client, config)
        logger.info(f"Confluence connection successful. User: {display_name}")
        return {"status": "success", "user": display_name}
    except Exception as e:
        logger.error(f"Confluence connection failed: {e}", exc_info=True)
        raise _map_error_to_http_exception(e)


def _validate_connection(client: Confluence, config: dict) -> str:
    """
    Validate connection by fetching spaces.

    This validates server reachability, credentials, and permissions.

    Returns:
        Display name for the user
    """
    logger.info("Validating credentials by fetching spaces")
    spaces = client.get_all_spaces(start=0, limit=1, expand=None)
    logger.info(f"Connected to Confluence. Found {spaces.get('size', 0)} spaces")

    return config.get('username', 'Confluence User')


def _contains_any_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    """Check if text contains any of the given keywords."""
    return any(keyword in text for keyword in keywords)


def _map_error_to_http_exception(error: Exception) -> HTTPException:
    """Map Confluence API errors to HTTP exceptions."""
    error_str = str(error).lower()

    error_mappings = {
        ("401", "unauthorized"): (401, "Invalid Confluence credentials"),
        ("404", "not found"): (404, "Confluence page or resource not found"),
        ("403", "forbidden"): (403, "Access denied to Confluence resource"),
        ("timeout",): (504, "Confluence request timed out"),
    }

    for keywords, (status_code, detail) in error_mappings.items():
        if _contains_any_keyword(error_str, keywords):
            return HTTPException(status_code=status_code, detail=detail)

    return HTTPException(status_code=500, detail=f"Confluence API error: {str(error)}")
