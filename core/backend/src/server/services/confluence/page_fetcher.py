"""
Confluence page fetching logic
"""
import logging
from collections import deque

from atlassian import Confluence
from fastapi import HTTPException

from .constants import DEFAULT_PAGINATION_LIMIT
from .conversion import convert_to_markdown

logger = logging.getLogger(__name__)


async def fetch_page_content(
    client: Confluence,
    page_url: str,
    base_url: str
) -> dict:
    """
    Fetch a Confluence page from URL and convert to markdown.

    This is a convenience wrapper that:
    1. Extracts page ID from URL
    2. Fetches the page content
    3. Converts to markdown

    Args:
        client: Confluence API client
        page_url: Confluence page URL or page ID
        base_url: Confluence base URL

    Returns:
        dict with keys: title, content (markdown), page_id, url, version, last_modified
    """
    from .url_parser import extract_page_id_from_url

    # Extract page ID from URL
    page_id = await extract_page_id_from_url(page_url, client)

    # Fetch the page
    return await fetch_single_page(client, page_id, base_url)


async def _fetch_page_from_api(client: Confluence, page_id: str) -> dict:
    """Fetch page data from Confluence API."""
    from .client import _run_in_executor

    try:
        return await _run_in_executor(
            client.get_page_by_id,
            page_id,
            expand='body.storage,version'
        )
    except Exception as e:
        logger.error(f"Failed to fetch page {page_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch page: {str(e)}")


async def fetch_single_page(
    client: Confluence,
    page_id: str,
    base_url: str
) -> dict:
    """
    Fetch a single Confluence page with content by page ID.

    Args:
        client: Confluence API client
        page_id: Page ID to fetch
        base_url: Confluence base URL

    Returns:
        dict with keys: title, content (markdown), page_id, url, version, last_modified
    """
    page = await _fetch_page_from_api(client, page_id)
    logger.warning(f"[CONFLUENCE] Fetched page {page_id}: {page.get('title')}")

    storage_content = _extract_storage_content(page, page_id)
    markdown_content = await convert_to_markdown(storage_content)
    logger.warning(f"[CONFLUENCE] Converted page {page_id} to {len(markdown_content)} chars markdown")

    return _build_page_dict(page, markdown_content, base_url)


def _extract_storage_content(page: dict, page_id: str) -> str:
    """Extract storage content from page with error checking."""
    try:
        storage_content = page['body']['storage']['value']
        logger.warning(f"[CONFLUENCE] Extracted {len(storage_content)} chars from page {page_id}")

        if not storage_content:
            logger.error(f"[CONFLUENCE] Empty storage content for page {page_id}")

        return storage_content
    except KeyError as e:
        logger.error(f"[CONFLUENCE] Missing body content from page {page_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Page missing body content: {e}")


def _build_page_dict(page: dict, markdown_content: str, base_url: str) -> dict:
    """Build standardized page dictionary."""
    return {
        "title": page['title'],
        "content": markdown_content,
        "page_id": str(page['id']),
        "url": f"{base_url}/wiki/pages/{page['id']}",
        "version": page['version']['number'],
        "last_modified": page['version']['when']
    }


async def _fetch_page_children_batch(
    client: Confluence,
    page_id: str,
    start: int,
    limit: int
) -> dict:
    """
    Fetch a batch of child pages.

    Args:
        client: Confluence client
        page_id: Parent page ID
        start: Start index for pagination
        limit: Max results per page

    Returns:
        Response from Confluence API (dict or list depending on API version)
    """
    from .client import _run_in_executor

    return await _run_in_executor(
        client.get_page_child_by_type,
        page_id,
        type='page',
        start=start,
        limit=limit,
        expand='body.storage,version'
    )


async def fetch_child_pages(
    client: Confluence,
    parent_page_id: str,
    base_url: str,
    max_depth: int = 10,
    max_pages: int = 50
) -> list[dict]:
    """
    Recursively fetch child pages using BFS traversal.

    Args:
        client: Confluence client
        parent_page_id: Parent page ID
        base_url: Confluence base URL
        max_depth: Maximum depth to traverse
        max_pages: Maximum total pages to fetch

    Returns:
        List of page dictionaries
    """
    children = []
    queue = deque([(parent_page_id, 0)])
    visited = {parent_page_id}

    while queue and len(children) < max_pages:
        current_id, depth = queue.popleft()

        if depth >= max_depth:
            continue

        await _fetch_children_of_page(
            client, current_id, depth, base_url,
            children, queue, visited, max_pages
        )

    logger.info(f"Fetched {len(children)} child pages from parent {parent_page_id}")
    return children


async def _process_child_page(
    child: dict,
    base_url: str,
    children: list,
    queue: deque,
    visited: set,
    depth: int
) -> None:
    """Process a single child page and add to results."""
    child_id = str(child['id'])
    if child_id in visited:
        return

    visited.add(child_id)
    storage_content = child['body']['storage']['value']
    markdown_content = await convert_to_markdown(storage_content)
    children.append(_build_page_dict(child, markdown_content, base_url))
    queue.append((child_id, depth + 1))


async def _fetch_children_of_page(
    client: Confluence,
    page_id: str,
    depth: int,
    base_url: str,
    children: list,
    queue: deque,
    visited: set,
    max_pages: int
) -> None:
    """Fetch all children of a single page with pagination."""
    start = 0

    while len(children) < max_pages:
        response = await _fetch_children_batch_safe(client, page_id, start)
        if not response:
            break

        results = _extract_results_from_response(response)
        if not results:
            break

        for child in results:
            if len(children) >= max_pages:
                break
            await _process_child_page(child, base_url, children, queue, visited, depth)

        if not _has_more_results(response, results, start):
            break

        start += DEFAULT_PAGINATION_LIMIT


async def _fetch_children_batch_safe(
    client: Confluence,
    page_id: str,
    start: int
) -> dict | None:
    """Fetch children batch with error handling."""
    try:
        return await _fetch_page_children_batch(client, page_id, start, DEFAULT_PAGINATION_LIMIT)
    except Exception as e:
        logger.warning(f"Failed to fetch children of page {page_id}: {e}")
        return None


def _extract_results_from_response(response) -> list:
    """Extract results list from API response."""
    if isinstance(response, list):
        return response
    if isinstance(response, dict):
        return response.get('results', [])

    logger.warning(f"Unexpected response type: {type(response)}")
    return []


def _has_more_results(response, results: list, start: int) -> bool:
    """Check if more results are available for pagination."""
    if isinstance(response, dict):
        total_size = response.get('size', len(results))
        return start + DEFAULT_PAGINATION_LIMIT < total_size

    # For list responses, fewer results than limit means we're done
    return len(results) >= DEFAULT_PAGINATION_LIMIT

