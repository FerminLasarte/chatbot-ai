"""Gestion de la base de conocimiento del cliente."""

from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status
from sqlalchemy import func, select

from app.ai.rag.ingest import ingest_document
from app.api.v1.deps import CurrentTenant, DbSession
from app.models.tenant import Chunk, Document
from app.schemas.chat import DocumentRead

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.post("/documents", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    tenant: CurrentTenant,
    db: DbSession,
    file: Annotated[UploadFile, File()],
) -> DocumentRead:
    """Sube un .txt/.md y lo indexa.

    TODO: PDF y DOCX. Mover a `workers/` cuando los archivos pasen de unos pocos MB:
    embeber en el request bloquea el worker de uvicorn.
    """
    raw = await file.read()
    text = raw.decode("utf-8", errors="replace")

    document = await ingest_document(db, tenant.id, title=file.filename or "sin-titulo", text=text)
    count = await db.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.document_id == document.id)
    )
    return DocumentRead(id=str(document.id), title=document.title, chunks=count or 0)


@router.get("/documents", response_model=list[DocumentRead])
async def list_documents(tenant: CurrentTenant, db: DbSession) -> list[DocumentRead]:
    stmt = (
        select(Document, func.count(Chunk.id))
        .outerjoin(Chunk, Chunk.document_id == Document.id)
        .where(Document.tenant_id == tenant.id)  # aislamiento tambien aca
        .group_by(Document.id)
        .order_by(Document.created_at.desc())
    )
    rows = await db.execute(stmt)
    return [DocumentRead(id=str(d.id), title=d.title, chunks=n) for d, n in rows.all()]
