"""Configuracion de Alembic.

Dos cosas que no vienen en el template y son necesarias en este proyecto:

1. La URL sale de `app.core.config.settings`, no de alembic.ini. Asi hay una sola
   fuente de verdad y no queda una credencial hardcodeada en un archivo versionado.

2. `render_item` ensena a --autogenerate a escribir el tipo `Vector` de pgvector.
   Sin esto, las migraciones generadas salen con el tipo mal y sin el import,
   y fallan al aplicarse.
"""

import asyncio
from logging.config import fileConfig
from typing import Any

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# app.models re-exporta TODOS los modelos. Si uno no llega hasta aca,
# --autogenerate no lo ve y genera un DROP de esa tabla.
import app.models  # noqa: F401
from alembic import context
from app.core.config import settings
from app.db.session import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def render_item(type_: str, obj: Any, autogen_context: Any) -> str | bool:
    """Hace que --autogenerate emita bien el tipo Vector de pgvector."""
    if type_ == "type" and obj.__class__.__module__.startswith("pgvector"):
        autogen_context.imports.add("import pgvector.sqlalchemy")
        return f"pgvector.sqlalchemy.Vector(dim={obj.dim})"
    return False  # el resto lo maneja Alembic


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_item=render_item,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_item=render_item,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
