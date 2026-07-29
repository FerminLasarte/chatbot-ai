"""Dependencias compartidas: autenticacion, scopes y resolucion de tenant.

Este es el punto donde se decide de quien es una peticion. Todo lo que toque
datos aguas abajo recibe el tenant como dependencia, nunca lo deduce por su cuenta.

Los webhooks de WhatsApp NO pasan por aca: se autentican con la firma HMAC de
Meta y resuelven el tenant por phone_number_id (ver routes/webhooks.py).
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import tenant_id_ctx
from app.core.security import KEY_PREFIX_LEN, verify_api_key
from app.db.session import get_db
from app.models.api_key import ApiKey, Scope
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)

DbSession = Annotated[AsyncSession, Depends(get_db)]

# auto_error=False para responder siempre el mismo 401 generico: que falte el
# header y que la clave sea invalida no deben distinguirse desde afuera.
_bearer = HTTPBearer(auto_error=False, description="API key: Authorization: Bearer cba_...")

_CREDENCIAL_INVALIDA = HTTPException(
    status.HTTP_401_UNAUTHORIZED,
    "credenciales invalidas",
    headers={"WWW-Authenticate": "Bearer"},
)

# Cada cuanto refrescamos last_used_at. Escribir en cada request seria un write
# por peticion para un dato que solo sirve para auditar claves abandonadas.
_INTERVALO_LAST_USED = timedelta(hours=1)


async def get_api_key(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> ApiKey:
    """Autentica la peticion y devuelve la clave usada."""
    if credentials is None or not credentials.credentials:
        raise _CREDENCIAL_INVALIDA

    raw = credentials.credentials
    # Buscamos por prefijo (indexado). El prefijo no es secreto: identifica la
    # fila sin permitir deducir el resto de la clave.
    key = await db.scalar(
        select(ApiKey)
        .where(ApiKey.key_prefix == raw[:KEY_PREFIX_LEN])
        .options(selectinload(ApiKey.tenant))
    )

    # Mismo error para "no existe", "revocada", "vencida" y "hash no coincide":
    # no le damos pistas a quien esta probando claves.
    if key is None or not verify_api_key(raw, key.key_hash) or not key.is_active:
        raise _CREDENCIAL_INVALIDA

    if key.tenant_id is not None:
        # Una clave de un cliente desactivado no sirve, aunque la clave este viva.
        if key.tenant is None or not key.tenant.is_active:
            raise _CREDENCIAL_INVALIDA
        tenant_id_ctx.set(str(key.tenant_id))

    await _tocar_last_used(db, key)
    return key


async def _tocar_last_used(db: AsyncSession, key: ApiKey) -> None:
    """Mejor esfuerzo: si falla, no rompe la peticion."""
    ahora = datetime.now(UTC)
    if key.last_used_at is not None and ahora - key.last_used_at < _INTERVALO_LAST_USED:
        return
    try:
        key.last_used_at = ahora
        await db.commit()
    except Exception:  # noqa: BLE001
        logger.warning("no se pudo actualizar last_used_at", exc_info=True)
        await db.rollback()


def require_scopes(*required: Scope) -> Callable[[ApiKey], Awaitable[ApiKey]]:
    """Fabrica una dependencia que exige al menos uno de los scopes indicados.

    `admin` NO abre todas las puertas por si solo: una clave admin no tiene
    tenant, asi que no puede usar los endpoints que operan sobre un cliente.
    Es a proposito — evita que una clave con permisos amplios opere sobre datos
    de un cliente sin decir explicitamente cual.
    """
    permitidos = {s.value for s in required}

    async def dependency(key: Annotated[ApiKey, Depends(get_api_key)]) -> ApiKey:
        if not permitidos.intersection(key.scopes):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"esta clave no tiene permiso para esta operacion (requiere: {sorted(permitidos)})",
            )
        return key

    return dependency


async def get_current_tenant(
    key: Annotated[ApiKey, Depends(get_api_key)],
) -> Tenant:
    """El tenant sale de la clave, no de un header que cualquiera puede escribir."""
    if key.tenant_id is None or key.tenant is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "esta clave no esta asociada a ningun cliente",
        )
    return key.tenant


CurrentTenant = Annotated[Tenant, Depends(get_current_tenant)]
AdminKey = Annotated[ApiKey, Depends(require_scopes(Scope.ADMIN))]
TenantKey = Annotated[ApiKey, Depends(require_scopes(Scope.TENANT))]
ChatKey = Annotated[ApiKey, Depends(require_scopes(Scope.TENANT, Scope.CHAT))]
