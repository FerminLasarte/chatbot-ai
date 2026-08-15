"""El portal del cliente: que vea lo suyo, y SOLO lo suyo.

Este archivo es el hermano de test_tenant_isolation.py. Alla se defiende que la
busqueda vectorial no mezcle documentos entre clientes; aca, que la credencial
que la agencia le manda por WhatsApp al duenio de una PyME no sirva para nada
mas que su propio negocio.

Importa mas que en el resto de la API porque esta es la unica clave que sale de
servidores controlados por la agencia: vive en el telefono de un tercero.

Lo que se defiende:

1. Con la clave del portal se ven las conversaciones propias y se pausa el bot.
2. Con la clave del portal NO se ve ni se toca la conversacion de otro cliente,
   aunque se sepa el UUID exacto.
3. La clave del portal no abre ningun endpoint de la agencia ni del dashboard.
4. Ninguna otra clave abre el portal.
5. Revocarla corta el acceso en el acto: es lo que reemplaza al vencimiento.
6. Emitir un link nuevo revoca el anterior.
"""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_api_key
from app.main import app
from app.models.api_key import ApiKey, Scope
from app.models.tenant import Conversation, Tenant
from app.services.conversation import _guardar_mensaje

NUMERO = "5491199988877"


@pytest_asyncio.fixture
async def cliente() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def dos_negocios(db: AsyncSession) -> AsyncIterator[tuple[Tenant, Tenant]]:
    """Dos clientes de la agencia, cada uno con una conversacion propia."""
    sufijo = uuid.uuid4().hex[:8]
    mio = Tenant(slug=f"test-portal-mio-{sufijo}", name="Panaderia de la esquina")
    ajeno = Tenant(slug=f"test-portal-ajeno-{sufijo}", name="Ferreteria de enfrente")
    db.add_all([mio, ajeno])
    await db.commit()
    await db.refresh(mio)
    await db.refresh(ajeno)

    yield mio, ajeno

    for t in (mio, ajeno):
        await db.execute(delete(Tenant).where(Tenant.id == t.id))
    await db.commit()


@pytest_asyncio.fixture
async def emitir(db: AsyncSession) -> AsyncIterator[Callable[..., Awaitable[str]]]:
    """Fabrica de claves que se limpia sola al terminar el test.

    Las de cliente se irian igual por la CASCADE del tenant, pero las admin no
    tienen tenant: sin esto quedan claves vivas en la base de desarrollo.
    """
    emitidas: list[str] = []

    async def _emitir(tenant: Tenant | None, *scopes: Scope) -> str:
        raw, prefix, hashed = generate_api_key()
        db.add(
            ApiKey(
                name=f"test-{'-'.join(s.value for s in scopes)}",
                key_prefix=prefix,
                key_hash=hashed,
                tenant_id=tenant.id if tenant else None,
                scopes=[s.value for s in scopes],
            )
        )
        await db.commit()
        emitidas.append(prefix)
        return raw

    yield _emitir

    await db.execute(delete(ApiKey).where(ApiKey.key_prefix.in_(emitidas)))
    await db.commit()


async def _conversacion(db: AsyncSession, tenant: Tenant) -> Conversation:
    c = Conversation(tenant_id=tenant.id, channel="whatsapp", external_id=NUMERO)
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


def _auth(k: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {k}"}


# --------------------------------------------------------------------------
# 1. Lo que el cliente SI puede hacer
# --------------------------------------------------------------------------


async def test_el_cliente_ve_sus_conversaciones(
    db: AsyncSession,
    dos_negocios: tuple[Tenant, Tenant],
    cliente: AsyncClient,
    emitir: Callable[..., Awaitable[str]],
) -> None:
    mio, _ajeno = dos_negocios
    conversacion = await _conversacion(db, mio)
    await _guardar_mensaje(db, conversacion.id, "user", "hacen tortas para 20 personas?")
    await _guardar_mensaje(db, conversacion.id, "assistant", "si! contame para cuando")
    clave = await emitir(mio, Scope.CLIENT_PORTAL)

    r = await cliente.get("/api/v1/portal/conversations", headers=_auth(clave))
    assert r.status_code == 200
    (fila,) = r.json()
    assert fila["external_id"] == NUMERO
    assert fila["mensajes"] == 2
    assert fila["ultimo_mensaje"] == "si! contame para cuando"
    assert fila["en_modo_manual"] is False


async def test_el_cliente_pausa_y_reanuda_su_bot(
    db: AsyncSession,
    dos_negocios: tuple[Tenant, Tenant],
    cliente: AsyncClient,
    emitir: Callable[..., Awaitable[str]],
) -> None:
    mio, _ajeno = dos_negocios
    conversacion = await _conversacion(db, mio)
    clave = await emitir(mio, Scope.CLIENT_PORTAL)
    url = f"/api/v1/portal/conversations/{conversacion.id}/manual"

    r = await cliente.post(url, headers=_auth(clave), json={"horas": 3})
    assert r.status_code == 200
    assert r.json()["en_modo_manual"] is True
    assert 175 <= r.json()["minutos_restantes"] <= 180

    await db.refresh(conversacion)
    assert conversacion.en_modo_manual()

    r = await cliente.delete(url, headers=_auth(clave))
    assert r.status_code == 200
    assert r.json()["en_modo_manual"] is False

    await db.refresh(conversacion)
    assert not conversacion.en_modo_manual()


async def test_el_portal_dice_de_que_negocio_es(
    db: AsyncSession,
    dos_negocios: tuple[Tenant, Tenant],
    cliente: AsyncClient,
    emitir: Callable[..., Awaitable[str]],
) -> None:
    """Es tambien la ruta con la que el frontend valida el link al canjearlo."""
    mio, _ajeno = dos_negocios
    clave = await emitir(mio, Scope.CLIENT_PORTAL)

    r = await cliente.get("/api/v1/portal/me", headers=_auth(clave))
    assert r.status_code == 200
    assert r.json() == {"nombre": "Panaderia de la esquina"}, (
        "el portal no tiene que devolver prompt, slug ni tope: solo el nombre"
    )


async def test_el_cliente_no_puede_pausar_para_siempre(
    db: AsyncSession,
    dos_negocios: tuple[Tenant, Tenant],
    cliente: AsyncClient,
    emitir: Callable[..., Awaitable[str]],
) -> None:
    """Mismo tope que para la agencia: la pausa siempre vence."""
    mio, _ajeno = dos_negocios
    conversacion = await _conversacion(db, mio)
    clave = await emitir(mio, Scope.CLIENT_PORTAL)

    r = await cliente.post(
        f"/api/v1/portal/conversations/{conversacion.id}/manual",
        headers=_auth(clave),
        json={"horas": 24 * 365},
    )
    assert r.status_code == 422


# --------------------------------------------------------------------------
# 2. ★ Lo que NO puede hacer: el corazon de esta feature
# --------------------------------------------------------------------------


async def test_no_ve_las_conversaciones_de_otro_negocio(
    db: AsyncSession,
    dos_negocios: tuple[Tenant, Tenant],
    cliente: AsyncClient,
    emitir: Callable[..., Awaitable[str]],
) -> None:
    """★ El caso que motiva que /portal no tenga tenant_id en la URL."""
    mio, ajeno = dos_negocios
    await _conversacion(db, mio)
    conversacion_ajena = await _conversacion(db, ajeno)
    await _guardar_mensaje(db, conversacion_ajena.id, "user", "SECRETO DE LA FERRETERIA")
    clave = await emitir(mio, Scope.CLIENT_PORTAL)

    r = await cliente.get("/api/v1/portal/conversations", headers=_auth(clave))
    assert r.status_code == 200
    ids = {fila["id"] for fila in r.json()}
    assert str(conversacion_ajena.id) not in ids, (
        "FUGA ENTRE CLIENTES: el portal de un negocio listo la conversacion de otro"
    )
    assert all(fila["ultimo_mensaje"] != "SECRETO DE LA FERRETERIA" for fila in r.json())


async def test_no_puede_pausar_la_conversacion_de_otro_negocio(
    db: AsyncSession,
    dos_negocios: tuple[Tenant, Tenant],
    cliente: AsyncClient,
    emitir: Callable[..., Awaitable[str]],
) -> None:
    """★ Sabiendo el UUID exacto, que es el peor caso realista.

    404 y no 403: no le confirmamos a nadie que ese id exista en otro lado.
    """
    mio, ajeno = dos_negocios
    ajena = await _conversacion(db, ajeno)
    clave = await emitir(mio, Scope.CLIENT_PORTAL)
    url = f"/api/v1/portal/conversations/{ajena.id}/manual"

    r = await cliente.post(url, headers=_auth(clave), json={"horas": 2})
    assert r.status_code == 404

    r = await cliente.delete(url, headers=_auth(clave))
    assert r.status_code == 404

    await db.refresh(ajena)
    assert ajena.pausada_hasta is None, "la conversacion del otro negocio quedo intacta"


async def test_la_clave_del_portal_no_abre_nada_de_la_agencia(
    db: AsyncSession,
    dos_negocios: tuple[Tenant, Tenant],
    cliente: AsyncClient,
    emitir: Callable[..., Awaitable[str]],
) -> None:
    """★ El alcance minimo es la premisa: esta clave vive en un telefono ajeno.

    Si alguna de estas empieza a devolver 200, la clave dejo de ser "ver y
    pausar" y paso a ser algo que la agencia no querria haber mandado por
    WhatsApp.
    """
    mio, ajeno = dos_negocios
    clave = await emitir(mio, Scope.CLIENT_PORTAL)

    prohibidas = [
        ("get", "/api/v1/tenants", None),  # la lista de TODOS los clientes
        ("get", f"/api/v1/tenants/{mio.id}/conversations", None),  # la ruta de agencia
        ("get", f"/api/v1/tenants/{ajeno.id}/conversations", None),
        ("get", f"/api/v1/tenants/{mio.id}/documents", None),
        ("get", f"/api/v1/tenants/{mio.id}/usage", None),
        ("get", f"/api/v1/tenants/{mio.id}/whatsapp", None),  # credenciales
        ("get", f"/api/v1/tenants/{mio.id}/keys", None),
        ("get", "/api/v1/tenants/me", None),  # el dashboard del cliente
        ("get", "/api/v1/tenants/me/usage", None),
        ("post", f"/api/v1/tenants/{mio.id}/portal-link", None),  # emitirse claves solo
        ("patch", "/api/v1/tenants/me/prompt", {"system_prompt": "sos un pirata"}),
        ("patch", f"/api/v1/tenants/{mio.id}/limit", {"monthly_message_limit": 999999}),
    ]

    for metodo, url, cuerpo in prohibidas:
        r = await getattr(cliente, metodo)(
            url, headers=_auth(clave), **({"json": cuerpo} if cuerpo else {})
        )
        assert r.status_code == 403, f"{metodo.upper()} {url} dio {r.status_code}, no 403"


async def test_ninguna_otra_clave_abre_el_portal(
    db: AsyncSession,
    dos_negocios: tuple[Tenant, Tenant],
    cliente: AsyncClient,
    emitir: Callable[..., Awaitable[str]],
) -> None:
    """El portal tampoco es una puerta de atras para las claves que ya existen.

    Incluye la clave `chat`, que es publica y viaja en el navegador de cualquier
    visitante de la web del cliente: si esa abriera el portal, los telefonos de
    los usuarios finales quedarian a un fetch de distancia.
    """
    mio, _ajeno = dos_negocios

    for scopes in ((Scope.TENANT,), (Scope.CHAT,), (Scope.ADMIN,)):
        tenant = None if scopes == (Scope.ADMIN,) else mio
        clave = await emitir(tenant, *scopes)
        r = await cliente.get("/api/v1/portal/conversations", headers=_auth(clave))
        assert r.status_code == 403, f"la clave {scopes[0].value} entro al portal"


async def test_sin_clave_no_se_entra(cliente: AsyncClient) -> None:
    r = await cliente.get("/api/v1/portal/conversations")
    assert r.status_code == 401


# --------------------------------------------------------------------------
# 3. Revocacion: lo que reemplaza al vencimiento
# --------------------------------------------------------------------------


async def test_revocar_la_clave_corta_el_acceso(
    db: AsyncSession,
    dos_negocios: tuple[Tenant, Tenant],
    cliente: AsyncClient,
    emitir: Callable[..., Awaitable[str]],
) -> None:
    """★ El link no vence, asi que esto es lo unico que lo apaga."""
    mio, _ajeno = dos_negocios
    await _conversacion(db, mio)
    clave = await emitir(mio, Scope.CLIENT_PORTAL)

    assert (await cliente.get("/api/v1/portal/me", headers=_auth(clave))).status_code == 200

    fila = await db.scalar(select(ApiKey).where(ApiKey.key_prefix == clave[:16]))
    assert fila is not None
    fila.revoked_at = datetime.now(UTC)
    await db.commit()

    r = await cliente.get("/api/v1/portal/me", headers=_auth(clave))
    assert r.status_code == 401


async def test_emitir_un_link_nuevo_revoca_el_anterior(
    db: AsyncSession,
    dos_negocios: tuple[Tenant, Tenant],
    cliente: AsyncClient,
    emitir: Callable[..., Awaitable[str]],
) -> None:
    """★ Es el remedio que tiene la agencia cuando un cliente dice "se me filtro".

    Sin esto, el link viejo seguiria abriendo el portal para siempre y no habria
    forma de cerrarlo sin ir a buscar la fila a mano.
    """
    mio, _ajeno = dos_negocios
    admin = await emitir(None, Scope.ADMIN)

    r = await cliente.post(f"/api/v1/tenants/{mio.id}/portal-link", headers=_auth(admin))
    assert r.status_code == 200
    primera = r.json()
    vieja = primera["url"].split("/mi-negocio/")[1]
    # La URL lleva la clave entera; el prefijo devuelto aparte es lo que despues
    # permite reconocerla en la lista de claves del panel para revocarla.
    assert vieja.startswith(primera["key_prefix"])
    assert (await cliente.get("/api/v1/portal/me", headers=_auth(vieja))).status_code == 200

    r = await cliente.post(f"/api/v1/tenants/{mio.id}/portal-link", headers=_auth(admin))
    assert r.status_code == 200
    nueva = r.json()["url"].split("/mi-negocio/")[1]
    assert nueva != vieja

    assert (await cliente.get("/api/v1/portal/me", headers=_auth(vieja))).status_code == 401, (
        "el link viejo sigue vivo: emitir uno nuevo tiene que revocarlo"
    )
    assert (await cliente.get("/api/v1/portal/me", headers=_auth(nueva))).status_code == 200


async def test_el_link_emitido_no_toca_las_otras_claves_del_cliente(
    db: AsyncSession,
    dos_negocios: tuple[Tenant, Tenant],
    cliente: AsyncClient,
    emitir: Callable[..., Awaitable[str]],
) -> None:
    """Revocar 'los links de portal anteriores' no puede llevarse puesto el widget.

    La clave `chat` esta pegada en la web del cliente: si se revocara sin querer,
    el bot deja de responder ahi y nadie relaciona la causa con este boton.
    """
    mio, _ajeno = dos_negocios
    admin = await emitir(None, Scope.ADMIN)
    del_widget = await emitir(mio, Scope.CHAT)
    del_dashboard = await emitir(mio, Scope.TENANT)

    r = await cliente.post(f"/api/v1/tenants/{mio.id}/portal-link", headers=_auth(admin))
    assert r.status_code == 200

    for otra in (del_widget, del_dashboard):
        fila = await db.scalar(select(ApiKey).where(ApiKey.key_prefix == otra[:16]))
        assert fila is not None
        assert fila.revoked_at is None, "se revoco una clave que no era del portal"
