"""Registro de mensajes entrantes, para idempotencia y observabilidad.

Meta reintenta los webhooks: si no recibimos el 200 a tiempo, o si sospecha que
se perdio, vuelve a mandar el mismo mensaje. Sin deduplicacion el bot responde
dos o tres veces y pagamos esos tokens de mas.

La deduplicacion es por RECLAMO ATOMICO, no por consulta previa:

    INSERT ... ON CONFLICT DO NOTHING  ->  si no inserto, otro lo tomo primero

Un `SELECT` seguido de un `INSERT` tiene una carrera: dos entregas simultaneas
del mismo mensaje pueden ver ambas "no existe" y procesar las dos.

La fila ademas queda como bitacora: que fallo, cuantas veces, y cuando.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class EventStatus(str, enum.Enum):
    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"


class ProcessedEvent(Base):
    __tablename__ = "processed_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel: Mapped[str] = mapped_column(String(32))
    # El ID que asigna el proveedor al mensaje (wamid.xxx en WhatsApp).
    external_id: Mapped[str] = mapped_column(String(255))
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(16), default=EventStatus.PENDING.value)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # La restriccion que hace posible el reclamo atomico.
        Index("uq_processed_events_channel_external_id", "channel", "external_id", unique=True),
        # Para encontrar rapido lo que quedo a medias o fallado.
        Index("ix_processed_events_status", "status"),
    )
