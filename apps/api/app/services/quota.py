"""Cuota mensual de mensajes por cliente.

Con precio plano a pymes, un cliente sin tope puede comerse la ganancia del mes.
Y una clave de widget filtrada (viaja en el navegador) puede quemar presupuesto
en un loop. La cuota acota la perdida maxima.

EL CHEQUEO Y EL INCREMENTO SON UNA SOLA SENTENCIA, a proposito:

    consultar el contador -> decidir -> incrementar

tiene una carrera. Con la cuota en 1999/2000, veinte peticiones simultaneas leen
todas 1999, todas concluyen "hay lugar", y terminas con 2019 mensajes cobrados.
El UPDATE condicional resuelve el chequeo y el incremento atomicamente: solo
prospera si el contador todavia esta por debajo del limite.
"""

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.models.usage import TenantUsage, periodo_actual

logger = logging.getLogger(__name__)


class QuotaExcedida(Exception):
    """El cliente agoto su cuota del mes."""

    def __init__(self, tenant_id: uuid.UUID, limite: int, periodo: str) -> None:
        self.tenant_id = tenant_id
        self.limite = limite
        self.periodo = periodo
        super().__init__(f"cuota mensual agotada ({limite} mensajes en {periodo})")


@dataclass(frozen=True)
class Consumo:
    period: str
    messages: int
    limit: int | None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int

    @property
    def remaining(self) -> int | None:
        return None if self.limit is None else max(self.limit - self.messages, 0)


async def consumir_mensaje(db: AsyncSession, tenant: Tenant) -> None:
    """Reserva un mensaje de la cuota. Levanta QuotaExcedida si no queda.

    Se llama ANTES de gastar en el LLM: la cuota tiene que frenar el gasto, no
    contabilizarlo despues de haberlo hecho.
    """
    limite = tenant.monthly_message_limit
    if limite is None:
        await _incrementar_sin_tope(db, tenant.id)
        return

    periodo = periodo_actual()

    if limite <= 0:
        raise QuotaExcedida(tenant.id, limite, periodo)

    # INSERT si es el primer mensaje del mes; si ya hay fila, incrementa solo
    # mientras el contador siga por debajo del limite. Si el WHERE no se cumple,
    # no devuelve fila: la cuota esta agotada.
    stmt = (
        insert(TenantUsage)
        .values(tenant_id=tenant.id, period=periodo, messages=1)
        .on_conflict_do_update(
            index_elements=["tenant_id", "period"],
            set_={"messages": TenantUsage.__table__.c.messages + 1},
            where=TenantUsage.__table__.c.messages < limite,
        )
        .returning(TenantUsage.messages)
    )
    usados = await db.scalar(stmt)
    await db.commit()

    if usados is None:
        logger.warning(
            "cuota agotada",
            extra={"tenant_id": str(tenant.id), "limite": limite, "periodo": periodo},
        )
        raise QuotaExcedida(tenant.id, limite, periodo)

    if usados == limite:
        logger.warning(
            "el cliente llego al 100%% de su cuota",
            extra={"tenant_id": str(tenant.id), "limite": limite},
        )


async def _incrementar_sin_tope(db: AsyncSession, tenant_id: uuid.UUID) -> None:
    stmt = (
        insert(TenantUsage)
        .values(tenant_id=tenant_id, period=periodo_actual(), messages=1)
        .on_conflict_do_update(
            index_elements=["tenant_id", "period"],
            set_={"messages": TenantUsage.__table__.c.messages + 1},
        )
    )
    await db.execute(stmt)
    await db.commit()


async def registrar_tokens(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> None:
    """Acumula tokens para facturar y medir. No frena nada.

    Best-effort a proposito: si esto falla, el usuario ya tiene su respuesta y no
    tiene sentido romperle la peticion por un contador.
    """
    try:
        cols = TenantUsage.__table__.c
        stmt = (
            insert(TenantUsage)
            .values(
                tenant_id=tenant_id,
                period=periodo_actual(),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read_tokens,
            )
            .on_conflict_do_update(
                index_elements=["tenant_id", "period"],
                set_={
                    "input_tokens": cols.input_tokens + input_tokens,
                    "output_tokens": cols.output_tokens + output_tokens,
                    "cache_read_tokens": cols.cache_read_tokens + cache_read_tokens,
                },
            )
        )
        await db.execute(stmt)
        await db.commit()
    except Exception:  # noqa: BLE001
        logger.warning("no se pudieron registrar los tokens", exc_info=True)
        await db.rollback()


async def consumo_actual(db: AsyncSession, tenant: Tenant) -> Consumo:
    periodo = periodo_actual()
    fila = await db.scalar(
        select(TenantUsage).where(TenantUsage.tenant_id == tenant.id, TenantUsage.period == periodo)
    )
    if fila is None:
        return Consumo(periodo, 0, tenant.monthly_message_limit, 0, 0, 0)
    return Consumo(
        period=periodo,
        messages=fila.messages,
        limit=tenant.monthly_message_limit,
        input_tokens=fila.input_tokens,
        output_tokens=fila.output_tokens,
        cache_read_tokens=fila.cache_read_tokens,
    )
