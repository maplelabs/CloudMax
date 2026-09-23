"""
Common test fixtures for API v1 tests.

This module sets up:
- A PostgreSQL test container (with pgvector)
- Async database engine and session
- FastAPI test client with dependency overrides
- Mock embedding manager
"""

import asyncio
import base64
import logging
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from testcontainers.postgres import PostgresContainer

from src.server.apis_v1.dependencies import get_db_session
from src.server.models.db import Base
from src.server.web import app

logging.basicConfig(level=logging.INFO)


# Async event loop (shared across tests)

@pytest.fixture(scope="session")
def event_loop():
    """Create a single asyncio event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# PostgreSQL container setup

@pytest.fixture(scope="session")
def postgres_container():
    """Start PostgreSQL container with pgvector extension enabled."""
    # Image: pgvector/pgvector:pg15 already includes the extension
    with PostgresContainer("pgvector/pgvector:pg15", driver="psycopg2") as postgres:
        yield postgres


# Async engine + schema setup

@pytest_asyncio.fixture
async def engine(postgres_container):
    """Create async SQLAlchemy engine using the test Postgres container."""
    sync_url = postgres_container.get_connection_url()

    # Convert psycopg2 sync URL to asyncpg format
    db_url = sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")

    print(f"Original URL: {sync_url}")
    print(f"Async URL: {db_url}")

    engine = create_async_engine(
        db_url,
        echo=True,
        future=True,
        # Match production connection pool settings for concurrent operations
        pool_size=20,
        max_overflow=30,
        pool_timeout=60,
        pool_recycle=3600,
        pool_pre_ping=True,
        pool_reset_on_return='commit',  # Essential for concurrent operations
        # Match production timeout settings
        connect_args={
            "command_timeout": 120,
            "server_settings": {
                "application_name": "sre_ops_test",
                "statement_timeout": "300000",
                "idle_in_transaction_session_timeout": "600000",
            }
        }
    )

    # Create tables and enable pgvector
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)

    yield engine

    # Dispose engine after tests
    await engine.dispose()


# Database session

@pytest_asyncio.fixture
async def db_session(engine):
    """Create a fresh database session for each test"""
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with async_session() as session:
        yield session
        await session.execute(text(
            "TRUNCATE TABLE fault_ledger_to_alerts, evaluations, triages, alerts, app_config, fault_ledger, runbooks RESTART IDENTITY CASCADE"))
        await session.commit()


# FastAPI test client with DB override

@pytest_asyncio.fixture
async def client(db_session):
    """Provide an async FastAPI test client using the test DB session."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db

    # Add optional basic auth header
    credentials = base64.b64encode(b"admin:sreAdmin@321&1").decode("ascii")
    headers = {"Authorization": f"Basic {credentials}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as ac:
        yield ac

    # Cleanup overrides
    app.dependency_overrides.clear()


# Mock authentication (bypass JWT or BasicAuth for tests)

@pytest_asyncio.fixture(autouse=True)
async def mock_auth(request):
    """Automatically bypass authentication for all tests except those testing auth."""
    from src.server.apis_v1 import dependencies

    # Skip authentication bypass for tests that specifically test authentication
    if "require_authentication" in request.node.name:
        yield
        return

    def fake_get_current_user():
        # Return a mock User object that matches the real function's return type
        from unittest.mock import MagicMock
        mock_user = MagicMock()
        mock_user.username = "test_user"
        mock_user.id = "test-user-id"
        mock_user.admin = False
        return mock_user

    # Apply override globally to FastAPI
    app.dependency_overrides[dependencies.get_current_user] = fake_get_current_user

    yield

    # Clean up overrides after test
    app.dependency_overrides.clear()


# Mock embedding manager

@pytest_asyncio.fixture
async def mock_embedding_manager():
    """Mock embedding manager to avoid real model/API calls."""
    mock_manager = MagicMock()
    mock_model = MagicMock()

    # Mock embedding responses
    mock_model.aembed_documents = AsyncMock(return_value=[[0.1] * 1536])
    mock_model.aembed_query = AsyncMock(return_value=[0.1] * 1536)
    mock_manager.get_embedding_model.return_value = mock_model

    async def mock_get_embedding_manager_async():
        return mock_manager

    with patch("src.server.apis_v1.runbooks.get_embedding_manager_async", side_effect=mock_get_embedding_manager_async):
        yield mock_manager
