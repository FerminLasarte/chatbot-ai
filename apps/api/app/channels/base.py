"""Interfaz de un canal.

Un canal traduce entre el formato del proveedor y el formato interno. Nada mas.
La respuesta del bot no cambia segun el canal: cuando aparezca Instagram o Telegram
se agrega una carpeta al lado, no un `if channel == ...` en los services.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class IncomingMessage:
    """Mensaje entrante normalizado, independiente del proveedor."""

    channel: str
    from_number: str
    text: str
    phone_number_id: str
    external_id: str


class ChannelAdapter(Protocol):
    def parse_incoming(self, payload: dict) -> IncomingMessage | None: ...

    async def send_message(self, to: str, text: str) -> None: ...
