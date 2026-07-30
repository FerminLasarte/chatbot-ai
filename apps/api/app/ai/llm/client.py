"""Wrapper del SDK de Anthropic.

Model ID: `claude-opus-5` (sin sufijo de fecha).

Notas de la API vigente:
- El thinking esta activo por defecto en Opus 5. `max_tokens` acota thinking +
  respuesta juntos, asi que dejamos margen.
- `temperature` / `top_p` / `top_k` fueron removidos: devuelven 400. El tono se
  controla por prompt.
- `effort` va dentro de `output_config`, no en el nivel superior.
"""

import logging
import re
from dataclasses import dataclass

from anthropic import AsyncAnthropic, omit
from anthropic.types import MessageParam, OutputConfigParam, TextBlockParam

from app.core.config import settings

logger = logging.getLogger(__name__)

_client = AsyncAnthropic(api_key=settings.anthropic_api_key or None)


RECHAZO = "Perdon, no puedo ayudarte con eso. Si queres te derivo con alguien del equipo."

# El prompt le pide al modelo que no use markdown, pero no todos lo respetan
# siempre (confirmado: haiku-4-5 a veces igual manda **negrita**). WhatsApp no
# renderiza doble asterisco, lo muestra literal -asi que se limpia aca, en el
# unico punto de salida, en vez de confiar en que el modelo obedezca siempre.
_MARKDOWN_NEGRITA = re.compile(r"\*\*(.+?)\*\*")


def _limpiar_markdown(texto: str) -> str:
    return _MARKDOWN_NEGRITA.sub(r"\1", texto)


# `effort` solo lo soporta la familia Claude 5 (opus-5, sonnet-5). Haiku 4.5 no
# es parte de esa familia y devuelve 400 "This model does not support the
# effort parameter" (confirmado con una llamada real).
_MODELOS_CON_EFFORT = ("claude-opus-5", "claude-sonnet-5")


@dataclass(frozen=True)
class Respuesta:
    """Texto mas consumo. El consumo se necesita para facturar y medir cuota."""

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0


async def complete(
    system_blocks: list[TextBlockParam],
    messages: list[MessageParam],
    max_tokens: int | None = None,
) -> Respuesta:
    """Una respuesta de texto. Streaming para no chocar con timeouts HTTP."""
    output_config: OutputConfigParam | None = (
        OutputConfigParam(effort=settings.llm_effort)  # type: ignore[typeddict-item]
        if settings.llm_model.startswith(_MODELOS_CON_EFFORT)
        else None
    )

    async with _client.messages.stream(
        model=settings.llm_model,
        max_tokens=max_tokens or settings.llm_max_tokens,
        system=system_blocks,
        messages=messages,
        output_config=output_config if output_config is not None else omit,
    ) as stream:
        response = await stream.get_final_message()

    usage = response.usage
    consumo = {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_read_tokens": usage.cache_read_input_tokens or 0,
    }

    # Los clasificadores de seguridad pueden declinar: HTTP 200 con stop_reason
    # "refusal" y `content` vacio. Hay que chequearlo ANTES de leer content.
    # Igual se devuelve el consumo: el rechazo tambien se paga.
    if response.stop_reason == "refusal":
        logger.warning("respuesta rechazada por clasificadores de seguridad")
        return Respuesta(text=RECHAZO, **consumo)

    logger.info(
        "llm ok",
        extra={**consumo, "cache_write": usage.cache_creation_input_tokens},
    )

    texto = "".join(b.text for b in response.content if b.type == "text").strip()
    return Respuesta(text=_limpiar_markdown(texto), **consumo)
