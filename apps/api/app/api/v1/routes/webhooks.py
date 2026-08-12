"""Entrada cruda de los canales. Traduce y delega; nada de logica de negocio.

Dos garantias que este modulo tiene que dar:

1. IDEMPOTENCIA. Meta reintenta las entregas. Cada mensaje se procesa una sola
   vez, gracias al reclamo atomico en `services.inbox.claim`.

2. NINGUN FALLO SILENCIOSO. Le respondemos 200 a Meta enseguida (si tardamos,
   reintenta), asi que el procesamiento real ocurre despues, en background. Si
   ahi algo falla, Meta ya no va a reintentar: el error queda registrado en
   `processed_events` y el usuario recibe un mensaje de cortesia en vez de
   quedarse esperando para siempre.
"""

import logging
import uuid

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
from app.services import conversation, inbox, whatsapp
from app.services.conversation import answer
from app.services.quota import QuotaExcedida

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

MENSAJE_DE_CORTESIA = (
    "Perdon, tuve un problema tecnico y no pude procesar tu mensaje. "
    "Podes escribirme de nuevo en un momento."
)

# El usuario final no tiene por que enterarse de que el negocio agoto su cuota.
MENSAJE_SIN_CUOTA = (
    "En este momento no puedo responderte automaticamente. "
    "Alguien del equipo te va a contactar a la brevedad."
)


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
    raw = await request.body()
    if not verify_meta_signature(raw, x_hub_signature_256):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "firma invalida")

    incoming = parse_incoming(await request.json())
    if incoming is None:
        return {"status": "ignored"}  # status de entrega, reaccion, etc.

    tenant = await db.scalar(
        select(Tenant).where(
            Tenant.whatsapp_phone_number_id == incoming.phone_number_id,
            Tenant.is_active.is_(True),
        )
    )
    if tenant is None:
        logger.warning("mensaje para un phone_number_id sin tenant asociado")
        return {"status": "unknown_tenant"}

    tenant_id_ctx.set(str(tenant.id))

    # Reclamo ANTES de responderle 200 a Meta: si el proceso se cae justo
    # despues, la fila queda en 'pending' y es visible/reintentable.
    event_id = await inbox.claim(db, incoming.channel, incoming.external_id, tenant.id)
    if event_id is None:
        return {"status": "duplicate"}

    background.add_task(
        _handle,
        event_id,
        tenant.id,
        incoming.from_number,
        incoming.text,
        incoming.phone_number_id,
    )
    return {"status": "accepted"}


async def _handle(
    event_id: uuid.UUID,
    tenant_id: uuid.UUID,
    to_number: str,
    text: str,
    phone_number_id: str,
) -> None:
    """Procesamiento real, fuera del ciclo request/response.

    Nada de esto puede propagar una excepcion: seria un fallo silencioso, porque
    ya le dijimos 200 a Meta y no va a reintentar.
    """
    tenant_id_ctx.set(str(tenant_id))
    token: str | None = None
    try:
        async with SessionLocal() as db:
            tenant = await db.get(Tenant, tenant_id)
            if tenant is None:
                raise RuntimeError(f"el tenant {tenant_id} desaparecio entre el claim y el handle")

            # La conversacion se reanuda por el numero del usuario final, dentro
            # de la ventana de inactividad configurada.
            conversacion = await conversation.resolver_conversacion(
                db, tenant, channel="whatsapp", external_id=to_number
            )

            # ★ El unico punto de control del modo manual. Va ANTES de leer el
            # token y de llamar al modelo: si alguien esta contestando a mano
            # desde la bandeja de Meta, el bot no tiene que pisarle la respuesta
            # -ni gastar en generar una que no se va a mandar-.
            #
            # El mensaje igual se guarda: cuando la pausa vence, el bot retoma
            # con el historial completo en vez de con un agujero.
            if conversacion.en_modo_manual():
                await conversation.registrar_entrante(db, conversacion, text)
                logger.info(
                    "conversacion en modo manual: mensaje guardado sin responder",
                    extra={"tenant_id": str(tenant_id), "conversation_id": str(conversacion.id)},
                )
                await inbox.mark_done(db, event_id)
                return

            # Se lee antes de generar la respuesta: si falta la credencial, no
            # tiene sentido gastar en el LLM una respuesta que no se va a poder
            # entregar.
            token = whatsapp.leer_token(tenant)

            try:
                reply, _conversacion = await answer(
                    db,
                    tenant,
                    text,
                    channel="whatsapp",
                    external_id=to_number,
                    conversation_id=conversacion.id,
                )
            except QuotaExcedida:
                # No es un error: es politica. Se procesó, y el evento queda
                # 'done' para que no se reintente. Al usuario final no se le
                # cuenta que el negocio se quedo sin cuota.
                logger.warning(
                    "mensaje no atendido por cuota agotada",
                    extra={"tenant_id": str(tenant_id)},
                )
                await send_text(
                    to=to_number,
                    text=MENSAJE_SIN_CUOTA,
                    phone_number_id=phone_number_id,
                    access_token=token or "",
                )
                await inbox.mark_done(db, event_id)
                return

            await send_text(
                to=to_number,
                text=reply,
                phone_number_id=phone_number_id,
                access_token=token or "",
            )
            await inbox.mark_done(db, event_id)

    except Exception as exc:  # noqa: BLE001 — frontera: aca no puede escapar nada
        logger.exception("fallo el procesamiento del mensaje", extra={"event_id": str(event_id)})
        await _registrar_fallo(event_id, exc)
        await _avisar_al_usuario(to_number, phone_number_id, token)


async def _registrar_fallo(event_id: uuid.UUID, exc: Exception) -> None:
    """Sesion nueva a proposito: la anterior puede estar en estado invalido."""
    try:
        async with SessionLocal() as db:
            await inbox.mark_failed(db, event_id, f"{type(exc).__name__}: {exc}")
    except Exception:  # noqa: BLE001
        logger.exception("tampoco se pudo registrar el fallo", extra={"event_id": str(event_id)})


async def _avisar_al_usuario(
    to_number: str, phone_number_id: str, access_token: str | None
) -> None:
    """Mejor un 'tuve un problema' que un silencio indistinguible de ser ignorado.

    Si el fallo fue justamente que no hay credencial, no hay forma de avisarle:
    se registra y se sale, en vez de encadenar otro error.
    """
    if not access_token:
        logger.error("sin access token: no se puede avisar al usuario del fallo")
        return
    try:
        await send_text(
            to=to_number,
            text=MENSAJE_DE_CORTESIA,
            phone_number_id=phone_number_id,
            access_token=access_token,
        )
    except Exception:  # noqa: BLE001
        logger.exception("no se pudo entregar ni el mensaje de cortesia")
