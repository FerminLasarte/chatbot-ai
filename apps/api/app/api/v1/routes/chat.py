"""POST /chat — el endpoint del motor. Lo consume el widget web y el dashboard."""

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
    reply = await answer(db, tenant, payload.message)
    return ChatResponse(
        reply=reply,
        conversation_id=payload.conversation_id or str(uuid.uuid4()),
    )
