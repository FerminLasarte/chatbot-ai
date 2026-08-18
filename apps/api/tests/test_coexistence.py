"""Coexistence: el comercio contesta a mano desde el celular y el bot se calla solo.

Lo que se defiende aca, en orden de que tan caro es equivocarse:

1. ★ EL BOT NO SE AUTO-PAUSA. Si el echo de la respuesta del propio bot entrara
   como si la hubiera escrito una persona, el bot se callaria a si mismo en cada
   turno y el comercio quedaria mudo. Hay dos defensas -por id de mensaje y por
   texto- y las dos tienen test.

2. ★ UN ECHO NO ES UNA PREGUNTA. El payload de un echo se parece al de un
   mensaje entrante. Si `parse_incoming` lo aceptara, el bot le contestaria al
   duenio del negocio como si fuera un cliente, y le cobraria el turno.

3. La pausa se dispara sola, se estira con cada mensaje manual, y lo que
   escribio la persona queda en el historial que ve el modelo al retomar.

4. Con la funcion apagada no se actua sobre ningun echo: solo se loguea crudo.
   Es el estado con el que esto se mergea (ver docs/coexistence.md).
"""

import hashlib
import hmac
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.routes import webhooks
from app.channels.whatsapp.parser import CANAL_ECHO, parse_echo, parse_incoming
from app.core import cifrado as cifrado_mod
from app.core import security as seguridad
from app.main import app
from app.models.event import EventStatus, ProcessedEvent
from app.models.tenant import Conversation, Message, Tenant
from app.services import inbox, whatsapp
from app.services.conversation import _guardar_mensaje

CLAVE_DE_PRUEBA = "6DLQaJDkYtFB3LMlBI1nCH_1kBaRhGSFTOM6vD-FJTM="
TOKEN_DE_PRUEBA = "EAAGtoken-de-prueba"
CLIENTE_FINAL = "5491133344455"
NUMERO_DEL_COMERCIO = "5491199988877"
PHONE_NUMBER_ID = "PHONE123"


# --------------------------------------------------------------------------
# Payloads
# --------------------------------------------------------------------------


def _payload_echo(texto: str, *, wamid: str, clave_lista: str = "message_echoes") -> dict:
    """La forma documentada del webhook `smb_message_echoes`.

    ★ NO esta verificada contra un evento real de Meta. Es la hipotesis que
    implementa el parser; el dia que llegue el primero de produccion (queda
    crudo en el log, ver `_recibir_echo`) hay que comparar y corregir los dos.
    """
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_ID",
                "changes": [
                    {
                        "field": "smb_message_echoes",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": NUMERO_DEL_COMERCIO,
                                "phone_number_id": PHONE_NUMBER_ID,
                            },
                            clave_lista: [
                                {
                                    "from": NUMERO_DEL_COMERCIO,
                                    "to": CLIENTE_FINAL,
                                    "id": wamid,
                                    "timestamp": "1747000000",
                                    "type": "text",
                                    "text": {"body": texto},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _payload_entrante(texto: str, *, wamid: str) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_ID",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": PHONE_NUMBER_ID},
                            "messages": [
                                {
                                    "from": CLIENTE_FINAL,
                                    "id": wamid,
                                    "timestamp": "1747000000",
                                    "type": "text",
                                    "text": {"body": texto},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest_asyncio.fixture
async def tenant(db: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Tenant]:
    monkeypatch.setattr(cifrado_mod.settings, "encryption_key", CLAVE_DE_PRUEBA)
    t = Tenant(slug=f"test-coex-{uuid.uuid4().hex[:8]}", name="Cliente de prueba")
    whatsapp.guardar_token(t, TOKEN_DE_PRUEBA)
    t.whatsapp_phone_number_id = PHONE_NUMBER_ID
    db.add(t)
    await db.commit()
    await db.refresh(t)
    yield t
    await db.execute(delete(ProcessedEvent).where(ProcessedEvent.tenant_id == t.id))
    await db.execute(delete(Tenant).where(Tenant.id == t.id))
    await db.commit()


@pytest_asyncio.fixture
async def cliente() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def wamid(db: AsyncSession) -> AsyncIterator[str]:
    valor = f"wamid.echo.{uuid.uuid4().hex}"
    yield valor
    await db.execute(delete(ProcessedEvent).where(ProcessedEvent.external_id == valor))
    await db.commit()


async def _postear(
    cliente: AsyncClient, payload: dict, monkeypatch: pytest.MonkeyPatch
) -> httpx.Response:
    """POST al webhook real, firmado como lo firma Meta.

    La firma va sobre los BYTES exactos que se mandan, no sobre el JSON
    re-serializado: por eso el body se arma una sola vez y se manda como
    `content`.
    """
    secreto = "secreto-de-prueba"
    monkeypatch.setattr(seguridad.settings, "whatsapp_app_secret", secreto)
    crudo = json.dumps(payload).encode()
    firma = hmac.new(secreto.encode(), crudo, hashlib.sha256).hexdigest()
    return await cliente.post(
        "/api/v1/webhooks/whatsapp",
        content=crudo,
        headers={
            "X-Hub-Signature-256": f"sha256={firma}",
            "Content-Type": "application/json",
        },
    )


async def _conversacion(db: AsyncSession, tenant: Tenant) -> Conversation:
    c = Conversation(tenant_id=tenant.id, channel="whatsapp", external_id=CLIENTE_FINAL)
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


async def _mensajes(db: AsyncSession, conversation_id: uuid.UUID) -> list[Message]:
    filas = await db.scalars(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.position)
    )
    return list(filas)


# --------------------------------------------------------------------------
# ★ Un echo no puede entrar por la puerta de los mensajes entrantes
# --------------------------------------------------------------------------


def test_parse_incoming_ignora_un_echo() -> None:
    """★ Sin esto, el bot le contesta al duenio del negocio como si fuera un cliente.

    El payload de un echo trae metadata y un mensaje de texto igual que uno
    entrante: lo unico que los separa es el nombre del campo.
    """
    assert parse_incoming(_payload_echo("ya te paso el presupuesto", wamid="wamid.x")) is None


def test_parse_echo_ignora_un_mensaje_entrante() -> None:
    """Y al reves: un mensaje del cliente final no puede pausar el bot."""
    assert parse_echo(_payload_entrante("hola, que horario tienen?", wamid="wamid.y")) is None


def test_un_payload_sin_campo_sigue_entrando_como_mensaje() -> None:
    """Compatibilidad: el filtro descarta lo que se identifica como otra cosa,
    no lo que no trae identificacion."""
    payload = _payload_entrante("hola", wamid="wamid.z")
    del payload["entry"][0]["changes"][0]["field"]
    entrante = parse_incoming(payload)
    assert entrante is not None
    assert entrante.text == "hola"


async def test_un_mensaje_entrante_real_sigue_entrando(
    db: AsyncSession, tenant: Tenant, cliente: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ La regresion que hay que descartar antes de prender coexistence.

    `parse_incoming` paso a filtrar por el nombre del campo, y esta en la ruta
    caliente de TODOS los mensajes. Si ese filtro estuviera mal, el bot dejaria
    de contestarle a todo el mundo. Este test entra por el endpoint de verdad
    -firma incluida- con un payload con la forma que manda Meta.
    """
    encolados: list = []

    async def falso_handle(*args: object) -> None:
        encolados.append(args)

    monkeypatch.setattr(webhooks, "_handle", falso_handle)

    wamid_entrante = f"wamid.in.{uuid.uuid4().hex}"
    try:
        r = await _postear(
            cliente, _payload_entrante("que horario tienen?", wamid=wamid_entrante), monkeypatch
        )

        assert r.json() == {"status": "accepted"}, "el bot dejo de recibir mensajes"
        assert len(encolados) == 1
        _event_id, tenant_id, from_number, texto, phone_number_id = encolados[0]
        assert tenant_id == tenant.id
        assert from_number == CLIENTE_FINAL
        assert texto == "que horario tienen?"
        assert phone_number_id == PHONE_NUMBER_ID
    finally:
        await db.execute(delete(ProcessedEvent).where(ProcessedEvent.external_id == wamid_entrante))
        await db.commit()


async def test_una_firma_invalida_no_entra(
    cliente: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cualquiera puede postear a esa URL: sin firma valida, nada pasa."""
    monkeypatch.setattr(seguridad.settings, "whatsapp_app_secret", "secreto-de-prueba")
    r = await cliente.post(
        "/api/v1/webhooks/whatsapp",
        json=_payload_entrante("hola", wamid="wamid.falso"),
        headers={"X-Hub-Signature-256": "sha256=0000"},
    )
    assert r.status_code == 401


async def test_un_campo_desconocido_se_nombra_en_el_log(
    db: AsyncSession,
    cliente: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """★ El unico modo de fallar de `parse_incoming` es el silencio.

    Descarta todo lo que no sea el campo `messages`. Si Meta mandara los
    mensajes bajo otro nombre, el bot dejaria de contestar sin un solo error:
    ni excepcion, ni evento fallado, nada. El log con el nombre del campo es lo
    que convierte esa caida muda en un grep.
    """
    payload = _payload_entrante("hola", wamid="wamid.raro")
    payload["entry"][0]["changes"][0]["field"] = "mensajes_pero_con_otro_nombre"

    with caplog.at_level("WARNING"):
        r = await _postear(cliente, payload, monkeypatch)

    assert r.json() == {"status": "ignored"}
    assert "mensajes_pero_con_otro_nombre" in caplog.text


async def test_un_status_de_entrega_no_ensucia_el_log(
    db: AsyncSession,
    cliente: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Los acuses de entrega y lectura llegan con field=`messages` y son la
    mayoria del trafico. Si cayeran en el WARNING de arriba, el log quedaria
    inservible justo para lo que se agrego."""
    payload = _payload_entrante("hola", wamid="wamid.status")
    valor = payload["entry"][0]["changes"][0]["value"]
    del valor["messages"]
    valor["statuses"] = [{"id": "wamid.status", "status": "delivered"}]

    with caplog.at_level("WARNING"):
        r = await _postear(cliente, payload, monkeypatch)

    assert r.json() == {"status": "ignored"}
    assert "no se maneja" not in caplog.text


# --------------------------------------------------------------------------
# Lectura del echo
# --------------------------------------------------------------------------


def test_el_echo_se_lee_con_el_numero_del_cliente_final() -> None:
    """★ La conversacion la identifica el DESTINATARIO.

    En un echo el remitente es el comercio, que es el mismo para todos sus
    hilos: usarlo como identidad mezclaria las conversaciones de todos sus
    clientes en una sola.
    """
    echo = parse_echo(_payload_echo("salimos a las 18", wamid="wamid.abc"))
    assert echo is not None
    assert echo.to_number == CLIENTE_FINAL
    assert echo.text == "salimos a las 18"
    assert echo.external_id == "wamid.abc"
    assert echo.phone_number_id == PHONE_NUMBER_ID
    assert echo.channel == CANAL_ECHO, "espacio de ids separado del entrante"


def test_el_echo_tambien_se_lee_si_la_lista_se_llama_messages() -> None:
    """La forma real no esta confirmada. Equivocarse en el nombre de la lista
    significaria ignorar en silencio todos los mensajes manuales."""
    echo = parse_echo(_payload_echo("ahi te mando", wamid="wamid.def", clave_lista="messages"))
    assert echo is not None
    assert echo.text == "ahi te mando"


@pytest.mark.parametrize(
    "romper",
    [
        pytest.param(lambda v: v.pop("message_echoes"), id="sin-lista"),
        pytest.param(lambda v: v.update(message_echoes=[]), id="lista-vacia"),
        pytest.param(lambda v: v["message_echoes"][0].pop("to"), id="sin-destinatario"),
        pytest.param(lambda v: v["message_echoes"][0].pop("id"), id="sin-id"),
        pytest.param(lambda v: v.pop("metadata"), id="sin-metadata"),
        pytest.param(lambda v: v["message_echoes"][0].update(type="image"), id="no-es-texto"),
    ],
)
def test_un_echo_que_no_se_entiende_devuelve_none(romper) -> None:  # type: ignore[no-untyped-def]
    """Ante la duda no se actua: el webhook lo loguea crudo en vez de adivinar."""
    payload = _payload_echo("hola", wamid="wamid.roto")
    romper(payload["entry"][0]["changes"][0]["value"])
    assert parse_echo(payload) is None


# --------------------------------------------------------------------------
# El efecto: guardar y pausar
# --------------------------------------------------------------------------


async def test_una_respuesta_manual_pausa_el_bot_y_queda_en_el_historial(
    db: AsyncSession, tenant: Tenant, wamid: str
) -> None:
    """★ El caso que motiva la feature: nadie toco el portal."""
    conversacion = await _conversacion(db, tenant)
    assert not conversacion.en_modo_manual()

    event_id = await inbox.claim(db, CANAL_ECHO, wamid, tenant.id)
    assert event_id is not None
    await webhooks._handle_echo(event_id, tenant.id, CLIENTE_FINAL, "te lo dejo apartado")

    await db.refresh(conversacion)
    assert conversacion.en_modo_manual(), "el bot tiene que callarse solo"

    mensajes = await _mensajes(db, conversacion.id)
    assert [(m.role, m.content) for m in mensajes] == [("assistant", "te lo dejo apartado")], (
        "lo que escribio la persona va como respuesta del negocio: "
        "cuando el bot retome tiene que ver lo que se dijo, no un agujero"
    )

    evento = await db.get(ProcessedEvent, event_id)
    assert evento is not None
    assert evento.status == EventStatus.DONE.value


async def test_cada_mensaje_manual_estira_la_pausa(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mientras la persona siga contestando, el bot no vuelve. Cuando deja, si."""
    conversacion = await _conversacion(db, tenant)
    ids = [f"wamid.echo.{uuid.uuid4().hex}" for _ in range(2)]
    try:
        primero = await inbox.claim(db, CANAL_ECHO, ids[0], tenant.id)
        assert primero is not None
        await webhooks._handle_echo(primero, tenant.id, CLIENTE_FINAL, "hola, te atiendo yo")
        await db.refresh(conversacion)
        vencimiento_inicial = conversacion.pausada_hasta
        assert vencimiento_inicial is not None

        monkeypatch.setattr(webhooks.settings, "manual_mode_hours", 12)
        segundo = await inbox.claim(db, CANAL_ECHO, ids[1], tenant.id)
        assert segundo is not None
        await webhooks._handle_echo(segundo, tenant.id, CLIENTE_FINAL, "te confirmo en un rato")

        await db.refresh(conversacion)
        assert conversacion.pausada_hasta is not None
        assert conversacion.pausada_hasta > vencimiento_inicial
    finally:
        await db.execute(delete(ProcessedEvent).where(ProcessedEvent.external_id.in_(ids)))
        await db.commit()


async def test_un_echo_abre_la_conversacion_si_el_comercio_escribio_primero(
    db: AsyncSession, tenant: Tenant, wamid: str
) -> None:
    """El negocio puede iniciar el contacto. Ese hilo tambien nace pausado: si el
    cliente responde, contesta la persona que empezo la charla, no el bot."""
    event_id = await inbox.claim(db, CANAL_ECHO, wamid, tenant.id)
    assert event_id is not None
    await webhooks._handle_echo(event_id, tenant.id, CLIENTE_FINAL, "hola! te queria comentar")

    conversacion = await db.scalar(
        select(Conversation).where(
            Conversation.tenant_id == tenant.id, Conversation.external_id == CLIENTE_FINAL
        )
    )
    assert conversacion is not None
    assert conversacion.en_modo_manual()


# --------------------------------------------------------------------------
# ★ Las dos defensas contra la auto-pausa
# --------------------------------------------------------------------------


async def test_el_id_del_mensaje_que_enviamos_queda_reclamado(
    db: AsyncSession, tenant: Tenant, wamid: str
) -> None:
    """★ Primera defensa: cuando llegue el echo de nuestro propio envio, su id
    ya esta tomado y el webhook lo descarta como duplicado."""
    await webhooks._registrar_envio_propio(tenant.id, wamid)

    assert await inbox.claim(db, CANAL_ECHO, wamid, tenant.id) is None, (
        "el echo de nuestra propia respuesta no puede llegar a pausar el bot"
    )


async def test_un_echo_identico_a_la_ultima_respuesta_del_bot_no_pausa(
    db: AsyncSession, tenant: Tenant, wamid: str
) -> None:
    """★ Segunda defensa, por si la del id fallara.

    El escenario que arruina el producto: el bot contesta, Meta hace echo de esa
    misma respuesta, el bot la lee como si la hubiera escrito una persona y se
    pausa. Con la pausa puesta deja de contestar, y como ya no contesta nadie
    vuelve a destrabarlo hasta que el cliente se queja.
    """
    conversacion = await _conversacion(db, tenant)
    await _guardar_mensaje(db, conversacion.id, "assistant", "Atendemos de 9 a 18.")

    event_id = await inbox.claim(db, CANAL_ECHO, wamid, tenant.id)
    assert event_id is not None
    await webhooks._handle_echo(event_id, tenant.id, CLIENTE_FINAL, "Atendemos de 9 a 18.")

    await db.refresh(conversacion)
    assert not conversacion.en_modo_manual(), "el bot se pauso con su propia respuesta"
    assert len(await _mensajes(db, conversacion.id)) == 1, "tampoco se duplica en el historial"


async def test_el_mismo_texto_escrito_despues_de_un_mensaje_del_cliente_si_pausa(
    db: AsyncSession, tenant: Tenant, wamid: str
) -> None:
    """La defensa por texto mira SOLO el ultimo mensaje. Si en el medio escribio
    el cliente, lo que llega es una respuesta de verdad aunque el texto se repita."""
    conversacion = await _conversacion(db, tenant)
    await _guardar_mensaje(db, conversacion.id, "assistant", "Atendemos de 9 a 18.")
    await _guardar_mensaje(db, conversacion.id, "user", "y los sabados?")

    event_id = await inbox.claim(db, CANAL_ECHO, wamid, tenant.id)
    assert event_id is not None
    await webhooks._handle_echo(event_id, tenant.id, CLIENTE_FINAL, "Atendemos de 9 a 18.")

    await db.refresh(conversacion)
    assert conversacion.en_modo_manual()


async def test_el_id_de_un_echo_no_colisiona_con_el_de_un_entrante(
    db: AsyncSession, tenant: Tenant
) -> None:
    """Los dos canales tienen espacios de ids separados: si compartieran uno, un
    echo podria hacer pasar por duplicado a un mensaje del cliente -que entonces
    quedaria sin contestar- o al reves."""
    compartido = f"wamid.compartido.{uuid.uuid4().hex}"
    try:
        assert await inbox.claim(db, "whatsapp", compartido, tenant.id) is not None
        assert await inbox.claim(db, CANAL_ECHO, compartido, tenant.id) is not None
    finally:
        await db.execute(delete(ProcessedEvent).where(ProcessedEvent.external_id == compartido))
        await db.commit()


# --------------------------------------------------------------------------
# El interruptor
# --------------------------------------------------------------------------


async def test_con_la_funcion_apagada_el_echo_no_hace_nada(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Es el estado con el que esto se mergea: los echoes se loguean crudos para
    poder confirmar la forma real del payload, y nada mas."""
    monkeypatch.setattr(webhooks.settings, "coexistence_enabled", False)
    conversacion = await _conversacion(db, tenant)

    tareas: list = []

    class _Background:
        def add_task(self, *args: object, **kwargs: object) -> None:
            tareas.append(args)

    payload = _payload_echo("contesto yo", wamid=f"wamid.echo.{uuid.uuid4().hex}")
    resultado = await webhooks._recibir_echo(payload, db, _Background())  # type: ignore[arg-type]

    assert resultado == {"status": "coexistence_disabled"}
    assert tareas == []
    await db.refresh(conversacion)
    assert not conversacion.en_modo_manual()


async def test_con_la_funcion_prendida_el_echo_se_encola(
    db: AsyncSession, tenant: Tenant, wamid: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(webhooks.settings, "coexistence_enabled", True)

    tareas: list = []

    class _Background:
        def add_task(self, *args: object, **kwargs: object) -> None:
            tareas.append(args)

    payload = _payload_echo("contesto yo", wamid=wamid)
    resultado = await webhooks._recibir_echo(payload, db, _Background())  # type: ignore[arg-type]

    assert resultado == {"status": "accepted"}
    assert len(tareas) == 1
    _fn, _event_id, tenant_id, to_number, texto = tareas[0]
    assert tenant_id == tenant.id
    assert to_number == CLIENTE_FINAL
    assert texto == "contesto yo"


async def test_un_echo_reentregado_se_procesa_una_sola_vez(
    db: AsyncSession, tenant: Tenant, wamid: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Meta reintenta los webhooks tambien para los echoes."""
    monkeypatch.setattr(webhooks.settings, "coexistence_enabled", True)

    class _Background:
        def add_task(self, *args: object, **kwargs: object) -> None:
            return None

    payload = _payload_echo("contesto yo", wamid=wamid)
    primero = await webhooks._recibir_echo(payload, db, _Background())  # type: ignore[arg-type]
    segundo = await webhooks._recibir_echo(payload, db, _Background())  # type: ignore[arg-type]

    assert primero == {"status": "accepted"}
    assert segundo == {"status": "duplicate"}


async def test_un_echo_de_un_numero_sin_cliente_no_rompe(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(webhooks.settings, "coexistence_enabled", True)

    class _Background:
        def add_task(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("no tendria que haber encolado nada")

    payload = _payload_echo("hola", wamid=f"wamid.echo.{uuid.uuid4().hex}")
    payload["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"] = "PHONE-INEXISTENTE"

    resultado = await webhooks._recibir_echo(payload, db, _Background())  # type: ignore[arg-type]
    assert resultado == {"status": "unknown_tenant"}


async def test_un_echo_con_forma_desconocida_se_ignora_sin_romper(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El caso esperable mientras la forma real no este confirmada."""
    monkeypatch.setattr(webhooks.settings, "coexistence_enabled", True)

    class _Background:
        def add_task(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("no tendria que haber encolado nada")

    payload = _payload_echo("hola", wamid="wamid.raro")
    payload["entry"][0]["changes"][0]["value"]["message_echoes"] = "esto no es una lista"

    resultado = await webhooks._recibir_echo(payload, db, _Background())  # type: ignore[arg-type]
    assert resultado == {"status": "ignored"}


# --------------------------------------------------------------------------
# Convivencia con el modo manual que ya existia
# --------------------------------------------------------------------------


async def test_con_la_pausa_puesta_por_un_echo_el_bot_no_contesta(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La pausa que pone el echo es la misma que la del portal: la respeta el
    mismo unico punto de control en `_handle`."""
    llamadas: list[str] = []

    async def falso_answer(*args: object, **kwargs: object) -> tuple[str, uuid.UUID]:
        llamadas.append("answer")
        return "respuesta automatica", uuid.uuid4()

    async def falso_envio(**kwargs: object) -> str | None:
        raise AssertionError("no tendria que haber enviado nada")

    monkeypatch.setattr(webhooks, "answer", falso_answer)
    monkeypatch.setattr(webhooks, "send_text", falso_envio)

    conversacion = await _conversacion(db, tenant)
    ids = [f"wamid.echo.{uuid.uuid4().hex}", f"wamid.in.{uuid.uuid4().hex}"]
    try:
        echo_id = await inbox.claim(db, CANAL_ECHO, ids[0], tenant.id)
        assert echo_id is not None
        await webhooks._handle_echo(echo_id, tenant.id, CLIENTE_FINAL, "yo me encargo")

        entrante_id = await inbox.claim(db, "whatsapp", ids[1], tenant.id)
        assert entrante_id is not None
        await webhooks._handle(entrante_id, tenant.id, CLIENTE_FINAL, "gracias!", PHONE_NUMBER_ID)

        assert llamadas == [], "el bot no puede pisarle la respuesta a la persona"
        mensajes = await _mensajes(db, conversacion.id)
        assert [(m.role, m.content) for m in mensajes] == [
            ("assistant", "yo me encargo"),
            ("user", "gracias!"),
        ]
    finally:
        await db.execute(delete(ProcessedEvent).where(ProcessedEvent.external_id.in_(ids)))
        await db.commit()


async def test_la_pausa_por_echo_tambien_vence(db: AsyncSession, tenant: Tenant) -> None:
    """Mismo diseño que el modo manual: si el duenio se olvida, el bot vuelve."""
    conversacion = await _conversacion(db, tenant)
    conversacion.pausada_hasta = datetime.now(UTC) - timedelta(minutes=1)
    await db.commit()
    await db.refresh(conversacion)

    assert not conversacion.en_modo_manual()
