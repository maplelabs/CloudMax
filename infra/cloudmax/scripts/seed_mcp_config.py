"""
One-off seed: ensure CloudMax's AppConfig.mcp_connections includes enabled
Grafana and Jaeger MCP server entries, enabled by default.

Run inside the cloudmax-backend container (has DATABASE_URL + all the app's
own models already available on PYTHONPATH=/app), so this reuses the exact
same SQLAlchemy models/Pydantic enum values the running app itself uses --
no hand-written SQL, no enum-value guessing.

Endpoint URLs point at the demo VM's own public IP on the host-published
MCP ports (grafana-mcp-server: 8012->8000, jaeger-mcp-server: 8011->8000 in
infra/hotel-app/docker-compose.yml) rather than internal container names --
this matches what a user actually reaches when testing the connection from
CloudMax's Settings UI (which runs the validate_connection() check from the
backend container, but the user may also re-verify/re-save from a browser
hitting the same public endpoint).

Required env vars:
  VM_PUBLIC_IP  -- the demo VM's public IP address

Idempotent: replaces any existing grafana/jaeger entries in
mcp_connections.systems (keeping any other entries, e.g. opensearch,
untouched) rather than appending duplicates on every demo-create.yml run.
"""
import asyncio
import os

from sqlalchemy import select

from src.server.apis_v1.dependencies import async_db_session
from src.server.models.db.app_config import AppConfig
from src.server.models.api.enums import Severity, ObservabilitySystem, ConnectionType

GRAFANA_MCP_PORT = 8012
JAEGER_MCP_PORT = 8011


def _require_env(name):
    val = os.environ.get(name)
    if not val:
        raise SystemExit(f"Missing required env var: {name}")
    return val


def mcp_system(name: str, url: str) -> dict:
    return {
        "observability_system": name,
        "enabled": True,
        "connection_config": {
            "connection_type": ConnectionType.STREAMABLE_HTTP.value,
            "endpoint_url": url,
            "http_headers": [],
            "mtls_enabled": False,
        },
    }


async def main():
    vm_ip = _require_env("VM_PUBLIC_IP")
    grafana_url = f"http://{vm_ip}:{GRAFANA_MCP_PORT}/mcp"
    jaeger_url = f"http://{vm_ip}:{JAEGER_MCP_PORT}/mcp"

    async with async_db_session() as session:
        result = await session.execute(
            select(AppConfig).order_by(AppConfig.id.desc()).limit(1)
        )
        config = result.scalar_one_or_none()

        new_systems = [
            mcp_system(ObservabilitySystem.GRAFANA.value, grafana_url),
            mcp_system(ObservabilitySystem.JAEGER.value, jaeger_url),
        ]

        if config:
            existing = (config.mcp_connections or {}).get("systems", [])
            kept = [
                s for s in existing
                if s.get("observability_system") not in (
                    ObservabilitySystem.GRAFANA.value, ObservabilitySystem.JAEGER.value,
                )
            ]
            config.mcp_connections = {"systems": kept + new_systems}
            print(f"Updated existing AppConfig (id={config.id}) with grafana/jaeger MCP connections.")
        else:
            config = AppConfig(
                enabled_severities=[Severity.P1],
                mcp_connections={"systems": new_systems},
                code_triaging_agent_enabled=False,
                orchestrator_agents=1,
                chaos_system_enabled=False,
                automatic_triage=True,
                alert_grouping_enabled=True,
            )
            session.add(config)
            print("No existing AppConfig found -- created a new one with grafana/jaeger MCP connections.")

        await session.commit()


asyncio.run(main())
print("Done.")
