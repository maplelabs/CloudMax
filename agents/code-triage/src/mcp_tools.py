"""GitHub MCP tools implemented using langchain_mcp_adapters.

This module delegates all MCP protocol details to MultiServerMCPClient from
langchain_mcp_adapters and exposes a small, async API tailored to the
code-retrieval logic.

Public async API:

* get_file_contents(owner, repo, path) -> str | None
* validate_github_repository(owner, repo, token) -> tuple[bool, str | None]

Custom Exceptions:

* MCPToolNotInitializedError: Raised when MCP tool is not properly initialized
* MCPAuthenticationError: Raised when authentication fails (403, 401)
* MCPTimeoutError: Raised when request times out
* MCPHTTPError: Raised for other HTTP errors (rate limiting, server errors, etc.)
"""

import asyncio
import json
import logging
import re
from typing import Any, List, Optional

import httpx
from langchain_core.tools.base import ToolException
from langchain_mcp_adapters.client import MultiServerMCPClient

from src.config import GITHUB_MCP_URL, GITHUB_TOKEN

logger = logging.getLogger(__name__)

# GitHub MCP Server Status Message Patterns (detect status vs file content)
MCP_STATUS_PREFIXES = (
    "successfully downloaded",
    "Resolved potential matches",
)

MCP_STATUS_INDICATORS = (
    "SHA:",
    "matching files:",
)


def _extract_root_cause(exception: Exception) -> Exception:
    """Extract the root cause from an exception, handling ExceptionGroup.

    Python 3.11+ uses ExceptionGroup to wrap multiple exceptions. This function
    recursively unwraps ExceptionGroups to find the actual root cause error.

    Args:
        exception: The exception to unwrap

    Returns:
        The root cause exception
    """
    if hasattr(exception, 'exceptions'):
        exceptions = getattr(exception, 'exceptions', ())
        if exceptions:
            return _extract_root_cause(exceptions[0])

    if exception.__cause__:
        return _extract_root_cause(exception.__cause__)

    if exception.__context__ and not exception.__suppress_context__:
        return _extract_root_cause(exception.__context__)

    return exception


def _is_status_message(text: str) -> bool:
    """Check if text is a GitHub API status message rather than file content.

    GitHub MCP server sometimes returns status/metadata messages instead of file content.
    This function detects these patterns to distinguish them from actual code.

    Args:
        text: The text to check

    Returns:
        True if text appears to be a status message, False otherwise

    Examples:
        >>> _is_status_message("successfully downloaded text file (SHA: abc123)")
        True
        >>> _is_status_message("Resolved potential matches... matching files: ['foo.py']")
        True
        >>> _is_status_message("def hello():\\n    print('world')")
        False
    """
    return (
        any(text.startswith(prefix) for prefix in MCP_STATUS_PREFIXES) or
        any(indicator in text for indicator in MCP_STATUS_INDICATORS)
    )


def _extract_path_from_search_result(text: str) -> Optional[str]:
    """Extract the actual file path from a GitHub MCP search result message.

    GitHub MCP returns messages like:
    'Resolved potential matches... matching files: ["path/to/file.py"]'

    Args:
        text: The search result message

    Returns:
        The extracted file path, or None if not found or if validation fails
    """
    match = re.search(r'matching files:\s*(\[.*?\])', text)
    if not match:
        return None

    try:
        files = json.loads(match.group(1))

        if not isinstance(files, list):
            logger.warning("Expected list from MCP search result, got %s", type(files).__name__)
            return None

        if not files:  # More Pythonic, handles None and empty list
            logger.debug("MCP search result returned empty file list")
            return None

        first_file = files[0]
        if not isinstance(first_file, str):
            logger.warning("Expected string path in MCP search result, got %s", type(first_file).__name__)
            return None

        return first_file

    except json.JSONDecodeError as e:
        logger.warning("Failed to parse JSON from MCP search result: %s", str(e))
        return None


def extract_relevant_lines(
    content: str,
    line_number: int,
    context_lines: int = 50
) -> tuple[str, dict]:
    """Extract relevant lines around the error line from file content.

    This prevents sending massive files to the LLM by extracting only the
    relevant context around where the error occurred.

    Args:
        content: Full file content
        line_number: Line number where error occurred (1-based)
        context_lines: Number of lines to include before and after the error line

    Returns:
        Tuple of (extracted_content, metadata_dict)
        - extracted_content: The relevant lines as a string
        - metadata_dict: Information about what was extracted
    """
    lines = content.split('\n')
    total_lines = len(lines)

    # Convert to 0-based indexing
    error_line_idx = line_number - 1

    # Calculate range (with bounds checking)
    start = max(0, error_line_idx - context_lines)
    end = min(total_lines, error_line_idx + context_lines + 1)

    # Extract relevant lines
    relevant_lines = lines[start:end]
    extracted_content = '\n'.join(relevant_lines)

    # Create metadata
    metadata = {
        "extracted": True,
        "total_lines": total_lines,
        "extracted_lines": len(relevant_lines),
        "line_range": f"{start + 1}-{end}",  # Convert back to 1-based
        "error_line": line_number,
        "context_lines": context_lines,
    }

    return extracted_content, metadata


# Custom exception classes for better error handling
class MCPToolNotInitializedError(RuntimeError):
    """Raised when an MCP tool is not properly initialized."""
    pass


class MCPAuthenticationError(Exception):
    """Raised when authentication fails (403, 401 status codes)."""
    pass


class MCPTimeoutError(Exception):
    """Raised when an MCP request times out."""
    pass


class MCPHTTPError(Exception):
    """Raised for HTTP errors other than 404 (rate limiting, server errors, etc.)."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(message)


async def validate_github_repository(
    owner: str, repo: str, token: str
) -> tuple[bool, str | None]:
    """
    Validate that a GitHub repository exists and is accessible.

    Args:
        owner: Repository owner (user or organization)
        repo: Repository name
        token: GitHub personal access token

    Returns:
        (is_valid, error_message)
        - (True, None) if repository is valid and accessible
        - (False, "reason") if validation fails
    """
    # Check repository accessibility via GitHub API
    url = f"https://api.github.com/repos/{owner}/{repo}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=10.0)

        if response.status_code == 200:
            logger.info("Repository validation successful: %s/%s", owner, repo)
            return True, None
        elif response.status_code == 404:
            error_msg = f"Repository {owner}/{repo} not found or not accessible with provided token"
            logger.warning("Repository validation failed: %s", error_msg)
            return False, error_msg
        elif response.status_code == 401:
            error_msg = "GitHub token is invalid or expired"
            logger.warning("Repository validation failed: %s", error_msg)
            return False, error_msg
        else:
            error_msg = f"GitHub API returned status {response.status_code}"
            logger.warning("Repository validation failed: %s", error_msg)
            return False, error_msg

    except Exception as e:
        error_msg = f"Failed to validate repository: {str(e)}"
        logger.error("Repository validation error: %s", e, exc_info=True)
        return False, error_msg


class GitHubMCPTools:
    """Async GitHub MCP tools backed by MultiServerMCPClient.

    This class is intentionally thin: it knows how to locate the relevant MCP
    tools from the GitHub MCP server and how to normalize their results into
    the shapes expected by the code-retrieval subgraph.
    """

    # Shared client and tool handles across instances
    _client: Optional[MultiServerMCPClient] = None
    _tools_loaded: bool = False
    _get_file_tool: Any = None
    _init_lock: asyncio.Lock = asyncio.Lock()

    def __init__(self) -> None:
        """Initialize the shared MultiServerMCPClient if needed."""

        if GitHubMCPTools._client is None:
            # Configure a single MCP server for GitHub
            GitHubMCPTools._client = MultiServerMCPClient(
                {
                    "github": {
                        # GitHub MCP is exposed over HTTP
                        "transport": "http",
                        "url": GITHUB_MCP_URL,
                        "headers": {
                            "Authorization": f"Bearer {GITHUB_TOKEN}",
                        },
                    }
                }
            )
            logger.info(
                "Initialized MultiServerMCPClient for GitHub MCP server: %s",
                GITHUB_MCP_URL,
            )

    @classmethod
    async def _ensure_tools_loaded(cls) -> None:
        """Ensure we have located the GitHub MCP tools we care about.

        We fetch all tools from the MCP server once and cache the one whose
        name contains "get_file_contents".
        """

        if cls._tools_loaded and cls._get_file_tool:
            return

        # Ensure only one coroutine performs the initialization / tool loading
        async with cls._init_lock:
            # Double-check inside the lock in case another waiter finished init
            if cls._tools_loaded and cls._get_file_tool:
                return

            if cls._client is None:
                # Instantiate a default client if __init__ hasn't been called yet
                cls()

            assert cls._client is not None

            # Retry logic for transient failures
            max_retries = 3
            tools: List[Any] = []

            for attempt in range(max_retries):
                try:
                    # Add timeout protection to prevent indefinite hangs
                    tools = await asyncio.wait_for(
                        cls._client.get_tools(),
                        timeout=60.0,
                    )
                    # Success - break out of retry loop
                    break

                except asyncio.TimeoutError:
                    if attempt < max_retries - 1:
                        # Transient timeout - retry with exponential backoff
                        backoff_seconds = 2 ** attempt
                        logger.warning(
                            "MCP server timeout (attempt %d/%d), retrying in %ds...",
                            attempt + 1,
                            max_retries,
                            backoff_seconds,
                        )
                        await asyncio.sleep(backoff_seconds)
                    else:
                        # Max retries exceeded
                        error_msg = f"MCP server timeout after {max_retries} attempts - check GITHUB_MCP_URL"
                        logger.error(error_msg)
                        raise RuntimeError(error_msg)

                except ToolException as e:
                    # MCP tool error - check if it's auth-related
                    error_str = str(e).lower()
                    if "auth" in error_str or "unauthorized" in error_str or "forbidden" in error_str:
                        error_msg = "GitHub MCP authentication failed - check GITHUB_TOKEN"
                        logger.error(error_msg)
                        raise RuntimeError(error_msg) from e
                    else:
                        # Other tool error - don't retry
                        error_msg = f"Failed to load MCP tools: {str(e)}"
                        logger.error(error_msg)
                        raise RuntimeError(error_msg) from e

                except Exception as e:
                    # Unexpected error - extract root cause from ExceptionGroup if present
                    root_cause = _extract_root_cause(e)

                    # Check for specific error types to provide better diagnostics
                    if isinstance(root_cause, httpx.ConnectError):
                        error_msg = (
                            f"Failed to connect to GitHub MCP server at {GITHUB_MCP_URL}\n"
                            f"Error: {str(root_cause)}\n"
                            f"Possible causes:\n"
                            f"  - DNS resolution failure (check if hostname is correct)\n"
                            f"  - Network connectivity issues\n"
                            f"  - Incorrect GITHUB_MCP_URL\n"
                            f"  - Firewall blocking the connection"
                        )
                        logger.error(error_msg)
                        raise RuntimeError(error_msg) from e

                    # Generic error handling
                    logger.error("Failed to load tools from GitHub MCP server: %s", e, exc_info=True)
                    raise RuntimeError(
                        f"Failed to initialize GitHub MCP client: {type(e).__name__}\n"
                        f"Root cause: {type(root_cause).__name__}: {str(root_cause)}"
                    ) from e

            get_file_tool: Any = None

            for tool in tools:
                name = getattr(tool, "name", "") or ""
                if "get_file_contents" in name:
                    get_file_tool = tool

            if get_file_tool is None:
                logger.error(
                    "Required GitHub MCP tool 'get_file_contents' not found. Available tools: %s",
                    [getattr(t, "name", "") for t in tools],
                )
                raise RuntimeError(
                    "GitHub MCP tool 'get_file_contents' is required",
                )

            cls._get_file_tool = get_file_tool
            cls._tools_loaded = True

            logger.info(
                "Loaded GitHub MCP tool: get_file_contents=%s",
                getattr(get_file_tool, "name", ""),
            )

    async def _retry_with_extracted_path(
        self,
        status_message: str,
        owner: str,
        repo: str,
        original_path: str,
        retry_depth: int,
    ) -> Optional[str]:
        """Attempt to extract actual path from status message and retry retrieval.

        GitHub MCP sometimes returns search results instead of file content.
        This method extracts the actual file path and retries the request.

        Args:
            status_message: The status message containing potential file path
            owner: Repository owner
            repo: Repository name
            original_path: The original path that was requested
            retry_depth: Current retry depth (prevents infinite recursion)

        Returns:
            File content if retry succeeds, None otherwise

        Note:
            Catches specific exceptions (RuntimeError, ValueError, KeyError) that may occur
            during MCP retrieval. These exceptions are expected when:
            - RuntimeError: MCP tool encounters runtime issues during retrieval
            - ValueError: Invalid data format received from MCP server
            - KeyError: Missing required fields in MCP response structure
        """
        actual_path = _extract_path_from_search_result(status_message)
        if actual_path and actual_path != original_path and retry_depth == 0:
            logger.info(
                "Extracted actual file path from search result: %s -> %s (retry_depth=%d)",
                original_path,
                actual_path,
                retry_depth,
            )
            try:
                return await self.get_file_contents(owner, repo, actual_path, _retry_depth=1)
            except (RuntimeError, ValueError, KeyError) as e:
                # These specific exceptions are caught because they represent expected
                # failure modes when retrying with an extracted path from MCP responses
                logger.warning(
                    "Failed to retrieve file with extracted path %s: %s",
                    actual_path,
                    str(e),
                )
        return None

    async def get_file_contents(
        self, owner: str, repo: str, path: str, _retry_depth: int = 0
    ) -> Optional[str]:
        """Get file contents from GitHub via MCP.

        Returns the file content as a string, or None if the file is not found.

        Timeout: 60 seconds - operation will raise MCPTimeoutError if it exceeds this limit.

        Args:
            owner: Repository owner
            repo: Repository name
            path: File path within repository
            _retry_depth: Internal parameter to prevent infinite recursion (max 1 retry)

        Raises:
            MCPToolNotInitializedError: If the MCP tool is not properly initialized
            MCPAuthenticationError: If authentication fails (403, 401, or permission errors)
            MCPTimeoutError: If the request times out (60s operation timeout or network timeout)
            MCPHTTPError: For other HTTP errors (rate limiting, server errors, etc.)
            ToolException: For MCP tool errors that don't match known patterns
            Exception: For unexpected errors

        The exact MCP response shape is handled by the adapter; this method
        normalizes common variants into a plain string.
        """

        await self._ensure_tools_loaded()
        tool = self._get_file_tool

        if tool is None:
            error_msg = "get_file_contents tool is not initialized"
            logger.error(error_msg)
            raise MCPToolNotInitializedError(error_msg)

        try:
            # LangChain tools accept a dict of arguments matching the tool
            # schema. The adapter handles conversion to MCP calls.
            # Add timeout protection to prevent indefinite hangs
            result: Any = await asyncio.wait_for(
                tool.ainvoke({"owner": owner, "repo": repo, "path": path}),
                timeout=60.0
            )
        except asyncio.TimeoutError:
            error_msg = f"MCP file retrieval timeout (60s) for {owner}/{repo}:{path} - operation exceeded timeout"
            logger.error(error_msg)
            raise MCPTimeoutError(error_msg)

        except ToolException as e:
            # MCP adapter raises ToolException for various errors
            error_str = str(e).lower()

            # Check if it's a file not found error
            if "does not exist" in error_str or "not found" in error_str or "no such file" in error_str:
                logger.warning("File not found: %s/%s:%s", owner, repo, path)
                return None

            # Check if it's an authentication error
            elif "unauthorized" in error_str or "forbidden" in error_str or "permission" in error_str:
                error_msg = f"Access denied to {owner}/{repo}:{path} - check token permissions"
                logger.error(error_msg)
                raise MCPAuthenticationError(error_msg) from e

            # Check if it's a rate limiting error
            elif "rate limit" in error_str or "too many requests" in error_str:
                error_msg = f"Rate limited fetching {owner}/{repo}:{path}"
                logger.error(error_msg)
                raise MCPHTTPError(429, error_msg) from e

            # Other ToolException errors - re-raise as generic error
            else:
                logger.error("MCP tool error fetching %s/%s:%s: %s", owner, repo, path, e)
                raise

        except httpx.TimeoutException as e:
            error_msg = f"Timeout fetching {owner}/{repo}:{path} - request exceeded timeout limit"
            logger.error(error_msg)
            raise MCPTimeoutError(error_msg) from e

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # File not found is an expected case - return None
                logger.warning("File not found: %s/%s:%s", owner, repo, path)
                return None
            elif e.response.status_code in (401, 403):
                error_msg = f"Access denied to {owner}/{repo}:{path} (HTTP {e.response.status_code}) - check token permissions"
                logger.error(error_msg)
                raise MCPAuthenticationError(error_msg) from e
            else:
                # Rate limiting (429), server errors (5xx), or other HTTP errors
                error_msg = f"HTTP {e.response.status_code} fetching {owner}/{repo}:{path}"
                logger.error(error_msg)
                raise MCPHTTPError(e.response.status_code, error_msg) from e

        except Exception as e:
            # Don't hide unexpected errors - log with full traceback and re-raise
            logger.error(
                "Unexpected error fetching %s/%s:%s: %s",
                owner,
                repo,
                path,
                e,
                exc_info=True,
            )
            raise

        # Many MCP tools return plain text directly once adapted to LangChain
        if isinstance(result, str):
            # Validate that we got actual file content, not a GitHub API message
            if _is_status_message(result):
                logger.warning(
                    "MCP returned GitHub API message instead of file content for %s/%s:%s: %s",
                    owner,
                    repo,
                    path,
                    result[:100],
                )
                # Try to extract and retry with actual path
                retry_result = await self._retry_with_extracted_path(
                    result, owner, repo, path, _retry_depth
                )
                return retry_result  # Returns None if retry fails or not attempted

            return result

        # If the adapter returns a dict (e.g. full MCP message), try common
        # patterns similar to the previous implementation.
        if isinstance(result, dict):
            # Newer adapters may surface "text" directly
            text = result.get("text")
            if isinstance(text, str):
                return text

            content = result.get("content")
            if isinstance(content, list):
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") == "resource":
                        resource = item.get("resource", {})
                        txt = resource.get("text")
                        if isinstance(txt, str):
                            return txt

        # Some MCP adapters may surface the "content" as a list at the top
        # level rather than inside a dict. Handle common patterns here.
        if isinstance(result, list):
            status_message_found = None

            for item in result:
                # Raw strings
                if isinstance(item, str):
                    if not _is_status_message(item):
                        return item
                    else:
                        # Store the status message for potential retry
                        status_message_found = item
                    continue

                if not isinstance(item, dict):
                    continue

                # Direct text field
                txt = item.get("text")
                if isinstance(txt, str):
                    # Skip status messages (GitHub MCP returns status as first item)
                    if not _is_status_message(txt):
                        return txt
                    else:
                        # Store the status message for potential retry
                        status_message_found = txt
                    continue

                # Resource-style wrapper
                if item.get("type") == "resource":
                    resource = item.get("resource", {})
                    txt2 = resource.get("text")
                    if isinstance(txt2, str):
                        if not _is_status_message(txt2):
                            return txt2
                        else:
                            status_message_found = txt2

            # If we found a status message, try to extract path and retry
            if status_message_found:
                logger.warning(
                    "MCP returned status message in list for %s/%s:%s: %s",
                    owner,
                    repo,
                    path,
                    status_message_found[:100],
                )
                # Try to extract and retry with actual path
                return await self._retry_with_extracted_path(
                    status_message_found, owner, repo, path, _retry_depth
                )

        logger.warning("Unexpected get_file_contents result type: %s", type(result))
        return None
