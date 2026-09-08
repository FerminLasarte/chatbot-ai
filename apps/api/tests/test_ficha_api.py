"""La ficha del negocio por sus dos puertas.

Una sola ficha, dos credenciales: la agencia con clave admin diciendo sobre que
cliente opera, y el duenio con la clave de su portal, que ya trae su tenant.

Lo que se defiende:

1. Las dos puertas leen y escriben LA MISMA ficha. Si divergieran, el duenio
   corregiria su horario y la agencia seguiria viendo el viejo.

2. ★ La clave del portal no toca la ficha de otro negocio. No hay `tenant_id`
   en la URL del portal justamente para que no haya nada que cruzar.

3. Escribir la ficha NO le abrio la puerta a nada mas: la clave del portal
   sigue sin poder tocar el prompt, los documentos ni las claves.

4. Ninguna otra clave abre la ficha del portal, la publica del widget incluida.

5. Una ficha invalida se rechaza en el borde, con 422, y no llega a la base.
"""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_api_key
from app.main import app
from app.models.api_key import ApiKey, Scope
from app.models.tenant import Tenant

FICHA = {
    "direccion": "Av. Siempreviva 742",
    "horarios": [{"dia": 0, "desde": "09:00", "hasta": "13:00"}],
    "medios_de_pago": "Efectivo y transferencia.",
    "extras": [{"titulo": "Estacionamiento", "texto": "Hay cochera en la esquina."}],
}


@pytest_asyncio.fixture
async def cliente() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def dos_negocios(db: AsyncSession) -> AsyncIterator[tuple[Tenant, Tenant]]:
    sufijo = uuid.uuid4().hex[:8]
    mio = Tenant(slug=f"ficha-mio-{sufijo}", name="Panaderia de la esquina")
    ajeno = Tenant(slug=f"ficha-ajeno-{sufijo}", name="Ferreteria de enfrente")
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
    """Fabrica de claves que se limpia sola: las admin no cuelgan de un tenant."""
    emitidas: list[str] = []

    async def _emitir(tenant: Tenant | None, *scopes: Scope) -> str:
        raw, prefix, hashed = generate_api_key()
        db.add(
            ApiKey(
                name=f"test-ficha-{'-'.join(s.value for s in scopes)}",
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


def _auth(k: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {k}"}


# --------------------------------------------------------------------------
# 1. Las dos puertas, una sola ficha
# --------------------------------------------------------------------------


async def test_un_cliente_nuevo_devuelve_la_ficha_vacia(
    dos_negocios: tuple[Tenant, Tenant],
    cliente: AsyncClient,
    emitir: Callable[..., Awaitable[str]],
) -> None:
    mio, _ = dos_negocios
    clave = await emitir(mio, Scope.CLIENT_PORTAL)

    r = await cliente.get("/api/v1/portal/ficha", headers=_auth(clave))
    assert r.status_code == 200
    assert r.json()["direccion"] is None
    assert r.json()["horarios"] == []


async def test_el_duenio_guarda_su_ficha_y_la_agencia_la_ve(
    dos_negocios: tuple[Tenant, Tenant],
    cliente: AsyncClient,
    emitir: Callable[..., Awaitable[str]],
) -> None:
    """★ Es la misma ficha. Si fueran dos, el duenio corregiria su horario y la
    agencia seguiria mirando el viejo."""
    mio, _ = dos_negocios
    portal = await emitir(mio, Scope.CLIENT_PORTAL)
    admin = await emitir(None, Scope.ADMIN)

    guardado = await cliente.put("/api/v1/portal/ficha", headers=_auth(portal), json=FICHA)
    assert guardado.status_code == 200

    visto = await cliente.get(f"/api/v1/tenants/{mio.id}/ficha", headers=_auth(admin))
    assert visto.status_code == 200
    assert visto.json()["direccion"] == "Av. Siempreviva 742"
    assert visto.json()["extras"][0]["titulo"] == "Estacionamiento"


async def test_la_agencia_guarda_y_el_duenio_lo_ve(
    dos_negocios: tuple[Tenant, Tenant],
    cliente: AsyncClient,
    emitir: Callable[..., Awaitable[str]],
) -> None:
    """El camino de vuelta: la agencia completa la ficha en el alta."""
    mio, _ = dos_negocios
    portal = await emitir(mio, Scope.CLIENT_PORTAL)
    admin = await emitir(None, Scope.ADMIN)

    await cliente.put(f"/api/v1/tenants/{mio.id}/ficha", headers=_auth(admin), json=FICHA)

    r = await cliente.get("/api/v1/portal/ficha", headers=_auth(portal))
    assert r.json()["medios_de_pago"] == "Efectivo y transferencia."


async def test_guardar_reemplaza_y_permite_borrar(
    dos_negocios: tuple[Tenant, Tenant],
    cliente: AsyncClient,
    emitir: Callable[..., Awaitable[str]],
) -> None:
    """Es PUT: mandar la ficha sin un campo lo borra. Sin esto no habria forma
    de sacar un horario que dejo de valer."""
    mio, _ = dos_negocios
    portal = await emitir(mio, Scope.CLIENT_PORTAL)

    await cliente.put("/api/v1/portal/ficha", headers=_auth(portal), json=FICHA)
    r = await cliente.put(
        "/api/v1/portal/ficha", headers=_auth(portal), json={"direccion": "Corrientes 1234"}
    )

    assert r.json()["direccion"] == "Corrientes 1234"
    assert r.json()["horarios"] == []
    assert r.json()["medios_de_pago"] is None


# --------------------------------------------------------------------------
# 2. Aislamiento
# --------------------------------------------------------------------------


async def test_la_ficha_que_se_escribe_es_la_del_duenio_de_la_clave(
    dos_negocios: tuple[Tenant, Tenant],
    cliente: AsyncClient,
    emitir: Callable[..., Awaitable[str]],
) -> None:
    """★ No hay `tenant_id` que cruzar en el portal, y esto lo comprueba: el de
    al lado tiene que quedar intacto."""
    mio, ajeno = dos_negocios
    portal = await emitir(mio, Scope.CLIENT_PORTAL)
    admin = await emitir(None, Scope.ADMIN)

    await cliente.put("/api/v1/portal/ficha", headers=_auth(portal), json=FICHA)

    del_ajeno = await cliente.get(f"/api/v1/tenants/{ajeno.id}/ficha", headers=_auth(admin))
    assert del_ajeno.json()["direccion"] is None


async def test_la_agencia_no_puede_escribir_en_un_cliente_que_no_existe(
    cliente: AsyncClient,
    emitir: Callable[..., Awaitable[str]],
) -> None:
    admin = await emitir(None, Scope.ADMIN)
    r = await cliente.put(f"/api/v1/tenants/{uuid.uuid4()}/ficha", headers=_auth(admin), json=FICHA)
    assert r.status_code == 404


# --------------------------------------------------------------------------
# 3. Que el permiso nuevo no haya abierto nada mas
# --------------------------------------------------------------------------


async def test_escribir_la_ficha_no_le_abrio_la_puerta_a_nada_mas(
    dos_negocios: tuple[Tenant, Tenant],
    cliente: AsyncClient,
    emitir: Callable[..., Awaitable[str]],
) -> None:
    """★ La ficha es lo UNICO que esta clave puede escribir.

    El prompt y los documentos definen como se comporta el bot; la ficha son
    datos que el bot cita. Si alguna de estas empieza a devolver 200, la clave
    que la agencia manda por WhatsApp dejo de ser lo que dice ser.
    """
    mio, ajeno = dos_negocios
    clave = await emitir(mio, Scope.CLIENT_PORTAL)

    prohibidas = [
        ("patch", "/api/v1/tenants/me/prompt", {"system_prompt": "sos un pirata"}),
        ("patch", f"/api/v1/tenants/{mio.id}/prompt", {"system_prompt": "sos un pirata"}),
        ("get", f"/api/v1/tenants/{mio.id}/documents", None),
        ("get", f"/api/v1/tenants/{mio.id}/keys", None),
        ("get", f"/api/v1/tenants/{mio.id}/ficha", None),  # la puerta de la agencia
        ("put", f"/api/v1/tenants/{ajeno.id}/ficha", FICHA),
    ]

    for metodo, url, cuerpo in prohibidas:
        r = await getattr(cliente, metodo)(
            url, headers=_auth(clave), **({"json": cuerpo} if cuerpo else {})
        )
        assert r.status_code == 403, f"{metodo.upper()} {url} dio {r.status_code}, no 403"


async def test_ninguna_otra_clave_abre_la_ficha_del_portal(
    dos_negocios: tuple[Tenant, Tenant],
    cliente: AsyncClient,
    emitir: Callable[..., Awaitable[str]],
) -> None:
    """La clave `chat` es publica: viaja en el navegador de cualquier visitante."""
    mio, _ = dos_negocios

    for scopes in ((Scope.TENANT,), (Scope.CHAT,), (Scope.ADMIN,)):
        tenant = None if scopes == (Scope.ADMIN,) else mio
        clave = await emitir(tenant, *scopes)

        leer = await cliente.get("/api/v1/portal/ficha", headers=_auth(clave))
        escribir = await cliente.put("/api/v1/portal/ficha", headers=_auth(clave), json=FICHA)

        assert leer.status_code == 403, f"la clave {scopes[0].value} leyo la ficha"
        assert escribir.status_code == 403, f"la clave {scopes[0].value} escribio la ficha"


async def test_sin_clave_no_se_entra(cliente: AsyncClient) -> None:
    assert (await cliente.get("/api/v1/portal/ficha")).status_code == 401
    assert (await cliente.put("/api/v1/portal/ficha", json=FICHA)).status_code == 401


# --------------------------------------------------------------------------
# 4. Validacion en el borde
# --------------------------------------------------------------------------


async def test_una_ficha_invalida_se_rechaza_antes_de_la_base(
    dos_negocios: tuple[Tenant, Tenant],
    cliente: AsyncClient,
    emitir: Callable[..., Awaitable[str]],
) -> None:
    """Las mismas reglas del schema, ahora sobre HTTP. Un 500 aca seria una
    validacion que quedo solo del lado del formulario."""
    mio, _ = dos_negocios
    clave = await emitir(mio, Scope.CLIENT_PORTAL)

    invalidas = [
        {"horarios": [{"dia": 9, "desde": "09:00", "hasta": "13:00"}]},  # no existe el dia 9
        {"horarios": [{"dia": 0, "desde": "09:00", "hasta": "09:00"}]},  # duracion cero
        {"horarios": [{"dia": 0, "desde": "maniana", "hasta": "13:00"}]},  # no es una hora
        {"direccion": "x" * 5000},  # se pasa del tope
        {"extras": [{"titulo": "", "texto": "algo"}]},  # bloque a medio llenar
    ]

    for cuerpo in invalidas:
        r = await cliente.put("/api/v1/portal/ficha", headers=_auth(clave), json=cuerpo)
        assert r.status_code == 422, f"{cuerpo} dio {r.status_code}, no 422"

    # Y despues de todo eso, la ficha sigue vacia: nada de eso se guardo.
    assert (await cliente.get("/api/v1/portal/ficha", headers=_auth(clave))).json()[
        "direccion"
    ] is None
