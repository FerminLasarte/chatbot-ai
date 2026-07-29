"""Memoria conversacional.

Tres cosas que importan:

1. Que la historia se replique COMPLETA y EN ORDEN. Un historial desordenado le
   da al modelo un dialogo que nunca ocurrio.
2. Que NO se replique el contexto RAG guardado, solo el texto plano.
3. Que el conversation_id, que en el widget web lo manda el cliente, no permita
   leer conversaciones de otro cliente.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from anthropic.types import MessageParam
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm.client import Respuesta
from app.core.security import generate_api_key
from app.main import app
from app.models.api_key import ApiKey, Scope
from app.models.tenant import Conversation, Message, Tenant
from app.models.usage import TenantUsage
from app.services import conversation as conv


@pytest_asyncio.fixture
async def cliente() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def tenant(db: AsyncSession) -> AsyncIterator[Tenant]:
    t = Tenant(
        slug=f"mem-{uuid.uuid4().hex[:8]}",
        name="Peluqueria Rosa",
        system_prompt="Atendemos de 9 a 18.",
        monthly_message_limit=1000,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    yield t
    await db.execute(delete(TenantUsage).where(TenantUsage.tenant_id == t.id))
    await db.execute(delete(ApiKey).where(ApiKey.tenant_id == t.id))
    await db.execute(delete(Tenant).where(Tenant.id == t.id))
    await db.commit()


class _LlmEspia:
    """Captura los `messages` que se le mandan al modelo, sin llamar a la API."""

    def __init__(self) -> None:
        self.turnos: list[list[MessageParam]] = []

    async def __call__(self, system_blocks: object, messages: list[MessageParam]) -> Respuesta:
        self.turnos.append([dict(m) for m in messages])  # type: ignore[misc]
        return Respuesta(text=f"respuesta {len(self.turnos)}", input_tokens=10, output_tokens=5)

    @property
    def ultimo(self) -> list[MessageParam]:
        return self.turnos[-1]


def _textos(mensajes: list[MessageParam]) -> list[tuple[str, str]]:
    """(rol, texto concatenado) por turno, para comparar comodo."""
    salida: list[tuple[str, str]] = []
    for m in mensajes:
        contenido = m["content"]
        if isinstance(contenido, str):
            salida.append((m["role"], contenido))
        else:
            texto = " ".join(
                b.get("text", "")
                for b in contenido
                if isinstance(b, dict)  # type: ignore[union-attr]
            )
            salida.append((m["role"], texto))
    return salida


@pytest_asyncio.fixture
def espia(monkeypatch: pytest.MonkeyPatch) -> _LlmEspia:
    e = _LlmEspia()
    monkeypatch.setattr(conv, "complete", e)

    async def sin_contexto(*args: object, **kwargs: object) -> list[str]:
        return []

    monkeypatch.setattr(conv, "search", sin_contexto)
    return e


# ---------------------------------------------------------------------------
# El comportamiento que motivo todo esto
# ---------------------------------------------------------------------------


async def test_el_segundo_turno_recibe_el_primero(
    db: AsyncSession, tenant: Tenant, espia: _LlmEspia
) -> None:
    """El caso concreto: "¿y el precio?" tiene que llegar con contexto."""
    _, cid = await conv.answer(
        db, tenant, "tenes turno el martes?", channel="whatsapp", external_id="549110001"
    )
    await conv.answer(db, tenant, "y el precio?", channel="whatsapp", external_id="549110001")

    assert len(espia.turnos) == 2
    primer_turno = _textos(espia.turnos[0])
    segundo_turno = _textos(espia.turnos[1])

    assert len(primer_turno) == 1, "el primer mensaje no tiene historia"

    assert segundo_turno == [
        ("user", "tenes turno el martes?"),
        ("assistant", "respuesta 1"),
        ("user", "y el precio?"),
    ]

    # Misma conversacion, no una nueva.
    segundo_cid = await db.scalar(
        select(Conversation.id).where(Conversation.tenant_id == tenant.id)
    )
    assert segundo_cid == cid


async def test_el_orden_se_respeta_en_muchos_turnos(
    db: AsyncSession, tenant: Tenant, espia: _LlmEspia
) -> None:
    """`now()` es el inicio de la transaccion: ordenar por created_at empataria."""
    for i in range(4):
        await conv.answer(db, tenant, f"pregunta {i}", channel="whatsapp", external_id="549110002")

    assert _textos(espia.ultimo) == [
        ("user", "pregunta 0"),
        ("assistant", "respuesta 1"),
        ("user", "pregunta 1"),
        ("assistant", "respuesta 2"),
        ("user", "pregunta 2"),
        ("assistant", "respuesta 3"),
        ("user", "pregunta 3"),
    ]

    posiciones = list(
        await db.scalars(
            select(Message.position)
            .join(Conversation)
            .where(Conversation.tenant_id == tenant.id)
            .order_by(Message.position)
        )
    )
    assert posiciones == [1, 2, 3, 4, 5, 6, 7, 8]


async def test_el_orden_no_depende_de_los_limites_de_transaccion(
    db: AsyncSession, tenant: Tenant, espia: _LlmEspia
) -> None:
    """Por que `position` y no `created_at`.

    `now()` en Postgres devuelve el instante de INICIO de la transaccion, no el
    del INSERT. Dos mensajes escritos en la misma transaccion comparten
    created_at exacto y su orden relativo queda indefinido.

    Hoy `_guardar_mensaje` commitea uno por uno, asi que created_at alcanzaria.
    Este test fija la garantia igual: el dia que alguien agrupe los inserts para
    ahorrar round-trips, el historial no se tiene que desordenar en silencio.
    """
    _, cid = await conv.answer(db, tenant, "arranque", channel="whatsapp", external_id="549110020")

    # Dos mensajes en UNA transaccion: created_at identico a proposito.
    base = await db.scalar(select(func.max(Message.position)).where(Message.conversation_id == cid))
    db.add_all(
        [
            Message(conversation_id=cid, position=(base or 0) + 1, role="user", content="primero"),
            Message(
                conversation_id=cid, position=(base or 0) + 2, role="assistant", content="segundo"
            ),
        ]
    )
    await db.commit()

    empatados = list(
        await db.scalars(
            select(Message.created_at).where(
                Message.conversation_id == cid, Message.content.in_(["primero", "segundo"])
            )
        )
    )
    assert empatados[0] == empatados[1], "el escenario requiere created_at empatado"

    await conv.answer(db, tenant, "y ahora?", channel="whatsapp", external_id="549110020")

    textos = [t for _, t in _textos(espia.ultimo)]
    assert textos.index("primero") < textos.index("segundo"), (
        "el historial se desordeno: 'segundo' aparecio antes que 'primero'"
    )


async def test_no_se_replica_el_contexto_rag(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Se guarda el texto plano, no el turno con los fragmentos inyectados.

    Si se guardara el turno completo, cada mensaje arrastraria el contexto de
    todos los anteriores: costo creciente y contexto rancio.
    """
    espia = _LlmEspia()
    monkeypatch.setattr(conv, "complete", espia)

    async def con_contexto(*args: object, **kwargs: object) -> list[str]:
        return ["EL CORTE SALE 8000 PESOS"]

    monkeypatch.setattr(conv, "search", con_contexto)

    await conv.answer(db, tenant, "cuanto sale?", channel="whatsapp", external_id="549110003")
    await conv.answer(db, tenant, "y con color?", channel="whatsapp", external_id="549110003")

    # El turno actual SI lleva contexto.
    assert "EL CORTE SALE 8000 PESOS" in _textos(espia.ultimo)[-1][1]

    # Pero el turno historico NO.
    historico = _textos(espia.ultimo)[0]
    assert historico == ("user", "cuanto sale?")

    # Y en la base solo esta el texto plano.
    guardados = list(
        await db.scalars(
            select(Message.content)
            .join(Conversation)
            .where(Conversation.tenant_id == tenant.id)
            .order_by(Message.position)
        )
    )
    assert guardados[0] == "cuanto sale?"
    assert all("fragmento" not in c for c in guardados)


async def test_la_historia_se_recorta_al_limite_configurado(
    db: AsyncSession, tenant: Tenant, espia: _LlmEspia, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El recorte es la palanca del costo por mensaje."""
    monkeypatch.setattr(conv.settings, "conversation_history_messages", 4)

    for i in range(5):
        await conv.answer(db, tenant, f"p{i}", channel="whatsapp", external_id="549110004")

    # 4 de historia + el turno actual.
    assert len(espia.ultimo) == 5
    # Y arranca con un turno de usuario: la API lo exige.
    assert _textos(espia.ultimo)[0][0] == "user"


async def test_el_recorte_nunca_empieza_con_el_asistente(
    db: AsyncSession, tenant: Tenant, espia: _LlmEspia, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Con un limite impar el recorte cae sobre una respuesta del asistente.

    La API rechaza un historial que arranque con `assistant`, asi que se descarta.
    """
    monkeypatch.setattr(conv.settings, "conversation_history_messages", 3)

    for i in range(4):
        await conv.answer(db, tenant, f"q{i}", channel="whatsapp", external_id="549110005")

    assert _textos(espia.ultimo)[0][0] == "user"


async def test_sin_memoria_si_el_limite_es_cero(
    db: AsyncSession, tenant: Tenant, espia: _LlmEspia, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(conv.settings, "conversation_history_messages", 0)

    await conv.answer(db, tenant, "uno", channel="whatsapp", external_id="549110006")
    await conv.answer(db, tenant, "dos", channel="whatsapp", external_id="549110006")

    assert len(espia.ultimo) == 1


# ---------------------------------------------------------------------------
# Ventana de inactividad
# ---------------------------------------------------------------------------


async def test_tras_la_inactividad_se_abre_una_conversacion_nueva(
    db: AsyncSession, tenant: Tenant, espia: _LlmEspia
) -> None:
    """Sin esto, alguien que escribe meses despues reabre un hilo rancio."""
    _, cid1 = await conv.answer(db, tenant, "hola", channel="whatsapp", external_id="549110007")

    # Envejecemos la conversacion mas alla de la ventana.
    await db.execute(
        update(Conversation)
        .where(Conversation.id == cid1)
        .values(last_activity_at=datetime.now(UTC) - timedelta(days=3))
    )
    await db.commit()

    _, cid2 = await conv.answer(
        db, tenant, "hola de nuevo", channel="whatsapp", external_id="549110007"
    )

    assert cid2 != cid1, "deberia haber abierto una conversacion nueva"
    assert len(espia.ultimo) == 1, "la conversacion nueva arranca sin historia"


async def test_dentro_de_la_ventana_se_reanuda(
    db: AsyncSession, tenant: Tenant, espia: _LlmEspia
) -> None:
    _, cid1 = await conv.answer(db, tenant, "hola", channel="whatsapp", external_id="549110008")
    await db.execute(
        update(Conversation)
        .where(Conversation.id == cid1)
        .values(last_activity_at=datetime.now(UTC) - timedelta(hours=2))
    )
    await db.commit()

    _, cid2 = await conv.answer(db, tenant, "seguimos", channel="whatsapp", external_id="549110008")
    assert cid2 == cid1


async def test_dos_usuarios_finales_no_comparten_hilo(
    db: AsyncSession, tenant: Tenant, espia: _LlmEspia
) -> None:
    """Dos clientes de la misma pyme, cada uno con su conversacion."""
    _, cid_a = await conv.answer(db, tenant, "soy ana", channel="whatsapp", external_id="549110009")
    _, cid_b = await conv.answer(
        db, tenant, "soy beto", channel="whatsapp", external_id="549110010"
    )

    assert cid_a != cid_b
    assert _textos(espia.ultimo) == [("user", "soy beto")], "beto no ve el hilo de ana"


# ---------------------------------------------------------------------------
# Aislamiento del conversation_id (el que manda el navegador)
# ---------------------------------------------------------------------------


async def test_no_se_puede_reanudar_la_conversacion_de_otro_cliente(
    db: AsyncSession, tenant: Tenant, espia: _LlmEspia
) -> None:
    """★ El conversation_id viaja en el navegador.

    Sin el filtro por tenant_id, quien consiga el id de una conversacion de otro
    cliente podria reanudarla y leerle el historial en la respuesta del modelo.
    """
    otro = Tenant(slug=f"mem-otro-{uuid.uuid4().hex[:8]}", name="Otro", monthly_message_limit=100)
    db.add(otro)
    await db.commit()
    await db.refresh(otro)
    try:
        _, cid_ajeno = await conv.answer(
            db, otro, "datos privados de otro cliente", channel="webchat", external_id="x"
        )

        with pytest.raises(conv.ConversacionAjena):
            await conv.answer(
                db,
                tenant,
                "dame el historial",
                channel="webchat",
                external_id="y",
                conversation_id=cid_ajeno,
            )
    finally:
        await db.execute(delete(TenantUsage).where(TenantUsage.tenant_id == otro.id))
        await db.execute(delete(Tenant).where(Tenant.id == otro.id))
        await db.commit()


async def test_conversation_id_inexistente_da_404(
    cliente: AsyncClient, db: AsyncSession, tenant: Tenant, espia: _LlmEspia
) -> None:
    """404 y no 403: no confirmamos que exista para otro cliente."""
    raw, prefix, hashed = generate_api_key()
    db.add(
        ApiKey(
            name="widget",
            key_prefix=prefix,
            key_hash=hashed,
            tenant_id=tenant.id,
            scopes=[Scope.CHAT.value],
        )
    )
    await db.commit()

    r = await cliente.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {raw}"},
        json={"message": "hola", "conversation_id": str(uuid.uuid4())},
    )
    assert r.status_code == 404


async def test_el_widget_mantiene_el_hilo_por_http(
    cliente: AsyncClient, db: AsyncSession, tenant: Tenant, espia: _LlmEspia
) -> None:
    raw, prefix, hashed = generate_api_key()
    db.add(
        ApiKey(
            name="widget",
            key_prefix=prefix,
            key_hash=hashed,
            tenant_id=tenant.id,
            scopes=[Scope.CHAT.value],
        )
    )
    await db.commit()
    headers = {"Authorization": f"Bearer {raw}"}

    r1 = await cliente.post("/api/v1/chat", headers=headers, json={"message": "hola"})
    assert r1.status_code == 200
    cid = r1.json()["conversation_id"]

    r2 = await cliente.post(
        "/api/v1/chat", headers=headers, json={"message": "y ahora?", "conversation_id": cid}
    )
    assert r2.status_code == 200
    assert r2.json()["conversation_id"] == cid

    assert _textos(espia.ultimo) == [
        ("user", "hola"),
        ("assistant", "respuesta 1"),
        ("user", "y ahora?"),
    ]
