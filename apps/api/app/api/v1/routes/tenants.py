"""CRUD de clientes. Lo consume el dashboard de Next.js."""

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.v1.deps import CurrentTenant, DbSession
from app.models.tenant import Tenant
from app.schemas.chat import TenantCreate, TenantRead

router = APIRouter(prefix="/tenants", tags=["tenants"])


def _to_read(t: Tenant) -> TenantRead:
    return TenantRead(
        id=str(t.id),
        slug=t.slug,
        name=t.name,
        system_prompt=t.system_prompt,
        is_active=t.is_active,
    )


@router.post("", response_model=TenantRead, status_code=status.HTTP_201_CREATED)
async def create_tenant(payload: TenantCreate, db: DbSession) -> TenantRead:
    """TODO: proteger con auth de admin antes de exponerlo."""
    tenant = Tenant(**payload.model_dump())
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return _to_read(tenant)


@router.get("/me", response_model=TenantRead)
async def read_me(tenant: CurrentTenant) -> TenantRead:
    return _to_read(tenant)


@router.patch("/me/prompt", response_model=TenantRead)
async def update_prompt(system_prompt: str, tenant: CurrentTenant, db: DbSession) -> TenantRead:
    """Editar el System Prompt del cliente. Sin deploy: es una fila en la DB."""
    tenant.system_prompt = system_prompt
    await db.commit()
    await db.refresh(tenant)
    return _to_read(tenant)


@router.get("", response_model=list[TenantRead])
async def list_tenants(db: DbSession) -> list[TenantRead]:
    result = await db.execute(select(Tenant).order_by(Tenant.created_at.desc()))
    return [_to_read(t) for t in result.scalars().all()]
