"""
Main FastAPI application for SRE Alert Dashboard.
"""

import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.server.apis_v1.alerts import router as v1_alerts_router
from src.server.apis_v1.alert_groups import router as v1_alert_groups_router
# Scheduled jobs are now handled by the job-scheduler pod
from src.server.apis_v1.auth import router as v1_auth_router
from src.server.apis_v1.config import router as v1_config_router
from src.server.apis_v1.dependencies import db_engine, validate_async_connection
from src.server.apis_v1.fault_ledger import router as v1_fault_ledger
from src.server.apis_v1.knowledge_base import router as v1_knowledge_base_router
from src.server.apis_v1.runbooks import router as v1_runbooks_router
from src.server.apis_v1.stats import router as v1_stats_router
from src.server.apis_v1.users import router as v1_users_router
from src.server.apis_v1.webhooks import router as v1_webhooks_router

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO').upper()),
    format='%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s'
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting SRE Alert Dashboard API...")

    # Load environment variables
    load_dotenv()

    # Note: Runbook indexing is now handled automatically on startup
    logger.info("Runbook auto-indexing will be performed after database initialization")

    # Validate async database connection
    try:
        is_async = await validate_async_connection()
        if is_async:
            logger.info("Async PostgreSQL connection validated successfully")
        else:
            logger.warning("Database connection validation failed - may not be using async driver")
    except Exception:
        logger.exception(f"Database connection validation error")

    # Auto-configure mTLS for diagnostic MCP server if certificates exist
    try:
        from src.server.startup_mtls_config import configure_mtls_on_startup
        await configure_mtls_on_startup()
    except Exception as e:
        logger.warning(f"mTLS auto-configuration skipped: {e}")

    # Periodic job scheduling is now handled by the dedicated job-scheduler pod
    # No need to register jobs from web server instances
    logger.info("Web server started - periodic jobs handled by job-scheduler pod")

    ## DONOT USE moved to alembic migrations
    # Initialize DB tables
    # try:
    #     async with db_engine.begin() as conn:
    #         await conn.run_sync(Base.metadata.create_all)
    #     logger.info("Database tables initialized")
    # except Exception:
    #     logger.exception(f"Database initialization failed")

    yield

    # Shutdown
    logger.info("Shutting down SRE Alert Dashboard API...")

    # Shutdown Confluence ThreadPoolExecutor
    try:
        from src.server.services.confluence.constants import confluence_executor
        confluence_executor.shutdown(wait=True, cancel_futures=True)
        logger.info("Confluence ThreadPoolExecutor shutdown successfully")
    except Exception as e:
        logger.warning(f"Error shutting down Confluence executor: {e}")

    # Gracefully close database connections
    try:
        await db_engine.dispose()
        logger.info("Database connections closed successfully")
    except Exception as e:
        logger.warning(f"Error closing database connections: {e}")


# Create FastAPI application
app = FastAPI(
    title="SRE Alert Dashboard API",
    description="FastAPI backend for SRE Alert Dashboard with observability and triage capabilities",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint for health check."""
    return {
        "message": "SRE Alert Dashboard API",
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy"
    }


# Include new API routers from apis directory
app.include_router(v1_runbooks_router, prefix="/v1/runbooks", tags=["runbooks"])
app.include_router(v1_alerts_router, prefix="/v1/alerts", tags=["alerts"])
app.include_router(v1_alert_groups_router, prefix="/v1/alert-groups", tags=["alert-groups"])
app.include_router(v1_webhooks_router, prefix="/v1/webhooks", tags=["webhooks"])
app.include_router(v1_stats_router, prefix="/v1/stats", tags=["stats"])
app.include_router(v1_config_router, prefix="/v1/config", tags=["config"])
app.include_router(v1_knowledge_base_router, prefix="/v1/knowledge-base", tags=["knowledge-base"])
app.include_router(v1_auth_router, prefix="/v1/auth", tags=["auth"])
app.include_router(v1_users_router, prefix="/v1/users", tags=["users"])
app.include_router(v1_fault_ledger, prefix="/v1/fault-ledger", tags=["Fault Ledger"])

if __name__ == "__main__":
    uvicorn.run(
        "src.main:app", host="0.0.0.0", port=8000, reload=True, log_level="info"
    )
