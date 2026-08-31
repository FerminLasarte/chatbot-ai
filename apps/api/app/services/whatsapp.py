"""Credenciales de WhatsApp por cliente.

Unico lugar que cifra y descifra el access token. El resto del codigo maneja el
token en claro solo el tiempo que dura un envio, o el texto cifrado tal cual
sale de la base -nunca hace la conversion por su cuenta-.
"""

import hashlib
import hmac
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.whatsapp import client
from app.core.cifrado import cifrar, descifrar
from app.core.config import settings
from app.core.retry import RetryableHTTPError
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)


class NumeroYaAsignado(Exception):
    """Ese phone_number_id ya es de otro cliente.

    No se puede permitir: el webhook resuelve a que cliente pertenece un mensaje
    entrante justamente por ese numero (ver routes/webhooks.py).
    """


def guardar_token(tenant: Tenant, token: str | None) -> None:
    """Cifra y asigna el token. `None` o vacio lo borra.

    No hace commit: queda a cargo de quien maneja la transaccion.
    """
    tenant.whatsapp_access_token_cifrado = cifrar(token) if token else None


def leer_token(tenant: Tenant) -> str | None:
    """Token en claro, o None si el cliente no tiene uno cargado."""
    if not tenant.whatsapp_access_token_cifrado:
        return None
    return descifrar(tenant.whatsapp_access_token_cifrado)


def tiene_whatsapp(tenant: Tenant) -> bool:
    """Si le falta cualquiera de las dos partes, el canal no funciona."""
    return bool(tenant.whatsapp_phone_number_id and tenant.whatsapp_access_token_cifrado)


def pin_de_registro(tenant_id: uuid.UUID) -> str:
    """El PIN de verificacion en dos pasos del numero de un cliente.

    Se DERIVA en vez de guardarse: mismo cliente, mismo PIN, siempre. Asi no hay
    que sumar una columna para un dato que solo se usa al registrar el numero, y
    no queda un secreto mas dando vueltas en la base.

    Sale de JWT_SECRET, asi que no es adivinable desde afuera ni esta escrito en
    el repo. Contra a tener presente: si algun dia se rota JWT_SECRET, el PIN de
    los clientes ya dados de alta cambia y hay que resetearlo desde Meta si
    hiciera falta volver a registrar el numero.
    """
    digest = hmac.new(
        settings.jwt_secret.encode(), b"whatsapp-pin:" + str(tenant_id).encode(), hashlib.sha256
    ).digest()
    # 6 digitos es lo que pide Meta. int.from_bytes sobre 4 bytes da de sobra.
    return f"{int.from_bytes(digest[:4], 'big') % 1_000_000:06d}"


@dataclass(frozen=True)
class Alta:
    """Resultado de conectar un WhatsApp por Embedded Signup."""

    phone_number_id: str
    # El alta quedo usable, pero hay algo que conviene mirar. Hoy solo lo usa el
    # registro del numero: ver `conectar_desde_signup`.
    advertencia: str | None = None


# Lo que contesta Meta al intentar registrar un numero que vino por
# coexistence: "Register endpoint is not available for SMB businesses." Se
# compara por el pedazo estable del mensaje y no por el codigo de error, que es
# el generico 100 y lo comparte con media docena de fallas distintas.
_RECHAZO_ESPERABLE = "not available for smb"


def _es_alta_de_coexistence(exc: Exception) -> bool:
    """El registro fallo porque el numero ya vive en la app del celular."""
    return _RECHAZO_ESPERABLE in str(exc).lower()


async def conectar_desde_signup(
    db: AsyncSession, tenant: Tenant, *, code: str, waba_id: str, phone_number_id: str
) -> Alta:
    """Completa el alta con lo que devolvio el popup de Facebook.

    ★ EL ORDEN NO ES ARBITRARIO. Todo lo que puede fallar ocurre ANTES de tocar
    la fila del cliente, y recien al final se guarda. Asi el cliente nunca queda
    "a medio conectar": o tiene un WhatsApp que funciona, o sigue sin WhatsApp y
    puede reintentar con el mismo link. Un alta a medias es peor que ninguna,
    porque el panel la muestra como lista y los mensajes igual no llegan.

    La unica excepcion es el registro del numero, que va como advertencia: falla
    cuando el cliente ya tenia puesta la verificacion en dos pasos con otro PIN,
    y en ese caso todo lo demas quedo bien —conviene guardar y avisar, no tirar
    el alta entera y hacerlo empezar de cero.
    """
    # 1. El numero tiene que estar libre. Esto se comprueba primero porque es lo
    #    unico que podemos saber sin gastar el `code`, que es de un solo uso.
    ocupado = await db.scalar(
        select(Tenant).where(
            Tenant.whatsapp_phone_number_id == phone_number_id, Tenant.id != tenant.id
        )
    )
    if ocupado is not None:
        raise NumeroYaAsignado(
            "ese numero de WhatsApp ya esta conectado a otro cliente. "
            "Si es tuyo, avisale a quien te paso el link."
        )

    # 2. Canje del code por el token del cliente (server-to-server, con App Secret).
    token = await client.canjear_code_por_token(code)

    # 3. Suscripcion del webhook. Si esto falla no se guarda nada: un cliente con
    #    token pero sin webhook no recibe un solo mensaje y nadie se entera.
    await client.suscribir_webhook(waba_id, token)

    # 4. Registro del numero. Best effort, ver el docstring.
    advertencia: str | None = None
    try:
        await client.registrar_numero(phone_number_id, token, pin_de_registro(tenant.id))
    except (client.AltaWhatsAppError, RetryableHTTPError) as exc:
        if _es_alta_de_coexistence(exc):
            # No es un fallo: el numero venia de la app WhatsApp Business y ya
            # quedo registrado por ese vinculo. Meta rechaza el endpoint aposta.
            # Sin esta rama, un alta perfecta termina con un cartel que manda al
            # cliente a buscar una verificacion en dos pasos que no existe.
            logger.info(
                "el numero del cliente %s viene de la app WhatsApp Business: "
                "no hace falta registrarlo",
                tenant.id,
            )
        else:
            logger.warning("no se pudo registrar el numero del cliente %s: %s", tenant.id, exc)
            advertencia = (
                "El numero quedo conectado, pero Meta no acepto registrarlo automaticamente. "
                "Suele pasar cuando el numero ya tenia verificacion en dos pasos. "
                "Avisale a quien te paso el link antes de empezar a usarlo."
            )

    # 5. Recien aca se toca la fila del cliente.
    guardar_token(tenant, token)
    tenant.whatsapp_phone_number_id = phone_number_id
    tenant.whatsapp_waba_id = waba_id
    await db.commit()

    return Alta(phone_number_id=phone_number_id, advertencia=advertencia)
