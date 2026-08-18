"""Payload de la Cloud API de Meta -> tipos internos.

Meta manda muchos eventos que no son mensajes de texto (statuses de entrega,
reacciones, lecturas). Todos esos devuelven None y se ignoran.

Con coexistence activo aparece ademas un campo nuevo, `smb_message_echoes`: los
mensajes que el duenio del comercio escribe A MANO desde la app del celular,
con el mismo numero que usa el bot. Ver docs/coexistence.md.
"""

from app.channels.base import IncomingMessage, OutgoingEcho

CANAL = "whatsapp"

# Espacio de ids separado del entrante a proposito. La unicidad de
# `processed_events` es por (channel, external_id): con un canal propio, el id
# de un echo no puede colisionar nunca con el de un mensaje del usuario final.
CANAL_ECHO = "whatsapp_echo"

CAMPO_MENSAJES = "messages"
CAMPO_ECHOES = "smb_message_echoes"


def campo_del_evento(payload: dict) -> str | None:
    """Que clase de evento manda Meta (`messages`, `smb_message_echoes`, ...).

    None si el payload no tiene la forma esperada o si el campo no viene.
    """
    cambio = _cambio(payload)
    return cambio[0] if cambio is not None else None


def parse_incoming(payload: dict) -> IncomingMessage | None:
    cambio = _cambio(payload)
    if cambio is None:
        return None
    campo, value = cambio

    # ★ El filtro por campo NO es opcional cuando hay coexistence. Un echo tiene
    # una forma parecida a la de un mensaje entrante, pero lo escribio el propio
    # comercio: leerlo por esta puerta seria contestarle al duenio como si fuera
    # un cliente, y cobrarle el turno. Un payload sin `field` (los de los tests,
    # y cualquier forma vieja) sigue entrando: el filtro descarta lo que se
    # identifica como otra cosa, no lo que no se identifica.
    if campo is not None and campo != CAMPO_MENSAJES:
        return None

    try:
        message = value["messages"][0]
    except (KeyError, IndexError, TypeError):
        return None  # status update, reaccion, o forma desconocida

    if message.get("type") != "text":
        return None

    return IncomingMessage(
        channel=CANAL,
        from_number=message["from"],
        text=message["text"]["body"],
        phone_number_id=value["metadata"]["phone_number_id"],
        external_id=message["id"],
    )


def parse_echo(payload: dict) -> OutgoingEcho | None:
    """Un mensaje que el comercio mando desde la app del celular.

    ★ La forma exacta de este payload NO esta confirmada contra un evento real
    de Meta (ver docs/coexistence.md). Por eso se lee campo por campo y con
    `.get()`: si algo no viene como se espera devuelve None y el webhook lo
    deja registrado crudo en el log, en vez de romper o -peor- de actuar sobre
    una lectura equivocada.
    """
    cambio = _cambio(payload)
    if cambio is None:
        return None
    campo, value = cambio
    if campo != CAMPO_ECHOES:
        return None

    # Meta documenta la lista como `message_echoes`. Se acepta tambien
    # `messages` porque es la unica variacion esperable mientras no haya un
    # payload real a la vista, y equivocarse ahi significaria ignorar en
    # silencio todos los mensajes manuales.
    lista = value.get("message_echoes") or value.get("messages")
    if not isinstance(lista, list) or not lista:
        return None

    echo = lista[0]
    if not isinstance(echo, dict) or echo.get("type") != "text":
        return None

    texto = echo.get("text")
    metadata = value.get("metadata")
    destinatario = echo.get("to")
    external_id = echo.get("id")
    cuerpo = texto.get("body") if isinstance(texto, dict) else None
    phone_number_id = metadata.get("phone_number_id") if isinstance(metadata, dict) else None

    if not (destinatario and cuerpo and external_id and phone_number_id):
        return None

    return OutgoingEcho(
        channel=CANAL_ECHO,
        to_number=str(destinatario),
        text=str(cuerpo),
        phone_number_id=str(phone_number_id),
        external_id=str(external_id),
    )


def _cambio(payload: dict) -> tuple[str | None, dict] | None:
    """(campo, value) del primer cambio del payload, o None si no tiene forma."""
    try:
        change = payload["entry"][0]["changes"][0]
        value = change["value"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(value, dict):
        return None
    campo = change.get("field")
    return (campo if isinstance(campo, str) else None), value
