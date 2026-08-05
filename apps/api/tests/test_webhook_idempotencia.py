"""Idempotencia y manejo de fallos del webhook.

Cubre las dos garantias del modulo `api/v1/routes/webhooks.py`:
un mensaje se procesa una sola vez, y ningun fallo queda en silencio.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.routes import webhooks
from app.channels.whatsapp.client import WhatsAppSendError
from app.core import cifrado as cifrado_mod
from app.core.retry import RetryableHTTPError, with_retry
from app.db.session import SessionLocal
from app.models.event import EventStatus, ProcessedEvent
from app.models.tenant import Tenant
from app.services import inbox, whatsapp

CLAVE_DE_PRUEBA = "6DLQaJDkYtFB3LMlBI1nCH_1kBaRhGSFTOM6vD-FJTM="
TOKEN_DE_PRUEBA = "EAAGtoken-de-prueba"


@pytest_asyncio.fixture
async def external_id(db: AsyncSession) -> AsyncIterator[str]:
    valor = f"wamid.test.{uuid.uuid4().hex}"
    yield valor
    await db.execute(delete(ProcessedEvent).where(ProcessedEvent.external_id == valor))
    await db.commit()


# --------------------------------------------------------------------------
# Idempotencia
# --------------------------------------------------------------------------


async def test_el_mismo_mensaje_se_reclama_una_sola_vez(db: AsyncSession, external_id: str) -> None:
    """Es el caso real: Meta reentrega el mismo mensaje."""
    primero = await inbox.claim(db, "whatsapp", external_id)
    segundo = await inbox.claim(db, "whatsapp", external_id)

    assert primero is not None, "el primer intento tiene que reclamar el mensaje"
    assert segundo is None, "la reentrega tiene que ser ignorada"


async def test_reclamos_concurrentes_solo_uno_gana(external_id: str) -> None:
    """Dos entregas simultaneas del mismo mensaje.

    Este es el caso que un `SELECT` + `INSERT` NO cubre: ambas transacciones
    verian "no existe" y las dos procesarian. Con ON CONFLICT solo una gana.
    """

    async def intentar() -> uuid.UUID | None:
        async with SessionLocal() as session:
            return await inbox.claim(session, "whatsapp", external_id)

    resultados = await asyncio.gather(*(intentar() for _ in range(5)))
    ganadores = [r for r in resultados if r is not None]

    assert len(ganadores) == 1, f"esperaba 1 ganador, hubo {len(ganadores)}"


async def test_mensajes_distintos_se_reclaman_los_dos(db: AsyncSession) -> None:
    a, b = f"wamid.{uuid.uuid4().hex}", f"wamid.{uuid.uuid4().hex}"
    try:
        assert await inbox.claim(db, "whatsapp", a) is not None
        assert await inbox.claim(db, "whatsapp", b) is not None
    finally:
        await db.execute(delete(ProcessedEvent).where(ProcessedEvent.external_id.in_([a, b])))
        await db.commit()


async def test_el_mismo_id_en_canales_distintos_no_colisiona(db: AsyncSession) -> None:
    """La unicidad es por (canal, external_id), no por external_id solo."""
    ext = f"id-compartido-{uuid.uuid4().hex}"
    try:
        assert await inbox.claim(db, "whatsapp", ext) is not None
        assert await inbox.claim(db, "webchat", ext) is not None
    finally:
        await db.execute(delete(ProcessedEvent).where(ProcessedEvent.external_id == ext))
        await db.commit()


# --------------------------------------------------------------------------
# Registro de resultado
# --------------------------------------------------------------------------


async def test_un_fallo_queda_registrado_y_es_encontrable(
    db: AsyncSession, external_id: str
) -> None:
    """Sin esto, un fallo en background es invisible."""
    event_id = await inbox.claim(db, "whatsapp", external_id)
    assert event_id is not None

    await inbox.mark_failed(db, event_id, "RuntimeError: Anthropic devolvio 429")

    evento = await db.scalar(select(ProcessedEvent).where(ProcessedEvent.id == event_id))
    assert evento is not None
    assert evento.status == EventStatus.FAILED.value
    assert "429" in (evento.error or "")

    fallados = await db.scalars(
        select(ProcessedEvent).where(ProcessedEvent.status == EventStatus.FAILED.value)
    )
    assert event_id in [e.id for e in fallados]


async def test_marcar_done_limpia_el_error(db: AsyncSession, external_id: str) -> None:
    event_id = await inbox.claim(db, "whatsapp", external_id)
    assert event_id is not None

    await inbox.mark_failed(db, event_id, "fallo transitorio")
    await inbox.mark_done(db, event_id)

    evento = await db.scalar(select(ProcessedEvent).where(ProcessedEvent.id == event_id))
    assert evento is not None
    assert evento.status == EventStatus.DONE.value
    assert evento.error is None


# --------------------------------------------------------------------------
# Reintentos
# --------------------------------------------------------------------------


async def test_reintenta_los_errores_transitorios() -> None:
    intentos = 0

    async def falla_dos_veces() -> str:
        nonlocal intentos
        intentos += 1
        if intentos < 3:
            raise httpx.ConnectTimeout("timeout simulado")
        return "ok"

    resultado = await with_retry(falla_dos_veces, base_delay=0.01, descripcion="test")
    assert resultado == "ok"
    assert intentos == 3


async def test_no_reintenta_errores_del_cliente() -> None:
    """Un 401 no mejora por insistir: hay que fallar de una y no gastar tiempo."""
    intentos = 0

    async def no_autorizado() -> None:
        nonlocal intentos
        intentos += 1
        raise httpx.HTTPStatusError(
            "401",
            request=httpx.Request("POST", "https://x"),
            response=httpx.Response(401, request=httpx.Request("POST", "https://x")),
        )

    with pytest.raises(httpx.HTTPStatusError):
        await with_retry(no_autorizado, base_delay=0.01, descripcion="test")
    assert intentos == 1, "un 401 no se reintenta"


async def test_agota_reintentos_y_levanta_excepcion_propia() -> None:
    async def siempre_falla() -> None:
        raise httpx.ConnectError("caido")

    with pytest.raises(RetryableHTTPError, match="tras 3 intentos"):
        await with_retry(siempre_falla, intentos=3, base_delay=0.01, descripcion="test")


# --------------------------------------------------------------------------
# El handler completo: ningun fallo puede escapar
# --------------------------------------------------------------------------


@pytest_asyncio.fixture
async def tenant(db: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Tenant]:
    # Un cliente que recibe mensajes de WhatsApp tiene, por definicion, sus
    # credenciales cargadas: sin token no habria como contestarle.
    monkeypatch.setattr(cifrado_mod.settings, "encryption_key", CLAVE_DE_PRUEBA)
    t = Tenant(slug=f"test-wh-{uuid.uuid4().hex[:8]}", name="Cliente de prueba")
    whatsapp.guardar_token(t, TOKEN_DE_PRUEBA)
    db.add(t)
    await db.commit()
    await db.refresh(t)
    yield t
    await db.execute(delete(ProcessedEvent).where(ProcessedEvent.tenant_id == t.id))
    await db.execute(delete(Tenant).where(Tenant.id == t.id))
    await db.commit()


async def test_si_falla_el_llm_no_propaga_registra_y_avisa_al_usuario(
    db: AsyncSession,
    tenant: Tenant,
    external_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El escenario que hoy perdia mensajes en silencio.

    Ya le respondimos 200 a Meta, asi que si `_handle` explota nadie se entera:
    ni reintento, ni log util, ni respuesta al usuario.
    """
    enviados: list[str] = []
    tokens_usados: list[str] = []

    async def llm_caido(*args: object, **kwargs: object) -> tuple[str, uuid.UUID]:
        raise RuntimeError("Anthropic devolvio 529 overloaded")

    async def capturar_envio(
        *, to: str, text: str, phone_number_id: str, access_token: str
    ) -> None:
        enviados.append(text)
        tokens_usados.append(access_token)

    monkeypatch.setattr(webhooks, "answer", llm_caido)
    monkeypatch.setattr(webhooks, "send_text", capturar_envio)

    event_id = await inbox.claim(db, "whatsapp", external_id, tenant.id)
    assert event_id is not None

    # No debe levantar: es la frontera del background task.
    await webhooks._handle(event_id, tenant.id, "549111234", "hola", "PHONE123")

    evento = await db.scalar(select(ProcessedEvent).where(ProcessedEvent.id == event_id))
    assert evento is not None
    assert evento.status == EventStatus.FAILED.value, "el fallo tiene que quedar registrado"
    assert "529" in (evento.error or ""), "el error tiene que ser diagnosticable"
    assert enviados == [webhooks.MENSAJE_DE_CORTESIA], "el usuario no puede quedar sin respuesta"


async def test_camino_feliz_marca_done_y_responde(
    db: AsyncSession,
    tenant: Tenant,
    external_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enviados: list[str] = []
    tokens_usados: list[str] = []

    async def llm_ok(*args: object, **kwargs: object) -> tuple[str, uuid.UUID]:
        return "Hola! Atendemos de 9 a 18.", uuid.uuid4()

    async def capturar_envio(
        *, to: str, text: str, phone_number_id: str, access_token: str
    ) -> None:
        enviados.append(text)
        tokens_usados.append(access_token)

    monkeypatch.setattr(webhooks, "answer", llm_ok)
    monkeypatch.setattr(webhooks, "send_text", capturar_envio)

    event_id = await inbox.claim(db, "whatsapp", external_id, tenant.id)
    assert event_id is not None

    await webhooks._handle(event_id, tenant.id, "549111234", "que horario tienen?", "PHONE123")

    evento = await db.scalar(select(ProcessedEvent).where(ProcessedEvent.id == event_id))
    assert evento is not None
    assert evento.status == EventStatus.DONE.value
    assert enviados == ["Hola! Atendemos de 9 a 18."]
    # El token que se usa para enviar es el del cliente dueño del numero, no
    # uno global: es lo que permite que cada negocio conteste desde el suyo.
    assert tokens_usados == [TOKEN_DE_PRUEBA]


async def test_si_falla_el_envio_no_se_marca_como_done(
    db: AsyncSession,
    tenant: Tenant,
    external_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generar la respuesta y no poder entregarla NO es un exito."""

    async def llm_ok(*args: object, **kwargs: object) -> tuple[str, uuid.UUID]:
        return "respuesta que nunca llega", uuid.uuid4()

    intentos: list[str] = []

    async def envio_roto(*, to: str, text: str, phone_number_id: str, access_token: str) -> None:
        intentos.append(text)
        raise WhatsAppSendError("Meta rechazo el envio (400)")

    monkeypatch.setattr(webhooks, "answer", llm_ok)
    monkeypatch.setattr(webhooks, "send_text", envio_roto)

    event_id = await inbox.claim(db, "whatsapp", external_id, tenant.id)
    assert event_id is not None

    await webhooks._handle(event_id, tenant.id, "549111234", "hola", "PHONE123")

    evento = await db.scalar(select(ProcessedEvent).where(ProcessedEvent.id == event_id))
    assert evento is not None
    assert evento.status == EventStatus.FAILED.value
    # Intento la respuesta y despues el mensaje de cortesia, que tambien falla.
    assert len(intentos) == 2
