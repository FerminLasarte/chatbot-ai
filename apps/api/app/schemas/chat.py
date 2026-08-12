"""Contratos de entrada/salida de la API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.api_key import Scope


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    # Si no viene, se abre una conversacion nueva. Tipado como UUID para que un
    # valor invalido de 422 en el borde, antes de llegar a la base.
    conversation_id: UUID | None = None


class ChatResponse(BaseModel):
    reply: str
    conversation_id: str
    escalate: bool = False


class TenantCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9-]+$")
    name: str
    system_prompt: str = ""
    whatsapp_phone_number_id: str | None = None


class TenantRead(BaseModel):
    id: str
    slug: str
    name: str
    system_prompt: str
    is_active: bool
    monthly_message_limit: int | None


class LimitUpdate(BaseModel):
    """None = sin limite. Con precio plano eso deja el margen expuesto."""

    monthly_message_limit: int | None = Field(default=None, ge=0)


class UsageRead(BaseModel):
    period: str
    messages: int
    limit: int | None
    remaining: int | None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int


class PromptUpdate(BaseModel):
    """En el body, no como query param.

    Como query param el prompt quedaria en los logs de acceso del servidor y del
    proxy, y ademas chocaria con el limite de largo de la URL.
    """

    system_prompt: str = Field(max_length=100_000)


class WhatsAppUpdate(BaseModel):
    """Credenciales del canal de WhatsApp de un cliente.

    El access token va en el body, nunca en la URL: como query param terminaria
    escrito en los logs de acceso del servidor y de cualquier proxy intermedio.
    """

    phone_number_id: str | None = Field(default=None, max_length=64)
    # None = no tocar el token guardado (para poder editar solo el numero sin
    # tener que volver a pegar el token). Cadena vacia = borrarlo.
    access_token: str | None = Field(default=None, max_length=1000)


class WhatsAppRead(BaseModel):
    """Estado del canal. NUNCA devuelve el token, ni siquiera parcial."""

    phone_number_id: str | None
    tiene_token: bool
    configurado: bool


class ConversationRead(BaseModel):
    """Una conversacion en la vista del panel.

    `external_id` es el numero del usuario final en WhatsApp: es lo unico que
    permite reconocer con quien se esta hablando al ir a la bandeja de Meta.
    """

    id: str
    channel: str
    external_id: str
    last_activity_at: datetime
    pausada_hasta: datetime | None
    # ★ Los tres derivados de abajo los calcula la API a proposito: el reloj lo
    # tiene un solo lado. El panel se renderiza en el servidor -en Railway, en
    # UTC-, asi que si comparara fechas por su cuenta mostraria horas que no son
    # las del usuario. Aca solo llegan numeros ya resueltos, que el panel
    # formatea ("hace 5 min", "vuelve en 2 h").
    en_modo_manual: bool
    minutos_inactiva: int
    minutos_restantes: int | None
    mensajes: int
    ultimo_mensaje: str | None


class ManualModeStart(BaseModel):
    """Cuanto dura la pausa. Sin valor, se usa `settings.manual_mode_hours`.

    El tope de una semana es a proposito: no existe la pausa indefinida. Ver el
    comentario de `Conversation.pausada_hasta`.
    """

    horas: int | None = Field(default=None, ge=1, le=168)


class DocumentRead(BaseModel):
    id: str
    title: str
    chunks: int


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    scopes: list[Scope] = Field(min_length=1)
    expires_at: datetime | None = None


class ApiKeyRead(BaseModel):
    id: str
    name: str
    key_prefix: str
    scopes: list[str]
    is_active: bool
    last_used_at: datetime | None


class ApiKeyCreated(ApiKeyRead):
    """Respuesta de emision: es la unica vez que se devuelve el secreto."""

    api_key: str
    is_active: bool = True
    last_used_at: datetime | None = None
