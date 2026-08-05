"""Credenciales de WhatsApp por cliente.

Unico lugar que cifra y descifra el access token. El resto del codigo maneja el
token en claro solo el tiempo que dura un envio, o el texto cifrado tal cual
sale de la base -nunca hace la conversion por su cuenta-.
"""

from app.core.cifrado import cifrar, descifrar
from app.models.tenant import Tenant


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
