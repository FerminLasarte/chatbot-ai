"""Gestion de clientes y emision de sus claves.

Reparto de permisos:
  admin   crear/listar clientes, emitir y revocar claves
  tenant  leer y editar la configuracion del propio cliente
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.v1.deps import AdminKey, CurrentTenant, DbSession, TenantKey
from app.core.config import settings
from app.core.security import generate_api_key
from app.models.api_key import ApiKey, Scope
from app.models.tenant import Tenant
from app.schemas.chat import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyRead,
    LimitUpdate,
    PromptUpdate,
    TenantCreate,
    TenantRead,
    UsageRead,
)
from app.services import quota

router = APIRouter(prefix="/tenants", tags=["tenants"])


def _to_read(t: Tenant) -> TenantRead:
    return TenantRead(
        id=str(t.id),
        slug=t.slug,
        name=t.name,
        system_prompt=t.system_prompt,
        is_active=t.is_active,
        monthly_message_limit=t.monthly_message_limit,
    )


# ---------------------------------------------------------------------------
# Operaciones del propio cliente
#
# ORDEN IMPORTANTE: estas rutas literales (/me, /me/usage) van ANTES que las
# parametrizadas (/{tenant_id}/...). FastAPI matchea en orden de declaracion:
# si /{tenant_id}/usage se declara primero, una peticion a /me/usage entra por
# ahi con tenant_id='me' y pide clave admin, devolviendo 403 al cliente.
# ---------------------------------------------------------------------------


def _to_usage(c: quota.Consumo) -> UsageRead:
    return UsageRead(
        period=c.period,
        messages=c.messages,
        limit=c.limit,
        remaining=c.remaining,
        input_tokens=c.input_tokens,
        output_tokens=c.output_tokens,
        cache_read_tokens=c.cache_read_tokens,
    )


@router.get("/me", response_model=TenantRead)
async def read_me(tenant: CurrentTenant, _: TenantKey) -> TenantRead:
    return _to_read(tenant)


@router.get("/me/usage", response_model=UsageRead)
async def read_my_usage(tenant: CurrentTenant, db: DbSession, _: TenantKey) -> UsageRead:
    """El cliente ve su consumo, pero no puede cambiar su limite."""
    return _to_usage(await quota.consumo_actual(db, tenant))


@router.patch("/me/prompt", response_model=TenantRead)
async def update_prompt(
    payload: PromptUpdate, tenant: CurrentTenant, db: DbSession, _: TenantKey
) -> TenantRead:
    """Editar el System Prompt del cliente. Sin deploy: es una fila en la DB."""
    tenant.system_prompt = payload.system_prompt
    await db.commit()
    await db.refresh(tenant)
    return _to_read(tenant)


# ---------------------------------------------------------------------------
# Operaciones de la agencia
# ---------------------------------------------------------------------------


@router.post("", response_model=TenantRead, status_code=status.HTTP_201_CREATED)
async def create_tenant(payload: TenantCreate, db: DbSession, _: AdminKey) -> TenantRead:
    if await db.scalar(select(Tenant).where(Tenant.slug == payload.slug)):
        raise HTTPException(status.HTTP_409_CONFLICT, "ya existe un cliente con ese slug")

    datos = payload.model_dump()
    # Nunca crear un cliente sin tope: con precio plano, eso deja el margen
    # expuesto desde el minuto cero.
    if datos.get("monthly_message_limit") is None:
        datos["monthly_message_limit"] = settings.default_monthly_message_limit
    tenant = Tenant(**datos)
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return _to_read(tenant)


@router.get("", response_model=list[TenantRead])
async def list_tenants(db: DbSession, _: AdminKey) -> list[TenantRead]:
    result = await db.execute(select(Tenant).order_by(Tenant.created_at.desc()))
    return [_to_read(t) for t in result.scalars().all()]


@router.post(
    "/{tenant_id}/keys",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
)
async def issue_key(
    tenant_id: uuid.UUID, payload: ApiKeyCreate, db: DbSession, _: AdminKey
) -> ApiKeyCreated:
    """Emite una clave para un cliente. El secreto se devuelve UNA sola vez."""
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cliente no encontrado")

    if Scope.ADMIN in payload.scopes:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "una clave de cliente no puede tener scope admin",
        )

    raw, prefix, hashed = generate_api_key()
    key = ApiKey(
        name=payload.name,
        key_prefix=prefix,
        key_hash=hashed,
        tenant_id=tenant.id,
        scopes=[s.value for s in payload.scopes],
        expires_at=payload.expires_at,
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)

    return ApiKeyCreated(
        id=str(key.id),
        name=key.name,
        key_prefix=key.key_prefix,
        scopes=key.scopes,
        api_key=raw,  # unica vez que se ve
    )


@router.get("/{tenant_id}/keys", response_model=list[ApiKeyRead])
async def list_keys(tenant_id: uuid.UUID, db: DbSession, _: AdminKey) -> list[ApiKeyRead]:
    result = await db.execute(
        select(ApiKey).where(ApiKey.tenant_id == tenant_id).order_by(ApiKey.created_at.desc())
    )
    return [
        ApiKeyRead(
            id=str(k.id),
            name=k.name,
            key_prefix=k.key_prefix,
            scopes=k.scopes,
            is_active=k.is_active,
            last_used_at=k.last_used_at,
        )
        for k in result.scalars().all()
    ]


@router.delete("/{tenant_id}/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_key(tenant_id: uuid.UUID, key_id: uuid.UUID, db: DbSession, _: AdminKey) -> None:
    """Revoca sin borrar: la fila queda como registro de que existio."""
    key = await db.get(ApiKey, key_id)
    if key is None or key.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "clave no encontrada")

    key.revoked_at = datetime.now(UTC)
    await db.commit()


@router.patch("/{tenant_id}/limit", response_model=TenantRead)
async def update_limit(
    tenant_id: uuid.UUID, payload: LimitUpdate, db: DbSession, _: AdminKey
) -> TenantRead:
    """Ajusta la cuota mensual. Solo la agencia: el cliente no se sube el techo."""
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cliente no encontrado")

    tenant.monthly_message_limit = payload.monthly_message_limit
    await db.commit()
    await db.refresh(tenant)
    return _to_read(tenant)


@router.get("/{tenant_id}/usage", response_model=UsageRead)
async def read_usage_admin(tenant_id: uuid.UUID, db: DbSession, _: AdminKey) -> UsageRead:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cliente no encontrado")
    return _to_usage(await quota.consumo_actual(db, tenant))
