"""Verificacion de firmas de webhook y emision/validacion de API keys."""

import hashlib
import hmac
import secrets

from app.core.config import settings

# cba = chatbot-ai. El sufijo distingue produccion de desarrollo para que una
# clave de test no pase inadvertida en produccion (y para poder buscarlas en logs).
KEY_PREFIX_LEN = 16


def verify_meta_signature(payload: bytes, header: str | None) -> bool:
    """Valida el header X-Hub-Signature-256 de los webhooks de Meta.

    Meta firma el cuerpo crudo con HMAC-SHA256 usando el App Secret. Hay que
    verificar contra los bytes exactos del request, no contra el JSON re-serializado.
    """
    if not header or not header.startswith("sha256="):
        return False
    if not settings.whatsapp_app_secret:
        return False

    expected = hmac.new(settings.whatsapp_app_secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------


def hash_api_key(raw_key: str) -> str:
    """Hash de la clave para guardar en la base.

    SHA-256 a proposito, NO bcrypt/argon2.

    Esos algoritmos son deliberadamente lentos para frenar la fuerza bruta sobre
    contrasenas humanas, que tienen poca entropia. Una API key nuestra son 32
    bytes de `secrets.token_urlsafe`: ~256 bits de entropia real. No hay fuerza
    bruta posible contra eso, asi que el costo de bcrypt no compraria seguridad
    — solo agregaria ~100 ms a CADA request autenticado.

    Al reves tambien es un error: guardar la clave en texto plano. Con hash, una
    filtracion de la tabla no da acceso a nadie.
    """
    return hashlib.sha256(raw_key.encode()).hexdigest()


def generate_api_key(entorno: str | None = None) -> tuple[str, str, str]:
    """Emite una clave nueva.

    Devuelve (clave_completa, prefijo, hash). La clave completa se muestra UNA
    sola vez a quien la pide; nosotros solo persistimos prefijo y hash.

    El prefijo es la parte publica: sirve para encontrar la fila por indice
    (en lugar de hashear toda la tabla en cada request) y para que en el
    dashboard se pueda identificar la clave sin revelarla.
    """
    marca = "live" if (entorno or settings.environment) == "production" else "test"
    raw = f"cba_{marca}_{secrets.token_urlsafe(32)}"
    return raw, raw[:KEY_PREFIX_LEN], hash_api_key(raw)


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    """Comparacion en tiempo constante: no filtra informacion por el tiempo."""
    return hmac.compare_digest(hash_api_key(raw_key), stored_hash)
