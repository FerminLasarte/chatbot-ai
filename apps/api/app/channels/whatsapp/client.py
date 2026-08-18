"""Salida hacia la Graph API de Meta."""

import logging

import httpx

from app.core.config import settings
from app.core.retry import with_retry

logger = logging.getLogger(__name__)


class WhatsAppSendError(Exception):
    """No se pudo entregar el mensaje al usuario final."""


class WhatsAppSinCredencial(WhatsAppSendError):
    """El cliente no tiene cargado su access token."""


class AltaWhatsAppError(Exception):
    """Fallo un paso del alta de un cliente nuevo (Embedded Signup)."""


def _base() -> str:
    return f"https://graph.facebook.com/{settings.whatsapp_api_version}"


def _detalle(exc: httpx.HTTPStatusError) -> str:
    """El mensaje de error de Meta, que suele decir exactamente que falto."""
    return f"{exc.response.status_code}: {exc.response.text[:500]}"


def _id_del_mensaje(resp: httpx.Response) -> str | None:
    """El wamid del mensaje recien enviado, si Meta lo devolvio.

    Nunca levanta: el mensaje YA se entrego cuando esto corre. Quedarse sin el
    id degrada un filtro (ver send_text), pero romper aca haria fallar un envio
    exitoso y lo mandaria de nuevo en el reintento.
    """
    try:
        return str(resp.json()["messages"][0]["id"])
    except Exception:  # noqa: BLE001 — cualquier forma inesperada vale como "no vino"
        logger.warning("Meta acepto el envio pero no devolvio el id del mensaje")
        return None


async def send_text(to: str, text: str, phone_number_id: str, access_token: str) -> str | None:
    """Envia un mensaje de texto en nombre del numero indicado.

    El access_token es POR CLIENTE y llega descifrado desde `tenants` (ver
    services.whatsapp.credenciales). No sale de la config global: autoriza a
    escribir en nombre del negocio, asi que dos clientes nunca comparten uno.

    Levanta excepcion si no se pudo entregar: quien llama necesita saberlo para
    no marcar el mensaje como procesado con exito.

    Devuelve el id (wamid) que Meta le asigno al mensaje, o None si no vino.
    ★ No es decorativo: con coexistence, ese id es lo que permite reconocer el
    echo de nuestro propio envio y no confundirlo con una respuesta escrita a
    mano (ver docs/coexistence.md). El envio no falla por no tener el id.
    """
    if not access_token:
        raise WhatsAppSinCredencial(
            "el cliente no tiene access token de WhatsApp cargado (se configura en el panel)"
        )

    url = f"{_base()}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }

    async def _call() -> str | None:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                url,
                json=payload,
                # Sin este header Meta responde 401 y no se entrega nada.
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            return _id_del_mensaje(resp)

    try:
        return await with_retry(_call, descripcion="envio a WhatsApp")
    except httpx.HTTPStatusError as exc:
        # 4xx no reintentable: numero invalido, ventana de 24h cerrada, token vencido.
        raise WhatsAppSendError(
            f"Meta rechazo el envio ({exc.response.status_code}): {exc.response.text[:500]}"
        ) from exc


# ---------------------------------------------------------------------------
# Alta de un cliente nuevo (Embedded Signup)
#
# Los tres pasos que van despues de que el cliente termina el popup de Facebook.
# Ninguno se puede saltear: sin el canje no hay token, sin la suscripcion no
# llegan los mensajes entrantes, y sin el registro no se pueden mandar.
# ---------------------------------------------------------------------------


async def canjear_code_por_token(code: str) -> str:
    """Cambia el `code` de un solo uso que devolvio el popup por un access token.

    ★ Esto va SIEMPRE del servidor, nunca del navegador: la llamada lleva el App
    Secret. Si el canje se hiciera en el frontend, el secreto de la App —que vale
    para todos los clientes— quedaria a la vista de cualquiera.

    El token que devuelve no vence: es el que queda cifrado en la fila del
    cliente y con el que se le envian los mensajes de ahi en adelante.
    """
    if not settings.whatsapp_app_id or not settings.whatsapp_app_secret:
        raise AltaWhatsAppError(
            "faltan WHATSAPP_APP_ID o WHATSAPP_APP_SECRET en la configuracion del servidor"
        )

    async def _call() -> str:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{_base()}/oauth/access_token",
                params={
                    "client_id": settings.whatsapp_app_id,
                    "client_secret": settings.whatsapp_app_secret,
                    "code": code,
                },
            )
            resp.raise_for_status()
            token = resp.json().get("access_token")
            if not token:
                raise AltaWhatsAppError("Meta no devolvio ningun access token")
            return str(token)

    try:
        return await with_retry(_call, descripcion="canje de code por token")
    except httpx.HTTPStatusError as exc:
        # El caso tipico es un code ya usado o vencido: duran pocos minutos.
        raise AltaWhatsAppError(f"Meta rechazo el canje del codigo ({_detalle(exc)})") from exc


async def suscribir_webhook(waba_id: str, access_token: str) -> None:
    """Engancha nuestra App al WhatsApp Business Account del cliente.

    ★ Sin este paso el alta parece exitosa —hay numero y hay token, y hasta se
    pueden mandar mensajes— pero no llega NINGUN mensaje entrante, porque Meta
    no sabe que tiene que avisarnos de lo que pasa en esa cuenta. Es el error
    silencioso mas caro del flujo, asi que si falla se corta el alta entera.
    """

    async def _call() -> None:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{_base()}/{waba_id}/subscribed_apps",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()

    try:
        await with_retry(_call, descripcion="suscripcion del webhook")
    except httpx.HTTPStatusError as exc:
        raise AltaWhatsAppError(
            f"no se pudo suscribir el webhook a la cuenta del cliente ({_detalle(exc)})"
        ) from exc


async def registrar_numero(phone_number_id: str, access_token: str, pin: str) -> None:
    """Da de alta el numero en la Cloud API para poder enviar desde el.

    Hace falta sobre todo cuando el cliente MIGRA un numero que ya usaba en la
    app comun de WhatsApp Business: hasta que no se registra, el numero figura
    conectado pero cualquier envio falla.

    El `pin` es el de la verificacion en dos pasos. Si el cliente ya tenia uno
    puesto y no es este, Meta rechaza el registro: por eso quien llama trata el
    fallo como advertencia y no como alta fallida (ver services/whatsapp.py).
    """

    async def _call() -> None:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{_base()}/{phone_number_id}/register",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"messaging_product": "whatsapp", "pin": pin},
            )
            resp.raise_for_status()

    try:
        await with_retry(_call, descripcion="registro del numero")
    except httpx.HTTPStatusError as exc:
        raise AltaWhatsAppError(f"no se pudo registrar el numero ({_detalle(exc)})") from exc
