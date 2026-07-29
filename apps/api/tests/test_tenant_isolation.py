"""El test que no se negocia.

Si esto se rompe, un cliente ve los documentos de otro. Se escribe en la semana 1,
no en el mes 3.

Requiere un Postgres con pgvector (`docker compose -f infra/docker-compose.yml up -d`)
y la variable DATABASE_URL apuntando a una base de test.
"""

import inspect

import pytest

from app.ai.rag import retriever
from app.models.tenant import Chunk


def test_el_retriever_siempre_filtra_por_tenant() -> None:
    """Guardarraíl estatico: la query de busqueda menciona tenant_id.

    Barato y sorprendentemente efectivo: detecta el dia que alguien "simplifica"
    el retriever y borra el WHERE.
    """
    source = inspect.getsource(retriever.search)
    assert "Chunk.tenant_id == tenant_id" in source, (
        "El retriever perdio el filtro por tenant. Esto expone datos entre clientes."
    )


def test_chunk_tiene_tenant_id_indexado() -> None:
    """El filtro tiene que poder aplicarse sin JOIN y con indice."""
    column = Chunk.__table__.c.tenant_id
    assert not column.nullable
    assert column.index is True


@pytest.mark.skip(reason="TODO: integracion end-to-end con Postgres+pgvector de test")
async def test_busqueda_no_devuelve_chunks_de_otro_tenant() -> None:
    """Crear tenant A y B, indexar un documento en cada uno, buscar como A con un
    texto que matchea el documento de B, y verificar que no vuelve nada de B."""
