"""Conversaciones de un cliente y modo manual, para la agencia.

El modo manual resuelve un caso concreto: alguien entra a la bandeja de Meta
Business Suite a contestarle a mano a un cliente puntual, y necesita que el bot
se calle mientras tanto para no pisarle la respuesta.

DOS DECISIONES QUE VALE LA PENA CONOCER
---------------------------------------
1. La pausa VENCE (ver `Conversation.pausada_hasta`). No hay pausa indefinida:
   un interruptor olvidado deja a un cliente sin respuestas automaticas para
   siempre, en silencio.

2. La pausa es POR CONVERSACION, no por cliente. Callar al bot entero para
   atender a una sola persona es un remedio peor que la enfermedad.

Estas rutas son las de la AGENCIA (clave admin): el cliente se dice en la URL
porque una clave admin no tiene tenant propio. El duenio del negocio llega a las
mismas dos operaciones por otra puerta, con una clave que ya trae su tenant y
sin poder nombrar a ningun otro (ver routes/portal.py). Las consultas de fondo
son unas solas, en services/conversaciones.py.
"""

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import AdminKey, DbSession
from app.core.config import settings
from app.models.tenant import Tenant
from app.schemas.chat import (
    ConversationRead,
    ManualModeStart,
    MessageRead,
    RespuestaManual,
)
from app.services import conversaciones, responder

router = APIRouter(prefix="/tenants/{tenant_id}/conversations", tags=["conversations"])


async def _tenant_o_404(db: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cliente no encontrado")
    return tenant


def _no_encontrada() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "conversacion no encontrada")


@router.get("", response_model=list[ConversationRead])
async def list_conversations(
    tenant_id: uuid.UUID,
    db: DbSession,
    _: AdminKey,
    limite: int = Query(default=50, ge=1, le=200),
) -> list[ConversationRead]:
    """Las conversaciones mas recientes del cliente, la ultima primero."""
    await _tenant_o_404(db, tenant_id)
    return await conversaciones.listar(db, tenant_id, limite=limite)


@router.get("/{conversation_id}/messages", response_model=list[MessageRead])
async def read_messages(
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    db: DbSession,
    _: AdminKey,
    limite: int = Query(default=200, ge=1, le=500),
) -> list[MessageRead]:
    """El hilo completo, para dar soporte sin pedirle capturas al cliente."""
    await _tenant_o_404(db, tenant_id)
    try:
        return await conversaciones.listar_mensajes(db, tenant_id, conversation_id, limite=limite)
    except conversaciones.ConversacionNoEncontrada as exc:
        raise _no_encontrada() from exc


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
)
async def responder_a_mano(
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    payload: RespuestaManual,
    db: DbSession,
    _: AdminKey,
) -> MessageRead:
    """Le contesta al cliente final en nombre del negocio, desde el panel.

    Ademas de enviar, pausa el bot y da por atendida la derivacion: contestar a
    mano es la forma mas fuerte de decir "esto lo atiendo yo". El detalle de
    por que esas tres cosas van juntas esta en services/responder.py.

    409 y no 400 para los rechazos: no esta mal escrita la peticion, es el
    estado de la conversacion el que no admite un envio ahora (la ventana de
    24 h vencida es el caso normal, no un error de programacion).
    """
    tenant = await _tenant_o_404(db, tenant_id)
    try:
        return await responder.responder(db, tenant, conversation_id, payload.texto)
    except conversaciones.ConversacionNoEncontrada as exc:
        raise _no_encontrada() from exc
    except responder.NoSePuedeResponder as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/{conversation_id}/manual", response_model=ConversationRead)
async def pausar_bot(
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    payload: ManualModeStart,
    db: DbSession,
    _: AdminKey,
) -> ConversationRead:
    """Silencia al bot en esta conversacion por un rato."""
    horas = payload.horas if payload.horas is not None else settings.manual_mode_hours
    try:
        return await conversaciones.pausar(db, tenant_id, conversation_id, horas=horas)
    except conversaciones.ConversacionNoEncontrada as exc:
        raise _no_encontrada() from exc


@router.delete("/{conversation_id}/manual", response_model=ConversationRead)
async def reanudar_bot(
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    db: DbSession,
    _: AdminKey,
) -> ConversationRead:
    """Devuelve la conversacion al bot antes de que venza la pausa."""
    try:
        return await conversaciones.reanudar(db, tenant_id, conversation_id)
    except conversaciones.ConversacionNoEncontrada as exc:
        raise _no_encontrada() from exc
