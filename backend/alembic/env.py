import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

# Import Base and all models so Alembic can accurately auto-detect table metadata
from app.db.session import Base
from app.domain.models.models import (  # noqa: F401
    Patient,
    Visit,
    QueueEntry,
    DepartmentQueueCounter,
    DailyTokenCounter,
    Department,
    Staff,
    Appointment,
    Notification,
    AuditLog,
)
from app.core.config import settings

# This is the Alembic Config object, which provides access to values within the .ini file.
config = context.config

# Overwrite the URL in alembic.ini with the runtime environment configurations dynamically
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata for autogenerate support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine. Calls to
    context.execute() emit the SQL string to script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url, 
        target_metadata=target_metadata,
        literal_binds=True, 
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Helper sync context worker to handle the active transaction execution loop."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Creates an AsyncEngine and delegates transaction steps down to a synchronous runner context."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Handles creation of asynchronous event loops safely without colliding with active processes.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Delegate execution safely if an event loop thread pool is already running
        loop.create_task(run_async_migrations())
    else:
        asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
