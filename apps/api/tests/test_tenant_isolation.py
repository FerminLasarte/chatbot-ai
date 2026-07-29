"""El test que no se negocia.

Si esto se rompe, un cliente ve los documentos de otro.

Hay dos capas:

1. Guardarrailes estaticos: corren siempre, sin infraestructura.
2. Test de integracion contra Postgres+pgvector real. Se saltea solo si la base
   no esta levantada (`docker compose -f infra/docker-compose.yml up -d`).
"""

import inspect
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.rag import retriever
from app.core.config import settings
from app.models.tenant import Chunk, Document, Tenant

DIM = settings.embeddings_dim


# --------------------------------------------------------------------------
# 1. Guardarrailes estaticos
# --------------------------------------------------------------------------


def test_el_retriever_siempre_filtra_por_tenant() -> None:
    """Detecta el dia que alguien "simplifica" el retriever y borra el WHERE.

    Ignora las lineas comentadas: si no, comentar el filtro dejaria pasar el test
    porque el string seguiria presente en el archivo.
    """
    codigo = "\n".join(
        linea
        for linea in inspect.getsource(retriever.search).splitlines()
        if not linea.strip().startswith("#")
    )
    assert "Chunk.tenant_id == tenant_id" in codigo, (
        "El retriever perdio el filtro por tenant. Esto expone datos entre clientes."
    )


def test_chunk_tiene_tenant_id_indexado() -> None:
    """El filtro tiene que poder aplicarse sin JOIN y con indice."""
    column = Chunk.__table__.c.tenant_id
    assert not column.nullable
    assert column.index is True


# --------------------------------------------------------------------------
# 2. Integracion contra Postgres real
# --------------------------------------------------------------------------


def _vector(posicion_caliente: int) -> list[float]:
    """Vector unitario con un 1 en una sola posicion. Ortogonal a los demas."""
    v = [0.0] * DIM
    v[posicion_caliente] = 1.0
    return v


class _EmbedderFalso:
    """Devuelve un vector fijo. Evita depender de la API de Voyage en tests."""

    def __init__(self, vector: list[float]) -> None:
        self._vector = vector

    async def embed(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        return [self._vector for _ in texts]


@pytest_asyncio.fixture
async def dos_tenants(db: AsyncSession) -> AsyncIterator[tuple[Tenant, Tenant]]:
    sufijo = uuid.uuid4().hex[:8]
    a = Tenant(slug=f"test-a-{sufijo}", name="Cliente A")
    b = Tenant(slug=f"test-b-{sufijo}", name="Cliente B")
    db.add_all([a, b])
    await db.flush()

    # Documento y chunk para cada tenant, con vectores ortogonales entre si.
    for tenant, pos, texto in ((a, 0, "PRECIO DEL CLIENTE A"), (b, 1, "PRECIO DEL CLIENTE B")):
        doc = Document(tenant_id=tenant.id, title=f"doc-{tenant.slug}")
        db.add(doc)
        await db.flush()
        db.add(
            Chunk(
                tenant_id=tenant.id,
                document_id=doc.id,
                position=0,
                content=texto,
                embedding=_vector(pos),
            )
        )
    await db.commit()

    yield a, b

    for tenant in (a, b):
        await db.execute(delete(Chunk).where(Chunk.tenant_id == tenant.id))
        await db.execute(delete(Document).where(Document.tenant_id == tenant.id))
        await db.execute(delete(Tenant).where(Tenant.id == tenant.id))
    await db.commit()


async def test_busqueda_no_devuelve_chunks_de_otro_tenant(
    db: AsyncSession,
    dos_tenants: tuple[Tenant, Tenant],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Busca como A con una consulta IDENTICA al chunk de B.

    El vector de consulta es exactamente el de B y ortogonal al de A: si el filtro
    por tenant no existiera, el chunk de B seria el primer resultado. Es el peor
    caso posible a proposito.
    """
    a, b = dos_tenants
    monkeypatch.setattr(retriever, "get_embedder", lambda: _EmbedderFalso(_vector(1)))

    resultados = await retriever.search(db, a.id, "cuanto sale?")

    assert "PRECIO DEL CLIENTE B" not in resultados, (
        "FUGA ENTRE TENANTS: la busqueda de A devolvio contenido de B."
    )
    assert resultados == ["PRECIO DEL CLIENTE A"]


async def test_busqueda_de_tenant_sin_documentos_no_devuelve_nada(
    db: AsyncSession,
    dos_tenants: tuple[Tenant, Tenant],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un tenant recien creado no ve el corpus de nadie."""
    monkeypatch.setattr(retriever, "get_embedder", lambda: _EmbedderFalso(_vector(1)))

    huerfano = Tenant(slug=f"test-c-{uuid.uuid4().hex[:8]}", name="Cliente C")
    db.add(huerfano)
    await db.commit()
    try:
        assert await retriever.search(db, huerfano.id, "cuanto sale?") == []
    finally:
        await db.execute(delete(Tenant).where(Tenant.id == huerfano.id))
        await db.commit()
