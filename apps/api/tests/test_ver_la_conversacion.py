"""El hilo completo de una conversacion, por las dos puertas.

Lo que se defiende aca:

1. El hilo sale del mas viejo al mas nuevo. Un historial dado vuelta le hace
   creer al duenio que el bot contesto antes de que le preguntaran.

2. Se distingue quien escribio cada respuesta del negocio: el bot o una persona
   desde el celular. Es TODO el punto de la vista: sin eso, el duenio audita al
   asistente leyendo sus propios mensajes.

3. Los mensajes anteriores a la columna `autor` se muestran sin atribuir. No se
   les inventa un autor.

4. ★ Una conversacion de otro cliente no se puede leer, ni con clave admin
   diciendo el tenant equivocado, ni con la clave del portal de otro negocio.
   Son mensajes de los clientes finales de una PyME: el aislamiento es el
   requisito, no una comodidad.

5. En una conversacion mas larga que el limite se devuelven los ULTIMOS
   mensajes, que es lo que alguien quiere ver al abrir un hilo.
"""

import uuid
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_api_key
from app.main import app
from app.models.api_key import ApiKey, Scope
from app.models.tenant import Conversation, Tenant
from app.services.conversation import (
    AUTOR_BOT,
    AUTOR_PERSONA,
    ROL_ASISTENTE,
    ROL_USUARIO,
    _guardar_mensaje,
)

NUMERO = "5491133344455"


@pytest_asyncio.fixture
async def cliente() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def escenario(db: AsyncSession) -> AsyncIterator[dict]:
    """Dos negocios distintos, cada uno con su conversacion y su clave."""
    a = Tenant(slug=f"hilo-a-{uuid.uuid4().hex[:8]}", name="Negocio A")
    b = Tenant(slug=f"hilo-b-{uuid.uuid4().hex[:8]}", name="Negocio B")
    db.add_all([a, b])
    await db.commit()
    await db.refresh(a)
    await db.refresh(b)

    conv_a = Conversation(tenant_id=a.id, channel="whatsapp", external_id=NUMERO)
    conv_b = Conversation(tenant_id=b.id, channel="whatsapp", external_id=NUMERO)
    db.add_all([conv_a, conv_b])
    await db.commit()
    await db.refresh(conv_a)
    await db.refresh(conv_b)

    claves: dict[str, str] = {}
    prefijos: list[str] = []
    for nombre, tenant_id, scope in [
        ("admin", None, Scope.ADMIN.value),
        ("portal-a", a.id, Scope.CLIENT_PORTAL.value),
        ("portal-b", b.id, Scope.CLIENT_PORTAL.value),
    ]:
        raw, prefix, hashed = generate_api_key()
        db.add(
            ApiKey(
                name=f"{nombre}-hilo",
                key_prefix=prefix,
                key_hash=hashed,
                tenant_id=tenant_id,
                scopes=[scope],
            )
        )
        claves[nombre] = raw
        prefijos.append(prefix)
    await db.commit()

    yield {"a": a, "b": b, "conv_a": conv_a, "conv_b": conv_b, **claves}

    for prefix in prefijos:
        await db.execute(delete(ApiKey).where(ApiKey.key_prefix == prefix))
    await db.execute(delete(Tenant).where(Tenant.id.in_([a.id, b.id])))
    await db.commit()


def _auth(k: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {k}"}


async def _hilo_de_ejemplo(db: AsyncSession, conversacion: Conversation) -> None:
    """Un cliente pregunta, contesta el bot, y despues contesta una persona."""
    await _guardar_mensaje(db, conversacion.id, ROL_USUARIO, "hola, que horario tienen?")
    await _guardar_mensaje(db, conversacion.id, ROL_ASISTENTE, "Abrimos de 9 a 18.", AUTOR_BOT)
    await _guardar_mensaje(db, conversacion.id, ROL_USUARIO, "hacen envios?")
    await _guardar_mensaje(
        db, conversacion.id, ROL_ASISTENTE, "Si, te lo mando hoy mismo.", AUTOR_PERSONA
    )
    await db.commit()


async def test_el_portal_devuelve_el_hilo_en_orden_y_con_autor(
    cliente: AsyncClient, escenario: dict, db: AsyncSession
) -> None:
    await _hilo_de_ejemplo(db, escenario["conv_a"])

    r = await cliente.get(
        f"/api/v1/portal/conversations/{escenario['conv_a'].id}/messages",
        headers=_auth(escenario["portal-a"]),
    )
    assert r.status_code == 200
    hilo = r.json()

    assert [m["content"] for m in hilo] == [
        "hola, que horario tienen?",
        "Abrimos de 9 a 18.",
        "hacen envios?",
        "Si, te lo mando hoy mismo.",
    ]
    assert [(m["role"], m["autor"]) for m in hilo] == [
        ("user", None),
        ("assistant", "bot"),
        ("user", None),
        ("assistant", "persona"),
    ]


async def test_un_mensaje_viejo_no_se_muestra_atribuido(
    cliente: AsyncClient, escenario: dict, db: AsyncSession
) -> None:
    """Los que se guardaron antes de la columna `autor` quedan en None."""
    await _guardar_mensaje(db, escenario["conv_a"].id, ROL_ASISTENTE, "de antes")
    await db.commit()

    r = await cliente.get(
        f"/api/v1/portal/conversations/{escenario['conv_a'].id}/messages",
        headers=_auth(escenario["portal-a"]),
    )
    assert r.json()[0]["autor"] is None


async def test_la_agencia_ve_el_mismo_hilo(
    cliente: AsyncClient, escenario: dict, db: AsyncSession
) -> None:
    await _hilo_de_ejemplo(db, escenario["conv_a"])

    r = await cliente.get(
        f"/api/v1/tenants/{escenario['a'].id}/conversations/{escenario['conv_a'].id}/messages",
        headers=_auth(escenario["admin"]),
    )
    assert r.status_code == 200
    assert len(r.json()) == 4


async def test_el_portal_de_un_negocio_no_lee_el_hilo_de_otro(
    cliente: AsyncClient, escenario: dict, db: AsyncSession
) -> None:
    """★ Con el id de la conversacion ajena en la mano, igual no."""
    await _hilo_de_ejemplo(db, escenario["conv_b"])

    r = await cliente.get(
        f"/api/v1/portal/conversations/{escenario['conv_b'].id}/messages",
        headers=_auth(escenario["portal-a"]),
    )
    assert r.status_code == 404


async def test_la_agencia_no_puede_leer_un_hilo_diciendo_el_cliente_equivocado(
    cliente: AsyncClient, escenario: dict, db: AsyncSession
) -> None:
    """★ La clave admin puede nombrar a cualquier cliente: el par
    tenant/conversacion tiene que coincidir igual."""
    await _hilo_de_ejemplo(db, escenario["conv_b"])

    r = await cliente.get(
        f"/api/v1/tenants/{escenario['a'].id}/conversations/{escenario['conv_b'].id}/messages",
        headers=_auth(escenario["admin"]),
    )
    assert r.status_code == 404


async def test_sin_clave_no_se_lee_nada(cliente: AsyncClient, escenario: dict) -> None:
    r = await cliente.get(f"/api/v1/portal/conversations/{escenario['conv_a'].id}/messages")
    assert r.status_code == 401


async def test_un_hilo_largo_devuelve_los_ultimos_mensajes(
    cliente: AsyncClient, escenario: dict, db: AsyncSession
) -> None:
    for i in range(10):
        await _guardar_mensaje(db, escenario["conv_a"].id, ROL_USUARIO, f"mensaje {i}")
    await db.commit()

    r = await cliente.get(
        f"/api/v1/portal/conversations/{escenario['conv_a'].id}/messages?limite=3",
        headers=_auth(escenario["portal-a"]),
    )
    # Los ultimos tres, y en orden: no los tres primeros ni los tres al reves.
    assert [m["content"] for m in r.json()] == ["mensaje 7", "mensaje 8", "mensaje 9"]
