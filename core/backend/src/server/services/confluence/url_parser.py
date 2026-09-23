"""
URL parsing utilities for Confluence
"""
import logging
import re
from urllib.parse import unquote, urlparse

from atlassian import Confluence
from fastapi import HTTPException

logger = logging.getLogger(__name__)


async def extract_page_id_from_url(url: str, client: Confluence) -> str:
    """
    Extract Confluence page ID from various URL formats.

    Supports:
    - /wiki/pages/12345
    - /wiki/spaces/SPACE/pages/12345/Page+Title
    - /display/SPACE/Page+Title
    - Direct page ID: "12345"

    Args:
        url: Confluence page URL or ID
        client: Confluence API client for title lookups

    Returns:
        Page ID as string

    Raises:
        HTTPException: If URL cannot be parsed
    """
    if not url:
        raise HTTPException(status_code=400, detail="URL cannot be empty")

    if url.isdigit():
        return url

    try:
        path = unquote(urlparse(url).path)

        # Try direct page ID patterns first
        page_id = _extract_page_id_from_path(path)
        if page_id:
            return page_id

        # Try display URL pattern (requires lookup)
        return await _extract_page_id_from_display_url(path, client)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to parse Confluence URL {url}: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid Confluence URL: {str(e)}")


def _extract_page_id_from_path(path: str) -> str | None:
    """Extract page ID from URL path patterns."""
    patterns = [
        r'/pages/(\d+)',                      # /wiki/pages/12345 or /pages/12345
        r'/spaces/[^/]+/pages/(\d+)',         # /wiki/spaces/SPACE/pages/12345/Title
    ]

    for pattern in patterns:
        match = re.search(pattern, path)
        if match:
            return match.group(1)

    return None


async def _extract_page_id_from_display_url(path: str, client: Confluence) -> str:
    """Extract page ID from /display/SPACE/Title format."""
    match = re.search(r'/display/([^/]+)/(.+)', path)
    if not match:
        raise HTTPException(
            status_code=400,
            detail=f"Could not extract page ID from path: {path}"
        )

    space_key = match.group(1)
    page_title = unquote(match.group(2)).replace('+', ' ')
    return await _lookup_page_id_by_space_and_title(client, space_key, page_title)


async def _lookup_page_id_by_space_and_title(
    client: Confluence,
    space_key: str,
    title: str
) -> str:
    """
    Look up page ID by space key and title using CQL search.

    Args:
        client: Confluence client
        space_key: Space key (e.g., 'MYSPACE')
        title: Page title

    Returns:
        Page ID as string

    Raises:
        HTTPException: If page not found or lookup fails
    """
    from .client import _run_in_executor
    return await _run_in_executor(_perform_page_lookup, client, space_key, title)


def _escape_cql_value(value: str) -> str:
    """Escape special characters in CQL query values to prevent injection.

    Escapes backslashes first, then quotes to prevent CQL injection.
    Example: 'TEST\\"' becomes 'TEST\\\\\\"' (safe)
    """
    # Escape backslashes first, then quotes (order matters!)
    return value.replace('\\', '\\\\').replace('"', '\\"')


def _perform_page_lookup(client: Confluence, space_key: str, title: str) -> str:
    """Perform synchronous page lookup via CQL."""
    try:
        safe_space_key = _escape_cql_value(space_key)
        safe_title = _escape_cql_value(title)
        cql = f'space="{safe_space_key}" AND title="{safe_title}"'
        results = client.cql(cql, limit=1)

        if results and results.get('results'):
            return str(results['results'][0]['id'])

        raise HTTPException(
            status_code=404,
            detail=f"Page not found in space '{space_key}' with title '{title}'"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to lookup page by title: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to lookup page: {str(e)}"
        )
