"""Salida hacia la Graph API de Meta."""

import logging

import httpx

from app.core.config import settings
from app.core.retry import with_retry

logger = logging.getLogger(__name__)


class WhatsAppSendError(Exception):
    """No se pudo entregar el mensaje al usuario final."""


async def send_text(to: str, text: str, phone_number_id: str) -> None:
    """Envia un mensaje de texto.

    Levanta excepcion si no se pudo entregar: quien llama necesita saberlo para
    no marcar el mensaje como procesado con exito.

    TODO: el access token es por tenant — moverlo a la tabla `tenants` (cifrado)
    en vez de a settings globales.
    """
    url = f"https://graph.facebook.com/{settings.whatsapp_api_version}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }

    async def _call() -> None:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()

    try:
        await with_retry(_call, descripcion="envio a WhatsApp")
    except httpx.HTTPStatusError as exc:
        # 4xx no reintentable: numero invalido, ventana de 24h cerrada, token vencido.
        raise WhatsAppSendError(
            f"Meta rechazo el envio ({exc.response.status_code}): {exc.response.text[:500]}"
        ) from exc
