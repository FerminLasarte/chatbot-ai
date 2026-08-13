"""Los mensajes que no se llegaron a contestar tienen que verse.

La tabla `processed_events` guardaba los fallos desde el principio, con indice
por estado incluido, pero nadie los leia: un bot roto era invisible hasta que el
cliente reclamaba. Estos tests cubren que ahora salgan, y sobre todo el caso que
no es obvio -el mensaje que quedo `pending` para siempre porque el contenedor se
reinicio en el medio-, que no es un "fallo" para nadie pero tampoco se contesto.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_api_key
from app.main import app
from app.models.api_key import ApiKey, Scope
from app.models.event import EventStatus, ProcessedEvent
from app.models.tenant import Tenant
from app.services import inbox


@pytest_asyncio.fixture
async def cliente() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def escenario(db: AsyncSession) -> AsyncIterator[dict]:
    sufijo = uuid.uuid4().hex[:8]
    t = Tenant(slug=f"inc-{sufijo}", name="Panaderia Lopez", system_prompt="")
    otro = Tenant(slug=f"inc-otro-{sufijo}", name="Ferreteria Diaz", system_prompt="")
    db.add_all([t, otro])
    await db.commit()
    await db.refresh(t)
    await db.refresh(otro)

    raw, prefix, hashed = generate_api_key()
    db.add(
        ApiKey(
            name="admin-inc",
            key_prefix=prefix,
            key_hash=hashed,
            tenant_id=None,
            scopes=[Scope.ADMIN.value],
        )
    )
    await db.commit()

    yield {"t": t, "otro": otro, "admin": raw, "sufijo": sufijo}

    for ev in (
        await db.scalars(
            select(ProcessedEvent).where(ProcessedEvent.tenant_id.in_([t.id, otro.id]))
        )
    ).all():
        await db.delete(ev)
    for x in (t, otro):
        actual = await db.get(Tenant, x.id)
        if actual is not None:
            await db.delete(actual)
    clave = await db.scalar(select(ApiKey).where(ApiKey.key_prefix == prefix))
    if clave is not None:
        await db.delete(clave)
    await db.commit()


def _auth(k: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {k}"}


async def _evento(
    db: AsyncSession, tenant_id: uuid.UUID, sufijo: str, status: str, *, hace_minutos: int = 0
) -> ProcessedEvent:
    ev = ProcessedEvent(
        channel="whatsapp",
        external_id=f"wamid.{uuid.uuid4().hex}-{sufijo}",
        tenant_id=tenant_id,
        status=status,
        attempts=1,
        error="Meta rechazo el envio (401)" if status == EventStatus.FAILED.value else None,
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    if hace_minutos:
        # created_at tiene server_default, asi que se corre despues de insertar.
        ev.created_at = datetime.now(UTC) - timedelta(minutes=hace_minutos)
        await db.commit()
    return ev


async def test_un_mensaje_fallado_aparece(
    cliente: AsyncClient, escenario: dict, db: AsyncSession
) -> None:
    t = escenario["t"]
    await _evento(db, t.id, escenario["sufijo"], EventStatus.FAILED.value)

    r = await cliente.get(f"/api/v1/incidents?tenant_id={t.id}", headers=_auth(escenario["admin"]))
    assert r.status_code == 200
    datos = r.json()
    assert len(datos) == 1
    assert datos[0]["status"] == "failed"
    assert "401" in datos[0]["error"]


async def test_un_pending_viejo_cuenta_como_incidente(
    cliente: AsyncClient, escenario: dict, db: AsyncSession
) -> None:
    """★ El caso que no salta a la vista. `BackgroundTasks` vive en el proceso:
    si el contenedor se reinicia despues del 200 a Meta, el mensaje queda
    `pending` para siempre. Nadie lo marco como fallo, pero no se contesto."""
    t = escenario["t"]
    await _evento(
        db,
        t.id,
        escenario["sufijo"],
        EventStatus.PENDING.value,
        hace_minutos=inbox.MINUTOS_PARA_DAR_POR_COLGADO + 5,
    )

    r = await cliente.get(f"/api/v1/incidents?tenant_id={t.id}", headers=_auth(escenario["admin"]))
    assert [d["status"] for d in r.json()] == ["pending"]


async def test_un_pending_recien_creado_no_es_incidente(
    cliente: AsyncClient, escenario: dict, db: AsyncSession
) -> None:
    """Si no, cada mensaje que esta procesandose ahora mismo daria alarma."""
    t = escenario["t"]
    await _evento(db, t.id, escenario["sufijo"], EventStatus.PENDING.value)

    r = await cliente.get(f"/api/v1/incidents?tenant_id={t.id}", headers=_auth(escenario["admin"]))
    assert r.json() == []


async def test_un_mensaje_contestado_no_es_incidente(
    cliente: AsyncClient, escenario: dict, db: AsyncSession
) -> None:
    t = escenario["t"]
    await _evento(db, t.id, escenario["sufijo"], EventStatus.DONE.value)

    r = await cliente.get(f"/api/v1/incidents?tenant_id={t.id}", headers=_auth(escenario["admin"]))
    assert r.json() == []


async def test_el_filtro_por_cliente_no_mezcla(
    cliente: AsyncClient, escenario: dict, db: AsyncSession
) -> None:
    """★ Sin esto, el panel de un cliente mostraria las fallas de otro."""
    t, otro = escenario["t"], escenario["otro"]
    await _evento(db, t.id, escenario["sufijo"], EventStatus.FAILED.value)
    await _evento(db, otro.id, escenario["sufijo"], EventStatus.FAILED.value)

    r = await cliente.get(f"/api/v1/incidents?tenant_id={t.id}", headers=_auth(escenario["admin"]))
    assert {d["tenant_id"] for d in r.json()} == {str(t.id)}


async def test_sin_filtro_trae_los_de_todos(
    cliente: AsyncClient, escenario: dict, db: AsyncSession
) -> None:
    """Es lo que necesita la lista del panel para marcar que cliente esta roto."""
    t, otro = escenario["t"], escenario["otro"]
    await _evento(db, t.id, escenario["sufijo"], EventStatus.FAILED.value)
    await _evento(db, otro.id, escenario["sufijo"], EventStatus.FAILED.value)

    r = await cliente.get("/api/v1/incidents", headers=_auth(escenario["admin"]))
    ids = {d["tenant_id"] for d in r.json()}
    assert {str(t.id), str(otro.id)} <= ids


async def test_ver_incidentes_exige_clave_admin(cliente: AsyncClient, escenario: dict) -> None:
    r = await cliente.get("/api/v1/incidents")
    assert r.status_code == 401
