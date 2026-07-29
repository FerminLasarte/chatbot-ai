"""Compone el system prompt final: base + tenant + contexto recuperado.

ORDEN CRITICO PARA EL CACHE
---------------------------
El prompt caching de Anthropic es un match de PREFIJO: cualquier byte que cambie
invalida todo lo que viene despues. Por eso el orden es siempre:

    [0] BASE_SYSTEM_PROMPT   -> identico para todos los tenants  -> cache global
    [1] tenant.system_prompt -> estable por cliente              -> cache por tenant
    [2] contexto RAG         -> cambia en cada mensaje           -> SIN cache

El `cache_control` va en el bloque [1]: cachea base + prompt del cliente juntos.
El contexto recuperado va despues del breakpoint, en el turno del usuario, para no
invalidar nada.

Minimo cacheable en Claude Opus 5: 512 tokens. Por debajo de eso no cachea (sin
error, simplemente `cache_creation_input_tokens: 0`).
"""

from anthropic.types import ContentBlockParam, TextBlockParam

from app.ai.prompts.base_system import BASE_SYSTEM_PROMPT
from app.ai.prompts.rag_answer import format_context


def build_system_blocks(tenant_prompt: str) -> list[TextBlockParam]:
    """Devuelve los bloques `system` listos para la Messages API."""
    return [
        TextBlockParam(type="text", text=BASE_SYSTEM_PROMPT),
        TextBlockParam(
            type="text",
            text=_tenant_section(tenant_prompt),
            # Breakpoint: cachea tools + base + prompt del tenant.
            cache_control={"type": "ephemeral"},
        ),
    ]


def _tenant_section(tenant_prompt: str) -> str:
    body = tenant_prompt.strip() or "(sin instrucciones especificas)"
    return f"<instrucciones_del_negocio>\n{body}\n</instrucciones_del_negocio>"


def build_user_turn(question: str, chunks: list[str]) -> list[ContentBlockParam]:
    """Contexto + pregunta en el turno del usuario, DESPUES del breakpoint."""
    blocks: list[ContentBlockParam] = []
    if chunks:
        blocks.append(TextBlockParam(type="text", text=format_context(chunks)))
    blocks.append(TextBlockParam(type="text", text=question))
    return blocks
