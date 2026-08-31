"""Tablas del motor multi-tenant.

Decision clave: el System Prompt de cada cliente vive aca (columna `system_prompt`),
no en un archivo. Asi el dashboard lo edita sin desplegar.
"""

import uuid
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.session import Base


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = _uuid_pk()
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))

    # El prompt propio del cliente. Se compone con la plantilla base en runtime.
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    # Numero de WhatsApp (phone_number_id de Meta) para resolver el tenant entrante.
    whatsapp_phone_number_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )
    # Access token de la Graph API, CIFRADO (ver core/cifrado.py). Es por cliente:
    # autoriza a enviar mensajes en nombre de SU numero, asi que no puede vivir
    # en la config global ni compartirse entre clientes.
    whatsapp_access_token_cifrado: Mapped[str | None] = mapped_column(Text, nullable=True)
    # La WABA (WhatsApp Business Account) que Meta le creo al cliente durante el
    # alta. No se usa para operar -el envio va por phone_number_id-, se guarda
    # para poder identificar la cuenta del cliente del lado de Meta cuando algo
    # falla. Sin esto hay que ir a buscarla a mano al Business Manager.
    # Sin unique: una misma WABA puede tener varios numeros, y nada impide que
    # dos clientes nuestros cuelguen del mismo negocio.
    whatsapp_waba_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    settings_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(default=True)

    # Cuota mensual de mensajes. NULL = sin limite (usar con cuidado: con precio
    # plano, un cliente sin tope puede comerse la ganancia del mes).
    # Al crear un cliente se completa con settings.default_monthly_message_limit,
    # asi que el valor siempre es explicito en la fila salvo que se anule aposta.
    monthly_message_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # passive_deletes=True: al borrar un tenant, que la CASCADE de Postgres
    # borre los documentos (declarada en el ForeignKey de abajo), no el ORM.
    # Sin esto, SQLAlchemy intenta poner tenant_id=NULL en los documentos antes
    # de borrar el tenant -por si algun dia el objeto se "desasocia" en vez de
    # borrarse- y esa columna no admite NULL: revienta con NotNullViolation.
    documents: Mapped[list["Document"]] = relationship(
        back_populates="tenant", passive_deletes=True
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(512))
    source: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tenant: Mapped[Tenant] = relationship(back_populates="documents")
    # Mismo motivo que Tenant.documents: dejar que la CASCADE de Postgres borre
    # los chunks, no que el ORM intente vaciar chunks.document_id.
    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", passive_deletes=True)


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = _uuid_pk()
    # tenant_id denormalizado a proposito: el filtro de aislamiento tiene que poder
    # aplicarse sin JOIN, en el mismo WHERE de la busqueda vectorial.
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embeddings_dim))

    document: Mapped[Document] = relationship(back_populates="chunks")

    __table_args__ = (
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[str] = mapped_column(String(32))
    # WhatsApp: el numero del usuario final. Web: un id de sesion generado.
    external_id: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Se actualiza en cada turno. Define la ventana de inactividad: si alguien
    # escribe meses despues, se abre una conversacion nueva en vez de reabrir un
    # hilo con historia rancia (y de pagar por replicarla).
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # Hasta cuando el bot NO contesta esta conversacion, porque alguien la esta
    # atendiendo a mano desde la bandeja de Meta.
    #
    # ★ Es una fecha de vencimiento y no un booleano a proposito. Un interruptor
    # se queda prendido: el dia que alguien se olvida de apagarlo, ese cliente
    # deja de recibir respuestas para siempre y nadie se entera -no hay error,
    # no hay log, solo silencio-. Con vencimiento el peor caso es que el bot
    # vuelva unas horas mas tarde de lo ideal.
    pausada_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Mismo motivo que Tenant.documents.
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", passive_deletes=True
    )

    __table_args__ = (Index("ix_conversations_lookup", "tenant_id", "channel", "external_id"),)

    def en_modo_manual(self, ahora: datetime | None = None) -> bool:
        """Si la pausa sigue vigente. Una pausa vencida es como no tenerla."""
        if self.pausada_hasta is None:
            return False
        return self.pausada_hasta > (ahora or datetime.now(UTC))


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    # Orden explicito dentro de la conversacion. NO alcanza ordenar por
    # created_at: `now()` en Postgres devuelve el instante de INICIO de la
    # transaccion, asi que dos mensajes insertados en la misma transaccion
    # comparten timestamp y el orden queda indefinido. Un historial desordenado
    # le da al modelo un dialogo que nunca ocurrio.
    position: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped[Conversation] = relationship(back_populates="messages")

    __table_args__ = (Index("ix_messages_orden", "conversation_id", "position"),)
