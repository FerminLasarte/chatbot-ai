"""Claves de API con alcance (scopes).

Hay cuatro niveles de confianza y NO pueden compartir credencial:

  admin          la agencia: crear/listar clientes y emitir claves. Vive en tu servidor.
  tenant         el dashboard de un cliente: editar su prompt, subir sus documentos.
  chat           el widget web: solo POST /chat. VIAJA EN EL NAVEGADOR, es publica.
  client_portal  el duenio de la PyME: ver SUS conversaciones y pausar SU bot.

Si el widget usara la misma clave que el dashboard, cualquiera que abra el
inspector en la web del cliente podria editarle el prompt y leerle los documentos.

★ `client_portal` es deliberadamente MAS chico que `tenant`, no un alias suyo.
Una clave `tenant` puede reescribir el prompt del bot y subir documentos; esta
solo lee conversaciones y corre la fecha de `pausada_hasta`. La diferencia
importa porque esta clave viaja por WhatsApp o mail hasta el telefono del
duenio del negocio y se queda ahi: hay que asumir que en algun momento la ve
alguien mas que el (ver routes/portal.py).

De la clave solo se guarda el hash. El secreto se muestra una unica vez, al
emitirla. Si se pierde, se revoca y se emite otra.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Scope(enum.StrEnum):
    ADMIN = "admin"
    TENANT = "tenant"
    CHAT = "chat"
    CLIENT_PORTAL = "client_portal"


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))

    # Parte publica: identifica la fila sin revelar el secreto. Permite buscar
    # por indice en vez de hashear todas las claves de la tabla en cada request.
    key_prefix: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    key_hash: Mapped[str] = mapped_column(String(64))

    # NULL para claves admin: no pertenecen a ningun cliente.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(32)))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant")

    __table_args__ = (
        # Invariante en la base, no solo en el codigo: una clave de cliente sin
        # tenant_id no tendria a quien aislar; una admin con tenant_id confunde.
        CheckConstraint(
            "(tenant_id IS NULL AND 'admin' = ANY(scopes))"
            " OR (tenant_id IS NOT NULL AND NOT ('admin' = ANY(scopes)))",
            name="ck_api_keys_admin_sin_tenant",
        ),
    )

    @property
    def is_active(self) -> bool:
        from datetime import UTC

        ahora = datetime.now(UTC)
        if self.revoked_at is not None:
            return False
        return not (self.expires_at is not None and self.expires_at <= ahora)
