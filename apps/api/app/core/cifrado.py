"""Cifrado simetrico para credenciales de terceros guardadas en la base.

POR QUE CIFRAR ESTO Y NO LAS API KEYS NUESTRAS
----------------------------------------------
Nuestras claves se guardan HASHEADAS (ver core/security.py): nunca necesitamos
el valor original, solo comparar. Con el access token de WhatsApp es al reves:
hay que enviarselo a Meta en cada mensaje, asi que tiene que poder recuperarse.

Un hash no sirve, y texto plano tampoco: ese token permite enviar mensajes en
nombre del negocio del cliente. Si un backup de la base se filtra, quien lo
tenga puede escribirle a los clientes de nuestro cliente. Cifrar de este lado
hace que un volcado de la base, por si solo, no alcance.
"""

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class CifradoNoConfigurado(Exception):
    """Falta ENCRYPTION_KEY: no se puede guardar ni leer una credencial."""


class CifradoInvalido(Exception):
    """El dato no se pudo descifrar con la clave actual."""


def _fernet() -> Fernet:
    if not settings.encryption_key:
        raise CifradoNoConfigurado(
            "ENCRYPTION_KEY esta vacia. Generala con: "
            'python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
    try:
        return Fernet(settings.encryption_key.encode())
    except (ValueError, TypeError) as exc:
        raise CifradoNoConfigurado(f"ENCRYPTION_KEY con formato invalido: {exc}") from exc


def cifrar(texto: str) -> str:
    return _fernet().encrypt(texto.encode()).decode()


def descifrar(cifrado: str) -> str:
    """Levanta CifradoInvalido si la clave cambio o el dato esta corrupto.

    Es a proposito que falle ruidosamente: devolver un token vacio haria que el
    envio fallara despues, con un error de Meta que no dice nada del motivo real.
    """
    try:
        return _fernet().decrypt(cifrado.encode()).decode()
    except InvalidToken as exc:
        raise CifradoInvalido(
            "no se pudo descifrar la credencial: ¿cambio ENCRYPTION_KEY?"
        ) from exc
