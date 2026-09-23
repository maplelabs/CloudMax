"""A2A JSON-RPC server application for the Code Triaging Agent.

This module builds a FastAPI application using the official a2a-sdk server
primitives. It exposes the agent via the standard A2A "message/send" and
related methods on the `/a2a/tasks` endpoint, and serves an AgentCard at
`/.well-known/agent-card.json`.
"""

from __future__ import annotations

import logging

from a2a.server.apps.jsonrpc.fastapi_app import A2AFastAPIApplication
from a2a.server.events.in_memory_queue_manager import InMemoryQueueManager
from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, TransportProtocol

from src.agents.code_triaging_agent.a2a_executor import CodeTriagerAgentExecutor
from src.config import ORCHESTRATOR_PORT, validate_config


logger = logging.getLogger(__name__)


class HealthCheckFilter(logging.Filter):
    """Filter out health check endpoint logs from Uvicorn access logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Suppress logs for GET /health requests
        return "/health" not in record.getMessage()


def _build_agent_card() -> AgentCard:
    """Construct the A2A AgentCard for the code-triage-agent.

    This maps the existing, simpler agent card used by the legacy HTTP server
    into the richer A2A AgentCard type.
    """

    base_url = f"http://localhost:{ORCHESTRATOR_PORT}/a2a/tasks"

    capabilities = AgentCapabilities(
        streaming=False,
        push_notifications=False,
        state_transition_history=False,
        extensions=[],
    )

    triage_skill = AgentSkill(
        id="triage",
        name="Code triage",
        description=(
            "Analyze application errors using repository code context and "
            "provide root cause and fix suggestions."
        ),
        tags=["code", "triage", "debugging", "mcp"],
        examples=[
            "Given a Python traceback and a GitHub repo, explain the root cause and how to fix it.",
        ],
        input_modes=None,
        output_modes=None,
        security=None,
    )

    card = AgentCard(
        name="code-triage-agent",
        description=(
            "AI-powered code triage agent with intelligent routing, code "
            "retrieval via MCP, and structured analysis of application errors."
        ),
        version="2.0.0",
        url=base_url,
        preferred_transport=TransportProtocol.jsonrpc,
        protocol_version="0.3.0",
        capabilities=capabilities,
        default_input_modes=["application/json"],
        default_output_modes=["application/json"],
        skills=[triage_skill],
        additional_interfaces=[
            AgentInterface(transport=TransportProtocol.jsonrpc, url=base_url)
        ],
        provider=None,
        icon_url=None,
        documentation_url=None,
        security=None,
        security_schemes=None,
        signatures=None,
        supports_authenticated_extended_card=False,
    )

    return card


# Build the A2A FastAPI app that will be served by uvicorn.

_agent_executor = CodeTriagerAgentExecutor()
_task_store = InMemoryTaskStore()
_queue_manager = InMemoryQueueManager()
_request_handler = DefaultRequestHandler(
    agent_executor=_agent_executor,
    task_store=_task_store,
    queue_manager=_queue_manager,
)
_agent_card = _build_agent_card()

app = A2AFastAPIApplication(
    agent_card=_agent_card,
    http_handler=_request_handler,
).build(
    agent_card_url="/.well-known/agent-card.json",
    rpc_url="/a2a/tasks",
)


@app.on_event("startup")
async def startup_validation():
    """Validate configuration on application startup.

    This ensures that required environment variables (from Kubernetes secrets,
    AWS Secrets Manager, etc.) are available before the service starts handling requests.
    """
    validate_config()

    # Suppress noisy health check logs from Uvicorn
    logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())


@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestration."""
    return {"status": "healthy"}


logger.info(
    "Initialized A2A FastAPI application for code-triage-agent on /a2a/tasks"
)
