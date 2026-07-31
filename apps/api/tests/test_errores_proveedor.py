"""Un fallo de un proveedor externo tiene que salir como 503 JSON, no como 500.

Sin el handler de `RetryableHTTPError`, la excepcion sube sin manejar: FastAPI
responde 500 con cuerpo de texto plano y cualquier cliente que espere JSON
rompe al parsearlo -que es exactamente lo que tapaba el error real en el
frontend, mostrando "no se pudo conectar" cuando el servidor si habia
respondido.
"""

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.retry import RetryableHTTPError
from app.core.security import generate_api_key
from app.main import app
from app.models.api_key import ApiKey, Scope
from app.models.tenant import Tenant
from app.services import conversation as conversation_service


@pytest_asyncio.fixture
async def cliente() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def clave_chat(db: AsyncSession) -> AsyncIterator[str]:
    tenant = Tenant(slug=f"prov-{uuid.uuid4().hex[:8]}", name="Cliente", system_prompt="hola")
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)

    raw, prefix, hashed = generate_api_key()
    db.add(
        ApiKey(
            name="test-proveedor",
            key_prefix=prefix,
            key_hash=hashed,
            tenant_id=tenant.id,
            scopes=[Scope.TENANT.value],
        )
    )
    await db.commit()

    yield raw

    await db.execute(delete(ApiKey).where(ApiKey.key_prefix == prefix))
    await db.delete(tenant)
    await db.commit()


async def test_rate_limit_del_proveedor_devuelve_503_json(
    cliente: AsyncClient, clave_chat: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _explota(*args: object, **kwargs: object) -> list[str]:
        raise RetryableHTTPError("embeddings de Voyage fallo tras 4 intentos: 429")

    monkeypatch.setattr(conversation_service, "search", _explota)

    r = await cliente.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {clave_chat}"},
        json={"message": "hola"},
    )

    assert r.status_code == 503
    # Lo que importa: que el cuerpo sea JSON parseable. Si esto tira, el
    # cliente que hace res.json() vuelve a romper.
    assert "detail" in r.json()
