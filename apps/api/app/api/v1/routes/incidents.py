"""Que mensajes no se llegaron a contestar.

Es la vista de monitoreo mas barata que hay: los fallos ya se venian guardando
en `processed_events` desde siempre, con indice por estado incluido. Lo unico
que faltaba era leerlos.

Sin esto, un bot roto es invisible —el cliente escribe, el mensaje falla, y la
agencia se entera cuando el cliente reclama-.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.v1.deps import AdminKey, DbSession
from app.schemas.chat import IncidentRead
from app.services import inbox

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=list[IncidentRead])
async def listar_incidentes(
    db: DbSession,
    _: AdminKey,
    tenant_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[IncidentRead]:
    """Mensajes fallados o colgados, de todos los clientes o de uno solo.

    Sin filtro alcanza para el semaforo de la lista del panel; con `tenant_id`,
    para el detalle de un cliente. Un endpoint sirve a las dos vistas.
    """
    return [
        IncidentRead(
            id=str(i.id),
            tenant_id=str(i.tenant_id) if i.tenant_id else None,
            channel=i.channel,
            external_id=i.external_id,
            status=i.status,
            attempts=i.attempts,
            error=i.error,
            minutos=i.minutos,
        )
        for i in await inbox.incidentes(db, tenant_id)
    ]
