"""Salida hacia la Graph API de Meta."""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


async def send_text(to: str, text: str, phone_number_id: str | None = None) -> None:
    """Envia un mensaje de texto.

    TODO: el access token y el phone_number_id son por tenant — moverlos a la
    tabla `tenants` (cifrados) en vez de a settings globales.
    """
    if not phone_number_id:
        logger.warning("send_text sin phone_number_id: no se envio nada")
        return

    url = f"https://graph.facebook.com/{settings.whatsapp_api_version}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(url, json=payload)
        if resp.is_error:
            logger.error("fallo el envio a WhatsApp: %s %s", resp.status_code, resp.text)
