"""Cuota mensual por cliente.

Lo que se prueba en serio aca es la CONCURRENCIA. Un chequeo secuencial pasa
aunque la implementacion tenga una carrera; solo se nota con peticiones
simultaneas, que es exactamente lo que pasa con una clave de widget en un loop.
"""

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm.client import Respuesta
from app.core.security import generate_api_key
from app.db.session import SessionLocal
from app.main import app
from app.models.api_key import ApiKey, Scope
from app.models.tenant import Tenant
from app.models.usage import TenantUsage, periodo_actual
from app.services import conversation, quota


@pytest_asyncio.fixture
async def tenant(db: AsyncSession) -> AsyncIterator[Tenant]:
    t = Tenant(
        slug=f"quota-{uuid.uuid4().hex[:8]}",
        name="Cliente con cuota",
        monthly_message_limit=5,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    yield t
    await db.execute(delete(TenantUsage).where(TenantUsage.tenant_id == t.id))
    await db.execute(delete(Tenant).where(Tenant.id == t.id))
    await db.commit()


async def _set_limite(db: AsyncSession, tenant: Tenant, limite: int | None) -> None:
    await db.execute(
        update(Tenant).where(Tenant.id == tenant.id).values(monthly_message_limit=limite)
    )
    await db.commit()
    await db.refresh(tenant)


# ---------------------------------------------------------------------------
# Comportamiento basico
# ---------------------------------------------------------------------------


async def test_consume_hasta_el_limite_y_despues_frena(db: AsyncSession, tenant: Tenant) -> None:
    for _ in range(5):
        await quota.consumir_mensaje(db, tenant)

    with pytest.raises(quota.QuotaExcedida) as exc:
        await quota.consumir_mensaje(db, tenant)

    assert exc.value.limite == 5
    assert exc.value.periodo == periodo_actual()

    consumo = await quota.consumo_actual(db, tenant)
    assert consumo.messages == 5, "no debe contabilizar el mensaje rechazado"
    assert consumo.remaining == 0


async def test_limite_cero_frena_desde_el_primer_mensaje(db: AsyncSession, tenant: Tenant) -> None:
    """Sirve para suspender a un cliente sin borrarlo."""
    await _set_limite(db, tenant, 0)
    with pytest.raises(quota.QuotaExcedida):
        await quota.consumir_mensaje(db, tenant)

    assert (await quota.consumo_actual(db, tenant)).messages == 0


async def test_sin_limite_nunca_frena_pero_sigue_contando(db: AsyncSession, tenant: Tenant) -> None:
    """NULL = sin tope. Igual se mide, para poder facturar y detectar abuso."""
    await _set_limite(db, tenant, None)
    for _ in range(12):
        await quota.consumir_mensaje(db, tenant)

    consumo = await quota.consumo_actual(db, tenant)
    assert consumo.messages == 12
    assert consumo.limit is None
    assert consumo.remaining is None


async def test_la_cuota_de_un_cliente_no_afecta_a_otro(db: AsyncSession, tenant: Tenant) -> None:
    otro = Tenant(slug=f"quota-b-{uuid.uuid4().hex[:8]}", name="Otro", monthly_message_limit=5)
    db.add(otro)
    await db.commit()
    await db.refresh(otro)
    try:
        for _ in range(5):
            await quota.consumir_mensaje(db, tenant)
        with pytest.raises(quota.QuotaExcedida):
            await quota.consumir_mensaje(db, tenant)

        # El otro cliente arranca de cero.
        await quota.consumir_mensaje(db, otro)
        assert (await quota.consumo_actual(db, otro)).messages == 1
    finally:
        await db.execute(delete(TenantUsage).where(TenantUsage.tenant_id == otro.id))
        await db.execute(delete(Tenant).where(Tenant.id == otro.id))
        await db.commit()


# ---------------------------------------------------------------------------
# Concurrencia: el motivo por el que el chequeo y el incremento van juntos
# ---------------------------------------------------------------------------


async def test_peticiones_simultaneas_no_pasan_del_limite(tenant: Tenant) -> None:
    """20 peticiones simultaneas contra un limite de 5.

    Con `leer contador -> decidir -> incrementar`, las 20 leerian 0 y las 20
    pasarian. El UPDATE condicional deja pasar exactamente 5.
    """

    async def intentar() -> bool:
        async with SessionLocal() as session:
            fresco = await session.get(Tenant, tenant.id)
            assert fresco is not None
            try:
                await quota.consumir_mensaje(session, fresco)
                return True
            except quota.QuotaExcedida:
                return False

    resultados = await asyncio.gather(*(intentar() for _ in range(20)))
    aceptados = sum(resultados)

    assert aceptados == 5, f"pasaron {aceptados} mensajes con un limite de 5"

    async with SessionLocal() as session:
        fresco = await session.get(Tenant, tenant.id)
        assert fresco is not None
        assert (await quota.consumo_actual(session, fresco)).messages == 5


async def test_el_contador_nunca_supera_el_limite(tenant: Tenant) -> None:
    """Invariante fuerte: pase lo que pase, messages <= limite."""

    async def intentar() -> None:
        async with SessionLocal() as session:
            fresco = await session.get(Tenant, tenant.id)
            assert fresco is not None
            with contextlib.suppress(quota.QuotaExcedida):
                await quota.consumir_mensaje(session, fresco)

    await asyncio.gather(*(intentar() for _ in range(50)))

    async with SessionLocal() as session:
        fila = await session.scalar(
            text("SELECT messages FROM tenant_usage WHERE tenant_id = :t").bindparams(t=tenant.id)
        )
    assert fila <= 5, f"el contador se paso: {fila}"


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------


async def test_los_tokens_se_acumulan(db: AsyncSession, tenant: Tenant) -> None:
    await quota.consumir_mensaje(db, tenant)
    await quota.registrar_tokens(db, tenant.id, input_tokens=100, output_tokens=50)
    await quota.registrar_tokens(db, tenant.id, input_tokens=30, cache_read_tokens=900)

    consumo = await quota.consumo_actual(db, tenant)
    assert consumo.input_tokens == 130
    assert consumo.output_tokens == 50
    assert consumo.cache_read_tokens == 900


async def test_registrar_tokens_no_consume_cuota(db: AsyncSession, tenant: Tenant) -> None:
    """Facturar y cuotear son ejes distintos."""
    await quota.registrar_tokens(db, tenant.id, input_tokens=999_999)
    assert (await quota.consumo_actual(db, tenant)).messages == 0


async def test_sin_consumo_devuelve_ceros(db: AsyncSession, tenant: Tenant) -> None:
    consumo = await quota.consumo_actual(db, tenant)
    assert consumo.messages == 0
    assert consumo.limit == 5
    assert consumo.remaining == 5


# ---------------------------------------------------------------------------
# A nivel HTTP
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def cliente() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def clave_chat(db: AsyncSession, tenant: Tenant) -> AsyncIterator[str]:
    raw, prefix, hashed = generate_api_key()
    db.add(
        ApiKey(
            name="widget",
            key_prefix=prefix,
            key_hash=hashed,
            tenant_id=tenant.id,
            scopes=[Scope.CHAT.value],
        )
    )
    await db.commit()
    yield raw
    await db.execute(delete(ApiKey).where(ApiKey.key_prefix == prefix))
    await db.commit()


async def test_chat_devuelve_429_cuando_se_agota_la_cuota(
    cliente: AsyncClient,
    db: AsyncSession,
    tenant: Tenant,
    clave_chat: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Y sobre todo: la cuota frena ANTES de gastar en el LLM.

    Si contara el consumo despues de llamar al modelo, la cuota no protegeria
    nada: ya habrias pagado los tokens del mensaje que rechazas.
    """
    llamadas_al_llm = 0

    async def llm_espia(*args: object, **kwargs: object) -> Respuesta:
        nonlocal llamadas_al_llm
        llamadas_al_llm += 1
        return Respuesta(text="ok", input_tokens=10, output_tokens=5)

    async def sin_contexto(*args: object, **kwargs: object) -> list[str]:
        return []

    monkeypatch.setattr(conversation, "complete", llm_espia)
    monkeypatch.setattr(conversation, "search", sin_contexto)

    headers = {"Authorization": f"Bearer {clave_chat}"}
    for _ in range(5):
        r = await cliente.post("/api/v1/chat", headers=headers, json={"message": "hola"})
        assert r.status_code == 200

    assert llamadas_al_llm == 5

    r = await cliente.post("/api/v1/chat", headers=headers, json={"message": "hola"})
    assert r.status_code == 429
    assert r.json()["limit"] == 5
    assert llamadas_al_llm == 5, "el mensaje rechazado NO debe llegar al LLM"


async def test_el_cliente_ve_su_consumo_pero_no_puede_subirse_el_limite(
    cliente: AsyncClient, db: AsyncSession, tenant: Tenant
) -> None:
    raw, prefix, hashed = generate_api_key()
    db.add(
        ApiKey(
            name="dashboard",
            key_prefix=prefix,
            key_hash=hashed,
            tenant_id=tenant.id,
            scopes=[Scope.TENANT.value],
        )
    )
    await db.commit()
    headers = {"Authorization": f"Bearer {raw}"}
    try:
        await quota.consumir_mensaje(db, tenant)

        r = await cliente.get("/api/v1/tenants/me/usage", headers=headers)
        assert r.status_code == 200
        assert r.json()["messages"] == 1
        assert r.json()["remaining"] == 4

        # Subirse el techo es de la agencia, no del cliente.
        r2 = await cliente.patch(
            f"/api/v1/tenants/{tenant.id}/limit",
            headers=headers,
            json={"monthly_message_limit": 999999},
        )
        assert r2.status_code == 403
    finally:
        await db.execute(delete(ApiKey).where(ApiKey.key_prefix == prefix))
        await db.commit()
