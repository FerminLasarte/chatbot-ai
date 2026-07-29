"""Verificacion de firmas de webhook y auth del dashboard."""

import hashlib
import hmac

from app.core.config import settings


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
