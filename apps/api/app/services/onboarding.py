"""El pase que le damos al cliente para que conecte su WhatsApp solo.

QUE ES ESTO
-----------
El cliente no tiene usuario en el panel: el panel es de la agencia. Para que
igual pueda conectar su numero sin que nadie le pida credenciales, se le manda
un link con un token firmado que dice "esta persona puede conectarle un WhatsApp
al cliente X, hasta tal fecha".

POR QUE FIRMADO Y NO UNA FILA EN LA BASE
----------------------------------------
Un token firmado se valida con la clave que ya tenemos y no necesita tabla ni
migracion. La contra de no tener estado es que no se puede invalidar uno por uno
antes de que venza; se compensa con un vencimiento corto (ver
`onboarding_link_ttl_hours`) y con que el alcance del token es minimo.

QUE PUEDE HACER EL QUE TENGA EL LINK
------------------------------------
Solo dos cosas: ver el nombre del cliente y conectarle un WhatsApp. No lee
conversaciones, ni documentos, ni el consumo, y no sirve para ningun otro
endpoint. El peor caso de un link filtrado es que un tercero le conecte SU
propio numero de WhatsApp al cliente —molesto y visible, no una fuga de datos—.
Y ni siquiera eso si el cliente ya conecto el suyo: los endpoints se niegan a
pisar un WhatsApp ya configurado (ver routes/onboarding.py).
"""

import base64
import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.config import settings

# Separacion de dominio: se mezcla en la firma para que un token de onboarding
# no pueda pasar por un token de otra cosa firmada con el mismo JWT_SECRET (ni
# al reves). El sufijo de version permite rotar el formato sin aceptar los viejos.
_DOMINIO = b"onboarding-whatsapp-v1"


class LinkInvalido(Exception):
    """El token no existe, esta mal formado o la firma no coincide."""


class LinkVencido(LinkInvalido):
    """El token es autentico pero ya paso su fecha de vencimiento."""


@dataclass(frozen=True)
class Link:
    """Un link recien emitido, listo para mandarle al cliente."""

    url: str
    token: str
    expira_at: datetime


def _b64(datos: bytes) -> str:
    """base64url sin '=': el token va en una URL y el padding hay que escaparlo."""
    return base64.urlsafe_b64encode(datos).decode().rstrip("=")


def _des_b64(texto: str) -> bytes:
    # Se devuelve el padding que se saco al codificar.
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def _firmar(payload: bytes) -> str:
    return _b64(hmac.new(settings.jwt_secret.encode(), _DOMINIO + payload, hashlib.sha256).digest())


def emitir(tenant_id: uuid.UUID, *, horas: int | None = None) -> Link:
    """Arma el link que la agencia le pasa al cliente."""
    ttl = horas if horas is not None else settings.onboarding_link_ttl_hours
    expira = datetime.now(UTC) + timedelta(hours=ttl)

    payload = json.dumps(
        {"tid": str(tenant_id), "exp": int(expira.timestamp())},
        separators=(",", ":"),  # sin espacios: el token va en una URL
    ).encode()

    token = f"{_b64(payload)}.{_firmar(payload)}"
    base = settings.onboarding_base_url.rstrip("/")
    return Link(url=f"{base}/onboarding/{token}", token=token, expira_at=expira)


def verificar(token: str) -> uuid.UUID:
    """Devuelve el tenant al que apunta el token, o levanta excepcion.

    ★ El orden importa: primero la firma, despues el vencimiento. Al reves se le
    estaria contando a quien prueba tokens inventados si acerto el formato.
    """
    partes = token.split(".")
    if len(partes) != 2:
        raise LinkInvalido("el link no tiene el formato esperado")

    payload_b64, firma = partes
    try:
        payload = _des_b64(payload_b64)
    except (ValueError, TypeError) as exc:
        raise LinkInvalido("el link esta mal formado") from exc

    # compare_digest y no '==': una comparacion normal corta en el primer byte
    # distinto, y ese tiempo alcanza para ir adivinando la firma byte a byte.
    if not hmac.compare_digest(_firmar(payload), firma):
        raise LinkInvalido("el link no es valido")

    try:
        datos = json.loads(payload)
        tenant_id = uuid.UUID(datos["tid"])
        exp = int(datos["exp"])
    except (ValueError, KeyError, TypeError) as exc:
        raise LinkInvalido("el link esta mal formado") from exc

    if datetime.now(UTC).timestamp() > exp:
        raise LinkVencido("el link vencio, pedile uno nuevo a quien te lo mando")

    return tenant_id
