"""Consumo por cliente y por mes.

Una fila agregada por (tenant, periodo) en vez de un evento por mensaje: para
aplicar una cuota alcanza con un contador, y un append-only de un evento por
mensaje seria mucho mas caro de escribir y de consultar.

El periodo es 'YYYY-MM' en UTC. La facturacion es por mes calendario UTC, no por
la zona horaria del cliente: es una sola definicion para todos y no se corre
cuando un cliente esta en otro huso.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def periodo_actual() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


class TenantUsage(Base):
    __tablename__ = "tenant_usage"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    period: Mapped[str] = mapped_column(String(7))

    # Lo que se cuotea.
    messages: Mapped[int] = mapped_column(Integer, default=0)

    # Lo que se factura. BigInteger: los tokens se acumulan rapido.
    input_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(BigInteger, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # Lo que permite el incremento atomico con ON CONFLICT.
        Index("uq_tenant_usage_tenant_period", "tenant_id", "period", unique=True),
    )
