"""Entrada cruda de los canales. Traduce y delega; nada de logica de negocio."""

import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, Response, status
from sqlalchemy import select

from app.api.v1.deps import DbSession
from app.channels.whatsapp.client import send_text
from app.channels.whatsapp.parser import parse_incoming
from app.core.config import settings
from app.core.logging import tenant_id_ctx
from app.core.security import verify_meta_signature
from app.db.session import SessionLocal
from app.models.tenant import Tenant
from app.services.conversation import answer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.get("/whatsapp")
async def verify(request: Request) -> Response:
    """Handshake de verificacion de Meta (una sola vez, al registrar el webhook)."""
    params = request.query_params
    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == settings.whatsapp_verify_token
    ):
        return Response(content=params.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(status.HTTP_403_FORBIDDEN, "token de verificacion invalido")


@router.post("/whatsapp", status_code=status.HTTP_200_OK)
async def receive(
    request: Request,
    db: DbSession,
    background: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None),
) -> dict[str, str]:
    """Meta reintenta si tardamos: respondemos 200 ya y procesamos en background."""
    raw = await request.body()
    if not verify_meta_signature(raw, x_hub_signature_256):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "firma invalida")

    incoming = parse_incoming(await request.json())
    if incoming is None:
        return {"status": "ignored"}

    tenant = await db.scalar(
        select(Tenant).where(
            Tenant.whatsapp_phone_number_id == incoming.phone_number_id,
            Tenant.is_active.is_(True),
        )
    )
    if tenant is None:
        logger.warning("mensaje para un phone_number_id sin tenant asociado")
        return {"status": "unknown_tenant"}

    background.add_task(
        _handle,
        str(tenant.id),
        incoming.from_number,
        incoming.text,
        incoming.phone_number_id,
    )
    return {"status": "accepted"}


async def _handle(tenant_id: str, to_number: str, text: str, phone_number_id: str) -> None:
    tenant_id_ctx.set(tenant_id)
    async with SessionLocal() as db:
        tenant = await db.get(Tenant, tenant_id)
        if tenant is None:
            return
        reply = await answer(db, tenant, text)
    await send_text(to=to_number, text=reply, phone_number_id=phone_number_id)
