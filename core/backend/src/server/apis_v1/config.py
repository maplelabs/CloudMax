"""
Setup Configuration Service API endpoints.
Contains only the main API endpoint functions.
All helper functions have been moved to config_helpers.py
"""
import asyncio
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.server.apis_v1.dependencies import get_db_session, get_current_user
from src.server.models.api import (SetupConfigRequestOrResponse, ConfigOperationResponse, ConnectionTestResponse,
                                   DeploymentType, Severity, AlertTriageConfig, AlertGroupingConfig,
                                   CustomDeployment, AzureChatOpenAIConfig, AzureEmbeddingOpenAIConfig, McpConnections,
                                   GrafanaObservabilitySystem, StreamableHttpConnection, CodeTriagingAgent)
from src.server.models.db.app_config import AppConfig
from src.server.utilities.config import clear_all_manager_caches


def create_default_setup_response() -> SetupConfigRequestOrResponse:
    """Create default setup response structure"""

    return SetupConfigRequestOrResponse(
        alert_triage_config=AlertTriageConfig(
            enabled_severities=[Severity.P1]),
        deployment=DeploymentType.CUSTOM,
        custom_deployment=CustomDeployment(
            primary_llm_config=AzureChatOpenAIConfig(
                api_key="",
                endpoint_url="",
                deployment_name="",
                api_version="2024-02-01",
                price_usd_per_1k_ip_tokens=0,
                price_usd_per_1k_op_tokens=0
            ),
            embedding_config=AzureEmbeddingOpenAIConfig(
                api_key="",
                endpoint_url="",
                deployment_name="",
                api_version="2024-02-01"
            )
        ),
        mcp_connections=McpConnections(systems=[
            GrafanaObservabilitySystem(
                observability_system="grafana",
                enabled=False,
                connection_config=StreamableHttpConnection(
                    endpoint_url="",
                    http_headers=[]
                )
            )
        ]),
        code_triaging_agent=CodeTriagingAgent(
            enabled=False,
            base_url="http://code-triage-agent:8002",
            timeout_seconds=180,
            max_retries=3
        ),
        alert_grouping_config=AlertGroupingConfig(),  # Use default values
        chaos_system_enabled=False,
        orchestrator_agents=1,
        automatic_triage=True,
        alert_grouping_enabled=True,
        default_config=True
    )


def extract_deployment_config(request: SetupConfigRequestOrResponse):
    """Extract primary LLM and embedding configuration from request"""
    if not request.custom_deployment:
        return None, None, None, None, None, None

    primary_llm_config = request.custom_deployment.primary_llm_config
    secondary_llm_config = request.custom_deployment.secondary_llm_config
    embedding_config = request.custom_deployment.embedding_config

    # Extract primary LLM config
    primary_llm_provider = primary_llm_config.llm_type if hasattr(
        primary_llm_config, 'llm_type') else None
    primary_llm_connection_config = primary_llm_config.model_dump(
        exclude={"llm_type"}) if primary_llm_config else None

    # Process secondary LLM config
    from src.server.utilities.config import process_secondary_llm_config

    # Convert primary config to the format expected by process_secondary_llm_config
    primary_config_dict = primary_llm_connection_config.copy() if primary_llm_connection_config else {}
    if primary_llm_provider:
        primary_config_dict["llm_type"] = primary_llm_provider

    secondary_llm_provider, secondary_llm_connection_config = process_secondary_llm_config(
        primary_config_dict, secondary_llm_config.model_dump() if secondary_llm_config else None
    )

    # Extract embedding config
    embedding_provider = embedding_config.embedding_type if hasattr(
        embedding_config, 'embedding_type') else None
    embedding_connection_config = embedding_config.model_dump(
        exclude={"embedding_type"}) if embedding_config else None

    return (primary_llm_provider, primary_llm_connection_config,
            secondary_llm_provider, secondary_llm_connection_config,
            embedding_provider, embedding_connection_config)


async def validate_all_connections_from_request(request: SetupConfigRequestOrResponse) -> dict:
    """Validate all connections in a request using model's validate_connection methods"""
    results = {}

    # Test Primary LLM if configured
    if request.custom_deployment and request.custom_deployment.primary_llm_config:
        try:
            result = await request.custom_deployment.primary_llm_config.validate_connection()
            results["primary_llm"] = result.model_dump()
        except Exception as e:
            results["primary_llm"] = {
                "success": False,
                "message": f"Primary LLM validation failed: {str(e)}",
                "response_time_ms": 0
            }

    # Test Secondary LLM if configured and not same as primary
    if (request.custom_deployment and
            request.custom_deployment.secondary_llm_config and
            not request.custom_deployment.secondary_llm_config.same_as_primary and
            request.custom_deployment.secondary_llm_config.llm_config):
        try:
            result = await request.custom_deployment.secondary_llm_config.llm_config.validate_connection()
            results["secondary_llm"] = result.model_dump()
        except Exception as e:
            results["secondary_llm"] = {
                "success": False,
                "message": f"Secondary LLM validation failed: {str(e)}",
                "response_time_ms": 0
            }

    # Test Embedding if configured
    if request.custom_deployment and request.custom_deployment.embedding_config:
        try:
            result = await request.custom_deployment.embedding_config.validate_connection()
            results["embedding"] = result.model_dump()
        except Exception as e:
            results["embedding"] = {
                "success": False,
                "message": f"Embedding validation failed: {str(e)}",
                "response_time_ms": 0
            }

    # Test MCP connections (observability systems)
    if request.mcp_connections:
        for system in request.mcp_connections.systems:
            system_name = f"mcp_{system.observability_system}"
            try:
                result = await system.validate_connection()
                results[system_name] = result.model_dump()
            except Exception as e:
                results[system_name] = {
                    "success": False,
                    "message": f"MCP {system.observability_system} validation failed: {str(e)}",
                    "response_time_ms": 0
                }

    # Test Diagnostic MCP Servers (skip if disabled)
    if request.diagnostic_mcp_servers and request.diagnostic_mcp_servers.servers:
        for server in request.diagnostic_mcp_servers.servers:
            server_name = f"diagnostic_mcp_{server.name}"

            # Skip test connection if server is disabled
            if not server.enabled:
                logger.info(f"Skipping test connection for disabled diagnostic MCP server: {server.name}")
                results[server_name] = {
                    "success": True,
                    "message": f"Diagnostic MCP {server.name} is disabled - skipped validation",
                    "response_time_ms": 0
                }
                continue

            try:
                result = await server.validate_connection()
                results[server_name] = result.model_dump()
            except Exception as e:
                results[server_name] = {
                    "success": False,
                    "message": f"Diagnostic MCP {server.name} validation failed: {str(e)}",
                    "response_time_ms": 0
                }

    # Test Code Triaging Agent
    if request.code_triaging_agent:
        try:
            result = await request.code_triaging_agent.validate_connection()
            results["code_triaging"] = result.model_dump()
        except Exception as e:
            results["code_triaging"] = {
                "success": False,
                "message": f"Code triaging validation failed: {str(e)}",
                "response_time_ms": 0
            }

    return results


def handle_validation_results(validation_results: dict) -> None:
    """Handle validation results and raise HTTPException if any connections failed"""
    failed_connections = [name for name, result in validation_results.items(
    ) if not result.get("success", False)]

    if failed_connections:
        logger.warning(
            f"Connection validation failed for: {failed_connections}")
        error_details = []
        for conn_name in failed_connections:
            error_details.append(
                f"{conn_name}: {validation_results[conn_name]['message']}")

        raise HTTPException(
            status_code=422,
            detail={
                "message": "Connection validation failed. Please check your configuration.",
                "failed_connections": failed_connections,
                "validation_results": validation_results,
                "details": error_details
            }
        )


router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("")
async def get_config(
        session: AsyncSession = Depends(get_db_session),
        current_user: str = Depends(get_current_user)
) -> SetupConfigRequestOrResponse:
    """
    Get current application configuration.
    Returns the latest configuration from the database.
    """
    logger.info("get_config function called")
    try:
        # Get the latest configuration (assuming single config row)
        stmt = select(AppConfig).order_by(AppConfig.id.desc()).limit(1)
        result = await session.execute(stmt)
        config = result.scalar_one_or_none()

        if not config:
            # Return default configuration with full structure and empty values
            logger.info(
                "No config found, returning default configuration with full structure")
            return create_default_setup_response()

        # Prepare default values
        alert_triage_config = {
            "enabled_severities": config.enabled_severities or []
        }

        # Prepare MCP connections
        mcp_connections = config.mcp_connections or {"systems": []}

        # Prepare code triaging agent
        code_triaging_agent = {
            "enabled": config.code_triaging_agent_enabled or False,
            **(config.code_triaging_agent_config or {})
        }

        # Prepare custom deployment
        custom_deployment = None
        if config.primary_llm_provider and config.embedding_provider:
            custom_deployment = {
                "primary_llm_config": {
                    "llm_type": config.primary_llm_provider,
                    **(config.primary_llm_connection_config or {})
                },
                "embedding_config": {
                    "embedding_type": config.embedding_provider,
                    **(config.embedding_connection_config or {})
                }
            }

            # Add secondary LLM config if configured
            if config.secondary_llm_provider and config.secondary_llm_connection_config:
                secondary_config = config.secondary_llm_connection_config

                # Check same_as_primary flag value
                if secondary_config.get("same_as_primary") is True:
                    # Same as primary - only return the flag
                    custom_deployment["secondary_llm_config"] = {
                        "same_as_primary": True
                    }
                else:
                    # Custom config - return flag and config (excluding the flag from llm_config)
                    llm_config = {k: v for k, v in secondary_config.items() if k != "same_as_primary"}
                    custom_deployment["secondary_llm_config"] = {
                        "same_as_primary": False,
                        "llm_config": llm_config
                    }
            else:
                # Default to same as primary
                custom_deployment["secondary_llm_config"] = {
                    "same_as_primary": True,
                    "llm_config": None
                }

        # Parse diagnostic MCP servers from database
        from src.server.models.api.app_config import DiagnosticMcpServers, ExternalRunbookConfig
        diagnostic_mcp_servers = DiagnosticMcpServers()
        if config.diagnostic_mcp_servers:
            diagnostic_mcp_servers = DiagnosticMcpServers(**config.diagnostic_mcp_servers)

        # Parse external runbook config from database
        external_runbook_config = None
        if config.external_runbook_config:
            external_runbook_config = ExternalRunbookConfig(**config.external_runbook_config)

        # Parse alert grouping config from database
        alert_grouping_config = AlertGroupingConfig()  # Default
        if config.alert_grouping_config:
            alert_grouping_config = AlertGroupingConfig(**config.alert_grouping_config)

        response_data = {
            "alert_triage_config": alert_triage_config,
            "deployment": DeploymentType.CUSTOM,
            "custom_deployment": custom_deployment,
            "mcp_connections": mcp_connections,
            "diagnostic_mcp_servers": diagnostic_mcp_servers,
            "external_runbook_config": external_runbook_config,
            "code_triaging_agent": code_triaging_agent,
            "alert_grouping_config": alert_grouping_config,
            "chaos_system_enabled": config.chaos_system_enabled,
            "orchestrator_agents": config.orchestrator_agents or 1,
            "automatic_triage": config.automatic_triage,
            "alert_grouping_enabled": getattr(config, 'alert_grouping_enabled', True),
            "default_config": False  # Explicitly set to False for existing config
        }

        return SetupConfigRequestOrResponse(**response_data)

    except HTTPException:
        raise

    except Exception:
        logger.exception("Error in get_config")
        return create_default_setup_response()


@router.post("")
async def create_config(
        request: SetupConfigRequestOrResponse,
        current_user: str = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)
) -> ConfigOperationResponse:
    """
    Create first application configuration.
    Only allows creation if no configuration exists.
    Requires authentication to ensure only authorized users can create system configuration.
    """
    logger.info(f"Creating config for user: {current_user}")

    # Check if configuration already exists
    stmt = select(AppConfig).limit(1)
    result = await session.execute(stmt)
    existing_config = result.scalar_one_or_none()

    if existing_config:
        raise HTTPException(
            status_code=409, detail="Configuration already exists. Use PUT to update.")

    # Validate all connections before saving using model's validate_connection methods
    logger.info(
        f"Validating connections before creating config for user: {current_user}")
    try:
        validation_results = await validate_all_connections_from_request(request)

        # Handle validation results (raises HTTPException if any failed)
        handle_validation_results(validation_results)

    except HTTPException as e:
        # Instead of re-raising and sending 500 status code, send 400 bad request with specific failure details
        logger.warning(
            f"Connection validation failed during config creation: {e.detail}")
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Configuration validation failed. Please check your connection settings.",
                "error_type": "validation_failed",
                "validation_details": e.detail if hasattr(e, 'detail') else str(e),
                "suggestion": "Verify that all service endpoints are accessible and credentials are correct."
            }
        )
    except asyncio.TimeoutError:
        logger.error("Connection validation timed out during config creation")
        raise HTTPException(
            status_code=408,
            detail={
                "message": "Connection validation timed out. Please check your network connectivity and try again.",
                "error_type": "validation_timeout",
                "suggestion": "Verify that all service endpoints are accessible and responding."
            }
        )
    except Exception as e:
        logger.error(
            f"Unexpected error during connection validation: {str(e)}")
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Connection validation failed due to an unexpected error. Please check your configuration and try again.",
                "error_type": "validation_error",
                "error_details": str(e),
                "suggestion": "Verify all connection parameters are correct and services are accessible."
            }
        )

    # All connections validated successfully, create the config
    (primary_llm_provider, primary_llm_connection_config,
     secondary_llm_provider, secondary_llm_connection_config,
     embedding_provider, embedding_connection_config) = extract_deployment_config(request)

    new_config = AppConfig()
    new_config.enabled_severities = request.alert_triage_config.enabled_severities
    new_config.primary_llm_provider = primary_llm_provider
    new_config.primary_llm_connection_config = primary_llm_connection_config
    new_config.secondary_llm_provider = secondary_llm_provider
    new_config.secondary_llm_connection_config = secondary_llm_connection_config
    new_config.embedding_provider = embedding_provider
    new_config.embedding_connection_config = embedding_connection_config
    new_config.mcp_connections = request.mcp_connections.model_dump() if hasattr(request.mcp_connections,
                                                                                 'model_dump') else request.mcp_connections
    new_config.diagnostic_mcp_servers = request.diagnostic_mcp_servers.model_dump() if hasattr(
        request.diagnostic_mcp_servers,
        'model_dump') else request.diagnostic_mcp_servers
    new_config.external_runbook_config = (
        request.external_runbook_config.model_dump(exclude_none=True)
        if request.external_runbook_config and hasattr(request.external_runbook_config, 'model_dump')
        else (request.external_runbook_config if hasattr(request, 'external_runbook_config') else {})
    )
    new_config.code_triaging_agent_enabled = request.code_triaging_agent.enabled
    new_config.code_triaging_agent_config = request.code_triaging_agent.model_dump(exclude={"enabled"})
    new_config.alert_grouping_config = request.alert_grouping_config.model_dump() if hasattr(
        request.alert_grouping_config, 'model_dump') else request.alert_grouping_config
    new_config.chaos_system_enabled = request.chaos_system_enabled
    new_config.orchestrator_agents = request.orchestrator_agents
    new_config.automatic_triage = request.automatic_triage
    new_config.alert_grouping_enabled = request.alert_grouping_enabled
    new_config.created_by = current_user

    try:
        session.add(new_config)
        await session.commit()

        # Clear all manager caches to force reinitialization with new config
        clear_all_manager_caches()

        logger.info(
            f"Configuration created successfully for user: {current_user} (all connections validated)")
        return ConfigOperationResponse(
            status="success",
            message="Configuration created successfully. All connections validated.",
            validation_results=validation_results
        )
    except Exception as e:
        logger.error(f"Error creating config: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        await session.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to create configuration: {str(e)}")


@router.put("")
async def update_config(
        request: SetupConfigRequestOrResponse,
        current_user: str = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)
) -> ConfigOperationResponse:
    """
    Update application configuration.
    Updates the existing configuration. Returns 404 if no configuration exists.
    Use POST to create a new configuration.
    Requires authentication to ensure only authorized users can modify system configuration.
    """
    logger.info(f"Updating config for user: {current_user}")

    try:
        # Get existing configuration
        stmt = select(AppConfig).order_by(AppConfig.id.desc()).limit(1)
        result = await session.execute(stmt)
        config = result.scalar_one_or_none()

        if not config:
            # Return 404 if no configuration exists - use POST to create new config
            raise HTTPException(
                status_code=404,
                detail={
                    "message": "No configuration found to update. Use POST /config to create a new configuration first.",
                    "error_type": "config_not_found",
                    "suggestion": "Create a configuration using POST /config before attempting to update it."
                }
            )

        # Validate all connections before updating using model's validate_connection methods
        logger.info(
            f"Validating connections before updating config for user: {current_user}")
        try:
            validation_results = await validate_all_connections_from_request(request)
            logger.info(
                f"Validation completed with results: {len(validation_results)} connections tested")

            # Handle validation results (raises HTTPException if any failed)
            handle_validation_results(validation_results)

        except HTTPException as e:
            # Instead of re-raising and sending 500 status code, send 400 bad request with specific failure details
            logger.warning(
                f"Connection validation failed during config update: {e.detail}")
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Configuration validation failed. Please check your connection settings.",
                    "error_type": "validation_failed",
                    "validation_details": e.detail if hasattr(e, 'detail') else str(e),
                    "suggestion": "Verify that all service endpoints are accessible and credentials are correct."
                }
            )
        except asyncio.TimeoutError:
            logger.error(
                "Connection validation timed out during config update")
            raise HTTPException(
                status_code=408,
                detail={
                    "message": "Connection validation timed out. Please check your network connectivity and try again.",
                    "error_type": "validation_timeout",
                    "suggestion": "Verify that all service endpoints are accessible and responding."
                }
            )
        except Exception as e:
            logger.error(
                f"Unexpected error during connection validation: {str(e)}")
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Connection validation failed due to an unexpected error. Please check your configuration and try again.",
                    "error_type": "validation_error",
                    "error_details": str(e),
                    "suggestion": "Verify all connection parameters are correct and services are accessible."
                }
            )

        # All connections validated successfully, update the config
        (primary_llm_provider, primary_llm_connection_config,
         secondary_llm_provider, secondary_llm_connection_config,
         embedding_provider, embedding_connection_config) = extract_deployment_config(request)

        config.enabled_severities = request.alert_triage_config.enabled_severities
        config.primary_llm_provider = primary_llm_provider
        config.primary_llm_connection_config = primary_llm_connection_config
        config.secondary_llm_provider = secondary_llm_provider
        config.secondary_llm_connection_config = secondary_llm_connection_config
        config.embedding_provider = embedding_provider
        config.embedding_connection_config = embedding_connection_config
        config.mcp_connections = request.mcp_connections.model_dump() \
            if hasattr(request.mcp_connections, 'model_dump') else request.mcp_connections
        config.diagnostic_mcp_servers = request.diagnostic_mcp_servers.model_dump() \
            if hasattr(request.diagnostic_mcp_servers, 'model_dump') else request.diagnostic_mcp_servers
        config.external_runbook_config = (
            request.external_runbook_config.model_dump(exclude_none=True)
            if request.external_runbook_config and hasattr(request.external_runbook_config, 'model_dump')
            else (request.external_runbook_config if hasattr(request, 'external_runbook_config') else {})
        )
        config.code_triaging_agent_enabled = request.code_triaging_agent.enabled
        config.code_triaging_agent_config = request.code_triaging_agent.model_dump(exclude={"enabled"})
        config.alert_grouping_config = request.alert_grouping_config.model_dump() \
            if hasattr(request.alert_grouping_config, 'model_dump') else request.alert_grouping_config
        config.chaos_system_enabled = request.chaos_system_enabled
        config.automatic_triage = request.automatic_triage
        config.alert_grouping_enabled = request.alert_grouping_enabled
        config.orchestrator_agents = request.orchestrator_agents

        await session.commit()

        # Clear all manager caches to force reinitialization with new config
        clear_all_manager_caches()

        logger.info(
            f"Configuration updated successfully for user: {current_user} (all connections validated)")

        return ConfigOperationResponse(
            status="success",
            message="Configuration updated successfully. All connections validated.",
            validation_results=validation_results
        )

    except HTTPException as e:
        # Instead of re-raising and sending 500 status code, send 400 bad request with specific failure details
        logger.warning(f"HTTP exception during config update: {e.detail}")
        await session.rollback()
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Configuration update failed. Please check your settings.",
                "error_type": "update_failed",
                "error_details": e.detail if hasattr(e, 'detail') else str(e),
                "suggestion": "Verify all configuration parameters and try again."
            }
        )
    except Exception as e:
        logger.error(f"Error updating config: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        await session.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to update configuration: {str(e)}")


@router.post("/test-connection")
async def test_connection(
        request: Request,
        current_user: str = Depends(get_current_user)
) -> ConnectionTestResponse:
    """
    Test a single connection using provided configuration (not database).

    Accepts ConnectionTestRequest which can be either:
    - Observability MCP connection test: Use GrafanaObservabilitySystem, JaegerObservabilitySystem, or OpenSearchObservabilitySystem structure
    - Generic MCP connection test: Use GenericMcpConnectionTestRequest (for testing any MCP server without specifying name/system)
    - Code Triaging Agent test: Use CodeTriagingAgent structure

    See models.api.connection_test for the exact request structures.
    """
    logger.info(f"Testing single connection for user: {current_user}")

    try:
        # Parse the raw JSON to determine the correct model type
        body = await request.json()
        logger.info(f"Received test connection request with fields: {list(body.keys())}")

        # Determine which model to use based on the presence of specific fields
        parsed_request = None

        # Check for observability system (has 'observability_system' field)
        if 'observability_system' in body:
            from pydantic import TypeAdapter
            from src.server.models.api.app_config import ObservabilitySystemUnion

            # Use TypeAdapter to validate Union types
            adapter = TypeAdapter(ObservabilitySystemUnion)
            parsed_request = adapter.validate_python(body)
            logger.info(f"Parsed as ObservabilitySystemUnion: {body.get('observability_system')}")

        # Check for generic MCP connection (has 'connection_config' but NOT 'base_url' or 'observability_system')
        elif 'connection_config' in body and 'base_url' not in body:
            from src.server.models.api.connection_test import GenericMcpConnectionTestRequest
            parsed_request = GenericMcpConnectionTestRequest.model_validate(body)
            logger.info("Parsed as GenericMcpConnectionTestRequest")

        # Check for code triaging agent (has 'base_url' field)
        elif 'base_url' in body:
            from src.server.models.api.app_config import CodeTriagingAgent
            parsed_request = CodeTriagingAgent.model_validate(body)
            logger.info("Parsed as CodeTriagingAgent")

        else:
            # Default to GenericMcpConnectionTestRequest if it has connection_config
            if 'connection_config' in body:
                from src.server.models.api.connection_test import GenericMcpConnectionTestRequest
                parsed_request = GenericMcpConnectionTestRequest.model_validate(body)
                logger.info("Parsed as GenericMcpConnectionTestRequest (default)")
            else:
                return ConnectionTestResponse(
                    success=False,
                    message="Invalid request: must include either 'observability_system', 'connection_config', or 'base_url' field",
                    response_time_ms=0
                )

        # Use the model's validate_connection method
        result = await parsed_request.validate_connection()
        return result

    except Exception as e:
        logger.error(f"Error testing connection: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")

        # Return ConnectionTestResponse for consistency
        return ConnectionTestResponse(
            success=False,
            message=f"Connection test failed: {str(e)}",
            response_time_ms=0
        )


# used for chaos_workflow.py
def get_chaos_max_workflow_time_minutes() -> int:
    """
    Reads chaos workflow max time threshold (in minutes) from environment variable.
    Returns an integer value, defaults to 30 if not set or invalid.
    """
    try:
        return int(os.getenv("CHAOS_MAX_WORKFLOW_TIME_MINUTES", 30))
    except ValueError:
        logger.warning(
            "Invalid CHAOS_MAX_WORKFLOW_TIME_MINUTES value in environment. Falling back to 30 minutes."
        )
        return 30


async def get_chaos_max_workflow_time_minutes_from_fault_ledger(
        fault_ledger_id: int,
        db: "AsyncSession"
) -> int:
    """
    Get max workflow time from FaultLedger's configured_duration if available,
    otherwise fall back to .env value.

    Converts configured_duration (in seconds) to minutes.

    Args:
        fault_ledger_id: ID of the FaultLedger entry
        db: Database session

    Returns:
        Max workflow time in minutes (from FaultLedger's duration or .env)
    """
    try:
        from sqlalchemy import select
        from src.server.models.db.fault_ledger import FaultLedger

        # Try to get the configured_duration from FaultLedger
        result = await db.execute(
            select(FaultLedger.configured_duration).where(FaultLedger.id == fault_ledger_id)
        )
        configured_duration_seconds = result.scalar()

        if configured_duration_seconds is not None:
            # Convert seconds to minutes
            max_time_minutes = int(configured_duration_seconds / 60)
            logger.info(
                f"Using max_workflow_time={max_time_minutes} minutes "
                f"(from FaultLedger id={fault_ledger_id} duration={configured_duration_seconds}s)"
            )
            return max_time_minutes
        else:
            logger.info(f"FaultLedger id={fault_ledger_id} not found, using .env value")
            return get_chaos_max_workflow_time_minutes()
    except Exception as e:
        logger.warning(
            f"Failed to get max_workflow_time from FaultLedger: {str(e)}. Using .env value."
        )
        return get_chaos_max_workflow_time_minutes()
