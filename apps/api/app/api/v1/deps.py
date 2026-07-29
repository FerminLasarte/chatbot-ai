"""Dependencias compartidas.

`get_current_tenant` es el unico punto donde se resuelve de que cliente es una
peticion. Todo lo que toque datos aguas abajo recibe ese tenant como dependencia,
nunca lo deduce por su cuenta.
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import tenant_id_ctx
from app.db.session import get_db
from app.models.tenant import Tenant

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_tenant(
    db: DbSession,
    x_tenant_slug: Annotated[str | None, Header()] = None,
) -> Tenant:
    """Resuelve el tenant para peticiones del dashboard y del widget web.

    Los webhooks de WhatsApp NO pasan por aca: resuelven el tenant por
    phone_number_id (ver channels/whatsapp/parser.py).

    TODO antes de produccion: reemplazar el header por una API key firmada por
    tenant. Hoy cualquiera que conozca el slug puede consultar.
    """
    if not x_tenant_slug:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "falta el header X-Tenant-Slug")

    tenant = await db.scalar(
        select(Tenant).where(Tenant.slug == x_tenant_slug, Tenant.is_active.is_(True))
    )
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant no encontrado")

    tenant_id_ctx.set(str(tenant.id))
    return tenant


CurrentTenant = Annotated[Tenant, Depends(get_current_tenant)]
