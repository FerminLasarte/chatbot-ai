"""Documento -> parseo -> chunking -> embeddings -> DB."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.rag.embedder import get_embedder
from app.core.config import settings
from app.models.tenant import Chunk, Document


def chunk_text(text: str, size: int | None = None, overlap: int | None = None) -> list[str]:
    """Chunking por caracteres con solape. Suficiente para el MVP.

    Mejora pendiente cuando duela: cortar por parrafo/heading en vez de por
    longitud fija, para no partir una respuesta a la mitad.
    """
    size = size or settings.chunk_size
    overlap = overlap or settings.chunk_overlap
    clean = " ".join(text.split())
    if not clean:
        return []

    step = max(size - overlap, 1)
    return [clean[i : i + size] for i in range(0, len(clean), step) if clean[i : i + size].strip()]


async def ingest_document(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    title: str,
    text: str,
    source: str | None = None,
) -> Document:
    document = Document(tenant_id=tenant_id, title=title, source=source)
    db.add(document)
    await db.flush()

    pieces = chunk_text(text)
    if pieces:
        vectors = await get_embedder().embed(pieces)
        db.add_all(
            Chunk(
                tenant_id=tenant_id,  # denormalizado: el retriever filtra sin JOIN
                document_id=document.id,
                position=i,
                content=piece,
                embedding=vector,
            )
            for i, (piece, vector) in enumerate(zip(pieces, vectors, strict=True))
        )

    await db.commit()
    return document
