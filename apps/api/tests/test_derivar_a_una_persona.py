"""Cuando el cliente final pide hablar con una persona.

Hasta ahora el bot decia "te derivo con alguien" y no pasaba nada: el campo
`escalate` existia en el contrato de la API y nunca se ponia en True. El
asistente prometia algo que el sistema no cumplia.

Lo que se defiende aca:

1. La marca del modelo NUNCA llega al chat del cliente final. Es lo unico de
   este mecanismo que quien escribe no tiene por que ver jamas.

2. Derivar CALLA al bot en esa conversacion, con vencimiento. Si el bot sigue
   contestando, le escribe encima a la persona que fue a atender.

3. La marca de "pidieron una persona" NO se limpia sola al vencer la pausa: el
   tiempo pasando no atiende a nadie. Se limpia cuando alguien reanuda el bot a
   mano, que es la forma de decir "ya lo atendi".

4. Una respuesta normal no deriva nada. Un falso positivo silencia al bot ocho
   horas en una conversacion que andaba bien.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm.client import Respuesta
from app.ai.prompts.base_system import MARCA_DERIVAR
from app.models.tenant import Conversation, Message, Tenant
from app.services import conversaciones
from app.services.conversation import (
    DERIVACION_SIN_TEXTO,
    answer,
    separar_derivacion,
)


@pytest_asyncio.fixture
async def tenant(db: AsyncSession) -> AsyncIterator[Tenant]:
    t = Tenant(slug=f"derivar-{uuid.uuid4().hex[:8]}", name="Negocio de prueba")
    db.add(t)
    await db.commit()
    await db.refresh(t)
    yield t
    await db.execute(delete(Tenant).where(Tenant.id == t.id))
    await db.commit()


def _modelo_que_responde(monkeypatch: pytest.MonkeyPatch, texto: str) -> None:
    """Reemplaza al LLM y al buscador: aca no se prueba ni uno ni otro."""

    async def falso_complete(system_blocks, messages, max_tokens=None):  # noqa: ANN001, ARG001
        return Respuesta(text=texto)

    async def falso_search(db, tenant_id, question):  # noqa: ANN001, ARG001
        return []

    monkeypatch.setattr("app.services.conversation.complete", falso_complete)
    monkeypatch.setattr("app.services.conversation.search", falso_search)


# --- La marca, sola ---


def test_la_marca_no_llega_al_cliente() -> None:
    texto, deriva = separar_derivacion(f"Te paso con alguien.\n{MARCA_DERIVAR}")
    assert texto == "Te paso con alguien."
    assert deriva is True


def test_la_marca_se_saca_este_donde_este() -> None:
    """El modelo no siempre la deja al final, y da igual: no se muestra."""
    texto, deriva = separar_derivacion(f"{MARCA_DERIVAR} Ahora te atienden.")
    assert MARCA_DERIVAR not in texto
    assert texto == "Ahora te atienden."
    assert deriva is True


def test_si_solo_manda_la_marca_igual_se_le_contesta_algo() -> None:
    """Un mensaje vacio deja a alguien que pidio ayuda mirando la pantalla."""
    texto, deriva = separar_derivacion(MARCA_DERIVAR)
    assert texto == DERIVACION_SIN_TEXTO
    assert deriva is True


def test_una_respuesta_normal_no_deriva() -> None:
    texto, deriva = separar_derivacion("Abrimos de 9 a 18.")
    assert texto == "Abrimos de 9 a 18."
    assert deriva is False


# --- El efecto sobre la conversacion ---


async def test_derivar_calla_al_bot_y_deja_la_marca(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    _modelo_que_responde(monkeypatch, f"Te derivo con una persona.\n{MARCA_DERIVAR}")

    texto, conversation_id, derivada = await answer(
        db, tenant, "quiero hablar con alguien", channel="webchat", external_id="sesion-1"
    )

    assert derivada is True
    assert MARCA_DERIVAR not in texto

    conversacion = await db.get(Conversation, conversation_id)
    assert conversacion is not None
    assert conversacion.derivada_at is not None
    assert conversacion.en_modo_manual()

    # Y lo que se guardo en el historial es lo mismo que se envio: sin la marca.
    guardado = await db.scalars(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.position)
    )
    assert all(MARCA_DERIVAR not in m.content for m in guardado.all())


async def test_una_respuesta_normal_no_pausa_nada(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ Un falso positivo silencia al bot ocho horas sin que nadie lo pida."""
    _modelo_que_responde(monkeypatch, "Abrimos de 9 a 18.")

    _texto, conversation_id, derivada = await answer(
        db, tenant, "que horario tienen?", channel="webchat", external_id="sesion-2"
    )

    assert derivada is False
    conversacion = await db.get(Conversation, conversation_id)
    assert conversacion is not None
    assert conversacion.derivada_at is None
    assert not conversacion.en_modo_manual()


async def test_la_marca_sobrevive_a_que_venza_la_pausa(db: AsyncSession, tenant: Tenant) -> None:
    """★ El tiempo pasando no atiende a nadie: sigue sin atenderse."""
    c = Conversation(
        tenant_id=tenant.id,
        channel="whatsapp",
        external_id="5491111111111",
        pausada_hasta=datetime.now(UTC) - timedelta(hours=1),
        derivada_at=datetime.now(UTC) - timedelta(hours=9),
    )
    db.add(c)
    await db.commit()

    filas = await conversaciones.listar(db, tenant.id, limite=10)
    fila = next(f for f in filas if f.id == str(c.id))

    assert fila.en_modo_manual is False  # la pausa ya vencio
    assert fila.derivada is True  # pero nadie la atendio
    assert fila.minutos_desde_derivacion is not None
    assert fila.minutos_desde_derivacion >= 540


async def test_reanudar_a_mano_da_la_derivacion_por_atendida(
    db: AsyncSession, tenant: Tenant
) -> None:
    c = Conversation(
        tenant_id=tenant.id,
        channel="whatsapp",
        external_id="5491122222222",
        pausada_hasta=datetime.now(UTC) + timedelta(hours=8),
        derivada_at=datetime.now(UTC),
    )
    db.add(c)
    await db.commit()

    fila = await conversaciones.reanudar(db, tenant.id, c.id)

    assert fila.derivada is False
    assert fila.en_modo_manual is False
