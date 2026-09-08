"""El resumen que ordena la pantalla principal del panel.

Lo que se defiende aca:

1. ★ NO SE MEZCLAN LOS CLIENTES. Es una consulta que agrupa a TODOS los
   negocios a la vez, sin ningun `WHERE tenant_id = ...` que la acote: es
   exactamente la forma de consulta donde un GROUP BY mal puesto le atribuye a
   un cliente las conversaciones del de al lado. Y falla en silencio, porque un
   numero equivocado se ve igual de bien que uno correcto.

2. ★ EL QUE ESPERA VA PRIMERO. Es el motivo entero de que este resumen exista.
   Si el orden se degrada a alfabetico, la pantalla vuelve a ser la lista de
   antes: hay que entrar cliente por cliente para saber a cual entrar.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Conversation, Message, Tenant
from app.services import resumen


@pytest_asyncio.fixture
async def negocios(db: AsyncSession) -> AsyncIterator[dict[str, Tenant]]:
    """Tres negocios con nombres elegidos para que el alfabeto NO de el orden.

    "Zapateria" es la que tiene gente esperando y "Almacen" no tiene nada: si
    el orden fuera alfabetico, la que pide accion quedaria ultima.
    """
    creados = {}
    for clave, nombre in [
        ("zapateria", "Zapatería del Centro"),
        ("almacen", "Almacén San Juan"),
        ("panaderia", "Panadería La Nueva"),
    ]:
        t = Tenant(slug=f"test-res-{clave}-{uuid.uuid4().hex[:8]}", name=nombre)
        db.add(t)
        creados[clave] = t
    await db.commit()
    for t in creados.values():
        await db.refresh(t)

    yield creados

    for t in creados.values():
        await db.execute(delete(Tenant).where(Tenant.id == t.id))
    await db.commit()


async def _conversacion(
    db: AsyncSession,
    tenant: Tenant,
    *,
    espera_hace_horas: float | None = None,
    activa_hace_minutos: int = 10,
    mensajes: int = 1,
) -> Conversation:
    ahora = datetime.now(UTC)
    c = Conversation(
        tenant_id=tenant.id,
        channel="whatsapp",
        external_id=f"54911{uuid.uuid4().hex[:8]}",
        last_activity_at=ahora - timedelta(minutes=activa_hace_minutos),
        derivada_at=(
            ahora - timedelta(hours=espera_hace_horas) if espera_hace_horas is not None else None
        ),
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)

    for i in range(mensajes):
        db.add(
            Message(
                conversation_id=c.id,
                position=i + 1,
                role="user",
                content=f"mensaje {i}",
            )
        )
    await db.commit()
    return c


def _por_id(resumenes: list[resumen.ResumenCliente], tenant: Tenant) -> resumen.ResumenCliente:
    return next(r for r in resumenes if r.id == tenant.id)


@pytest.mark.asyncio
async def test_cada_negocio_cuenta_solo_lo_suyo(
    db: AsyncSession, negocios: dict[str, Tenant]
) -> None:
    """★ El aislamiento, en la consulta que agrupa a todos a la vez."""
    await _conversacion(db, negocios["zapateria"], espera_hace_horas=3)
    await _conversacion(db, negocios["zapateria"], espera_hace_horas=1)
    await _conversacion(db, negocios["zapateria"])
    await _conversacion(db, negocios["panaderia"])

    todos = await resumen.por_cliente(db)

    zapateria = _por_id(todos, negocios["zapateria"])
    panaderia = _por_id(todos, negocios["panaderia"])
    almacen = _por_id(todos, negocios["almacen"])

    assert zapateria.esperando == 2
    assert zapateria.conversaciones == 3
    assert panaderia.esperando == 0, "la panaderia no tiene a nadie esperando"
    assert panaderia.conversaciones == 1
    assert almacen.conversaciones == 0, "el almacen no tiene ninguna conversacion"
    assert almacen.minutos_ultima_actividad is None


@pytest.mark.asyncio
async def test_el_que_tiene_gente_esperando_va_primero(
    db: AsyncSession, negocios: dict[str, Tenant]
) -> None:
    """★ El motivo de que este resumen exista.

    Sin esto la pantalla principal vuelve a ser una lista alfabetica donde hay
    que entrar cliente por cliente para saber a cual entrar.
    """
    await _conversacion(db, negocios["zapateria"], espera_hace_horas=3)
    await _conversacion(db, negocios["panaderia"])
    await _conversacion(db, negocios["almacen"])

    todos = await resumen.por_cliente(db)
    nuestros = [r for r in todos if r.id in {t.id for t in negocios.values()}]

    assert nuestros[0].id == negocios["zapateria"].id, (
        "el que tiene gente esperando tiene que ir primero, aunque su nombre empiece con Z"
    )
    # Entre los que no piden nada manda el nombre: es lo unico estable para
    # buscar con la vista.
    assert [r.name for r in nuestros[1:]] == ["Almacén San Juan", "Panadería La Nueva"]


@pytest.mark.asyncio
async def test_se_informa_hace_cuanto_espera_la_mas_vieja(
    db: AsyncSession, negocios: dict[str, Tenant]
) -> None:
    """Hace cuanto espera la mas vieja, que es lo que dice si esto es urgente."""
    await _conversacion(db, negocios["zapateria"], espera_hace_horas=3)
    await _conversacion(db, negocios["zapateria"], espera_hace_horas=1)

    zapateria = _por_id(await resumen.por_cliente(db), negocios["zapateria"])

    assert zapateria.minutos_de_la_mas_vieja is not None
    # La mas vieja, no la mas nueva ni el promedio.
    assert 175 <= zapateria.minutos_de_la_mas_vieja <= 185


@pytest.mark.asyncio
async def test_lo_viejo_no_cuenta_como_actividad_de_hoy(
    db: AsyncSession, negocios: dict[str, Tenant]
) -> None:
    """Activa es lo que sigue vivo hoy; mas viejo que eso ya es historial."""
    await _conversacion(db, negocios["panaderia"], activa_hace_minutos=30)
    await _conversacion(db, negocios["panaderia"], activa_hace_minutos=60 * 48)

    panaderia = _por_id(await resumen.por_cliente(db), negocios["panaderia"])

    assert panaderia.conversaciones == 2
    assert panaderia.conversaciones_activas == 1
