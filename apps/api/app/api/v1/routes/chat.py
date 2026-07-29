"""POST /chat — el endpoint del motor. Lo consume el widget web y el dashboard.

El `conversation_id` es opcional: si no viene, se abre una conversacion nueva y
se devuelve su id para que el cliente lo mande en los turnos siguientes.
"""

import uuid

from fastapi import APIRouter

from app.api.v1.deps import ChatKey, CurrentTenant, DbSession
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.conversation import answer

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    tenant: CurrentTenant,
    db: DbSession,
    _: ChatKey,
) -> ChatResponse:
    """Acepta claves con scope `chat` (widget publico) o `tenant` (dashboard)."""
    reply, conversation_id = await answer(
        db,
        tenant,
        payload.message,
        channel="webchat",
        # Solo se usa al crear: en el canal web la identidad del hilo es el
        # propio conversation_id, no un identificador externo.
        external_id=str(uuid.uuid4()),
        conversation_id=payload.conversation_id,
    )
    return ChatResponse(reply=reply, conversation_id=str(conversation_id))
