"""Reclamo y cierre de mensajes entrantes (idempotencia del webhook)."""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select, update
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


async def registrar_propio(
    db: AsyncSession,
    channel: str,
    external_id: str,
    tenant_id: uuid.UUID | None = None,
) -> None:
    """Marca un id de mensaje NUESTRO como ya procesado, antes de que llegue.

    ★ Es lo que evita que el bot se auto-pause con coexistence. Si Meta hace
    echo tambien de los mensajes que enviamos por la Cloud API -no esta
    confirmado, ver docs/coexistence.md-, el echo de la respuesta del bot
    llegaria al webhook indistinguible de una que escribio una persona, y el
    bot se callaria a si mismo para siempre.

    Con el id ya reclamado, `claim` devuelve None y el echo se descarta como
    duplicado. Es el mismo mecanismo de la idempotencia, usado al reves: en vez
    de recordar lo que ya procesamos, se anticipa lo que no hay que procesar.

    No levanta: no poder anotar el id no puede tumbar un envio que ya salio.
    """
    stmt = (
        insert(ProcessedEvent)
        .values(
            channel=channel,
            external_id=external_id,
            tenant_id=tenant_id,
            status=EventStatus.DONE.value,
            attempts=0,
        )
        .on_conflict_do_nothing(index_elements=["channel", "external_id"])
    )
    try:
        await db.execute(stmt)
        await db.commit()
    except Exception:  # noqa: BLE001
        logger.exception(
            "no se pudo anotar el id del mensaje propio", extra={"external_id": external_id}
        )


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


# ---------------------------------------------------------------------------
# Que se rompio
#
# La tabla venia guardando los fallos desde el principio -y hasta con un indice
# por estado- pero nadie los leia nunca. Un cliente con el bot roto no se veia
# desde ningun lado: habia que entrar a la base a buscarlo.
# ---------------------------------------------------------------------------

# Un mensaje que sigue `pending` despues de esto no se esta procesando: se
# perdio. `BackgroundTasks` vive en el proceso, asi que un reinicio del
# contenedor entre el 200 a Meta y el fin del procesamiento lo deja colgado
# para siempre (ver docs/architecture.md). 15 minutos es varias veces lo que
# tarda un mensaje normal, asi que no genera falsos positivos.
MINUTOS_PARA_DAR_POR_COLGADO = 15


@dataclass(frozen=True)
class Incidente:
    """Un mensaje entrante que no llego a contestarse."""

    id: uuid.UUID
    tenant_id: uuid.UUID | None
    channel: str
    external_id: str
    status: str
    attempts: int
    error: str | None
    # ★ Los minutos los calcula la API, no el panel. El panel se renderiza en el
    # servidor (Railway, en UTC): si restara fechas por su cuenta mostraria
    # antiguedades que no son las del usuario. Mismo criterio que Conversacion.
    minutos: int


async def incidentes(db: AsyncSession, tenant_id: uuid.UUID | None = None) -> list[Incidente]:
    """Mensajes fallados, mas los que quedaron colgados en `pending`.

    Sin `tenant_id` devuelve los de todos los clientes, que es lo que necesita
    la lista del panel para marcar cual esta roto.
    """
    ahora = datetime.now(UTC)
    corte = ahora - timedelta(minutes=MINUTOS_PARA_DAR_POR_COLGADO)

    condiciones = or_(
        ProcessedEvent.status == EventStatus.FAILED.value,
        and_(
            ProcessedEvent.status == EventStatus.PENDING.value,
            ProcessedEvent.created_at < corte,
        ),
    )
    stmt = select(ProcessedEvent).where(condiciones)
    if tenant_id is not None:
        stmt = stmt.where(ProcessedEvent.tenant_id == tenant_id)

    filas = await db.scalars(stmt.order_by(ProcessedEvent.created_at.desc()).limit(200))

    return [
        Incidente(
            id=f.id,
            tenant_id=f.tenant_id,
            channel=f.channel,
            external_id=f.external_id,
            status=f.status,
            attempts=f.attempts,
            error=f.error,
            minutos=int((ahora - f.created_at).total_seconds() // 60),
        )
        for f in filas
    ]
