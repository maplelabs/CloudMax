"""
Common dependencies for FastAPI SRE Alert Dashboard.
"""
import logging
import os
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import text, event
from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                    create_async_engine)

from src.server.models.db.auth import User

load_dotenv()

logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://otelu:otelp@postgres:5432/sreops"
)

# Create async engine optimized for long-running triage processes
db_engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Disable SQL logging in production for performance
    future=True,
    # Connection pool settings optimized for long-running processes
    pool_size=20,  # Higher pool size for concurrent triage jobs
    max_overflow=30,  # Increased overflow for peak loads
    pool_timeout=60,  # Longer timeout for connection acquisition during high load
    pool_recycle=3600,  # Recycle connections after 1 hour
    pool_pre_ping=True,  # Essential for long-running processes
    pool_reset_on_return='commit',  # Clean state for each connection return
    # Asyncpg-specific optimizations for long-running queries
    connect_args={
        "command_timeout": 120,  # 2 minutes for individual commands
        "server_settings": {
            "application_name": "sre_ops_backend",
            "statement_timeout": "300000",  # 5 minutes for complex queries
            "idle_in_transaction_session_timeout": "600000",  # 10 minutes for long transactions
        }
    }
)


# Register pgvector types for asyncpg connections (following official documentation)
@event.listens_for(db_engine.sync_engine, "connect")
def connect(dbapi_connection, _):
    """Register pgvector types for each new connection."""
    try:
        # For asyncpg connections, we need to run the async registration
        from pgvector.asyncpg import register_vector

        # Use run_async with the connection parameter as per SQLAlchemy docs
        async def register_vectors():
            await register_vector(dbapi_connection)

        dbapi_connection.run_async(register_vectors)
        logger.debug("Registered pgvector types for new connection")
    except Exception as e:
        logger.warning(f"Failed to register pgvector types for connection: {e}")
        # Don't fail connection creation if vector registration fails


# Create async session factory
async_db_session = async_sessionmaker(db_engine, expire_on_commit=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function to get database session.
    Vector types are registered at connection level via event listener.
    """
    async with async_db_session() as session:
        yield session


async def validate_async_connection() -> bool:
    """
    Validate that the database connection is truly async.

    Returns:
        bool: True if connection is async, False otherwise
    """
    try:
        async with async_db_session() as session:
            # Test async connection by executing a simple query
            result = await session.execute(text("SELECT 1 as test"))
            test_value = result.scalar()

            # Verify we're using asyncpg driver
            connection_info = str(db_engine.url)
            is_asyncpg = "+asyncpg" in connection_info

            logger.info(
                f"Database connection validation: test_query={test_value}, asyncpg_driver={is_asyncpg}")
            return test_value == 1 and is_asyncpg

    except Exception as e:

        logger.exception(f"Async connection validation failed")
        return False


# Authentication setup

jwt_security = HTTPBearer(auto_error=False)


async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(jwt_security),
        db: AsyncSession = Depends(get_db_session),
        required: bool = True,
) -> User | None:
    """Return current user from JWT (or None if optional)."""
    from src.server.utilities.auth_utils import decode_token
    if not credentials:
        if required:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )
        return None

    token = credentials.credentials
    payload = decode_token(token)

    if not payload or payload.get("type") != "access":
        if required:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
        return None

    user = await db.get(User, int(payload["sub"]))
    if not user:
        if required:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        return None

    return user


async def get_optional_user(
        credentials: HTTPAuthorizationCredentials = Depends(jwt_security),
        db: AsyncSession = Depends(get_db_session),
) -> User | None:
    """Like get_current_user but optional."""
    return await get_current_user(credentials, db, required=False)


async def get_current_admin_user(
        current_user: User = Depends(get_current_user),
) -> User:
    """Ensure current user is admin."""
    if not current_user or not current_user.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user
