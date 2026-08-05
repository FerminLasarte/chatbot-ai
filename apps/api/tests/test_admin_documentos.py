"""Endpoints de la agencia para operar sobre un cliente concreto.

Los casos que mas importan son los de AISLAMIENTO: que un document_id del
cliente A no se pueda leer ni borrar pasando el tenant_id del cliente B. Sin
esos filtros, una clave admin (que no tiene tenant propio) seria una puerta
abierta entre clientes.
"""

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_api_key
from app.main import app
from app.models.api_key import ApiKey, Scope
from app.models.tenant import Chunk, Document, Tenant


@pytest_asyncio.fixture
async def cliente() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def _clave(db: AsyncSession, scopes: list[Scope], tenant_id: uuid.UUID | None) -> str:
    raw, prefix, hashed = generate_api_key()
    db.add(
        ApiKey(
            name=f"test-{prefix}",
            key_prefix=prefix,
            key_hash=hashed,
            tenant_id=tenant_id,
            scopes=[s.value for s in scopes],
        )
    )
    await db.commit()
    return raw


@pytest_asyncio.fixture
async def escenario(db: AsyncSession) -> AsyncIterator[dict]:
    sufijo = uuid.uuid4().hex[:8]
    a = Tenant(slug=f"adm-a-{sufijo}", name="Cliente A", system_prompt="soy A")
    b = Tenant(slug=f"adm-b-{sufijo}", name="Cliente B", system_prompt="soy B")
    db.add_all([a, b])
    await db.commit()
    await db.refresh(a)
    await db.refresh(b)

    # Un documento de cada cliente, sin pasar por embeddings (no hace falta
    # gastar llamadas al proveedor para probar permisos y filtros).
    doc_a = Document(tenant_id=a.id, title="doc-de-a.txt")
    doc_b = Document(tenant_id=b.id, title="doc-de-b.txt")
    db.add_all([doc_a, doc_b])
    await db.commit()
    await db.refresh(doc_a)
    await db.refresh(doc_b)

    datos = {
        "a": a,
        "b": b,
        "doc_a": doc_a,
        "doc_b": doc_b,
        "admin": await _clave(db, [Scope.ADMIN], None),
        "tenant_a": await _clave(db, [Scope.TENANT], a.id),
    }
    yield datos

    for t in (a, b):
        actual = await db.get(Tenant, t.id)
        if actual is not None:
            await db.delete(actual)
    await db.commit()


def _auth(k: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {k}"}


async def _existe(db: AsyncSession, document_id: uuid.UUID) -> bool:
    """Consulta el estado REAL de la base, no la cache de la sesion del test.

    La peticion HTTP corre en otra sesion, asi que `db.get()` devolveria el
    objeto que ya estaba en el identity map de esta aunque la fila ya no exista:
    un test de borrado pasaria con el borrado roto, y -peor- el de aislamiento
    pasaria aunque el filtro por tenant no existiera.

    Se pide una COLUMNA en vez de la entidad a proposito: el resultado es un
    escalar que no pasa por el identity map, asi que no hay nada cacheado que
    pueda mentir (y a diferencia de expire_all(), no invalida los objetos del
    fixture, que despues los necesita el teardown).
    """
    return (await db.scalar(select(Document.id).where(Document.id == document_id))) is not None


# --- Prompt ---


async def test_admin_edita_el_prompt_de_un_cliente(
    cliente: AsyncClient, escenario: dict, db: AsyncSession
) -> None:
    a = escenario["a"]
    r = await cliente.patch(
        f"/api/v1/tenants/{a.id}/prompt",
        headers=_auth(escenario["admin"]),
        json={"system_prompt": "Sos el asistente de una inmobiliaria."},
    )
    assert r.status_code == 200
    assert r.json()["system_prompt"] == "Sos el asistente de una inmobiliaria."

    await db.refresh(a)
    assert a.system_prompt == "Sos el asistente de una inmobiliaria."


async def test_una_clave_de_cliente_no_puede_editar_prompts_por_esta_via(
    cliente: AsyncClient, escenario: dict
) -> None:
    """La ruta de la agencia exige scope admin, aunque el cliente sea el suyo."""
    r = await cliente.patch(
        f"/api/v1/tenants/{escenario['a'].id}/prompt",
        headers=_auth(escenario["tenant_a"]),
        json={"system_prompt": "me auto-asigno otro prompt"},
    )
    assert r.status_code == 403


async def test_prompt_de_cliente_inexistente_da_404(cliente: AsyncClient, escenario: dict) -> None:
    r = await cliente.patch(
        f"/api/v1/tenants/{uuid.uuid4()}/prompt",
        headers=_auth(escenario["admin"]),
        json={"system_prompt": "x"},
    )
    assert r.status_code == 404


# --- Listado de documentos ---


async def test_el_listado_solo_trae_documentos_del_cliente_pedido(
    cliente: AsyncClient, escenario: dict
) -> None:
    r = await cliente.get(
        f"/api/v1/tenants/{escenario['a'].id}/documents", headers=_auth(escenario["admin"])
    )
    assert r.status_code == 200
    titulos = [d["title"] for d in r.json()]
    assert titulos == ["doc-de-a.txt"]
    assert "doc-de-b.txt" not in titulos


async def test_listar_documentos_exige_clave_admin(cliente: AsyncClient, escenario: dict) -> None:
    r = await cliente.get(
        f"/api/v1/tenants/{escenario['a'].id}/documents", headers=_auth(escenario["tenant_a"])
    )
    assert r.status_code == 403


# --- Borrado ---


async def test_borrar_un_documento_lo_saca_de_la_base(
    cliente: AsyncClient, escenario: dict, db: AsyncSession
) -> None:
    doc_a = escenario["doc_a"]
    r = await cliente.delete(
        f"/api/v1/tenants/{escenario['a'].id}/documents/{doc_a.id}",
        headers=_auth(escenario["admin"]),
    )
    assert r.status_code == 204
    assert not await _existe(db, doc_a.id)


async def test_no_se_puede_borrar_un_documento_de_otro_cliente(
    cliente: AsyncClient, escenario: dict, db: AsyncSession
) -> None:
    """★ El caso peligroso: document_id de B pasando el tenant_id de A."""
    doc_b = escenario["doc_b"]
    r = await cliente.delete(
        f"/api/v1/tenants/{escenario['a'].id}/documents/{doc_b.id}",
        headers=_auth(escenario["admin"]),
    )
    assert r.status_code == 404, "no debe permitir borrar cruzando clientes"
    assert await _existe(db, doc_b.id), "el documento de B tiene que seguir existiendo"


async def test_borrar_documento_borra_tambien_sus_fragmentos(
    cliente: AsyncClient, escenario: dict, db: AsyncSession
) -> None:
    """Si quedaran fragmentos huerfanos, el bot seguiria respondiendo con el
    contenido de un documento que la agencia ya dio de baja."""
    a = escenario["a"]
    doc = Document(tenant_id=a.id, title="tarifario-viejo.txt")
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    db.add(
        Chunk(
            tenant_id=a.id,
            document_id=doc.id,
            position=0,
            content="el corte sale 100",
            embedding=[0.0] * 1024,
        )
    )
    await db.commit()

    r = await cliente.delete(
        f"/api/v1/tenants/{a.id}/documents/{doc.id}", headers=_auth(escenario["admin"])
    )
    assert r.status_code == 204

    # Se cuenta con una consulta escalar por el mismo motivo que en _existe:
    # traer las entidades devolveria las que esta sesion ya tiene en memoria.
    restantes = await db.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.document_id == doc.id)
    )
    assert restantes == 0


# --- Subida ---


async def test_subir_un_txt_lo_indexa_para_ese_cliente(
    cliente: AsyncClient, escenario: dict, db: AsyncSession
) -> None:
    """Toca el proveedor de embeddings de verdad; se saltea si no hay clave."""
    from app.core.config import settings

    if not settings.voyage_api_key:
        pytest.skip("sin VOYAGE_API_KEY")

    a = escenario["a"]
    r = await cliente.post(
        f"/api/v1/tenants/{a.id}/documents",
        headers=_auth(escenario["admin"]),
        files={"file": ("info.txt", b"La consulta sale 5000 pesos.", "text/plain")},
    )
    assert r.status_code == 201
    assert r.json()["chunks"] >= 1

    doc_id = uuid.UUID(r.json()["id"])
    doc = await db.get(Document, doc_id)
    assert doc is not None
    assert doc.tenant_id == a.id, "el documento tiene que quedar bajo el cliente pedido"


async def test_subir_documento_exige_clave_admin(cliente: AsyncClient, escenario: dict) -> None:
    r = await cliente.post(
        f"/api/v1/tenants/{escenario['a'].id}/documents",
        headers=_auth(escenario["tenant_a"]),
        files={"file": ("info.txt", b"hola", "text/plain")},
    )
    assert r.status_code == 403


async def test_un_pdf_ilegible_da_422_y_no_crea_el_documento(
    cliente: AsyncClient, escenario: dict, db: AsyncSession
) -> None:
    a = escenario["a"]
    r = await cliente.post(
        f"/api/v1/tenants/{a.id}/documents",
        headers=_auth(escenario["admin"]),
        files={"file": ("roto.pdf", b"esto no es un pdf", "application/pdf")},
    )
    assert r.status_code == 422

    docs = list(await db.scalars(select(Document).where(Document.tenant_id == a.id)))
    assert [d.title for d in docs] == ["doc-de-a.txt"], "no debe quedar un documento vacio"
