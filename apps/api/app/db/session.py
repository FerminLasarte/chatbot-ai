"""Engine y sesion async de SQLAlchemy."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# El driver ya viene normalizado desde `settings` (ver el validador de
# database_url): aca la URL se usa tal cual.
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    # Verifica la conexion antes de usarla. En un hosting administrado el
    # proveedor corta las conexiones ociosas sin avisar, y sin esto la primera
    # peticion despues de un rato de silencio falla con "server closed the
    # connection unexpectedly".
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
