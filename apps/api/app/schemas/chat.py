"""Contratos de entrada/salida de la API de chat."""

from pydantic import BaseModel, Field


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


class DocumentRead(BaseModel):
    id: str
    title: str
    chunks: int
