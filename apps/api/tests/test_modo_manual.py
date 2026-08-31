"""Modo manual: pausar el bot en una conversacion para atenderla a mano.

Lo que se defiende aca:

1. Con la pausa vigente NO se genera ni se envia respuesta, pero el mensaje del
   usuario SI se guarda. Perder el historial mientras una persona atiende seria
   dejarle un agujero al bot para cuando retome.

2. La pausa VENCE. Es la razon de ser del diseño: un interruptor olvidado deja a
   un cliente sin respuestas automaticas para siempre y en silencio.

3. Al retomar, la tanda de mensajes sin contestar entra como UN turno.

4. Una conversacion de otro cliente no se puede pausar ni ver.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.routes import webhooks
from app.core import cifrado as cifrado_mod
from app.core.security import generate_api_key
from app.main import app
from app.models.api_key import ApiKey, Scope
from app.models.event import EventStatus, ProcessedEvent
from app.models.tenant import Conversation, Message, Tenant
from app.services import inbox, whatsapp
from app.services.conversation import _cargar_historia, _guardar_mensaje

CLAVE_DE_PRUEBA = "6DLQaJDkYtFB3LMlBI1nCH_1kBaRhGSFTOM6vD-FJTM="
TOKEN_DE_PRUEBA = "EAAGtoken-de-prueba"
NUMERO = "5491133344455"


@pytest_asyncio.fixture
async def tenant(db: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Tenant]:
    monkeypatch.setattr(cifrado_mod.settings, "encryption_key", CLAVE_DE_PRUEBA)
    t = Tenant(slug=f"test-manual-{uuid.uuid4().hex[:8]}", name="Cliente de prueba")
    whatsapp.guardar_token(t, TOKEN_DE_PRUEBA)
    db.add(t)
    await db.commit()
    await db.refresh(t)
    yield t
    await db.execute(delete(ProcessedEvent).where(ProcessedEvent.tenant_id == t.id))
    await db.execute(delete(Tenant).where(Tenant.id == t.id))
    await db.commit()


@pytest_asyncio.fixture
async def admin(db: AsyncSession) -> AsyncIterator[str]:
    raw, prefix, hashed = generate_api_key()
    db.add(
        ApiKey(
            name="admin-manual",
            key_prefix=prefix,
            key_hash=hashed,
            tenant_id=None,
            scopes=[Scope.ADMIN.value],
        )
    )
    await db.commit()
    yield raw
    await db.execute(delete(ApiKey).where(ApiKey.key_prefix == prefix))
    await db.commit()


@pytest_asyncio.fixture
async def cliente() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def external_id(db: AsyncSession) -> AsyncIterator[str]:
    valor = f"wamid.manual.{uuid.uuid4().hex}"
    yield valor
    await db.execute(delete(ProcessedEvent).where(ProcessedEvent.external_id == valor))
    await db.commit()


def _auth(k: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {k}"}


async def _conversacion(
    db: AsyncSession, tenant: Tenant, *, pausada_hasta: datetime | None = None
) -> Conversation:
    c = Conversation(
        tenant_id=tenant.id,
        channel="whatsapp",
        external_id=NUMERO,
        pausada_hasta=pausada_hasta,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


def _espia_del_motor(monkeypatch: pytest.MonkeyPatch) -> tuple[list, list]:
    """Registra si se llamo al LLM y que se envio, sin llamar a ninguno."""
    llamadas: list[str] = []
    enviados: list[str] = []

    async def falso_answer(*args: object, **kwargs: object) -> tuple[str, uuid.UUID, bool]:
        llamadas.append("answer")
        return "respuesta automatica", uuid.uuid4(), False

    async def falso_envio(*, to: str, text: str, phone_number_id: str, access_token: str) -> None:
        enviados.append(text)

    monkeypatch.setattr(webhooks, "answer", falso_answer)
    monkeypatch.setattr(webhooks, "send_text", falso_envio)
    return llamadas, enviados


# --------------------------------------------------------------------------
# El punto de control del webhook
# --------------------------------------------------------------------------


async def test_con_la_pausa_vigente_no_se_responde_pero_se_guarda(
    db: AsyncSession,
    tenant: Tenant,
    external_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★ El caso que motiva toda la feature."""
    llamadas, enviados = _espia_del_motor(monkeypatch)
    conversacion = await _conversacion(
        db, tenant, pausada_hasta=datetime.now(UTC) + timedelta(hours=2)
    )

    event_id = await inbox.claim(db, "whatsapp", external_id, tenant.id)
    assert event_id is not None
    await webhooks._handle(event_id, tenant.id, NUMERO, "hola, necesito ayuda", "PHONE123")

    assert llamadas == [], "no se tiene que llamar al modelo con el bot pausado"
    assert enviados == [], "el bot no puede pisarle la respuesta a la persona"

    mensajes = (
        await db.scalars(
            select(Message)
            .where(Message.conversation_id == conversacion.id)
            .order_by(Message.position)
        )
    ).all()
    assert [m.content for m in mensajes] == ["hola, necesito ayuda"]
    assert [m.role for m in mensajes] == ["user"]

    evento = await db.get(ProcessedEvent, event_id)
    assert evento is not None
    assert evento.status == EventStatus.DONE.value, "esta procesado: no hay que reintentarlo"


async def test_con_la_pausa_vencida_el_bot_vuelve_a_responder(
    db: AsyncSession,
    tenant: Tenant,
    external_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★ La pausa se apaga sola. Sin esto, un olvido silencia al bot para siempre."""
    llamadas, enviados = _espia_del_motor(monkeypatch)
    await _conversacion(db, tenant, pausada_hasta=datetime.now(UTC) - timedelta(minutes=1))

    event_id = await inbox.claim(db, "whatsapp", external_id, tenant.id)
    assert event_id is not None
    await webhooks._handle(event_id, tenant.id, NUMERO, "seguis ahi?", "PHONE123")

    assert llamadas == ["answer"]
    assert enviados == ["respuesta automatica"]


async def test_sin_pausa_el_flujo_normal_no_cambia(
    db: AsyncSession,
    tenant: Tenant,
    external_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llamadas, enviados = _espia_del_motor(monkeypatch)

    event_id = await inbox.claim(db, "whatsapp", external_id, tenant.id)
    assert event_id is not None
    await webhooks._handle(event_id, tenant.id, NUMERO, "que horario tienen?", "PHONE123")

    assert llamadas == ["answer"]
    assert enviados == ["respuesta automatica"]


# --------------------------------------------------------------------------
# La historia que ve el modelo al retomar
# --------------------------------------------------------------------------


async def test_los_mensajes_sin_contestar_entran_como_un_solo_turno(
    db: AsyncSession, tenant: Tenant
) -> None:
    """Durante la pausa se acumulan mensajes del usuario sin respuesta en el medio.

    Al retomar tienen que llegar como UNA intervencion: es lo que realmente
    paso, y ademas evita mandarle a la API varios turnos 'user' pegados.
    """
    conversacion = await _conversacion(db, tenant)
    await _guardar_mensaje(db, conversacion.id, "user", "hola")
    await _guardar_mensaje(db, conversacion.id, "assistant", "hola! en que te ayudo?")
    await _guardar_mensaje(db, conversacion.id, "user", "queria consultar por un presupuesto")
    await _guardar_mensaje(db, conversacion.id, "user", "es para 40 personas")
    await _guardar_mensaje(db, conversacion.id, "user", "el sabado")

    historia = await _cargar_historia(db, conversacion.id)

    assert [m["role"] for m in historia] == ["user", "assistant", "user"]
    ultimo = historia[-1]["content"]
    assert isinstance(ultimo, list)
    assert [b["text"] for b in ultimo] == [
        "queria consultar por un presupuesto",
        "es para 40 personas",
        "el sabado",
    ]


# --------------------------------------------------------------------------
# El endpoint del panel
# --------------------------------------------------------------------------


async def test_listar_conversaciones_trae_estado_y_ultimo_mensaje(
    db: AsyncSession, tenant: Tenant, admin: str, cliente: AsyncClient
) -> None:
    conversacion = await _conversacion(db, tenant)
    await _guardar_mensaje(db, conversacion.id, "user", "hola")
    await _guardar_mensaje(db, conversacion.id, "assistant", "buenas! contame")

    r = await cliente.get(f"/api/v1/tenants/{tenant.id}/conversations", headers=_auth(admin))
    assert r.status_code == 200
    (fila,) = r.json()
    assert fila["external_id"] == NUMERO
    assert fila["mensajes"] == 2
    assert fila["ultimo_mensaje"] == "buenas! contame"
    assert fila["en_modo_manual"] is False
    assert fila["pausada_hasta"] is None


async def test_pausar_y_reanudar_desde_el_panel(
    db: AsyncSession, tenant: Tenant, admin: str, cliente: AsyncClient
) -> None:
    conversacion = await _conversacion(db, tenant)
    url = f"/api/v1/tenants/{tenant.id}/conversations/{conversacion.id}/manual"

    r = await cliente.post(url, headers=_auth(admin), json={"horas": 3})
    assert r.status_code == 200
    assert r.json()["en_modo_manual"] is True
    assert r.json()["pausada_hasta"] is not None
    # El panel muestra "vuelve en X" con este numero: lo resuelve la API porque
    # es la unica que tiene el reloj bien puesto.
    assert 175 <= r.json()["minutos_restantes"] <= 180

    await db.refresh(conversacion)
    assert conversacion.en_modo_manual()

    r = await cliente.delete(url, headers=_auth(admin))
    assert r.status_code == 200
    assert r.json()["en_modo_manual"] is False
    assert r.json()["pausada_hasta"] is None
    assert r.json()["minutos_restantes"] is None

    await db.refresh(conversacion)
    assert not conversacion.en_modo_manual()


async def test_no_se_puede_pausar_indefinidamente(
    db: AsyncSession, tenant: Tenant, admin: str, cliente: AsyncClient
) -> None:
    """Una semana es el tope. La pausa sin vencimiento es justo lo que se evita."""
    conversacion = await _conversacion(db, tenant)
    r = await cliente.post(
        f"/api/v1/tenants/{tenant.id}/conversations/{conversacion.id}/manual",
        headers=_auth(admin),
        json={"horas": 24 * 365},
    )
    assert r.status_code == 422


async def test_no_se_puede_tocar_la_conversacion_de_otro_cliente(
    db: AsyncSession, tenant: Tenant, admin: str, cliente: AsyncClient
) -> None:
    """★ Sin el filtro por tenant_id, un id ajeno entraria por aca."""
    otro = Tenant(slug=f"test-otro-{uuid.uuid4().hex[:8]}", name="Otro")
    db.add(otro)
    await db.commit()
    await db.refresh(otro)
    ajena = await _conversacion(db, otro)

    try:
        r = await cliente.post(
            f"/api/v1/tenants/{tenant.id}/conversations/{ajena.id}/manual",
            headers=_auth(admin),
            json={"horas": 2},
        )
        assert r.status_code == 404

        r = await cliente.delete(
            f"/api/v1/tenants/{tenant.id}/conversations/{ajena.id}/manual",
            headers=_auth(admin),
        )
        assert r.status_code == 404

        await db.refresh(ajena)
        assert ajena.pausada_hasta is None, "la conversacion ajena quedo intacta"
    finally:
        await db.execute(delete(Tenant).where(Tenant.id == otro.id))
        await db.commit()


async def test_listar_conversaciones_exige_clave_admin(
    db: AsyncSession, tenant: Tenant, cliente: AsyncClient
) -> None:
    raw, prefix, hashed = generate_api_key()
    db.add(
        ApiKey(
            name="tenant-key",
            key_prefix=prefix,
            key_hash=hashed,
            tenant_id=tenant.id,
            scopes=[Scope.TENANT.value],
        )
    )
    await db.commit()
    try:
        r = await cliente.get(f"/api/v1/tenants/{tenant.id}/conversations", headers=_auth(raw))
        assert r.status_code == 403
    finally:
        await db.execute(delete(ApiKey).where(ApiKey.key_prefix == prefix))
        await db.commit()
