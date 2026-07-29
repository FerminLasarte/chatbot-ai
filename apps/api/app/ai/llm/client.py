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

from anthropic import AsyncAnthropic
from anthropic.types import MessageParam, OutputConfigParam, TextBlockParam

from app.core.config import settings

logger = logging.getLogger(__name__)

_client = AsyncAnthropic(api_key=settings.anthropic_api_key or None)


async def complete(
    system_blocks: list[TextBlockParam],
    messages: list[MessageParam],
    max_tokens: int | None = None,
) -> str:
    """Una respuesta de texto. Streaming para no chocar con timeouts HTTP."""
    output_config = OutputConfigParam(effort=settings.llm_effort)  # type: ignore[typeddict-item]
    async with _client.messages.stream(
        model=settings.llm_model,
        max_tokens=max_tokens or settings.llm_max_tokens,
        system=system_blocks,
        messages=messages,
        output_config=output_config,
    ) as stream:
        response = await stream.get_final_message()

    # Los clasificadores de seguridad pueden declinar: HTTP 200 con stop_reason
    # "refusal" y `content` vacio. Hay que chequearlo ANTES de leer content.
    if response.stop_reason == "refusal":
        logger.warning("respuesta rechazada por clasificadores de seguridad")
        return "Perdon, no puedo ayudarte con eso. Si queres te derivo con alguien del equipo."

    usage = response.usage
    logger.info(
        "llm ok",
        extra={
            "cache_read": usage.cache_read_input_tokens,
            "cache_write": usage.cache_creation_input_tokens,
            "input": usage.input_tokens,
            "output": usage.output_tokens,
        },
    )

    return "".join(b.text for b in response.content if b.type == "text").strip()
