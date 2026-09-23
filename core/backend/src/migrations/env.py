import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Add the backend directory to sys.path so that 'src' becomes importable

current_dir = os.path.dirname(__file__)  # backend/src/migrations
backend_dir = os.path.abspath(os.path.join(current_dir, "..", ".."))  # backend/
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from src.server.models.db.base import Base

# Import all models to ensure they're registered with Base.metadata for Alembic
from src.server.models import db  # noqa: F401

# ALEMBIC CONFIG SETUP

config = context.config

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use the same Base.metadata used by all models
target_metadata = Base.metadata

# Database URL from environment variable or alembic.ini
database_url = os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)
else:
    print("⚠️  DATABASE_URL not set — using alembic.ini URL if available.")


# MIGRATION FUNCTIONS

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations asynchronously."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


print("Alembic sees models:", list(target_metadata.tables.keys()))

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
