"""
Confluence Integration Service

Provides async wrapper around synchronous atlassian-python-api library.
Uses ThreadPoolExecutor to prevent blocking the FastAPI event loop.

Module Structure:
- client.py: Client creation and validation
- url_parser.py: URL parsing utilities
- page_fetcher.py: Page fetching logic
- conversion.py: XHTML to Markdown conversion
- constants.py: Configuration and constants
"""
from .client import get_confluence_client, validate_confluence_config
from .constants import (
    CONFLUENCE_API_TIMEOUT,
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_PAGES,
    DEFAULT_PAGINATION_LIMIT,
    MAX_EXECUTOR_WORKERS,
    confluence_executor,
)
from .conversion import convert_to_markdown, replace_confluence_macros
from .page_fetcher import fetch_child_pages, fetch_page_content, fetch_single_page
from .url_parser import extract_page_id_from_url


class ConfluenceService:
    """
    Main service class for Confluence integration.

    All methods are static as this is a stateless service.
    """

    # Client management
    get_confluence_client = staticmethod(get_confluence_client)
    validate_config = staticmethod(validate_confluence_config)

    # URL parsing
    extract_page_id_from_url = staticmethod(extract_page_id_from_url)

    # Page fetching
    fetch_page_content = staticmethod(fetch_page_content)
    fetch_single_page = staticmethod(fetch_single_page)
    fetch_child_pages = staticmethod(fetch_child_pages)

    # Conversion
    convert_to_markdown = staticmethod(convert_to_markdown)
    _replace_confluence_macros = staticmethod(replace_confluence_macros)


__all__ = [
    'ConfluenceService',
    'get_confluence_client',
    'validate_confluence_config',
    'extract_page_id_from_url',
    'fetch_page_content',
    'fetch_single_page',
    'fetch_child_pages',
    'convert_to_markdown',
    'replace_confluence_macros',
    'MAX_EXECUTOR_WORKERS',
    'DEFAULT_PAGINATION_LIMIT',
    'DEFAULT_MAX_DEPTH',
    'DEFAULT_MAX_PAGES',
    'CONFLUENCE_API_TIMEOUT',
    'confluence_executor',
]
