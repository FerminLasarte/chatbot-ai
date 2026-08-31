"""Alta de WhatsApp por Embedded Signup: el cliente se conecta solo.

Lo que se cuida aca es de otra naturaleza que en test_whatsapp.py. Alla la carga
la hace la agencia con clave admin; aca la hace un desconocido con un link, y
contra la API de Meta, que puede fallar en cualquiera de los tres pasos.

Los dos invariantes que no se pueden romper:

  - El link es la unica credencial del flujo. Si se pudiera falsificar o si
    sobreviviera a su vencimiento, cualquiera podria conectarle un WhatsApp a un
    cliente ajeno.
  - Un alta a medias es peor que ninguna. Si algo falla contra Meta, la fila del
    cliente NO se toca: el panel lo sigue mostrando desconectado —que es la
    verdad— y el cliente puede reintentar con el mismo link.
"""

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.whatsapp import client as wa_client
from app.core import cifrado as cifrado_mod
from app.core.config import settings
from app.core.security import generate_api_key
from app.main import app
from app.models.api_key import ApiKey, Scope
from app.models.tenant import Tenant
from app.services import onboarding, whatsapp

CLAVE_PRUEBA = "6DLQaJDkYtFB3LMlBI1nCH_1kBaRhGSFTOM6vD-FJTM="


@pytest.fixture(autouse=True)
def _config(monkeypatch: pytest.MonkeyPatch) -> None:
    """La config que hace falta para que el flujo sea posible."""
    monkeypatch.setattr(cifrado_mod.settings, "encryption_key", CLAVE_PRUEBA)
    monkeypatch.setattr(settings, "jwt_secret", "secreto-de-test-largo-y-aleatorio")
    monkeypatch.setattr(settings, "whatsapp_app_id", "APPID123")
    monkeypatch.setattr(settings, "whatsapp_config_id", "CONFIGID456")
    monkeypatch.setattr(settings, "whatsapp_app_secret", "appsecret")
    monkeypatch.setattr(settings, "onboarding_base_url", "https://panel.test")


@pytest_asyncio.fixture
async def cliente() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def escenario(db: AsyncSession) -> AsyncIterator[dict]:
    sufijo = uuid.uuid4().hex[:8]
    a = Tenant(slug=f"onb-a-{sufijo}", name="Panaderia Lopez", system_prompt="soy A")
    b = Tenant(slug=f"onb-b-{sufijo}", name="Ferreteria Diaz", system_prompt="soy B")
    db.add_all([a, b])
    await db.commit()
    await db.refresh(a)
    await db.refresh(b)

    raw, prefix, hashed = generate_api_key()
    db.add(
        ApiKey(
            name="admin-onb",
            key_prefix=prefix,
            key_hash=hashed,
            tenant_id=None,
            scopes=[Scope.ADMIN.value],
        )
    )
    await db.commit()

    yield {"a": a, "b": b, "admin": raw}

    for t in (a, b):
        actual = await db.get(Tenant, t.id)
        if actual is not None:
            await db.delete(actual)
    clave = await db.scalar(
        __import__("sqlalchemy").select(ApiKey).where(ApiKey.key_prefix == prefix)
    )
    if clave is not None:
        await db.delete(clave)
    await db.commit()


def _auth(k: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {k}"}


def _payload(**extra: str) -> dict:
    return {"code": "CODE-DE-META", "waba_id": "WABA1", "phone_number_id": "PNID1", **extra}


class _MetaFalsa:
    """Reemplaza los tres pasos contra Meta y anota cuales se llamaron."""

    def __init__(self, *, falla: str | None = None) -> None:
        self.falla = falla
        self.llamadas: list[str] = []

    def instalar(self, monkeypatch: pytest.MonkeyPatch) -> "_MetaFalsa":
        async def canjear(code: str) -> str:
            self.llamadas.append("canjear")
            if self.falla == "canjear":
                raise wa_client.AltaWhatsAppError("Meta rechazo el codigo")
            return "EAAG-token-permanente"

        async def suscribir(waba_id: str, access_token: str) -> None:
            self.llamadas.append("suscribir")
            if self.falla == "suscribir":
                raise wa_client.AltaWhatsAppError("no se pudo suscribir el webhook")

        async def registrar(phone_number_id: str, access_token: str, pin: str) -> None:
            self.llamadas.append("registrar")
            if self.falla == "registrar":
                raise wa_client.AltaWhatsAppError("el numero ya tenia verificacion en dos pasos")

        monkeypatch.setattr(wa_client, "canjear_code_por_token", canjear)
        monkeypatch.setattr(wa_client, "suscribir_webhook", suscribir)
        monkeypatch.setattr(wa_client, "registrar_numero", registrar)
        return self


# ---------------------------------------------------------------------------
# El link: es la unica credencial del flujo
# ---------------------------------------------------------------------------


def test_el_link_lleva_al_cliente_que_lo_emitio() -> None:
    tid = uuid.uuid4()
    link = onboarding.emitir(tid)
    assert onboarding.verificar(link.token) == tid
    assert link.url == f"https://panel.test/onboarding/{link.token}"


def test_un_token_con_el_payload_cambiado_no_sirve() -> None:
    """★ Sin la firma, cambiar el tenant_id del token seria conectarle un
    WhatsApp a cualquier cliente con solo editar la URL."""
    otro = onboarding.emitir(uuid.uuid4())
    ajeno = onboarding.emitir(uuid.uuid4())
    # El payload de uno con la firma del otro.
    frankenstein = f"{ajeno.token.split('.')[0]}.{otro.token.split('.')[1]}"
    with pytest.raises(onboarding.LinkInvalido):
        onboarding.verificar(frankenstein)


def test_un_token_vencido_se_rechaza() -> None:
    vencido = onboarding.emitir(uuid.uuid4(), horas=-1)
    with pytest.raises(onboarding.LinkVencido):
        onboarding.verificar(vencido.token)


def test_un_token_firmado_con_otro_secreto_no_sirve(monkeypatch: pytest.MonkeyPatch) -> None:
    link = onboarding.emitir(uuid.uuid4())
    monkeypatch.setattr(settings, "jwt_secret", "otro-secreto-distinto")
    with pytest.raises(onboarding.LinkInvalido):
        onboarding.verificar(link.token)


@pytest.mark.parametrize("basura", ["", "sinpunto", "a.b.c", "no-base64!.firma", "."])
def test_un_token_con_cualquier_formato_raro_se_rechaza_sin_explotar(basura: str) -> None:
    """Lo escribe cualquiera en la barra del navegador: tiene que dar un error
    controlado, no un 500."""
    with pytest.raises(onboarding.LinkInvalido):
        onboarding.verificar(basura)


# ---------------------------------------------------------------------------
# Emision desde el panel
# ---------------------------------------------------------------------------


async def test_la_agencia_emite_el_link_de_un_cliente(
    cliente: AsyncClient, escenario: dict
) -> None:
    a = escenario["a"]
    r = await cliente.post(
        f"/api/v1/tenants/{a.id}/onboarding-link", headers=_auth(escenario["admin"])
    )
    assert r.status_code == 200
    assert onboarding.verificar(r.json()["url"].rsplit("/", 1)[-1]) == a.id


async def test_emitir_un_link_exige_clave_admin(cliente: AsyncClient, escenario: dict) -> None:
    r = await cliente.post(f"/api/v1/tenants/{escenario['a'].id}/onboarding-link")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# La pagina del cliente
# ---------------------------------------------------------------------------


async def test_el_cliente_ve_su_nombre_y_los_datos_del_popup(
    cliente: AsyncClient, escenario: dict
) -> None:
    """Sin API key: la autorizacion es el token de la URL."""
    token = onboarding.emitir(escenario["a"].id).token
    r = await cliente.get(f"/api/v1/onboarding/{token}")
    assert r.status_code == 200
    assert r.json() == {
        "nombre_cliente": "Panaderia Lopez",
        "app_id": "APPID123",
        "config_id": "CONFIGID456",
        "api_version": settings.whatsapp_signup_api_version,
        "ya_conectado": False,
    }


async def test_la_pagina_no_recibe_la_version_de_la_cloud_api(
    cliente: AsyncClient, escenario: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ Las dos versiones son cosas distintas y tienen que seguir separadas.

    La del alta decide que asistente le dibuja Meta al cliente; la de la Cloud
    API es contra que URL manda mensajes el servidor. Unificarlas -que es lo
    natural al verlas casi iguales- ya rompio el alta una vez: con el SDK en
    una version anterior a que coexistence existiera, Meta ignoraba el
    featureType sin decir nada y abria el asistente equivocado, el de numero
    nuevo, sin ningun error de por medio.

    Se fuerzan valores distintos en vez de comparar los defaults: asi el test
    sigue diciendo algo el dia que las dos versiones coincidan por casualidad.
    """
    monkeypatch.setattr(settings, "whatsapp_api_version", "v1.0")
    monkeypatch.setattr(settings, "whatsapp_signup_api_version", "v99.0")

    token = onboarding.emitir(escenario["a"].id).token
    r = await cliente.get(f"/api/v1/onboarding/{token}")
    assert r.json()["api_version"] == "v99.0"


async def test_la_pagina_nunca_expone_el_app_secret(cliente: AsyncClient, escenario: dict) -> None:
    """★ Es el secreto que vale para TODOS los clientes: si viajara al navegador
    del cliente, cualquiera podria canjear codes en nombre de la agencia."""
    token = onboarding.emitir(escenario["a"].id).token
    r = await cliente.get(f"/api/v1/onboarding/{token}")
    assert "appsecret" not in r.text


async def test_un_link_vencido_le_avisa_al_cliente(cliente: AsyncClient, escenario: dict) -> None:
    token = onboarding.emitir(escenario["a"].id, horas=-1).token
    r = await cliente.get(f"/api/v1/onboarding/{token}")
    assert r.status_code == 410


async def test_un_link_inventado_da_404(cliente: AsyncClient) -> None:
    r = await cliente.get("/api/v1/onboarding/inventado.deltodo")
    assert r.status_code == 404


async def test_sin_config_de_la_app_no_se_deja_abrir_el_popup(
    cliente: AsyncClient, escenario: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mejor un error que lea la agencia que un popup que muere con un mensaje
    de Facebook que el cliente no puede interpretar."""
    monkeypatch.setattr(settings, "whatsapp_config_id", "")
    token = onboarding.emitir(escenario["a"].id).token
    r = await cliente.get(f"/api/v1/onboarding/{token}")
    assert r.status_code == 503


# ---------------------------------------------------------------------------
# El alta
# ---------------------------------------------------------------------------


async def test_el_alta_completa_deja_al_cliente_listo_para_recibir(
    cliente: AsyncClient, escenario: dict, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    meta = _MetaFalsa().instalar(monkeypatch)
    a = escenario["a"]
    token = onboarding.emitir(a.id).token

    r = await cliente.post(f"/api/v1/onboarding/{token}/conectar", json=_payload())
    assert r.status_code == 200
    assert r.json() == {"conectado": True, "advertencia": None}

    # ★ Los tres pasos, en orden. Sin "suscribir" el cliente quedaria mudo.
    assert meta.llamadas == ["canjear", "suscribir", "registrar"]

    await db.refresh(a)
    assert a.whatsapp_phone_number_id == "PNID1"
    # El waba_id no se usa para operar, pero es lo unico que permite encontrar
    # despues la cuenta del cliente del lado de Meta.
    assert a.whatsapp_waba_id == "WABA1"
    assert whatsapp.leer_token(a) == "EAAG-token-permanente"
    assert whatsapp.tiene_whatsapp(a)


async def test_el_token_queda_cifrado_en_la_base(
    cliente: AsyncClient, escenario: dict, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _MetaFalsa().instalar(monkeypatch)
    a = escenario["a"]
    token = onboarding.emitir(a.id).token
    await cliente.post(f"/api/v1/onboarding/{token}/conectar", json=_payload())

    await db.refresh(a)
    assert a.whatsapp_access_token_cifrado is not None
    assert "EAAG-token-permanente" not in a.whatsapp_access_token_cifrado


async def test_si_falla_el_canje_no_se_guarda_nada(
    cliente: AsyncClient, escenario: dict, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    meta = _MetaFalsa(falla="canjear").instalar(monkeypatch)
    a = escenario["a"]
    token = onboarding.emitir(a.id).token

    r = await cliente.post(f"/api/v1/onboarding/{token}/conectar", json=_payload())
    assert r.status_code == 502
    assert meta.llamadas == ["canjear"]

    await db.refresh(a)
    assert not whatsapp.tiene_whatsapp(a)


async def test_si_falla_la_suscripcion_del_webhook_no_se_guarda_nada(
    cliente: AsyncClient, escenario: dict, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ EL CASO CARO. Con token y numero guardados pero sin webhook, el panel
    muestra al cliente como conectado, el bot puede escribir... y no le llega un
    solo mensaje entrante. Nadie se entera hasta que el cliente reclama.

    Por eso el alta se corta entera y la fila queda intacta: desconectado es la
    verdad, y el cliente puede reintentar con el mismo link."""
    _MetaFalsa(falla="suscribir").instalar(monkeypatch)
    a = escenario["a"]
    token = onboarding.emitir(a.id).token

    r = await cliente.post(f"/api/v1/onboarding/{token}/conectar", json=_payload())
    assert r.status_code == 502

    await db.refresh(a)
    assert a.whatsapp_phone_number_id is None
    assert a.whatsapp_access_token_cifrado is None


async def test_si_falla_el_registro_el_alta_igual_queda_pero_avisa(
    cliente: AsyncClient, escenario: dict, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A diferencia del webhook, aca todo lo demas quedo bien: tirar el alta
    entera obligaria al cliente a empezar de cero por algo que se arregla desde
    Meta."""
    _MetaFalsa(falla="registrar").instalar(monkeypatch)
    a = escenario["a"]
    token = onboarding.emitir(a.id).token

    r = await cliente.post(f"/api/v1/onboarding/{token}/conectar", json=_payload())
    assert r.status_code == 200
    assert r.json()["conectado"] is True
    assert r.json()["advertencia"] is not None

    await db.refresh(a)
    assert whatsapp.tiene_whatsapp(a)


async def test_no_se_puede_conectar_un_numero_que_ya_es_de_otro_cliente(
    cliente: AsyncClient, escenario: dict, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ El webhook resuelve el cliente por el numero: repetido, los mensajes de
    uno se contestarian con la informacion del otro."""
    meta = _MetaFalsa().instalar(monkeypatch)
    a, b = escenario["a"], escenario["b"]
    b.whatsapp_phone_number_id = "PNID1"
    whatsapp.guardar_token(b, "token-de-b")
    await db.commit()

    token = onboarding.emitir(a.id).token
    r = await cliente.post(f"/api/v1/onboarding/{token}/conectar", json=_payload())
    assert r.status_code == 409

    # No se gasto el code contra Meta: el numero se comprueba antes.
    assert meta.llamadas == []
    await db.refresh(a)
    assert not whatsapp.tiene_whatsapp(a)


async def test_un_link_no_pisa_un_whatsapp_ya_conectado(
    cliente: AsyncClient, escenario: dict, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ Es lo que hace que un link filtrado no le pueda robar el canal a un
    cliente que ya esta andando."""
    _MetaFalsa().instalar(monkeypatch)
    a = escenario["a"]
    a.whatsapp_phone_number_id = "EL-DE-VERDAD"
    whatsapp.guardar_token(a, "token-bueno")
    await db.commit()

    token = onboarding.emitir(a.id).token
    r = await cliente.post(f"/api/v1/onboarding/{token}/conectar", json=_payload())
    assert r.status_code == 409

    await db.refresh(a)
    assert a.whatsapp_phone_number_id == "EL-DE-VERDAD"
    assert whatsapp.leer_token(a) == "token-bueno"


async def test_no_se_puede_conectar_con_un_link_vencido(
    cliente: AsyncClient, escenario: dict, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _MetaFalsa().instalar(monkeypatch)
    a = escenario["a"]
    token = onboarding.emitir(a.id, horas=-1).token

    r = await cliente.post(f"/api/v1/onboarding/{token}/conectar", json=_payload())
    assert r.status_code == 410

    await db.refresh(a)
    assert not whatsapp.tiene_whatsapp(a)


async def test_un_cliente_desactivado_deja_el_link_muerto(
    cliente: AsyncClient, escenario: dict, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _MetaFalsa().instalar(monkeypatch)
    a = escenario["a"]
    token = onboarding.emitir(a.id).token
    a.is_active = False
    await db.commit()

    r = await cliente.post(f"/api/v1/onboarding/{token}/conectar", json=_payload())
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# El PIN de registro
# ---------------------------------------------------------------------------


def test_el_pin_es_estable_para_el_mismo_cliente() -> None:
    """Se deriva en vez de guardarse: tiene que dar siempre lo mismo o no se
    podria volver a registrar el numero mas adelante."""
    tid = uuid.uuid4()
    assert whatsapp.pin_de_registro(tid) == whatsapp.pin_de_registro(tid)


def test_cada_cliente_tiene_su_propio_pin() -> None:
    assert whatsapp.pin_de_registro(uuid.uuid4()) != whatsapp.pin_de_registro(uuid.uuid4())


def test_el_pin_tiene_los_seis_digitos_que_pide_meta() -> None:
    pin = whatsapp.pin_de_registro(uuid.uuid4())
    assert len(pin) == 6
    assert pin.isdigit()
