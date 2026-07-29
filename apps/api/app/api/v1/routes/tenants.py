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
from app.core.security import generate_api_key
from app.models.api_key import ApiKey, Scope
from app.models.tenant import Tenant
from app.schemas.chat import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyRead,
    PromptUpdate,
    TenantCreate,
    TenantRead,
)

router = APIRouter(prefix="/tenants", tags=["tenants"])


def _to_read(t: Tenant) -> TenantRead:
    return TenantRead(
        id=str(t.id),
        slug=t.slug,
        name=t.name,
        system_prompt=t.system_prompt,
        is_active=t.is_active,
    )


# ---------------------------------------------------------------------------
# Operaciones de la agencia
# ---------------------------------------------------------------------------


@router.post("", response_model=TenantRead, status_code=status.HTTP_201_CREATED)
async def create_tenant(payload: TenantCreate, db: DbSession, _: AdminKey) -> TenantRead:
    if await db.scalar(select(Tenant).where(Tenant.slug == payload.slug)):
        raise HTTPException(status.HTTP_409_CONFLICT, "ya existe un cliente con ese slug")

    tenant = Tenant(**payload.model_dump())
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


# ---------------------------------------------------------------------------
# Operaciones del propio cliente
# ---------------------------------------------------------------------------


@router.get("/me", response_model=TenantRead)
async def read_me(tenant: CurrentTenant, _: TenantKey) -> TenantRead:
    return _to_read(tenant)


@router.patch("/me/prompt", response_model=TenantRead)
async def update_prompt(
    payload: PromptUpdate, tenant: CurrentTenant, db: DbSession, _: TenantKey
) -> TenantRead:
    """Editar el System Prompt del cliente. Sin deploy: es una fila en la DB."""
    tenant.system_prompt = payload.system_prompt
    await db.commit()
    await db.refresh(tenant)
    return _to_read(tenant)
