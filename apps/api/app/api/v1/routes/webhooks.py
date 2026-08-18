"""Entrada cruda de los canales. Traduce y delega; nada de logica de negocio.

Dos garantias que este modulo tiene que dar:

1. IDEMPOTENCIA. Meta reintenta las entregas. Cada mensaje se procesa una sola
   vez, gracias al reclamo atomico en `services.inbox.claim`.

2. NINGUN FALLO SILENCIOSO. Le respondemos 200 a Meta enseguida (si tardamos,
   reintenta), asi que el procesamiento real ocurre despues, en background. Si
   ahi algo falla, Meta ya no va a reintentar: el error queda registrado en
   `processed_events` y el usuario recibe un mensaje de cortesia en vez de
   quedarse esperando para siempre.

3. EL BOT NO SE PAUSA A SI MISMO. Con coexistence, Meta avisa por webhook de
   los mensajes que el comercio escribe a mano desde el celular, y esos pausan
   al bot. Si una respuesta del propio bot entrara por esa puerta, se callaria
   solo y no volveria a contestar nunca. Ver `_recibir_echo`.
"""

import json
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, Response, status
from sqlalchemy import select

from app.api.v1.deps import DbSession
from app.channels.whatsapp.client import send_text
from app.channels.whatsapp.parser import (
    CAMPO_ECHOES,
    CAMPO_MENSAJES,
    CAMPOS_CONOCIDOS_SIN_USO,
    CANAL_ECHO,
    campo_del_evento,
    parse_echo,
    parse_incoming,
)
from app.core.config import settings
from app.core.logging import tenant_id_ctx
from app.core.security import verify_meta_signature
from app.db.session import SessionLocal
from app.models.tenant import Tenant
from app.services import conversaciones, conversation, inbox, whatsapp
from app.services.conversation import answer
from app.services.quota import QuotaExcedida

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

MENSAJE_DE_CORTESIA = (
    "Perdon, tuve un problema tecnico y no pude procesar tu mensaje. "
    "Podes escribirme de nuevo en un momento."
)

# Cuanto payload crudo se loguea al no reconocer un evento. Alcanza de sobra
# para un webhook de WhatsApp y evita llenar el log si Meta manda algo enorme.
LARGO_PAYLOAD_EN_LOG = 4000

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

    payload = await request.json()
    campo = campo_del_evento(payload)

    # Coexistence: el comercio contesto a mano desde el celular. Es un evento
    # de otra naturaleza -sale del negocio, no entra- y tiene su propio camino.
    if campo == CAMPO_ECHOES:
        return await _recibir_echo(payload, db, background)

    incoming = parse_incoming(payload)
    if incoming is None:
        # ★ Un campo desconocido se nombra en el log. `parse_incoming` descarta
        # todo lo que no sea `messages`, asi que si Meta alguna vez manda los
        # mensajes bajo otro nombre, el bot dejaria de contestar SIN ningun
        # error: solo silencio, que es el fallo mas caro de diagnosticar de
        # este modulo. Con esto, la causa esta a un grep de distancia.
        #
        # No entra por aca lo normal: los statuses de entrega y las reacciones
        # vienen con field=`messages` y caen en la rama de abajo, calladas.
        if campo is not None and campo != CAMPO_MENSAJES and campo not in CAMPOS_CONOCIDOS_SIN_USO:
            logger.warning(
                "webhook de Meta con un campo que no se maneja: %s "
                "(si los mensajes dejaron de llegar, empeza por aca)",
                campo,
            )
        return {"status": "ignored"}  # status de entrega, reaccion, etc.

    tenant = await _tenant_por_numero(db, incoming.phone_number_id)
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


async def _recibir_echo(
    payload: dict, db: DbSession, background: BackgroundTasks
) -> dict[str, str]:
    """Un mensaje que salio del numero del negocio sin pasar por el bot.

    Ver docs/coexistence.md. Mientras la funcion este apagada esto no actua:
    solo deja el payload crudo en el log, que es como se confirma su forma real
    sin arriesgar que una lectura equivocada silencie al bot.
    """
    if not settings.coexistence_enabled:
        logger.warning(
            "echo de coexistence recibido con la funcion apagada: %s",
            json.dumps(payload)[:LARGO_PAYLOAD_EN_LOG],
        )
        return {"status": "coexistence_disabled"}

    echo = parse_echo(payload)
    if echo is None:
        # No romper y no adivinar: queda el crudo para poder arreglar el parser.
        logger.warning(
            "echo de coexistence con forma no reconocida: %s",
            json.dumps(payload)[:LARGO_PAYLOAD_EN_LOG],
        )
        return {"status": "ignored"}

    tenant = await _tenant_por_numero(db, echo.phone_number_id)
    if tenant is None:
        logger.warning("echo para un phone_number_id sin tenant asociado")
        return {"status": "unknown_tenant"}

    tenant_id_ctx.set(str(tenant.id))

    # ★ ACA se corta la auto-pausa. Cada mensaje que enviamos por la Cloud API
    # deja su id anotado (ver `_registrar_envio_propio`), asi que si Meta
    # tambien hace echo de nuestros propios envios, el reclamo falla y el echo
    # se descarta. Sin esto, el bot se pausaria con su propia respuesta.
    event_id = await inbox.claim(db, echo.channel, echo.external_id, tenant.id)
    if event_id is None:
        return {"status": "duplicate"}

    background.add_task(_handle_echo, event_id, tenant.id, echo.to_number, echo.text)
    return {"status": "accepted"}


async def _handle_echo(
    event_id: uuid.UUID, tenant_id: uuid.UUID, to_number: str, text: str
) -> None:
    """Guarda lo que escribio la persona y calla al bot en ese hilo.

    Repetir la pausa corre el vencimiento: mientras el duenio siga contestando,
    la pausa se estira sola, y cuando deja de hacerlo el bot vuelve. Es el mismo
    comportamiento del boton del portal, sin que nadie tenga que apretarlo.

    Como el resto del procesamiento en background, aca no puede escapar nada.
    A diferencia de `_handle`, un fallo NO manda mensaje de cortesia: el evento
    es una respuesta del negocio, y escribirle al cliente final "tuve un
    problema" seria meter al bot justo donde se le pidio que no se meta.
    """
    tenant_id_ctx.set(str(tenant_id))
    try:
        async with SessionLocal() as db:
            tenant = await db.get(Tenant, tenant_id)
            if tenant is None:
                raise RuntimeError(f"el tenant {tenant_id} desaparecio entre el claim y el handle")

            # La identidad del hilo es el usuario final: en un echo ese es el
            # DESTINATARIO, no el remitente (el remitente es el comercio).
            conversacion = await conversation.resolver_conversacion(
                db, tenant, channel="whatsapp", external_id=to_number
            )

            if await conversation.coincide_con_la_ultima_respuesta(db, conversacion.id, text):
                # Llegar aca significa que el filtro por id no alcanzo. No es
                # fatal -por eso existe esta segunda linea- pero hay que verlo:
                # si pasa seguido, Meta hace echo de nuestros envios y el id no
                # los esta cubriendo.
                logger.warning(
                    "echo identico a la ultima respuesta del bot: se descarta para no auto-pausar",
                    extra={"tenant_id": str(tenant_id), "conversation_id": str(conversacion.id)},
                )
                await inbox.mark_done(db, event_id)
                return

            await conversation.registrar_saliente(db, conversacion, text)
            await conversaciones.pausar(
                db, tenant_id, conversacion.id, horas=settings.manual_mode_hours
            )
            logger.info(
                "respuesta manual desde el celular: bot pausado en esta conversacion",
                extra={"tenant_id": str(tenant_id), "conversation_id": str(conversacion.id)},
            )
            await inbox.mark_done(db, event_id)

    except Exception as exc:  # noqa: BLE001 — frontera: aca no puede escapar nada
        logger.exception("fallo el procesamiento de un echo", extra={"event_id": str(event_id)})
        await _registrar_fallo(event_id, exc)


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
                wamid = await send_text(
                    to=to_number,
                    text=MENSAJE_SIN_CUOTA,
                    phone_number_id=phone_number_id,
                    access_token=token or "",
                )
                await _registrar_envio_propio(tenant_id, wamid)
                await inbox.mark_done(db, event_id)
                return

            wamid = await send_text(
                to=to_number,
                text=reply,
                phone_number_id=phone_number_id,
                access_token=token or "",
            )
            await _registrar_envio_propio(tenant_id, wamid)
            await inbox.mark_done(db, event_id)

    except Exception as exc:  # noqa: BLE001 — frontera: aca no puede escapar nada
        logger.exception("fallo el procesamiento del mensaje", extra={"event_id": str(event_id)})
        await _registrar_fallo(event_id, exc)
        await _avisar_al_usuario(tenant_id, to_number, phone_number_id, token)


async def _tenant_por_numero(db: DbSession, phone_number_id: str) -> Tenant | None:
    """El cliente duenio de un numero de WhatsApp, si esta activo."""
    return await db.scalar(
        select(Tenant).where(
            Tenant.whatsapp_phone_number_id == phone_number_id,
            Tenant.is_active.is_(True),
        )
    )


async def _registrar_fallo(event_id: uuid.UUID, exc: Exception) -> None:
    """Sesion nueva a proposito: la anterior puede estar en estado invalido."""
    try:
        async with SessionLocal() as db:
            await inbox.mark_failed(db, event_id, f"{type(exc).__name__}: {exc}")
    except Exception:  # noqa: BLE001
        logger.exception("tampoco se pudo registrar el fallo", extra={"event_id": str(event_id)})


async def _avisar_al_usuario(
    tenant_id: uuid.UUID, to_number: str, phone_number_id: str, access_token: str | None
) -> None:
    """Mejor un 'tuve un problema' que un silencio indistinguible de ser ignorado.

    Si el fallo fue justamente que no hay credencial, no hay forma de avisarle:
    se registra y se sale, en vez de encadenar otro error.
    """
    if not access_token:
        logger.error("sin access token: no se puede avisar al usuario del fallo")
        return
    try:
        wamid = await send_text(
            to=to_number,
            text=MENSAJE_DE_CORTESIA,
            phone_number_id=phone_number_id,
            access_token=access_token,
        )
        await _registrar_envio_propio(tenant_id, wamid)
    except Exception:  # noqa: BLE001
        logger.exception("no se pudo entregar ni el mensaje de cortesia")


async def _registrar_envio_propio(tenant_id: uuid.UUID, wamid: str | None) -> None:
    """Anota el id de un mensaje que enviamos nosotros, para no leerlo de vuelta.

    ★ Es la defensa principal contra la auto-pausa por coexistence: cuando
    llegue el echo de este mismo mensaje -si es que Meta los manda-, su id ya
    va a estar reclamado y el webhook lo va a descartar como duplicado.

    Sesion propia, por el mismo motivo que `_registrar_fallo`: uno de los
    llamadores corre despues de una excepcion, con la sesion anterior en estado
    dudoso.
    """
    if not wamid:
        # Sin id queda solo la segunda linea de defensa (comparar el texto con
        # la ultima respuesta del bot, ver services/conversation.py).
        logger.warning("envio sin id de mensaje: el echo propio no se va a poder filtrar por id")
        return
    try:
        async with SessionLocal() as db:
            await inbox.registrar_propio(db, CANAL_ECHO, wamid, tenant_id)
    except Exception:  # noqa: BLE001
        logger.exception("no se pudo anotar el envio propio", extra={"external_id": wamid})
