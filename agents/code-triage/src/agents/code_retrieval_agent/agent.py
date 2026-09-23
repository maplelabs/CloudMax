"""LangChain code retrieval planning agent and structured output model.

This agent does *planning* for code retrieval (file paths vs search
queries). The actual MCP calls are handled by the orchestrator using
src.mcp_tools.GitHubMCPTools.
"""

from __future__ import annotations

from typing import List, Literal

from langchain.agents import create_agent
from langchain.messages import HumanMessage
from pydantic import BaseModel

from .prompts import (
	CODE_RETRIEVAL_SYSTEM_PROMPT,
	CODE_RETRIEVAL_STRATEGY_PROMPT_TEMPLATE,
)
from src.llm_client import get_llm
from src.agents.middlewares import TokenCountingCallback


class CodeRetrievalResult(BaseModel):
    """Structured output for the code retrieval planning agent."""

    retrieval_strategy: Literal["file_paths", "search", "both"]
    file_hints: List[str]
    search_queries: List[str]
    reasoning: str


# Token counting callback for this agent
_code_retrieval_token_callback = TokenCountingCallback(name="code_retrieval")

code_retrieval_agent = create_agent(
    model=get_llm(temperature=0.1, max_tokens=2000),
    tools=[],  # MCP tools are used directly based on this plan
    system_prompt=CODE_RETRIEVAL_SYSTEM_PROMPT,
    response_format=CodeRetrievalResult,
    name="code_retrieval_agent",
)


def plan_code_retrieval_from_state(state: dict) -> CodeRetrievalResult:
    """Build a retrieval plan from the current TriageState.

    We call the LangChain agent and then pull the structured response out
    of the returned state dict (``state["structured_response"]``) before
    validating it into our Pydantic model.
    """

    prompt = CODE_RETRIEVAL_STRATEGY_PROMPT_TEMPLATE.format(
        error_type=state.get("error_type", ""),
        language=state.get("language", ""),
        file_hints=state.get("file_hints", []),
        search_strategy=state.get("search_strategy", ""),
        severity=state.get("severity", "medium"),
    )

    agent_state = code_retrieval_agent.invoke(
        {"messages": [HumanMessage(content=prompt)]},
        config={"callbacks": [_code_retrieval_token_callback]}
    )

    # Agent may return the model directly or wrap it under structured_response
    if isinstance(agent_state, CodeRetrievalResult):
        return agent_state

    candidate = None
    if isinstance(agent_state, dict):
        if "structured_response" in agent_state:
            candidate = agent_state["structured_response"]
        else:
            candidate = agent_state
    else:
        candidate = agent_state

    if isinstance(candidate, CodeRetrievalResult):
        return candidate
    if isinstance(candidate, dict):
        return CodeRetrievalResult.model_validate(candidate)

    # Fallback: construct a minimal plan
    return CodeRetrievalResult(
        retrieval_strategy="search",
        file_hints=list(getattr(candidate, "file_hints", [])),
        search_queries=list(getattr(candidate, "search_queries", [])),
        reasoning=str(getattr(candidate, "reasoning", "fallback plan")),
    )

