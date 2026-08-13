"""Orquesta el motor: cuota, memoria, contexto, prompt y LLM.

Esta es la unica capa que conoce el flujo completo. Los canales (WhatsApp, web)
solo traducen formatos; el LLM solo genera; el retriever solo busca.

QUE SE GUARDA Y QUE NO
----------------------
Se persiste el texto PLANO del usuario y la respuesta. NO se guarda el turno con
el contexto RAG inyectado, por dos razones:

  - Al replicar la historia se estaria reenviando contexto viejo, recuperado para
    otra pregunta. Confunde al modelo mas de lo que ayuda.
  - El costo crece sin techo: cada turno arrastraria los fragmentos de todos los
    turnos anteriores.

El contexto se recupera fresco para la pregunta actual, en cada turno.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from anthropic.types import MessageParam, TextBlockParam
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm.client import complete
from app.ai.prompts.builder import build_system_blocks, build_user_turn
from app.ai.rag.retriever import search
from app.core.config import settings
from app.models.tenant import Conversation, Message, Tenant
from app.services import quota

logger = logging.getLogger(__name__)

ROL_USUARIO = "user"
ROL_ASISTENTE = "assistant"


class ConversacionAjena(Exception):
    """El conversation_id pedido no pertenece a este cliente."""


async def answer(
    db: AsyncSession,
    tenant: Tenant,
    question: str,
    *,
    channel: str,
    external_id: str,
    conversation_id: uuid.UUID | None = None,
) -> tuple[str, uuid.UUID]:
    """Responde un mensaje entrante y devuelve (respuesta, conversation_id).

    Levanta `quota.QuotaExcedida` si el cliente agoto su cuota del mes, y
    `ConversacionAjena` si el conversation_id no es de este cliente.
    """
    # PRIMERO la cuota: tiene que frenar el gasto, no contabilizarlo despues.
    await quota.consumir_mensaje(db, tenant)

    conversacion = await _resolver_conversacion(
        db, tenant, channel=channel, external_id=external_id, conversation_id=conversation_id
    )
    historia = await _cargar_historia(db, conversacion.id)

    # El mensaje del usuario se persiste ANTES de llamar al modelo: si la
    # generacion falla, la pregunta no se pierde.
    await _guardar_mensaje(db, conversacion.id, ROL_USUARIO, question)

    chunks = await search(db, tenant.id, question)

    messages: list[MessageParam] = [*historia]
    messages.append(MessageParam(role="user", content=build_user_turn(question, chunks)))

    respuesta = await complete(build_system_blocks(tenant.system_prompt), messages)

    await _guardar_mensaje(db, conversacion.id, ROL_ASISTENTE, respuesta.text)
    await _tocar_actividad(db, conversacion)

    await quota.registrar_tokens(
        db,
        tenant.id,
        input_tokens=respuesta.input_tokens,
        output_tokens=respuesta.output_tokens,
        cache_read_tokens=respuesta.cache_read_tokens,
    )
    return respuesta.text, conversacion.id


async def resolver_conversacion(
    db: AsyncSession, tenant: Tenant, *, channel: str, external_id: str
) -> Conversation:
    """Abre o reanuda el hilo de un usuario final, sin generar ninguna respuesta.

    La necesita el webhook: para saber si la conversacion esta en modo manual
    hay que tenerla en la mano ANTES de decidir si se llama al modelo.
    """
    return await _reanudar_o_crear(db, tenant, channel=channel, external_id=external_id)


async def registrar_entrante(db: AsyncSession, conversacion: Conversation, texto: str) -> None:
    """Guarda un mensaje del usuario y nada mas.

    Es el camino del modo manual: no se pierde el historial -la respuesta la
    escribe una persona en otra ventana- pero no se genera ni se cobra nada.
    """
    await _guardar_mensaje(db, conversacion.id, ROL_USUARIO, texto)
    await _tocar_actividad(db, conversacion)


# ---------------------------------------------------------------------------
# Identidad de la conversacion
# ---------------------------------------------------------------------------


async def _resolver_conversacion(
    db: AsyncSession,
    tenant: Tenant,
    *,
    channel: str,
    external_id: str,
    conversation_id: uuid.UUID | None,
) -> Conversation:
    if conversation_id is not None:
        return await _reanudar_por_id(db, tenant, conversation_id)
    return await _reanudar_o_crear(db, tenant, channel=channel, external_id=external_id)


async def _reanudar_por_id(
    db: AsyncSession, tenant: Tenant, conversation_id: uuid.UUID
) -> Conversation:
    """Camino del widget web, donde el id lo manda el cliente.

    ★ El filtro por tenant_id NO es opcional. El conversation_id viaja en el
    navegador; sin este filtro, alguien con el id de una conversacion de otro
    cliente podria reanudarla y leer su historial en la respuesta del modelo.
    """
    conversacion = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant.id,  # <- aislamiento entre clientes
        )
    )
    if conversacion is None:
        logger.warning(
            "conversation_id inexistente o de otro cliente",
            extra={"tenant_id": str(tenant.id), "conversation_id": str(conversation_id)},
        )
        raise ConversacionAjena(str(conversation_id))
    return conversacion


async def _reanudar_o_crear(
    db: AsyncSession, tenant: Tenant, *, channel: str, external_id: str
) -> Conversation:
    """Camino de WhatsApp: la identidad es el numero del usuario final."""
    # El corte se calcula en Python: evita SQL especifico de Postgres y hace el
    # limite trivial de mover en tests. Para una ventana de horas, la diferencia
    # entre el reloj de la app y el de la base es irrelevante.
    corte = datetime.now(UTC) - timedelta(minutes=settings.conversation_idle_minutes)
    conversacion = await db.scalar(
        select(Conversation)
        .where(
            Conversation.tenant_id == tenant.id,
            Conversation.channel == channel,
            Conversation.external_id == external_id,
            Conversation.last_activity_at >= corte,
        )
        .order_by(Conversation.last_activity_at.desc())
        .limit(1)
    )
    if conversacion is not None:
        return conversacion

    conversacion = Conversation(tenant_id=tenant.id, channel=channel, external_id=external_id)
    db.add(conversacion)
    await db.commit()
    await db.refresh(conversacion)
    return conversacion


# ---------------------------------------------------------------------------
# Historia
# ---------------------------------------------------------------------------


async def _cargar_historia(db: AsyncSession, conversation_id: uuid.UUID) -> list[MessageParam]:
    """Ultimos N mensajes, en orden cronologico y listos para la API."""
    limite = settings.conversation_history_messages
    if limite <= 0:
        return []

    # Se piden los mas recientes (DESC) y despues se invierte: para quedarse con
    # la cola de la conversacion, no con la cabeza.
    filas = await db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.position.desc())
        .limit(limite)
    )
    recientes = list(filas)[::-1]

    # La API exige que el primer mensaje sea del usuario. Si el recorte dejo una
    # respuesta del asistente arriba, se descarta.
    while recientes and recientes[0].role != ROL_USUARIO:
        recientes.pop(0)

    # Los mensajes seguidos del mismo rol se juntan en un turno.
    #
    # Hace falta por el modo manual: mientras el bot esta pausado se guardan
    # mensajes del usuario sin ninguna respuesta en el medio, asi que al
    # reanudar la historia trae varios turnos "user" pegados. Ademas de evitar
    # discutir con la API sobre alternancia de roles, leerlos como una sola
    # intervencion es mas fiel a lo que paso: el usuario escribio tres veces
    # seguidas, no mantuvo tres intercambios.
    historia: list[MessageParam] = []
    for m in recientes:
        # El tipo explicito no es decorativo: MessageParam["role"] es un Literal,
        # y sin la anotacion mypy infiere `str` y rechaza la construccion.
        rol: Literal["user", "assistant"] = "user" if m.role == ROL_USUARIO else "assistant"
        anterior = historia[-1] if historia else None
        if anterior is not None and anterior["role"] == rol:
            bloques = anterior["content"]
            if isinstance(bloques, list):
                bloques.append(TextBlockParam(type="text", text=m.content))
                continue
        historia.append(
            MessageParam(role=rol, content=[TextBlockParam(type="text", text=m.content)])
        )

    # Breakpoint de cache sobre la cola de la historia. El prefijo de tools +
    # system solo (~326 tokens) no llega al minimo de 512 de Opus 5, asi que hoy
    # no cachea; con historia suficiente, este si empieza a acertar.
    if historia:
        ultimo = historia[-1]
        bloques = ultimo["content"]
        if isinstance(bloques, list) and bloques:
            bloques[-1]["cache_control"] = {"type": "ephemeral"}

    return historia


async def _guardar_mensaje(
    db: AsyncSession, conversation_id: uuid.UUID, role: str, content: str
) -> None:
    """La posicion se calcula en la misma sentencia del INSERT.

    Leer el maximo y despues insertar tendria una carrera con dos mensajes
    simultaneos de la misma conversacion.
    """
    siguiente = (
        select(func.coalesce(func.max(Message.position), 0) + 1)
        .where(Message.conversation_id == conversation_id)
        .scalar_subquery()
    )
    db.add(
        Message(
            conversation_id=conversation_id,
            position=siguiente,
            role=role,
            content=content,
        )
    )
    await db.commit()


async def _tocar_actividad(db: AsyncSession, conversacion: Conversation) -> None:
    conversacion.last_activity_at = func.now()
    await db.commit()
