"""Contestar al cliente final desde el panel o desde el portal.

Lo que se defiende aca, en orden de que tan caro es equivocarse:

1. ★ EL BOT NO SE AUTO-PAUSA CON NUESTRO PROPIO ENVIO. Con coexistence
   prendido, Meta hace echo de todo lo que sale del numero del negocio,
   incluido lo que mandamos nosotros. Si ese echo entra al webhook como si lo
   hubiera escrito una persona, el bot se calla solo y ademas el mensaje
   aparece dos veces en el hilo. La defensa es anotar el id ANTES; si se cae,
   nada falla a la vista: simplemente el bot deja de contestar.

2. ★ NO SE LE PUEDE ESCRIBIR AL CLIENTE DE OTRO NEGOCIO. Es el mismo
   aislamiento que protege la lectura, pero al reves y peor: aca no se filtra
   informacion, se manda un WhatsApp en nombre de un comercio ajeno.

3. ★ LA VENTANA DE 24 h SE MIDE CONTRA EL ULTIMO MENSAJE DEL CLIENTE. Medirla
   contra `last_activity_at` -que se mueve tambien cuando contesta el bot-
   diria que la ventana esta abierta cuando Meta ya la cerro. El error se ve
   recien al enviar, con el texto de Meta, en ingles.

4. Contestar a mano pausa el bot y da por atendida la derivacion. Sin lo
   primero, el bot le pisa la respuesta a la persona en la misma conversacion;
   sin lo segundo, la conversacion queda para siempre en la lista de las que
   esperan.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.whatsapp import client
from app.core import cifrado as cifrado_mod
from app.models.event import ProcessedEvent
from app.models.tenant import Conversation, Message, Tenant
from app.services import conversaciones, responder, whatsapp

CLAVE_DE_PRUEBA = "6DLQaJDkYtFB3LMlBI1nCH_1kBaRhGSFTOM6vD-FJTM="
TOKEN_DE_PRUEBA = "EAAGtoken-de-prueba"
CLIENTE_FINAL = "5491133344455"


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


async def _nuevo_tenant(db: AsyncSession, sufijo: str) -> Tenant:
    t = Tenant(slug=f"test-resp-{sufijo}-{uuid.uuid4().hex[:8]}", name=f"Negocio {sufijo}")
    whatsapp.guardar_token(t, TOKEN_DE_PRUEBA)
    t.whatsapp_phone_number_id = f"PHONE-{uuid.uuid4().hex[:8]}"
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


@pytest_asyncio.fixture
async def tenant(db: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Tenant]:
    monkeypatch.setattr(cifrado_mod.settings, "encryption_key", CLAVE_DE_PRUEBA)
    t = await _nuevo_tenant(db, "a")
    yield t
    await db.execute(delete(ProcessedEvent).where(ProcessedEvent.tenant_id == t.id))
    await db.execute(delete(Tenant).where(Tenant.id == t.id))
    await db.commit()


@pytest_asyncio.fixture
async def vecino(db: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Tenant]:
    """Otro negocio, para comprobar que no se puede escribir en su nombre."""
    monkeypatch.setattr(cifrado_mod.settings, "encryption_key", CLAVE_DE_PRUEBA)
    t = await _nuevo_tenant(db, "b")
    yield t
    await db.execute(delete(ProcessedEvent).where(ProcessedEvent.tenant_id == t.id))
    await db.execute(delete(Tenant).where(Tenant.id == t.id))
    await db.commit()


async def _conversacion_con_cliente_que_escribio(
    db: AsyncSession, tenant: Tenant, *, hace_horas: float = 1
) -> Conversation:
    """Un hilo donde el cliente final escribio hace `hace_horas`.

    Las fechas se escriben a mano y no se dejan al default del servidor: lo que
    esta a prueba es justamente el calculo de la ventana, y con `now()` todas
    las conversaciones nacerian dentro de ella.
    """
    cuando = datetime.now(UTC) - timedelta(hours=hace_horas)
    c = Conversation(
        tenant_id=tenant.id,
        channel="whatsapp",
        external_id=CLIENTE_FINAL,
        last_activity_at=cuando,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)

    db.add(
        Message(
            conversation_id=c.id,
            position=1,
            role="user",
            content="hola, hacen envios?",
            created_at=cuando,
        )
    )
    await db.commit()
    return c


def _envio_falso(monkeypatch: pytest.MonkeyPatch, wamid: str | None = "wamid.propio.123") -> list:
    """Reemplaza el envio a Meta y registra con que se lo llamo."""
    llamadas: list[dict] = []

    async def falso_send_text(
        to: str, text: str, phone_number_id: str, access_token: str
    ) -> str | None:
        llamadas.append({"to": to, "text": text, "phone_number_id": phone_number_id})
        return wamid

    monkeypatch.setattr(client, "send_text", falso_send_text)
    return llamadas


# --------------------------------------------------------------------------
# ★ 1. El echo de nuestro propio envio no puede pausar al bot
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_el_id_del_mensaje_que_mandamos_queda_anotado_antes_de_que_llegue_el_echo(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sin esto el bot se calla solo y nadie se entera.

    El echo llega al webhook indistinguible de un mensaje escrito a mano desde
    el celular. La unica forma de reconocerlo es haber anotado antes el id que
    devolvio Meta al enviar.
    """
    _envio_falso(monkeypatch, wamid="wamid.nuestro.abc")
    conversacion = await _conversacion_con_cliente_que_escribio(db, tenant)

    await responder.responder(db, tenant, conversacion.id, "Sí, hacemos envíos a todo el país.")

    anotado = await db.scalar(
        select(ProcessedEvent).where(ProcessedEvent.external_id == "wamid.nuestro.abc")
    )
    assert anotado is not None, "el id del mensaje enviado no quedo reclamado"
    assert anotado.status == "done", "tiene que quedar como YA procesado, no pendiente"
    assert anotado.tenant_id == tenant.id


@pytest.mark.asyncio
async def test_si_meta_no_devuelve_el_id_el_envio_igual_prospera(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El mensaje ya salio: quedarse sin el id degrada un filtro, no el envio.

    Romper aca convertiria un envio exitoso en un error, y quien atiende lo
    mandaria de nuevo: el cliente final recibiria el mismo mensaje dos veces.
    """
    _envio_falso(monkeypatch, wamid=None)
    conversacion = await _conversacion_con_cliente_que_escribio(db, tenant)

    mensaje = await responder.responder(db, tenant, conversacion.id, "Ahí te confirmo.")

    assert mensaje.content == "Ahí te confirmo."
    assert mensaje.autor == "persona"


# --------------------------------------------------------------------------
# ★ 2. Aislamiento entre clientes
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_se_le_puede_escribir_al_cliente_de_otro_negocio(
    db: AsyncSession, tenant: Tenant, vecino: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Peor que filtrar datos: seria mandar un WhatsApp en nombre de un tercero."""
    llamadas = _envio_falso(monkeypatch)
    ajena = await _conversacion_con_cliente_que_escribio(db, vecino)

    with pytest.raises(conversaciones.ConversacionNoEncontrada):
        await responder.responder(db, tenant, ajena.id, "hola desde el negocio equivocado")

    assert llamadas == [], "no se puede haber llamado a Meta con la conversacion de otro"


# --------------------------------------------------------------------------
# ★ 3. La ventana de 24 h de Meta
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fuera_de_la_ventana_no_se_llama_a_meta(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Se corta de este lado, antes de gastar la llamada y el texto escrito."""
    llamadas = _envio_falso(monkeypatch)
    conversacion = await _conversacion_con_cliente_que_escribio(db, tenant, hace_horas=30)

    with pytest.raises(responder.NoSePuedeResponder) as exc:
        await responder.responder(db, tenant, conversacion.id, "perdon la demora")

    assert llamadas == [], "no se puede haber intentado enviar con la ventana cerrada"
    assert "24" in str(exc.value), "el motivo tiene que decir de cuanto es la ventana"


@pytest.mark.asyncio
async def test_la_ventana_se_mide_contra_el_ultimo_mensaje_del_cliente(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ El caso que se rompe silenciosamente si se usa `last_activity_at`.

    El cliente escribio hace 30 h y el bot le contesto hace 5 minutos. La
    actividad de la conversacion es reciente, pero para Meta la ventana esta
    cerrada: la cuenta corre desde el ultimo mensaje DEL CLIENTE.
    """
    _envio_falso(monkeypatch)
    conversacion = await _conversacion_con_cliente_que_escribio(db, tenant, hace_horas=30)

    # El bot contesto recien, asi que la conversacion figura activa.
    ahora = datetime.now(UTC)
    db.add(
        Message(
            conversation_id=conversacion.id,
            position=2,
            role="assistant",
            autor="bot",
            content="Seguimos a disposición.",
            created_at=ahora - timedelta(minutes=5),
        )
    )
    conversacion.last_activity_at = ahora - timedelta(minutes=5)
    await db.commit()

    estado = await conversaciones.detalle(db, conversacion)

    assert estado.minutos_inactiva < 60, "la conversacion figura activa, como corresponde"
    assert estado.ventana_abierta is False, (
        "la ventana tiene que estar cerrada: la cuenta corre desde el mensaje del cliente"
    )


@pytest.mark.asyncio
async def test_dentro_de_la_ventana_quedan_las_horas_que_faltan(
    db: AsyncSession, tenant: Tenant
) -> None:
    conversacion = await _conversacion_con_cliente_que_escribio(db, tenant, hace_horas=2)

    estado = await conversaciones.detalle(db, conversacion)

    assert estado.ventana_abierta is True
    assert estado.minutos_de_ventana is not None
    # 24 h menos las 2 que pasaron, con margen para el tiempo del test.
    assert 21 * 60 < estado.minutos_de_ventana <= 22 * 60


# --------------------------------------------------------------------------
# ★ 4. Contestar es atender
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_contestar_pausa_el_bot_y_da_por_atendida_la_derivacion(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Las dos mitades de "esto lo atiendo yo".

    Sin la pausa, el bot le contesta encima a la persona. Sin limpiar la
    derivacion, la conversacion queda para siempre arriba de la lista como si
    nadie la hubiera atendido.
    """
    _envio_falso(monkeypatch)
    conversacion = await _conversacion_con_cliente_que_escribio(db, tenant)
    conversacion.derivada_at = datetime.now(UTC) - timedelta(hours=3)
    await db.commit()

    await responder.responder(db, tenant, conversacion.id, "Hola, te atiendo yo.")
    await db.refresh(conversacion)

    assert conversacion.en_modo_manual(), "el bot tiene que quedar callado en este hilo"
    assert conversacion.derivada_at is None, "contestar a mano da por atendida la derivacion"


@pytest.mark.asyncio
async def test_el_mensaje_queda_atribuido_a_una_persona(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El rol es `assistant` -para el cliente final es "me contesto el negocio"-
    y la diferencia con el bot vive en `autor`. Sin eso, auditar al asistente es
    imposible: el duenio lee sus propias respuestas como si fueran del bot."""
    _envio_falso(monkeypatch)
    conversacion = await _conversacion_con_cliente_que_escribio(db, tenant)

    await responder.responder(db, tenant, conversacion.id, "Te confirmo por la tarde.")

    guardado = await db.scalar(
        select(Message)
        .where(Message.conversation_id == conversacion.id)
        .order_by(Message.position.desc())
        .limit(1)
    )
    assert guardado is not None
    assert guardado.role == "assistant"
    assert guardado.autor == "persona"


@pytest.mark.asyncio
async def test_si_meta_rechaza_el_envio_no_queda_el_mensaje_en_el_hilo(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ Guardar antes de enviar seria la peor de las dos mentiras posibles.

    Quien atiende veria su mensaje en el hilo y se quedaria esperando una
    respuesta a algo que el cliente final nunca recibio.
    """

    async def rechaza(**_: object) -> str | None:
        raise client.WhatsAppSendError("Meta rechazo el envio (400)")

    monkeypatch.setattr(client, "send_text", rechaza)
    conversacion = await _conversacion_con_cliente_que_escribio(db, tenant)

    with pytest.raises(client.WhatsAppSendError):
        await responder.responder(db, tenant, conversacion.id, "esto no llega")

    mensajes = await db.scalars(
        select(Message).where(
            Message.conversation_id == conversacion.id, Message.role == "assistant"
        )
    )
    assert list(mensajes) == [], "no puede quedar en el hilo un mensaje que no se envio"


@pytest.mark.asyncio
async def test_sin_whatsapp_conectado_no_se_intenta_enviar(
    db: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    llamadas = _envio_falso(monkeypatch)
    conversacion = await _conversacion_con_cliente_que_escribio(db, tenant)
    tenant.whatsapp_access_token_cifrado = None
    await db.commit()

    with pytest.raises(responder.NoSePuedeResponder):
        await responder.responder(db, tenant, conversacion.id, "hola")

    assert llamadas == []
