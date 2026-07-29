"""Reclamo y cierre de mensajes entrantes (idempotencia del webhook)."""

import logging
import uuid

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import EventStatus, ProcessedEvent

logger = logging.getLogger(__name__)


async def claim(
    db: AsyncSession,
    channel: str,
    external_id: str,
    tenant_id: uuid.UUID | None = None,
) -> uuid.UUID | None:
    """Intenta reclamar un mensaje para procesarlo.

    Devuelve el id de la fila si lo reclamamos nosotros, o None si ya estaba
    reclamado (o sea: es una reentrega y hay que ignorarla).

    El reclamo es un INSERT con ON CONFLICT DO NOTHING: es atomico. Un
    `SELECT` previo seguido de `INSERT` tendria una carrera entre dos entregas
    simultaneas del mismo mensaje.
    """
    stmt = (
        insert(ProcessedEvent)
        .values(
            channel=channel,
            external_id=external_id,
            tenant_id=tenant_id,
            status=EventStatus.PENDING.value,
            attempts=1,
        )
        .on_conflict_do_nothing(index_elements=["channel", "external_id"])
        .returning(ProcessedEvent.id)
    )
    event_id = await db.scalar(stmt)
    await db.commit()

    if event_id is None:
        logger.info("mensaje duplicado ignorado", extra={"external_id": external_id})
    return event_id


async def mark_done(db: AsyncSession, event_id: uuid.UUID) -> None:
    await db.execute(
        update(ProcessedEvent)
        .where(ProcessedEvent.id == event_id)
        .values(status=EventStatus.DONE.value, error=None)
    )
    await db.commit()


async def mark_failed(db: AsyncSession, event_id: uuid.UUID, error: str) -> None:
    """Deja la falla registrada para poder verla y reintentarla despues."""
    await db.execute(
        update(ProcessedEvent)
        .where(ProcessedEvent.id == event_id)
        .values(status=EventStatus.FAILED.value, error=error[:2000])
    )
    await db.commit()
