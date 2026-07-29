"""Orquesta el motor: cuota, recuperacion de contexto, prompt y LLM.

Esta es la unica capa que conoce el flujo completo. Los canales (WhatsApp, web)
solo traducen formatos; el LLM solo genera; el retriever solo busca.
"""

import uuid

from anthropic.types import MessageParam
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm.client import complete
from app.ai.prompts.builder import build_system_blocks, build_user_turn
from app.ai.rag.retriever import search
from app.models.tenant import Tenant
from app.services import quota


async def answer(
    db: AsyncSession,
    tenant: Tenant,
    question: str,
    history: list[MessageParam] | None = None,
) -> str:
    """Genera la respuesta del bot para un mensaje entrante.

    Levanta `quota.QuotaExcedida` si el cliente agoto su cuota del mes.
    """
    # PRIMERO la cuota: tiene que frenar el gasto, no contabilizarlo despues de
    # haberlo hecho. Los embeddings de la busqueda tambien se pagan.
    await quota.consumir_mensaje(db, tenant)

    chunks = await search(db, tenant.id, question)

    system_blocks = build_system_blocks(tenant.system_prompt)
    messages: list[MessageParam] = list(history or [])
    messages.append(MessageParam(role="user", content=build_user_turn(question, chunks)))

    respuesta = await complete(system_blocks, messages)

    await quota.registrar_tokens(
        db,
        tenant.id,
        input_tokens=respuesta.input_tokens,
        output_tokens=respuesta.output_tokens,
        cache_read_tokens=respuesta.cache_read_tokens,
    )
    return respuesta.text


async def get_or_create_conversation(
    db: AsyncSession, tenant_id: uuid.UUID, channel: str, external_id: str
) -> uuid.UUID:
    """TODO: persistir e hidratar el historial. El MVP responde sin memoria."""
    raise NotImplementedError
