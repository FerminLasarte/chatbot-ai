"""Payload de la Cloud API de Meta -> IncomingMessage.

Meta manda muchos eventos que no son mensajes de texto (statuses de entrega,
reacciones, lecturas). Todos esos devuelven None y se ignoran.
"""

from app.channels.base import IncomingMessage


def parse_incoming(payload: dict) -> IncomingMessage | None:
    try:
        value = payload["entry"][0]["changes"][0]["value"]
        message = value["messages"][0]
    except (KeyError, IndexError, TypeError):
        return None  # status update, reaccion, o forma desconocida

    if message.get("type") != "text":
        return None

    return IncomingMessage(
        channel="whatsapp",
        from_number=message["from"],
        text=message["text"]["body"],
        phone_number_id=value["metadata"]["phone_number_id"],
        external_id=message["id"],
    )
