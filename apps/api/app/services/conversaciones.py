"""Lectura y pausa de conversaciones, sin saber quien esta preguntando.

POR QUE ESTO NO VIVE EN LA RUTA
-------------------------------
Hay dos puertas hacia estas mismas operaciones y tienen autenticaciones
distintas: la agencia entra por `routes/conversations.py` con clave admin y
diciendo sobre que cliente opera, y el duenio del negocio entra por
`routes/portal.py` con una clave que YA trae su tenant. Si cada ruta tuviera su
propia copia de las consultas, el dia que se arregle un bug en una el otro
camino se queda con la version vieja —y uno de los dos caminos es el que ven
los clientes finales—.

Aca adentro el `tenant_id` es siempre un parametro obligatorio: este modulo no
decide de quien es la peticion, solo se niega a trabajar sin saberlo. Quien lo
llama es el responsable de que ese id salga de la credencial y no de algo que
mando el navegador.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Conversation, Message
from app.schemas.chat import ConversationRead, MessageRead

# Largo del adelanto del ultimo mensaje. Alcanza para reconocer de que se venia
# hablando; el resto seria volcar la conversacion entera en una lista.
LARGO_ADELANTO = 140


class ConversacionNoEncontrada(Exception):
    """No existe, o existe pero es de otro cliente. A proposito no se distingue."""


def _adelanto(texto: str | None) -> str | None:
    if texto is None:
        return None
    limpio = " ".join(texto.split())
    if len(limpio) <= LARGO_ADELANTO:
        return limpio
    return limpio[:LARGO_ADELANTO] + "…"


def _minutos(desde: datetime, hasta: datetime) -> int:
    return max(0, int((hasta - desde).total_seconds() // 60))


def _to_read(c: Conversation, mensajes: int, ultimo: str | None) -> ConversationRead:
    # Un unico `ahora` para toda la fila: con dos lecturas del reloj, una fila
    # podria salir "en modo manual" con cero minutos restantes.
    ahora = datetime.now(UTC)
    manual = c.en_modo_manual(ahora)
    return ConversationRead(
        id=str(c.id),
        channel=c.channel,
        external_id=c.external_id,
        last_activity_at=c.last_activity_at,
        pausada_hasta=c.pausada_hasta,
        en_modo_manual=manual,
        minutos_inactiva=_minutos(c.last_activity_at, ahora),
        # Solo tiene sentido mientras la pausa siga viva.
        minutos_restantes=(
            _minutos(ahora, c.pausada_hasta) if manual and c.pausada_hasta else None
        ),
        mensajes=mensajes,
        ultimo_mensaje=_adelanto(ultimo),
    )


async def buscar(
    db: AsyncSession, tenant_id: uuid.UUID, conversation_id: uuid.UUID
) -> Conversation:
    """★ El filtro por tenant_id NO es opcional.

    Sin el, el id de una conversacion de otro cliente entraria por aca y se
    podria pausar -o leer el ultimo mensaje de- un hilo ajeno.
    """
    conversacion = await db.get(Conversation, conversation_id)
    if conversacion is None or conversacion.tenant_id != tenant_id:
        raise ConversacionNoEncontrada
    return conversacion


async def detalle(db: AsyncSession, conversacion: Conversation) -> ConversationRead:
    """Recuenta una sola conversacion, para devolverla despues de tocarla."""
    mensajes = await db.scalar(
        select(func.count()).select_from(Message).where(Message.conversation_id == conversacion.id)
    )
    ultimo = await db.scalar(
        select(Message.content)
        .where(Message.conversation_id == conversacion.id)
        .order_by(Message.position.desc())
        .limit(1)
    )
    return _to_read(conversacion, mensajes or 0, ultimo)


async def listar(
    db: AsyncSession, tenant_id: uuid.UUID, *, limite: int = 50
) -> list[ConversationRead]:
    """Las conversaciones mas recientes del cliente, la ultima primero."""
    filas = await db.execute(
        select(Conversation, func.count(Message.id))
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .where(Conversation.tenant_id == tenant_id)
        .group_by(Conversation.id)
        .order_by(Conversation.last_activity_at.desc())
        .limit(limite)
    )
    conversaciones = filas.all()
    if not conversaciones:
        return []

    # El ultimo mensaje de cada hilo en UNA consulta (DISTINCT ON de Postgres),
    # no una por conversacion: con 50 hilos en pantalla, la version ingenua son
    # 50 viajes a la base cada vez que se abre la pagina.
    ids = [c.id for c, _n in conversaciones]
    ultimos_filas = await db.execute(
        select(Message.conversation_id, Message.content)
        .where(Message.conversation_id.in_(ids))
        .distinct(Message.conversation_id)
        .order_by(Message.conversation_id, Message.position.desc())
    )
    # .tuples() y no .all() a secas: devuelve tuplas tipadas en vez de Row, que
    # es lo que permite que dict() conserve los tipos (uuid -> texto del mensaje).
    ultimos = dict(ultimos_filas.tuples().all())

    return [_to_read(c, n, ultimos.get(c.id)) for c, n in conversaciones]


async def pausar(
    db: AsyncSession, tenant_id: uuid.UUID, conversation_id: uuid.UUID, *, horas: int
) -> ConversationRead:
    """Silencia al bot en esta conversacion por un rato.

    Repetir la llamada corre el vencimiento: sirve para estirar la pausa sin
    tener que reactivar y volver a pausar.
    """
    conversacion = await buscar(db, tenant_id, conversation_id)
    conversacion.pausada_hasta = datetime.now(UTC) + timedelta(hours=horas)
    await db.commit()
    await db.refresh(conversacion)
    return await detalle(db, conversacion)


async def reanudar(
    db: AsyncSession, tenant_id: uuid.UUID, conversation_id: uuid.UUID
) -> ConversationRead:
    """Devuelve la conversacion al bot antes de que venza la pausa."""
    conversacion = await buscar(db, tenant_id, conversation_id)
    conversacion.pausada_hasta = None
    await db.commit()
    await db.refresh(conversacion)
    return await detalle(db, conversacion)


async def listar_mensajes(
    db: AsyncSession, tenant_id: uuid.UUID, conversation_id: uuid.UUID, *, limite: int
) -> list[MessageRead]:
    """El hilo completo de una conversacion, del mas viejo al mas nuevo.

    ★ Pasa por `buscar`, igual que pausar y reanudar, y no por una consulta
    propia. Es lo unico que impide que alguien lea las conversaciones de otro
    negocio mandando un id ajeno: el filtro por tenant tiene que estar en el
    camino, no en la buena fe de quien llama.

    Cuando la conversacion es mas larga que `limite` se devuelven los ULTIMOS
    mensajes, que es lo que alguien quiere ver al abrir un hilo. Se piden al
    reves y se dan vuelta en memoria: pedirlos en orden obligaria a contar
    primero para saber desde donde.
    """
    await buscar(db, tenant_id, conversation_id)

    filas = await db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.position.desc())
        .limit(limite)
    )
    ahora = datetime.now(UTC)
    return [
        MessageRead(
            id=str(m.id),
            role=m.role,
            autor=m.autor,
            content=m.content,
            created_at=m.created_at,
            minutos=_minutos(m.created_at, ahora),
        )
        for m in reversed(filas.all())
    ]
