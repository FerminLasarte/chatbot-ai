"""Fixtures compartidas.

El engine async es un objeto de modulo y su pool de conexiones queda atado al
event loop en el que se creo. pytest-asyncio crea un loop nuevo por test, asi que
sin disponer el engine entre tests se reutilizan conexiones de un loop ya cerrado
y aparecen fallos intermitentes que no se reproducen corriendo el test solo.
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal, engine


@pytest_asyncio.fixture(autouse=True)
async def _limpiar_pool() -> AsyncIterator[None]:
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncSession]:
    """Sesion contra la base real. Saltea el test si Postgres no esta levantado."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Postgres no disponible ({type(exc).__name__}); levanta docker compose")

    async with SessionLocal() as session:
        yield session
