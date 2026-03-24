"""Alembic environment configuration for Medical RAG migrations."""
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

# Alembic Config object provides access to the .ini values
config = context.config

# Interpret the config file for Python logging unless suppressed
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use DATABASE_URL from environment (overrides alembic.ini sqlalchemy.url)
_db_url = os.getenv("DATABASE_URL", "postgresql://localhost/medical_rag")
config.set_main_option("sqlalchemy.url", _db_url)

# We do not use SQLAlchemy ORM models — migrations are written as raw SQL.
# Set target_metadata = None for a "plain SQL" workflow.
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (emits SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations with a live DB connection."""
    engine = create_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
    )
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
