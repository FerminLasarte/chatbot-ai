"""Canal de WhatsApp: credenciales por cliente y envio.

Lo critico aca es doble:
  - que el access token NUNCA vuelva por la API (es la credencial que permite
    escribir en nombre del negocio del cliente), y
  - que el envio realmente mande el header de autorizacion: sin el, Meta
    responde 401 y ningun mensaje llega, pero el codigo "parece" correcto.
"""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.whatsapp import client as wa_client
from app.channels.whatsapp.client import WhatsAppSinCredencial, send_text
from app.core import cifrado as cifrado_mod
from app.core.cifrado import CifradoInvalido, cifrar, descifrar
from app.core.security import generate_api_key
from app.main import app
from app.models.api_key import ApiKey, Scope
from app.models.tenant import Tenant
from app.services import whatsapp

CLAVE_PRUEBA = "6DLQaJDkYtFB3LMlBI1nCH_1kBaRhGSFTOM6vD-FJTM="
OTRA_CLAVE = "Yx4pJ7Xq2mF8vN3sKdR6wT9zL1cB5hG0aE7uI4oP2Qk="


@pytest.fixture(autouse=True)
def _clave_de_cifrado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cifrado_mod.settings, "encryption_key", CLAVE_PRUEBA)


@pytest_asyncio.fixture
async def cliente() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def escenario(db: AsyncSession) -> AsyncIterator[dict]:
    sufijo = uuid.uuid4().hex[:8]
    a = Tenant(slug=f"wa-a-{sufijo}", name="Cliente A", system_prompt="soy A")
    b = Tenant(slug=f"wa-b-{sufijo}", name="Cliente B", system_prompt="soy B")
    db.add_all([a, b])
    await db.commit()
    await db.refresh(a)
    await db.refresh(b)

    raw, prefix, hashed = generate_api_key()
    db.add(
        ApiKey(
            name="admin-wa",
            key_prefix=prefix,
            key_hash=hashed,
            tenant_id=None,
            scopes=[Scope.ADMIN.value],
        )
    )
    await db.commit()

    yield {"a": a, "b": b, "admin": raw, "prefijo_admin": prefix}

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


# --- Cifrado ---


def test_el_token_va_y_vuelve_igual() -> None:
    token = "EAAG1234tokendeprueba"
    assert descifrar(cifrar(token)) == token


def test_el_texto_cifrado_no_contiene_el_token() -> None:
    """Si el token se leyera del volcado de la base, cifrar no serviria de nada."""
    token = "EAAG1234tokendeprueba"
    assert token not in cifrar(token)


def test_dos_cifrados_del_mismo_token_no_son_iguales() -> None:
    """Fernet mete un nonce: dos filas con el mismo token no se ven iguales."""
    assert cifrar("mismo") != cifrar("mismo")


def test_con_otra_clave_no_se_puede_descifrar(monkeypatch: pytest.MonkeyPatch) -> None:
    guardado = cifrar("secreto")
    monkeypatch.setattr(cifrado_mod.settings, "encryption_key", OTRA_CLAVE)
    with pytest.raises(CifradoInvalido):
        descifrar(guardado)


# --- Servicio ---


def test_guardar_y_leer_el_token_de_un_cliente() -> None:
    t = Tenant(slug="x", name="X", system_prompt="")
    whatsapp.guardar_token(t, "EAAGtoken")
    assert t.whatsapp_access_token_cifrado is not None
    assert whatsapp.leer_token(t) == "EAAGtoken"


def test_guardar_vacio_borra_el_token() -> None:
    t = Tenant(slug="x", name="X", system_prompt="")
    whatsapp.guardar_token(t, "EAAGtoken")
    whatsapp.guardar_token(t, "")
    assert t.whatsapp_access_token_cifrado is None
    assert whatsapp.leer_token(t) is None


def test_hace_falta_numero_y_token_para_estar_configurado() -> None:
    t = Tenant(slug="x", name="X", system_prompt="")
    assert not whatsapp.tiene_whatsapp(t)

    t.whatsapp_phone_number_id = "123"
    assert not whatsapp.tiene_whatsapp(t), "con numero pero sin token no se puede enviar"

    whatsapp.guardar_token(t, "EAAGtoken")
    assert whatsapp.tiene_whatsapp(t)


# --- Envio ---


async def test_el_envio_manda_el_header_de_autorizacion(monkeypatch: pytest.MonkeyPatch) -> None:
    """★ Sin este header Meta devuelve 401 y no se entrega nada."""
    capturado: dict = {}

    class _Respuesta:
        def raise_for_status(self) -> None:
            return None

    class _ClienteFalso:
        async def __aenter__(self) -> "_ClienteFalso":
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

        async def post(self, url: str, json: dict, headers: dict) -> _Respuesta:
            capturado["url"] = url
            capturado["json"] = json
            capturado["headers"] = headers
            return _Respuesta()

    monkeypatch.setattr(wa_client.httpx, "AsyncClient", lambda **kw: _ClienteFalso())

    await send_text(to="549111", text="hola", phone_number_id="PNID", access_token="EAAGtoken")

    assert capturado["headers"]["Authorization"] == "Bearer EAAGtoken"
    assert "PNID" in capturado["url"]
    assert capturado["json"]["to"] == "549111"
    assert capturado["json"]["text"]["body"] == "hola"


async def test_el_envio_devuelve_el_id_del_mensaje(monkeypatch: pytest.MonkeyPatch) -> None:
    """★ Ese id es lo que evita que el bot se auto-pause con coexistence.

    Cuando llegue el echo de este mismo mensaje, se lo reconoce por el id (ver
    docs/coexistence.md). Sin el, queda solo la defensa por texto.
    """

    class _Respuesta:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"messages": [{"id": "wamid.HBgM123"}]}

    class _ClienteFalso:
        async def __aenter__(self) -> "_ClienteFalso":
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

        async def post(self, url: str, json: dict, headers: dict) -> _Respuesta:
            return _Respuesta()

    monkeypatch.setattr(wa_client.httpx, "AsyncClient", lambda **kw: _ClienteFalso())

    wamid = await send_text(
        to="549111", text="hola", phone_number_id="PNID", access_token="EAAGtoken"
    )
    assert wamid == "wamid.HBgM123"


async def test_un_envio_exitoso_sin_id_no_se_toma_como_fallido(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El mensaje ya salio. Romper aca lo haria reenviar en el reintento."""

    class _Respuesta:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"messages": []}

    class _ClienteFalso:
        async def __aenter__(self) -> "_ClienteFalso":
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

        async def post(self, url: str, json: dict, headers: dict) -> _Respuesta:
            return _Respuesta()

    monkeypatch.setattr(wa_client.httpx, "AsyncClient", lambda **kw: _ClienteFalso())

    assert (
        await send_text(to="549111", text="hola", phone_number_id="PNID", access_token="EAAGtoken")
        is None
    )


async def test_sin_token_no_se_intenta_enviar(monkeypatch: pytest.MonkeyPatch) -> None:
    """Falla con un error propio y claro, no con un 401 opaco de Meta."""

    def _explotar(**kw: object) -> None:
        raise AssertionError("no tendria que haber llamado a la API de Meta")

    monkeypatch.setattr(wa_client.httpx, "AsyncClient", _explotar)

    with pytest.raises(WhatsAppSinCredencial):
        await send_text(to="549111", text="hola", phone_number_id="PNID", access_token="")


async def test_un_4xx_de_meta_se_reporta_con_su_detalle(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Respuesta:
        status_code = 400
        text = '{"error":{"message":"Invalid phone number"}}'

        def raise_for_status(self) -> None:
            raise httpx.HTTPStatusError("400", request=None, response=self)  # type: ignore[arg-type]

    class _ClienteFalso:
        async def __aenter__(self) -> "_ClienteFalso":
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

        async def post(self, url: str, json: dict, headers: dict) -> _Respuesta:
            return _Respuesta()

    monkeypatch.setattr(wa_client.httpx, "AsyncClient", lambda **kw: _ClienteFalso())

    with pytest.raises(Exception, match="Invalid phone number"):
        await send_text(to="549111", text="hola", phone_number_id="PNID", access_token="EAAGtoken")


# --- Endpoint de configuracion ---


async def test_configurar_whatsapp_y_leer_el_estado(cliente: AsyncClient, escenario: dict) -> None:
    a = escenario["a"]
    r = await cliente.patch(
        f"/api/v1/tenants/{a.id}/whatsapp",
        headers=_auth(escenario["admin"]),
        json={"phone_number_id": "1234567890", "access_token": "EAAGsecreto"},
    )
    assert r.status_code == 200
    assert r.json() == {
        "phone_number_id": "1234567890",
        "tiene_token": True,
        "configurado": True,
    }


async def test_la_api_nunca_devuelve_el_token(cliente: AsyncClient, escenario: dict) -> None:
    """★ Ni entero ni parcial: solo si existe o no."""
    a = escenario["a"]
    await cliente.patch(
        f"/api/v1/tenants/{a.id}/whatsapp",
        headers=_auth(escenario["admin"]),
        json={"phone_number_id": "1234567890", "access_token": "EAAGsecretisimo"},
    )
    r = await cliente.get(f"/api/v1/tenants/{a.id}/whatsapp", headers=_auth(escenario["admin"]))
    assert r.status_code == 200
    assert "EAAGsecretisimo" not in r.text
    assert r.json()["tiene_token"] is True


async def test_editar_solo_el_numero_conserva_el_token(
    cliente: AsyncClient, escenario: dict
) -> None:
    a = escenario["a"]
    await cliente.patch(
        f"/api/v1/tenants/{a.id}/whatsapp",
        headers=_auth(escenario["admin"]),
        json={"phone_number_id": "111", "access_token": "EAAGtoken"},
    )
    r = await cliente.patch(
        f"/api/v1/tenants/{a.id}/whatsapp",
        headers=_auth(escenario["admin"]),
        json={"phone_number_id": "222"},  # sin access_token
    )
    assert r.status_code == 200
    assert r.json()["phone_number_id"] == "222"
    assert r.json()["tiene_token"] is True, "no habia que borrar el token"


async def test_mandar_token_vacio_lo_borra(cliente: AsyncClient, escenario: dict) -> None:
    a = escenario["a"]
    await cliente.patch(
        f"/api/v1/tenants/{a.id}/whatsapp",
        headers=_auth(escenario["admin"]),
        json={"phone_number_id": "111", "access_token": "EAAGtoken"},
    )
    r = await cliente.patch(
        f"/api/v1/tenants/{a.id}/whatsapp",
        headers=_auth(escenario["admin"]),
        json={"access_token": ""},
    )
    assert r.json()["tiene_token"] is False
    assert r.json()["configurado"] is False


async def test_dos_clientes_no_pueden_compartir_numero(
    cliente: AsyncClient, escenario: dict
) -> None:
    """★ El numero resuelve a que cliente pertenece un mensaje entrante. Si se
    repitiera, los mensajes de uno se contestarian con los datos del otro."""
    a, b = escenario["a"], escenario["b"]
    await cliente.patch(
        f"/api/v1/tenants/{a.id}/whatsapp",
        headers=_auth(escenario["admin"]),
        json={"phone_number_id": "compartido", "access_token": "t1"},
    )
    r = await cliente.patch(
        f"/api/v1/tenants/{b.id}/whatsapp",
        headers=_auth(escenario["admin"]),
        json={"phone_number_id": "compartido", "access_token": "t2"},
    )
    assert r.status_code == 409


async def test_configurar_whatsapp_exige_clave_admin(
    cliente: AsyncClient, escenario: dict, db: AsyncSession
) -> None:
    raw, prefix, hashed = generate_api_key()
    db.add(
        ApiKey(
            name="tenant-key",
            key_prefix=prefix,
            key_hash=hashed,
            tenant_id=escenario["a"].id,
            scopes=[Scope.TENANT.value],
        )
    )
    await db.commit()

    r = await cliente.patch(
        f"/api/v1/tenants/{escenario['a'].id}/whatsapp",
        headers=_auth(raw),
        json={"phone_number_id": "999"},
    )
    assert r.status_code == 403
