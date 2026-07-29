"""Contratos de entrada/salida de la API."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.api_key import Scope


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None


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


class PromptUpdate(BaseModel):
    """En el body, no como query param.

    Como query param el prompt quedaria en los logs de acceso del servidor y del
    proxy, y ademas chocaria con el limite de largo de la URL.
    """

    system_prompt: str = Field(max_length=100_000)


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
