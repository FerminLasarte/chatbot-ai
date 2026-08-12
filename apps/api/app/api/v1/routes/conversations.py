"""Conversaciones de un cliente y modo manual.

El modo manual resuelve un caso concreto: alguien del equipo entra a la bandeja
de Meta Business Suite a contestarle a mano a un cliente puntual, y necesita que
el bot se calle mientras tanto para no pisarle la respuesta.

DOS DECISIONES QUE VALE LA PENA CONOCER
---------------------------------------
1. La pausa VENCE (ver `Conversation.pausada_hasta`). No hay pausa indefinida:
   un interruptor olvidado deja a un cliente sin respuestas automaticas para
   siempre, en silencio.

2. La pausa es POR CONVERSACION, no por cliente. Callar al bot entero para
   atender a una sola persona es un remedio peor que la enfermedad.

Todo esto es para la agencia (clave admin): el cliente no administra sus propias
conversaciones desde la API.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import AdminKey, DbSession
from app.core.config import settings
from app.models.tenant import Conversation, Message, Tenant
from app.schemas.chat import ConversationRead, ManualModeStart

router = APIRouter(prefix="/tenants/{tenant_id}/conversations", tags=["conversations"])

# Largo del adelanto del ultimo mensaje. Alcanza para reconocer de que se venia
# hablando; el resto seria volcar la conversacion entera en una lista.
LARGO_ADELANTO = 140


async def _tenant_o_404(db: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cliente no encontrado")
    return tenant


async def _conversacion_o_404(
    db: AsyncSession, tenant_id: uuid.UUID, conversation_id: uuid.UUID
) -> Conversation:
    """★ El filtro por tenant_id NO es opcional.

    Sin el, el id de una conversacion de otro cliente entraria por aca y se
    podria pausar -o leer el ultimo mensaje de- un hilo ajeno.
    """
    conversacion = await db.get(Conversation, conversation_id)
    if conversacion is None or conversacion.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conversacion no encontrada")
    return conversacion


def _adelanto(texto: str | None) -> str | None:
    if texto is None:
        return None
    limpio = " ".join(texto.split())
    if len(limpio) <= LARGO_ADELANTO:
        return limpio
    return limpio[:LARGO_ADELANTO] + "…"


def _minutos(desde: datetime, hasta: datetime) -> int:
    return max(0, int((hasta - desde).total_seconds() // 60))


def _to_read(c: Conversation, mensajes: int, ultimo: str | None) -> ConversationRead:
    # Un unico `ahora` para toda la fila: con dos lecturas del reloj, una fila
    # podria salir "en modo manual" con cero minutos restantes.
    ahora = datetime.now(UTC)
    manual = c.en_modo_manual(ahora)
    return ConversationRead(
        id=str(c.id),
        channel=c.channel,
        external_id=c.external_id,
        last_activity_at=c.last_activity_at,
        pausada_hasta=c.pausada_hasta,
        en_modo_manual=manual,
        minutos_inactiva=_minutos(c.last_activity_at, ahora),
        # Solo tiene sentido mientras la pausa siga viva.
        minutos_restantes=(
            _minutos(ahora, c.pausada_hasta) if manual and c.pausada_hasta else None
        ),
        mensajes=mensajes,
        ultimo_mensaje=_adelanto(ultimo),
    )


async def _detalle(db: AsyncSession, conversacion: Conversation) -> ConversationRead:
    """Recuenta una sola conversacion, para devolverla despues de tocarla."""
    mensajes = await db.scalar(
        select(func.count()).select_from(Message).where(Message.conversation_id == conversacion.id)
    )
    ultimo = await db.scalar(
        select(Message.content)
        .where(Message.conversation_id == conversacion.id)
        .order_by(Message.position.desc())
        .limit(1)
    )
    return _to_read(conversacion, mensajes or 0, ultimo)


@router.get("", response_model=list[ConversationRead])
async def list_conversations(
    tenant_id: uuid.UUID,
    db: DbSession,
    _: AdminKey,
    limite: int = Query(default=50, ge=1, le=200),
) -> list[ConversationRead]:
    """Las conversaciones mas recientes del cliente, la ultima primero."""
    await _tenant_o_404(db, tenant_id)

    filas = await db.execute(
        select(Conversation, func.count(Message.id))
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .where(Conversation.tenant_id == tenant_id)
        .group_by(Conversation.id)
        .order_by(Conversation.last_activity_at.desc())
        .limit(limite)
    )
    conversaciones = filas.all()
    if not conversaciones:
        return []

    # El ultimo mensaje de cada hilo en UNA consulta (DISTINCT ON de Postgres),
    # no una por conversacion: con 50 hilos en pantalla, la version ingenua son
    # 50 viajes a la base cada vez que se abre la pagina.
    ids = [c.id for c, _n in conversaciones]
    ultimos_filas = await db.execute(
        select(Message.conversation_id, Message.content)
        .where(Message.conversation_id.in_(ids))
        .distinct(Message.conversation_id)
        .order_by(Message.conversation_id, Message.position.desc())
    )
    ultimos = dict(ultimos_filas.all())

    return [_to_read(c, n, ultimos.get(c.id)) for c, n in conversaciones]


@router.post("/{conversation_id}/manual", response_model=ConversationRead)
async def pausar_bot(
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    payload: ManualModeStart,
    db: DbSession,
    _: AdminKey,
) -> ConversationRead:
    """Silencia al bot en esta conversacion por un rato.

    Repetir la llamada corre el vencimiento: sirve para estirar la pausa sin
    tener que reactivar y volver a pausar.
    """
    conversacion = await _conversacion_o_404(db, tenant_id, conversation_id)

    horas = payload.horas if payload.horas is not None else settings.manual_mode_hours
    conversacion.pausada_hasta = datetime.now(UTC) + timedelta(hours=horas)
    await db.commit()
    await db.refresh(conversacion)
    return await _detalle(db, conversacion)


@router.delete("/{conversation_id}/manual", response_model=ConversationRead)
async def reanudar_bot(
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    db: DbSession,
    _: AdminKey,
) -> ConversationRead:
    """Devuelve la conversacion al bot antes de que venza la pausa."""
    conversacion = await _conversacion_o_404(db, tenant_id, conversation_id)

    conversacion.pausada_hasta = None
    await db.commit()
    await db.refresh(conversacion)
    return await _detalle(db, conversacion)
