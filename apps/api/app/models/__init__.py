"""Punto unico de importacion de modelos.

`alembic/env.py` importa este paquete. Todo modelo nuevo tiene que aparecer aca:
si no se importa, --autogenerate no lo ve y genera un DROP de la tabla que no conoce.
"""

from app.models.api_key import ApiKey, Scope
from app.models.event import EventStatus, ProcessedEvent
from app.models.tenant import Chunk, Conversation, Document, Message, Tenant
from app.models.usage import TenantUsage, periodo_actual

__all__ = [
    "ApiKey",
    "Chunk",
    "Conversation",
    "Document",
    "EventStatus",
    "Message",
    "ProcessedEvent",
    "Scope",
    "Tenant",
    "TenantUsage",
    "periodo_actual",
]
