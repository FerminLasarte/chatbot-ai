"""Busqueda vectorial.

★ ESTE ES EL ARCHIVO CRITICO DEL MULTI-TENANT.

`search` no acepta un modo "sin tenant". Si esta funcion se ejecuta sin el filtro
`WHERE tenant_id = :tenant_id`, un cliente ve los documentos de otro. El test
tests/test_tenant_isolation.py cubre exactamente eso.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.rag.embedder import get_embedder
from app.core.config import settings
from app.models.tenant import Chunk


async def search(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    query: str,
    top_k: int | None = None,
) -> list[str]:
    """Devuelve los fragmentos mas relevantes DEL TENANT indicado. Nunca de otro."""
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
