"""
Tests for Configuration API endpoints.

Tests cover:
- GET /v1/config - Get current configuration
- POST /v1/config - Save configuration
- POST /v1/config/test-connection - Test individual connections
- Error handling and validation
"""

import logging
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.server.models.api import (
    ConnectionTestResponse
)
from src.server.models.db.app_config import AppConfig

pytestmark = pytest.mark.asyncio
logger = logging.getLogger(__name__)


# Test fixtures

@pytest_asyncio.fixture
async def sample_config_data(db_session):
    """Create sample configuration data for testing"""
    config_data = {
        "alert_triage_config": {
            "enabled_severities": ["P1", "P2"]
        },
        "deployment": "custom",
        "custom_deployment": {
            "primary_llm_config": {
                "llm_type": "azure-openai",
                "api_key": "test-api-key",
                "endpoint_url": "https://test.openai.azure.com/",
                "deployment_name": "gpt-4",
                "api_version": "2024-02-01",
                "price_usd_per_1k_ip_tokens": 0.01,
                "price_usd_per_1k_op_tokens": 0.03
            },
            "embedding_config": {
                "embedding_type": "azure-openai",
                "api_key": "test-embedding-key",
                "endpoint_url": "https://test-embedding.openai.azure.com/",
                "deployment_name": "text-embedding-ada-002",
                "api_version": "2024-02-01"
            }
        },
        "mcp_connections": {
            "systems": [
                {
                    "observability_system": "grafana",
                    "enabled": True,
                    "connection_config": {
                        "connection_type": "streamable-http",
                        "endpoint_url": "http://localhost:3000/mcp",
                        "http_headers": []
                    }
                }
            ]
        },
        "code_triaging_agent": {
            "enabled": False,
            "base_url": "",
            "api_key": "",
            "notes": "",
            "timeout_seconds": 30,
            "max_retries": 3
        },
        "orchestrator_agents": 5,
        "chaos_system_enabled": False
    }

    # Create AppConfig record using the new schema
    from src.server.models.api.enums import Severity, LlmProvider, EmbeddingProvider

    # Primary LLM configuration
    primary_llm_config = {
        "api_key": "test-api-key",
        "endpoint_url": "https://test.openai.azure.com/",
        "deployment_name": "gpt-4",
        "api_version": "2024-02-01",
        "price_usd_per_1k_ip_tokens": 0.01,
        "price_usd_per_1k_op_tokens": 0.03
    }

    # Embedding configuration
    embedding_config = {
        "api_key": "test-embedding-key",
        "endpoint_url": "https://test-embedding.openai.azure.com/",
        "deployment_name": "text-embedding-ada-002",
        "api_version": "2024-02-01"
    }

    # MCP connections
    mcp_connections = {
        "systems": [
            {
                "observability_system": "grafana",
                "enabled": True,
                "connection_config": {
                    "endpoint_url": "http://localhost:3000/mcp"
                }
            }
        ]
    }

    app_config = AppConfig(
        enabled_severities=[Severity.P1, Severity.P2],
        primary_llm_provider=LlmProvider.AZURE_OPENAI,
        primary_llm_connection_config=primary_llm_config,
        embedding_provider=EmbeddingProvider.AZURE_OPENAI,
        embedding_connection_config=embedding_config,
        mcp_connections=mcp_connections,
        code_triaging_agent_enabled=False,
        orchestrator_agents=1,
        chaos_system_enabled=False
    )

    db_session.add(app_config)
    await db_session.commit()
    await db_session.refresh(app_config)

    yield app_config

    # Cleanup: Delete the created config
    await db_session.delete(app_config)
    await db_session.commit()


# GET /v1/config tests

async def test_get_config_success(client, sample_config_data):
    """Test successful configuration retrieval"""
    response = await client.get("/v1/config")

    assert response.status_code == 200
    data = response.json()

    # Verify structure
    assert "alert_triage_config" in data
    assert "deployment" in data
    assert "custom_deployment" in data
    assert "mcp_connections" in data

    # Verify specific values
    assert data["deployment"] == "custom"
    assert data["alert_triage_config"]["enabled_severities"] == ["P1", "P2"]
    assert data["custom_deployment"]["primary_llm_config"]["deployment_name"] == "gpt-4"


async def test_get_config_no_data_returns_default(client):
    """Test getting config when no data exists returns default"""
    response = await client.get("/v1/config")

    assert response.status_code == 200
    data = response.json()

    # Should return default configuration
    assert data["deployment"] == "custom"
    assert data["alert_triage_config"]["enabled_severities"] == ["P1"]
    assert data["custom_deployment"]["primary_llm_config"]["api_key"] == ""


async def test_get_config_database_error(client):
    """Test getting config when database error occurs"""
    # Mock database to raise exception
    with patch.object(AsyncSession, 'execute') as mock_execute:
        mock_execute.side_effect = Exception("Database connection failed")

        response = await client.get("/v1/config")

    # Should return default config on error
    assert response.status_code == 200
    data = response.json()
    assert data["deployment"] == "custom"


# POST /v1/config tests

async def test_create_config_success(client):
    """Test successful configuration creation"""
    # Mock connection validation to return success
    with patch('src.server.apis_v1.config.validate_all_connections_from_request') as mock_validate:
        mock_validate.return_value = {
            "primary_llm": {"success": True, "message": "Connection successful", "response_time_ms": 100},
            "embedding": {"success": True, "message": "Connection successful", "response_time_ms": 100},
            "mcp_ObservabilitySystem.GRAFANA": {"success": True, "message": "Connection successful",
                                                "response_time_ms": 100},
            "code_triaging": {"success": True, "message": "Connection successful", "response_time_ms": 100}
        }

        config_data = {
            "alert_triage_config": {
                "enabled_severities": ["P1", "P2", "P3"]
            },
            "deployment": "custom",
            "custom_deployment": {
                "primary_llm_config": {
                    "llm_type": "azure-openai",
                    "api_key": "new-api-key",
                    "endpoint_url": "https://new.openai.azure.com/",
                    "deployment_name": "gpt-4-turbo",
                    "api_version": "2024-02-01",
                    "price_usd_per_1k_ip_tokens": 0.01,
                    "price_usd_per_1k_op_tokens": 0.03
                },
                "embedding_config": {
                    "embedding_type": "azure-openai",
                    "api_key": "new-embedding-key",
                    "endpoint_url": "https://new-embedding.openai.azure.com/",
                    "deployment_name": "text-embedding-3-large",
                    "api_version": "2024-02-01"
                }
            },
            "mcp_connections": {
                "systems": [
                    {
                        "observability_system": "grafana",
                        "enabled": True,
                        "connection_config": {
                            "connection_type": "streamable-http",
                            "endpoint_url": "http://grafana:3000/mcp",
                            "http_headers": []
                        }
                    }
                ]
            },
            "code_triaging_agent": {
                "enabled": False,
                "base_url": "",
                "api_key": "",
                "notes": "",
                "timeout_seconds": 30,
                "max_retries": 3
            },
            "orchestrator_agents": 5,
            "chaos_system_enabled": False
        }

        response = await client.post("/v1/config", json=config_data)

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        assert "Configuration created successfully" in data["message"]


async def test_create_config_update_existing(client, sample_config_data):
    """Test updating existing configuration"""
    # Mock connection validation to return success
    with patch('src.server.apis_v1.config.validate_all_connections_from_request') as mock_validate:
        mock_validate.return_value = {
            "primary_llm": {"success": True, "message": "Connection successful", "response_time_ms": 100},
            "embedding": {"success": True, "message": "Connection successful", "response_time_ms": 100},
            "mcp_ObservabilitySystem.GRAFANA": {"success": True, "message": "Connection successful",
                                                "response_time_ms": 100},
            "code_triaging": {"success": True, "message": "Connection successful", "response_time_ms": 100}
        }

        updated_config = {
            "alert_triage_config": {
                "enabled_severities": ["P1"]  # Changed from P1, P2
            },
            "deployment": "custom",
            "custom_deployment": {
                "primary_llm_config": {
                    "llm_type": "azure-openai",
                    "api_key": "updated-api-key",  # Changed
                    "endpoint_url": "https://updated.openai.azure.com/",  # Changed
                    "deployment_name": "gpt-4",
                    "api_version": "2024-02-01",
                    "price_usd_per_1k_ip_tokens": 0.01,
                    "price_usd_per_1k_op_tokens": 0.03
                },
                "embedding_config": {
                    "embedding_type": "azure-openai",
                    "api_key": "test-embedding-key",
                    "endpoint_url": "https://test-embedding.openai.azure.com/",
                    "deployment_name": "text-embedding-ada-002",
                    "api_version": "2024-02-01"
                }
            },
            "mcp_connections": {
                "systems": [
                    {
                        "observability_system": "grafana",
                        "enabled": True,
                        "connection_config": {
                            "connection_type": "streamable-http",
                            "endpoint_url": "http://updated-grafana:3000/mcp",
                            "http_headers": []
                        }
                    }
                ]
            },
            "code_triaging_agent": {
                "enabled": False,
                "base_url": "http://code-triage-agent:8002",
                "timeout_seconds": 180,
                "max_retries": 3
            },
            "orchestrator_agents": 3,
            "chaos_system_enabled": False
        }

        response = await client.put("/v1/config", json=updated_config)

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        assert "Configuration updated successfully" in data["message"]


async def test_create_config_invalid_data(client):
    """Test creating config with invalid data"""
    invalid_config = {
        "deployment": "INVALID_TYPE",  # Invalid deployment type
        "alert_triage_config": {
            "enabled_severities": ["INVALID_SEVERITY"]  # Invalid severity
        }
    }

    response = await client.post("/v1/config", json=invalid_config)

    # Should return validation error
    assert response.status_code == 422


async def test_create_config_database_error(client):
    """Test creating config when database error occurs"""
    config_data = {
        "alert_triage_config": {
            "enabled_severities": ["P1"]
        },
        "deployment": "custom",
        "custom_deployment": {
            "primary_llm_config": {
                "llm_type": "azure-openai",
                "api_key": "test-api-key",
                "endpoint_url": "https://test.openai.azure.com/",
                "deployment_name": "gpt-4",
                "api_version": "2024-02-01",
                "price_usd_per_1k_ip_tokens": 0.01,
                "price_usd_per_1k_op_tokens": 0.03
            },
            "embedding_config": {
                "embedding_type": "azure-openai",
                "api_key": "test-embedding-key",
                "endpoint_url": "https://test-embedding.openai.azure.com/",
                "deployment_name": "text-embedding-ada-002",
                "api_version": "2024-02-01"
            }
        },
        "mcp_connections": {
            "systems": [
                {
                    "observability_system": "grafana",
                    "enabled": True,
                    "connection_config": {
                        "connection_type": "streamable-http",
                        "endpoint_url": "http://grafana:3000/mcp",
                        "http_headers": []
                    }
                }
            ]
        },
        "code_triaging_agent": {
            "enabled": False,
            "base_url": "http://code-triage-agent:8002",
            "timeout_seconds": 180,
            "max_retries": 3
        },
        "orchestrator_agents": 5,
        "chaos_system_enabled": False
    }

    # Mock connection validation to return success, then mock database to raise exception
    with patch('src.server.apis_v1.config.validate_all_connections_from_request') as mock_validate, \
            patch.object(AsyncSession, 'commit') as mock_commit:
        mock_validate.return_value = {
            "primary_llm": {"success": True, "message": "Connection successful", "response_time_ms": 100},
            "embedding": {"success": True, "message": "Connection successful", "response_time_ms": 100},
            "mcp_ObservabilitySystem.GRAFANA": {"success": True, "message": "Connection successful",
                                                "response_time_ms": 100},
            "code_triaging": {"success": True, "message": "Connection successful", "response_time_ms": 100}
        }
        mock_commit.side_effect = Exception("Database error")

        response = await client.post("/v1/config", json=config_data)

    assert response.status_code == 500
    assert "Failed to create configuration" in response.json()["detail"]


# POST /v1/config/test-connection tests

async def test_test_connection_mcp_grafana_success(client):
    """Test successful MCP Grafana connection test"""
    connection_request = {
        "observability_system": "grafana",
        "enabled": True,
        "connection_config": {
            "connection_type": "streamable-http",
            "endpoint_url": "http://localhost:3000/mcp",
            "http_headers": []
        }
    }

    # Mock the validation method to return success
    with patch('src.server.models.api.app_config.GrafanaObservabilitySystem.validate_connection') as mock_validate:
        mock_validate.return_value = ConnectionTestResponse(
            success=True,
            message="MCP Grafana connection successful",
            response_time_ms=150
        )

        response = await client.post("/v1/config/test-connection", json=connection_request)

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert "MCP Grafana connection successful" in data["message"]
    assert data["response_time_ms"] == 150


async def test_test_connection_mcp_grafana_failure(client):
    """Test failed MCP Grafana connection test"""
    connection_request = {
        "observability_system": "grafana",
        "enabled": True,
        "connection_config": {
            "connection_type": "streamable-http",
            "endpoint_url": "http://invalid-grafana:3000/mcp",
            "http_headers": []
        }
    }

    # Mock the validation method to return failure
    with patch('src.server.models.api.app_config.GrafanaObservabilitySystem.validate_connection') as mock_validate:
        mock_validate.return_value = ConnectionTestResponse(
            success=False,
            message="Connection failed: Host not reachable",
            response_time_ms=5000
        )

        response = await client.post("/v1/config/test-connection", json=connection_request)

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is False
    assert "Connection failed: Host not reachable" in data["message"]
    assert data["response_time_ms"] == 5000


async def test_test_connection_unsupported_type(client):
    """Test connection test with invalid request structure"""
    # Send a request that gets parsed as CodeTriagingAgent but fails validation
    connection_request = {
        "observability_system": "invalid_system",  # This field is ignored
        "enabled": True,  # This makes it parse as CodeTriagingAgent
        "connection_config": {  # This field is ignored
            "connection_type": "invalid_type",
            "endpoint_url": "http://localhost:3000/mcp",
            "http_headers": []
        }
        # Missing required base_url field for CodeTriagingAgent
    }

    response = await client.post("/v1/config/test-connection", json=connection_request)

    assert response.status_code == 200  # API handles gracefully
    data = response.json()
    assert data["success"] is False
    assert "base_url is required" in data["message"]


async def test_test_connection_validation_exception(client):
    """Test connection test when validation raises exception"""
    connection_request = {
        "observability_system": "grafana",
        "enabled": True,
        "connection_config": {
            "connection_type": "streamable-http",
            "endpoint_url": "http://localhost:3000/mcp",
            "http_headers": []
        }
    }

    # Mock the validation method to raise exception
    with patch('src.server.models.api.app_config.GrafanaObservabilitySystem.validate_connection') as mock_validate:
        mock_validate.side_effect = Exception("Network error")

        response = await client.post("/v1/config/test-connection", json=connection_request)

    assert response.status_code == 200  # API catches exceptions and returns them in response
    data = response.json()
    assert data["success"] is False
    assert "Connection test failed" in data["message"]


# Additional test cases for comprehensive coverage

async def test_test_connection_code_triaging_agent_success(client):
    """Test successful code triaging agent connection test"""
    connection_request = {
        "enabled": True,
        "base_url": "http://localhost:8080/api",
        "api_key": "test-api-key",
        "notes": "Test triaging agent",
        "timeout_seconds": 30,
        "max_retries": 3
    }

    # Mock the validation method to return success
    with patch('src.server.models.api.app_config.CodeTriagingAgent.validate_connection') as mock_validate:
        mock_validate.return_value = ConnectionTestResponse(
            success=True,
            message="Code triaging agent connection successful",
            response_time_ms=200
        )

        response = await client.post("/v1/config/test-connection", json=connection_request)

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert "Code triaging agent connection successful" in data["message"]


async def test_test_connection_code_triaging_agent_with_llm_config(client):
    """Test successful Code Triaging Agent connection test with LLM config"""
    connection_request = {
        "connection_type": "code_triaging_agent",
        "connection_config": {
            "enabled": True,
            "llm_config": {
                "llm_type": "azure-openai",
                "api_key": "test-key",
                "endpoint_url": "https://test.openai.azure.com/",
                "deployment_name": "gpt-4",
                "api_version": "2024-02-01"
            }
        }
    }

    # Mock Code Triaging Agent validation
    with patch('src.server.models.api.app_config.CodeTriagingAgent.validate_connection') as mock_validate:
        mock_validate.return_value = ConnectionTestResponse(
            success=True,
            message="Code Triaging Agent connection successful",
            response_time_ms=400
        )

        response = await client.post("/v1/config/test-connection", json=connection_request)

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert "Code Triaging Agent" in data["message"]


async def test_create_config_missing_required_fields(client):
    """Test creating config with missing required fields"""
    incomplete_config = {
        "deployment": "custom"
        # Missing alert_triage_config and custom_deployment
    }

    response = await client.post("/v1/config", json=incomplete_config)

    # Should return validation error
    assert response.status_code == 422


async def test_create_config_empty_llm_config(client):
    """Test creating config with empty LLM configuration"""
    # Mock connection validation to return success even with empty fields
    with patch('src.server.apis_v1.config.validate_all_connections_from_request') as mock_validate:
        mock_validate.return_value = {
            "primary_llm": {"success": True, "message": "Connection successful", "response_time_ms": 100},
            "embedding": {"success": True, "message": "Connection successful", "response_time_ms": 100},
            "code_triaging": {"success": True, "message": "Connection successful", "response_time_ms": 100}
        }

        config_with_empty_llm = {
            "alert_triage_config": {
                "enabled_severities": ["P1"]
            },
            "deployment": "custom",
            "custom_deployment": {
                "primary_llm_config": {
                    "llm_type": "azure-openai",
                    "api_key": "",  # Empty required field
                    "endpoint_url": "",  # Empty required field
                    "deployment_name": "",  # Empty required field
                    "api_version": "2024-02-01"
                },
                "embedding_config": {
                    "embedding_type": "azure-openai",
                    "api_key": "",
                    "endpoint_url": "",
                    "deployment_name": "",
                    "api_version": "2024-02-01"
                }
            },
            "mcp_connections": {
                "systems": []
            },
            "code_triaging_agent": {
                "enabled": False,
                "base_url": "",
                "api_key": "",
                "notes": "",
                "timeout_seconds": 30,
                "max_retries": 3
            },
            "orchestrator_agents": 5,
            "chaos_system_enabled": False
        }

        response = await client.post("/v1/config", json=config_with_empty_llm)

        # Should reject the config due to empty required fields
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data


async def test_get_config_with_cache_clearing(client, sample_config_data):
    """Test getting config after cache clearing"""
    # First request should populate cache
    response1 = await client.get("/v1/config")
    assert response1.status_code == 200

    # Mock cache clearing
    with patch('src.server.utilities.config.clear_all_manager_caches') as mock_clear:
        # Second request should still work
        response2 = await client.get("/v1/config")
        assert response2.status_code == 200

        # Verify cache clearing was called during config save
        # (This would happen in a real POST request)
        mock_clear.assert_not_called()  # GET doesn't clear cache


async def test_create_config_with_secondary_llm(client):
    """Test creating config with secondary LLM configuration"""
    # Mock connection validation to return success
    with patch('src.server.apis_v1.config.validate_all_connections_from_request') as mock_validate:
        mock_validate.return_value = {
            "primary_llm": {"success": True, "message": "Connection successful", "response_time_ms": 100},
            "secondary_llm": {"success": True, "message": "Connection successful", "response_time_ms": 100},
            "embedding": {"success": True, "message": "Connection successful", "response_time_ms": 100},
            "mcp_ObservabilitySystem.GRAFANA": {"success": True, "message": "Connection successful",
                                                "response_time_ms": 100},
            "code_triaging": {"success": True, "message": "Connection successful", "response_time_ms": 100}
        }

        config_with_secondary = {
            "alert_triage_config": {
                "enabled_severities": ["P1", "P2"]
            },
            "deployment": "custom",
            "custom_deployment": {
                "primary_llm_config": {
                    "llm_type": "azure-openai",
                    "api_key": "primary-key",
                    "endpoint_url": "https://primary.openai.azure.com/",
                    "deployment_name": "gpt-4",
                    "api_version": "2024-02-01",
                    "price_usd_per_1k_ip_tokens": 0.01,
                    "price_usd_per_1k_op_tokens": 0.03
                },
                "secondary_llm_config": {
                    "same_as_primary": False,
                    "llm_config": {
                        "llm_type": "azure-openai",
                        "api_key": "secondary-key",
                        "endpoint_url": "https://secondary.openai.azure.com/",
                        "deployment_name": "gpt-3.5-turbo",
                        "api_version": "2024-02-01",
                        "price_usd_per_1k_ip_tokens": 0.005,
                        "price_usd_per_1k_op_tokens": 0.015
                    }
                },
                "embedding_config": {
                    "embedding_type": "azure-openai",
                    "api_key": "embedding-key",
                    "endpoint_url": "https://embedding.openai.azure.com/",
                    "deployment_name": "text-embedding-ada-002",
                    "api_version": "2024-02-01"
                }
            },
            "mcp_connections": {
                "systems": [
                    {
                        "observability_system": "grafana",
                        "enabled": True,
                        "connection_config": {
                            "connection_type": "streamable-http",
                            "endpoint_url": "http://grafana:3000/mcp",
                            "http_headers": []
                        }
                    }
                ]
            },
            "code_triaging_agent": {
                "enabled": False,
                "base_url": "https://code-triage.example.com",
                "api_key": "test-code-triage-key",
                "notes": "Secondary LLM test",
                "timeout_seconds": 30,
                "max_retries": 3
            },
            "orchestrator_agents": 5,
            "chaos_system_enabled": False
        }

        response = await client.post("/v1/config", json=config_with_secondary)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"


async def test_create_config_with_multiple_mcp_systems(client):
    """Test creating config with multiple MCP systems"""
    # Mock connection validation to return success
    with patch('src.server.apis_v1.config.validate_all_connections_from_request') as mock_validate:
        mock_validate.return_value = {
            "primary_llm": {"success": True, "message": "Connection successful", "response_time_ms": 100},
            "embedding": {"success": True, "message": "Connection successful", "response_time_ms": 100},
            "mcp_ObservabilitySystem.GRAFANA": {"success": True, "message": "Connection successful",
                                                "response_time_ms": 100},
            "mcp_ObservabilitySystem.JAEGER": {"success": True, "message": "Connection successful",
                                               "response_time_ms": 100},
            "code_triaging": {"success": True, "message": "Connection successful", "response_time_ms": 100}
        }

        config_with_multiple_mcp = {
            "alert_triage_config": {
                "enabled_severities": ["P1"]
            },
            "deployment": "custom",
            "custom_deployment": {
                "primary_llm_config": {
                    "llm_type": "azure-openai",
                    "api_key": "test-key",
                    "endpoint_url": "https://test.openai.azure.com/",
                    "deployment_name": "gpt-4",
                    "api_version": "2024-02-01"
                },
                "embedding_config": {
                    "embedding_type": "azure-openai",
                    "api_key": "test-embedding-key",
                    "endpoint_url": "https://test-embedding.openai.azure.com/",
                    "deployment_name": "text-embedding-ada-002",
                    "api_version": "2024-02-01"
                }
            },
            "mcp_connections": {
                "systems": [
                    {
                        "observability_system": "grafana",
                        "enabled": True,
                        "connection_config": {
                            "connection_type": "streamable-http",
                            "endpoint_url": "http://grafana:3000/mcp",
                            "http_headers": []
                        }
                    },
                    {
                        "observability_system": "jaeger",
                        "enabled": False,
                        "connection_config": {
                            "connection_type": "streamable-http",
                            "endpoint_url": "http://jaeger:14268/mcp",
                            "http_headers": []
                        }
                    }
                ]
            },
            "code_triaging_agent": {
                "enabled": False,
                "base_url": "https://code-triage.example.com",
                "api_key": "test-code-triage-key",
                "notes": "Multiple MCP systems test",
                "timeout_seconds": 30,
                "max_retries": 3
            },
            "orchestrator_agents": 5,
            "chaos_system_enabled": False
        }

        response = await client.post("/v1/config", json=config_with_multiple_mcp)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"


async def test_test_connection_invalid_json(client):
    """Test connection test with invalid JSON in request"""
    # This would be handled by FastAPI validation before reaching our code
    response = await client.post("/v1/config/test-connection",
                                 data="invalid json",
                                 headers={"Content-Type": "application/json"})

    assert response.status_code == 422  # Unprocessable Entity


async def test_config_endpoints_require_authentication(client):
    """Test that config endpoints require authentication"""
    # Remove auth headers
    client.headers.pop("Authorization", None)

    # Test GET endpoint
    response = await client.get("/v1/config")
    assert response.status_code == 401

    # Test POST endpoint
    response = await client.post("/v1/config", json={"deployment": "custom"})
    assert response.status_code == 401

    # Test connection test endpoint
    response = await client.post("/v1/config/test-connection",
                                 json={"connection_type": "azure_openai"})
    assert response.status_code == 401
