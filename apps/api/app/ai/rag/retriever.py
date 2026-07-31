"""Busqueda vectorial.

★ ESTE ES EL ARCHIVO CRITICO DEL MULTI-TENANT.

`search` no acepta un modo "sin tenant". Si esta funcion se ejecuta sin el filtro
`WHERE tenant_id = :tenant_id`, un cliente ve los documentos de otro. El test
tests/test_tenant_isolation.py cubre exactamente eso.
"""

import unicodedata
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.rag.embedder import get_embedder
from app.core.config import settings
from app.models.tenant import Chunk

# Mensajes puramente sociales: no hay nada que buscar en la base de conocimiento
# porque no preguntan nada. Saltear la busqueda ahorra una llamada al proveedor
# de embeddings, que es el recurso escaso (se cuenta por requests por minuto).
#
# La lista es DELIBERADAMENTE corta y conservadora. Saltear cuando no
# correspondia degrada la respuesta -el modelo se queda sin contexto-, y eso es
# mucho peor que gastar una llamada de mas. Por eso NO entran aca "si", "no",
# "dale" ni "ok": suelen ser respuestas a una repregunta ("¿te cuento las
# tarifas?" -> "dale") y ahi el contexto si hace falta.
_SOCIALES = frozenset(
    {
        "hola",
        "holis",
        "buenas",
        "buen dia",
        "buenos dias",
        "buenas tardes",
        "buenas noches",
        "hey",
        "que tal",
        "como estas",
        "como andas",
        "gracias",
        "muchas gracias",
        "mil gracias",
        "te agradezco",
        "chau",
        "adios",
        "hasta luego",
        "nos vemos",
        "saludos",
    }
)


def _normalizar(texto: str) -> str:
    """Minusculas, sin acentos y sin signos, para comparar contra _SOCIALES."""
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    limpio = "".join(c if c.isalnum() or c.isspace() else " " for c in sin_acentos.lower())
    return " ".join(limpio.split())


def necesita_busqueda(query: str) -> bool:
    """False si el mensaje no tiene ninguna intencion de consulta."""
    normalizado = _normalizar(query)
    if not normalizado:  # solo signos ("?", "...") : no hay nada que buscar
        return False
    return normalizado not in _SOCIALES


async def search(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    query: str,
    top_k: int | None = None,
) -> list[str]:
    """Devuelve los fragmentos mas relevantes DEL TENANT indicado. Nunca de otro."""
    if not necesita_busqueda(query):
        return []

    embedder = get_embedder()
    [vector] = await embedder.embed([query], is_query=True)

    stmt = (
        select(Chunk.content)
        .where(Chunk.tenant_id == tenant_id)  # <- el aislamiento vive en esta linea
        .order_by(Chunk.embedding.cosine_distance(vector))
        .limit(top_k or settings.retrieval_top_k)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
