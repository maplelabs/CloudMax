"""
Confluence service constants and configuration
"""
from concurrent.futures import ThreadPoolExecutor

# Thread pool configuration
MAX_EXECUTOR_WORKERS = 4
DEFAULT_PAGINATION_LIMIT = 25
DEFAULT_MAX_DEPTH = 10
DEFAULT_MAX_PAGES = 50
CONFLUENCE_API_TIMEOUT = 60  # Timeout in seconds for Confluence API calls

# Thread pool for blocking Confluence API calls
confluence_executor = ThreadPoolExecutor(
    max_workers=MAX_EXECUTOR_WORKERS,
    thread_name_prefix="confluence"
)
