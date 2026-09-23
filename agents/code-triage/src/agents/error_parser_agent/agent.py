"""LangChain error parser agent and structured output model."""

from __future__ import annotations

from typing import List, Literal

from langchain.agents import create_agent
from langchain.messages import HumanMessage
from pydantic import BaseModel

from .prompts import ERROR_PARSER_SYSTEM_PROMPT, ERROR_PARSER_USER_PROMPT_TEMPLATE
from src.llm_client import get_llm, get_prompt_caching_middleware
from src.agents.middlewares import TokenCountingCallback, CacheMonitoringMiddleware
import logging

logger = logging.getLogger(__name__)


class ErrorParseResult(BaseModel):
    """Structured output for the error parser agent."""

    error_type: str
    language: str
    file_hints: List[str]
    line_hints: List[str] = []
    search_strategy: str
    needs_code: bool = True
    severity: Literal["low", "medium", "high", "critical"] = "medium"

    # Error classification: code defect vs operational issue
    issue_category: Literal["code_defect", "operational"] = "code_defect"
    category_confidence: float = 0.5


# Token counting callback for this agent
_error_parser_token_callback = TokenCountingCallback(name="error_parser")

# Build middleware list with prompt caching support and cache monitoring
_middlewares = []
_caching_middleware = get_prompt_caching_middleware()
if _caching_middleware:
    _middlewares.append(_caching_middleware)
    logger.info("error_parser_agent: Prompt caching middleware enabled")

# Add cache monitoring middleware to track cache hits/misses
_cache_monitor = CacheMonitoringMiddleware(agent_name="error_parser")
_middlewares.append(_cache_monitor)

# Single shared agent instance per process.
error_parser_agent = create_agent(
    model=get_llm(temperature=0.1, max_tokens=2000),
    tools=[],
    system_prompt=ERROR_PARSER_SYSTEM_PROMPT,
    response_format=ErrorParseResult,
    name="error_parser_agent",
    middleware=_middlewares if _middlewares else None,
)


def parse_error_with_agent(error_message: str, stack_trace: str) -> ErrorParseResult:
    """Run the error parser agent and return an ErrorParseResult.

    LangChain agents created via ``create_agent`` always return a *state*
    dict. When using ``response_format`` for structured output, the parsed
    model is stored under the ``"structured_response"`` key of that state.

    Here we:
    1. Invoke the agent to get its state.
    2. Pull out ``state["structured_response"]`` when present.
    3. Coerce that into our ``ErrorParseResult`` Pydantic model.
    """

    user_prompt = ERROR_PARSER_USER_PROMPT_TEMPLATE.format(
        error_message=error_message,
        stack_trace=stack_trace,
    )

    state = error_parser_agent.invoke(
        {"messages": [HumanMessage(content=user_prompt)]},
        config={"callbacks": [_error_parser_token_callback]}
    )

    # Fast path: agent already returned the model
    if isinstance(state, ErrorParseResult):
        return state

    # LangChain agents return a state dict; look for structured_response first
    candidate = None
    if isinstance(state, dict):
        if "structured_response" in state:
            candidate = state["structured_response"]
        else:
            candidate = state
    else:
        candidate = state

    if isinstance(candidate, ErrorParseResult):
        return candidate
    if isinstance(candidate, dict):  # expected common path
        return ErrorParseResult.model_validate(candidate)

    # Fallback: best-effort construction from arbitrary object
    return ErrorParseResult(
        error_type=str(getattr(candidate, "error_type", "Unknown")),
        language=str(getattr(candidate, "language", "unknown")),
        file_hints=list(getattr(candidate, "file_hints", [])),
        line_hints=list(getattr(candidate, "line_hints", [])),
        search_strategy=str(getattr(candidate, "search_strategy", "Search for error")),
        needs_code=bool(getattr(candidate, "needs_code", True)),
        severity=str(getattr(candidate, "severity", "medium")),
        issue_category=str(getattr(candidate, "issue_category", "code_defect")),
        category_confidence=float(getattr(candidate, "category_confidence", 0.5)),
    )

