"""Como viene cada cliente, todo junto y en cinco consultas.

QUE PROBLEMA RESUELVE
---------------------
La lista de clientes del panel mostraba el nombre, el slug y si estaba activo.
Nada de eso dice si hay alguien esperando que lo atiendan, asi que para saber
si un negocio necesitaba algo habia que entrar cliente por cliente. Con seis
clientes es tedioso; con veinte, directamente no se hace, y las derivaciones se
enfrian sin que nadie se entere.

★ POR QUE UN ENDPOINT Y NO CINCO LLAMADAS POR CLIENTE DESDE EL PANEL
--------------------------------------------------------------------
La otra forma de tener estos datos era que el panel pidiera, por cada cliente,
sus conversaciones, su consumo, su WhatsApp y sus claves. Con veinte clientes
eso son ochenta viajes HTTP -en serie, porque el panel se renderiza en el
servidor- cada vez que alguien abre la pantalla principal.

Aca son cinco consultas en total, y ninguna crece con la cantidad de clientes:
todas agrupan del lado de Postgres. Agregar un cliente numero cincuenta no suma
una sola consulta.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, any_, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey, Scope
from app.models.event import EventStatus, ProcessedEvent
from app.models.tenant import Conversation, Tenant
from app.models.usage import TenantUsage, periodo_actual
from app.services.inbox import MINUTOS_PARA_DAR_POR_COLGADO

# Que cuenta como "hoy" para la actividad de un cliente. Mas viejo que esto ya
# es historial y no dice nada sobre como viene el dia.
HORAS_DE_ACTIVIDAD = 24


@dataclass(frozen=True)
class ResumenCliente:
    """Un cliente y todo lo que hay que saber de el sin entrar."""

    id: uuid.UUID
    slug: str
    name: str
    is_active: bool

    # Lo que pide accion. `esperando` es el numero que ordena la lista entera.
    esperando: int
    minutos_de_la_mas_vieja: int | None

    # Como viene el dia.
    conversaciones_activas: int
    conversaciones: int
    minutos_ultima_actividad: int | None

    # El mes.
    mensajes_del_mes: int
    limite_mensual: int | None

    # Si el bot puede trabajar, y si el duenio puede mirar.
    whatsapp_configurado: bool
    tiene_portal: bool

    # Mensajes que entraron y no se contestaron.
    incidentes: int


async def por_cliente(db: AsyncSession) -> list[ResumenCliente]:
    """Todos los clientes, con el que necesita atencion primero."""
    ahora = datetime.now(UTC)

    clientes = list(await db.scalars(select(Tenant).order_by(Tenant.name)))
    if not clientes:
        return []

    conv = await _conversaciones(db, ahora)
    uso = await _uso(db)
    incidentes = await _incidentes(db, ahora)
    portales = await _portales(db, ahora)

    resumenes = [
        ResumenCliente(
            id=t.id,
            slug=t.slug,
            name=t.name,
            is_active=t.is_active,
            esperando=conv.get(t.id, _SIN_CONVERSACIONES).esperando,
            minutos_de_la_mas_vieja=_minutos_desde(
                conv.get(t.id, _SIN_CONVERSACIONES).derivada_mas_vieja, ahora
            ),
            conversaciones_activas=conv.get(t.id, _SIN_CONVERSACIONES).activas,
            conversaciones=conv.get(t.id, _SIN_CONVERSACIONES).total,
            minutos_ultima_actividad=_minutos_desde(
                conv.get(t.id, _SIN_CONVERSACIONES).ultima_actividad, ahora
            ),
            mensajes_del_mes=uso.get(t.id, 0),
            limite_mensual=t.monthly_message_limit,
            whatsapp_configurado=bool(
                t.whatsapp_phone_number_id and t.whatsapp_access_token_cifrado
            ),
            tiene_portal=t.id in portales,
            incidentes=incidentes.get(t.id, 0),
        )
        for t in clientes
    ]

    # ★ El orden lo decide lo que pide accion, no el alfabeto. Un cliente con
    # tres personas esperando no puede estar abajo de todo porque su nombre
    # empieza con Z. Entre los que no piden nada, manda el nombre, que es lo
    # unico estable para buscar con la vista.
    resumenes.sort(key=lambda r: (-r.esperando, -r.incidentes, r.name.lower()))
    return resumenes


def _minutos_desde(cuando: datetime | None, ahora: datetime) -> int | None:
    if cuando is None:
        return None
    return max(0, int((ahora - cuando).total_seconds() // 60))


@dataclass(frozen=True)
class _Conversaciones:
    esperando: int = 0
    activas: int = 0
    total: int = 0
    ultima_actividad: datetime | None = None
    derivada_mas_vieja: datetime | None = None


_SIN_CONVERSACIONES = _Conversaciones()


async def _conversaciones(
    db: AsyncSession, ahora: datetime
) -> dict[uuid.UUID, _Conversaciones]:
    """Los cuatro numeros de conversaciones, en una sola pasada por la tabla.

    `FILTER (WHERE ...)` de Postgres permite contar dos cosas distintas en la
    misma agregacion. La alternativa serian dos consultas con el mismo GROUP BY.
    """
    corte = ahora - timedelta(hours=HORAS_DE_ACTIVIDAD)

    filas = await db.execute(
        select(
            Conversation.tenant_id,
            func.count(Conversation.id).filter(Conversation.derivada_at.isnot(None)),
            func.count(Conversation.id).filter(Conversation.last_activity_at >= corte),
            func.count(Conversation.id),
            func.max(Conversation.last_activity_at),
            func.min(Conversation.derivada_at),
        ).group_by(Conversation.tenant_id)
    )

    return {
        tenant_id: _Conversaciones(
            esperando=esperando or 0,
            activas=activas or 0,
            total=total or 0,
            ultima_actividad=ultima,
            derivada_mas_vieja=mas_vieja,
        )
        for tenant_id, esperando, activas, total, ultima, mas_vieja in filas.all()
    }


async def _uso(db: AsyncSession) -> dict[uuid.UUID, int]:
    """Mensajes consumidos en el periodo corriente, por cliente."""
    filas = await db.execute(
        select(TenantUsage.tenant_id, TenantUsage.messages).where(
            TenantUsage.period == periodo_actual()
        )
    )
    return dict(filas.tuples().all())


async def _incidentes(db: AsyncSession, ahora: datetime) -> dict[uuid.UUID, int]:
    """Mensajes fallados o colgados, por cliente.

    Misma definicion que `inbox.incidentes`, y por eso importa la constante de
    ahi en vez de repetir el numero: si algun dia se ajusta cuanto hay que
    esperar para dar algo por colgado, la lista de clientes y el detalle del
    cliente no pueden empezar a contar cosas distintas.
    """
    corte = ahora - timedelta(minutes=MINUTOS_PARA_DAR_POR_COLGADO)
    filas = await db.execute(
        select(ProcessedEvent.tenant_id, func.count(ProcessedEvent.id))
        .where(
            ProcessedEvent.tenant_id.isnot(None),
            or_(
                ProcessedEvent.status == EventStatus.FAILED.value,
                and_(
                    ProcessedEvent.status == EventStatus.PENDING.value,
                    ProcessedEvent.created_at < corte,
                ),
            ),
        )
        .group_by(ProcessedEvent.tenant_id)
    )
    return {tenant_id: total for tenant_id, total in filas.all() if tenant_id is not None}


async def _portales(db: AsyncSession, ahora: datetime) -> set[uuid.UUID]:
    """Los clientes que tienen una clave de portal viva.

    literal(...) == any_(columna) y no columna.any(...): con `Mapped[list[str]]`
    SQLAlchemy no expone el operador de array sobre el atributo tipado. Mismo
    criterio que en routes/tenants.py.
    """
    filas = await db.scalars(
        select(ApiKey.tenant_id).where(
            ApiKey.tenant_id.isnot(None),
            ApiKey.revoked_at.is_(None),
            or_(ApiKey.expires_at.is_(None), ApiKey.expires_at > ahora),
            literal(Scope.CLIENT_PORTAL.value) == any_(ApiKey.scopes),
        )
    )
    return {tenant_id for tenant_id in filas if tenant_id is not None}
