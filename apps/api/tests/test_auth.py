"""Autenticacion y scopes.

Lo importante aca son los casos NEGATIVOS: que una clave que no deberia poder
hacer algo, efectivamente no pueda. Un test que solo prueba el camino feliz no
detecta un `require_scopes` mal puesto.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.routes import chat as chat_route
from app.core.security import generate_api_key, hash_api_key, verify_api_key
from app.main import app
from app.models.api_key import ApiKey, Scope
from app.models.tenant import Tenant


@pytest_asyncio.fixture
async def cliente() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def _crear_clave(
    db: AsyncSession,
    scopes: list[Scope],
    tenant_id: uuid.UUID | None,
    expires_at: datetime | None = None,
    revocada: bool = False,
) -> str:
    raw, prefix, hashed = generate_api_key()
    db.add(
        ApiKey(
            name=f"test-{prefix}",
            key_prefix=prefix,
            key_hash=hashed,
            tenant_id=tenant_id,
            scopes=[s.value for s in scopes],
            expires_at=expires_at,
            revoked_at=datetime.now(UTC) if revocada else None,
        )
    )
    await db.commit()
    return raw


@pytest_asyncio.fixture
async def escenario(db: AsyncSession) -> AsyncIterator[dict]:
    """Dos clientes, y una clave de cada tipo."""
    sufijo = uuid.uuid4().hex[:8]
    a = Tenant(slug=f"auth-a-{sufijo}", name="Cliente A", system_prompt="soy A")
    b = Tenant(slug=f"auth-b-{sufijo}", name="Cliente B", system_prompt="soy B")
    db.add_all([a, b])
    await db.commit()
    await db.refresh(a)
    await db.refresh(b)

    datos = {
        "tenant_a": a,
        "tenant_b": b,
        "admin": await _crear_clave(db, [Scope.ADMIN], None),
        "tenant_a_key": await _crear_clave(db, [Scope.TENANT], a.id),
        "chat_a_key": await _crear_clave(db, [Scope.CHAT], a.id),
        "revocada": await _crear_clave(db, [Scope.TENANT], a.id, revocada=True),
        "vencida": await _crear_clave(
            db, [Scope.TENANT], a.id, expires_at=datetime.now(UTC) - timedelta(days=1)
        ),
    }
    yield datos

    for t in (a, b):
        await db.execute(delete(ApiKey).where(ApiKey.tenant_id == t.id))
        await db.execute(delete(Tenant).where(Tenant.id == t.id))
    await db.execute(delete(ApiKey).where(ApiKey.tenant_id.is_(None)))
    await db.commit()


def _auth(clave: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {clave}"}


# ---------------------------------------------------------------------------
# Primitivas
# ---------------------------------------------------------------------------


def test_la_clave_no_se_guarda_en_texto_plano() -> None:
    raw, prefix, hashed = generate_api_key()
    assert raw.startswith("cba_")
    assert hashed != raw
    assert raw not in hashed
    assert len(hashed) == 64  # sha256 hex


def test_el_prefijo_no_alcanza_para_reconstruir_la_clave() -> None:
    raw, prefix, hashed = generate_api_key()
    assert raw.startswith(prefix)
    assert len(prefix) < len(raw)
    assert not verify_api_key(prefix, hashed)


def test_verificacion_correcta_e_incorrecta() -> None:
    raw, _, hashed = generate_api_key()
    assert verify_api_key(raw, hashed)
    assert not verify_api_key(raw + "x", hashed)
    assert not verify_api_key("cba_test_otra", hashed)


def test_dos_claves_nunca_colisionan() -> None:
    claves = {generate_api_key()[0] for _ in range(200)}
    assert len(claves) == 200


# ---------------------------------------------------------------------------
# Sin credencial o con credencial invalida
# ---------------------------------------------------------------------------


async def test_sin_header_no_se_entra(cliente: AsyncClient, escenario: dict) -> None:
    r = await cliente.get("/api/v1/tenants/me")
    assert r.status_code == 401


async def test_clave_inexistente(cliente: AsyncClient, escenario: dict) -> None:
    r = await cliente.get("/api/v1/tenants/me", headers=_auth("cba_test_noexiste"))
    assert r.status_code == 401


async def test_clave_revocada(cliente: AsyncClient, escenario: dict) -> None:
    r = await cliente.get("/api/v1/tenants/me", headers=_auth(escenario["revocada"]))
    assert r.status_code == 401


async def test_clave_vencida(cliente: AsyncClient, escenario: dict) -> None:
    r = await cliente.get("/api/v1/tenants/me", headers=_auth(escenario["vencida"]))
    assert r.status_code == 401


async def test_el_401_no_distingue_entre_causas(cliente: AsyncClient, escenario: dict) -> None:
    """No le decimos a quien prueba claves si acerto el prefijo, si vencio, etc."""
    cuerpos = set()
    for clave in ("cba_test_noexiste", escenario["revocada"], escenario["vencida"]):
        r = await cliente.get("/api/v1/tenants/me", headers=_auth(clave))
        cuerpos.add(r.text)
    assert len(cuerpos) == 1, f"los mensajes de error se diferencian: {cuerpos}"


# ---------------------------------------------------------------------------
# Scopes: lo que cada clave NO puede hacer
# ---------------------------------------------------------------------------


async def test_la_clave_del_widget_no_puede_leer_la_configuracion(
    cliente: AsyncClient, escenario: dict
) -> None:
    """La clave `chat` viaja en el navegador. Si pudiera leer /me, cualquiera
    que abra el inspector en la web del cliente le ve el system prompt."""
    r = await cliente.get("/api/v1/tenants/me", headers=_auth(escenario["chat_a_key"]))
    assert r.status_code == 403


async def test_la_clave_del_widget_no_puede_editar_el_prompt(
    cliente: AsyncClient, escenario: dict
) -> None:
    r = await cliente.patch(
        "/api/v1/tenants/me/prompt",
        headers=_auth(escenario["chat_a_key"]),
        json={"system_prompt": "sos un pirata"},
    )
    assert r.status_code == 403


async def test_la_clave_del_widget_no_puede_ver_documentos(
    cliente: AsyncClient, escenario: dict
) -> None:
    r = await cliente.get("/api/v1/knowledge/documents", headers=_auth(escenario["chat_a_key"]))
    assert r.status_code == 403


async def test_la_clave_de_un_cliente_no_puede_listar_todos_los_clientes(
    cliente: AsyncClient, escenario: dict
) -> None:
    r = await cliente.get("/api/v1/tenants", headers=_auth(escenario["tenant_a_key"]))
    assert r.status_code == 403


async def test_la_clave_de_un_cliente_no_puede_crear_clientes(
    cliente: AsyncClient, escenario: dict
) -> None:
    r = await cliente.post(
        "/api/v1/tenants",
        headers=_auth(escenario["tenant_a_key"]),
        json={"slug": "colado", "name": "Colado"},
    )
    assert r.status_code == 403


async def test_la_clave_de_un_cliente_no_puede_emitir_claves(
    cliente: AsyncClient, escenario: dict
) -> None:
    """Si pudiera, se auto-escalaria a admin."""
    r = await cliente.post(
        f"/api/v1/tenants/{escenario['tenant_a'].id}/keys",
        headers=_auth(escenario["tenant_a_key"]),
        json={"name": "escalada", "scopes": ["tenant"]},
    )
    assert r.status_code == 403


async def test_la_clave_admin_no_opera_sobre_un_cliente(
    cliente: AsyncClient, escenario: dict
) -> None:
    """Admin no tiene tenant asociado: /me no tiene sobre quien resolver.

    Es a proposito — obliga a decir explicitamente sobre que cliente se opera.
    """
    r = await cliente.get("/api/v1/tenants/me", headers=_auth(escenario["admin"]))
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Camino feliz + aislamiento
# ---------------------------------------------------------------------------


async def test_la_clave_del_cliente_lee_su_propia_configuracion(
    cliente: AsyncClient, escenario: dict
) -> None:
    r = await cliente.get("/api/v1/tenants/me", headers=_auth(escenario["tenant_a_key"]))
    assert r.status_code == 200
    assert r.json()["slug"] == escenario["tenant_a"].slug


async def test_la_clave_de_a_nunca_devuelve_datos_de_b(
    cliente: AsyncClient, escenario: dict
) -> None:
    """El tenant sale de la clave, no de un header manipulable."""
    r = await cliente.get(
        "/api/v1/tenants/me",
        headers={**_auth(escenario["tenant_a_key"]), "X-Tenant-Slug": escenario["tenant_b"].slug},
    )
    assert r.status_code == 200
    assert r.json()["slug"] == escenario["tenant_a"].slug, "el header no debe influir"


async def test_admin_emite_una_clave_y_el_secreto_se_muestra_una_vez(
    cliente: AsyncClient,
    escenario: dict,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    r = await cliente.post(
        f"/api/v1/tenants/{escenario['tenant_a'].id}/keys",
        headers=_auth(escenario["admin"]),
        json={"name": "widget de la web", "scopes": ["chat"]},
    )
    assert r.status_code == 201
    emitida = r.json()["api_key"]

    # Sirve de verdad contra /chat. Cortamos antes del LLM: lo que se prueba aca
    # es la autenticacion, no el motor.
    async def respuesta_fija(*args: object, **kwargs: object) -> str:
        return "hola!"

    monkeypatch.setattr(chat_route, "answer", respuesta_fija)
    r2 = await cliente.post("/api/v1/chat", headers=_auth(emitida), json={"message": "hola"})
    assert r2.status_code == 200

    # Y no se puede volver a obtener
    r3 = await cliente.get(
        f"/api/v1/tenants/{escenario['tenant_a'].id}/keys", headers=_auth(escenario["admin"])
    )
    assert r3.status_code == 200
    assert all("api_key" not in k for k in r3.json())

    # En la base solo esta el hash
    fila = await db.scalar(select(ApiKey).where(ApiKey.key_prefix == emitida[:16]))
    assert fila is not None
    assert fila.key_hash == hash_api_key(emitida)
    assert emitida not in fila.key_hash


async def test_admin_no_puede_emitir_otra_clave_admin_por_la_api(
    cliente: AsyncClient, escenario: dict
) -> None:
    r = await cliente.post(
        f"/api/v1/tenants/{escenario['tenant_a'].id}/keys",
        headers=_auth(escenario["admin"]),
        json={"name": "admin encubierta", "scopes": ["admin"]},
    )
    assert r.status_code == 400


async def test_una_clave_revocada_deja_de_funcionar_de_inmediato(
    cliente: AsyncClient, escenario: dict
) -> None:
    nueva = await cliente.post(
        f"/api/v1/tenants/{escenario['tenant_a'].id}/keys",
        headers=_auth(escenario["admin"]),
        json={"name": "temporal", "scopes": ["tenant"]},
    )
    clave = nueva.json()["api_key"]
    key_id = nueva.json()["id"]

    assert (await cliente.get("/api/v1/tenants/me", headers=_auth(clave))).status_code == 200

    await cliente.delete(
        f"/api/v1/tenants/{escenario['tenant_a'].id}/keys/{key_id}",
        headers=_auth(escenario["admin"]),
    )

    assert (await cliente.get("/api/v1/tenants/me", headers=_auth(clave))).status_code == 401
