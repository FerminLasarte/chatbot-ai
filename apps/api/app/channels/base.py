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


@dataclass(frozen=True)
class OutgoingEcho:
    """Un mensaje que salio del numero del negocio SIN pasar por nosotros.

    Es lo que trae coexistence: el duenio del comercio contesta a mano desde la
    app del celular y Meta nos avisa. Va en un tipo aparte y no en
    `IncomingMessage` con un campo `direccion` a proposito: quien lo recibe
    tiene que ramificar, porque tratar uno como el otro es justamente el error
    caro —contestarle al duenio como si fuera un cliente, o pausar el bot con
    la respuesta del propio bot—.

    `to_number` es el usuario final, y es la identidad de la conversacion: en
    un echo, `from` es el numero del comercio y no distingue un hilo de otro.
    """

    channel: str
    to_number: str
    text: str
    phone_number_id: str
    external_id: str


class ChannelAdapter(Protocol):
    def parse_incoming(self, payload: dict) -> IncomingMessage | None: ...

    async def send_message(self, to: str, text: str) -> None: ...
