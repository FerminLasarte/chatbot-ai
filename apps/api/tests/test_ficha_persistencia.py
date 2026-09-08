"""La ficha del negocio contra la base.

Lo que se defiende aca:

1. Un cliente que nunca cargo nada tiene una ficha VACIA, no `None`. Es lo que
   evita el tercer estado en todo el resto del codigo.

2. Lo que se guarda se lee igual, horas incluidas. Las horas son el unico tipo
   que no es JSON de por si: si se serializaran mal, el guardado explota o -peor-
   vuelve convertido en otra cosa.

3. Guardar reemplaza la ficha entera. No hay edicion parcial: es lo que hace
   que borrar un horario sea posible.

4. ★ Guardar dos veces lo mismo deja el MISMO json en la base. La ficha viaja
   en el bloque cacheado del prompt: si el json guardado variara entre
   guardados identicos, cada "Guardar" le invalidaria el cache al cliente sin
   que hubiera cambiado nada.
"""

import uuid
from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.schemas.negocio import FichaNegocio
from app.services import ficha as servicio

FICHA_COMPLETA = {
    "direccion": "Av. Siempreviva 742",
    "horarios": [
        {"dia": 0, "desde": "09:00", "hasta": "13:00"},
        {"dia": 0, "desde": "17:00", "hasta": "21:00"},
        {"dia": 5, "desde": "20:00", "hasta": "00:30"},
    ],
    "envios": "Hacemos envios en el dia dentro de CABA.",
    "medios_de_pago": "Efectivo, transferencia y todas las tarjetas.",
    "web_y_redes": "@elnegocio",
    "no_hacemos": "No tomamos reservas por WhatsApp.",
    "extras": [{"titulo": "Estacionamiento", "texto": "Hay cochera en la esquina."}],
}


@pytest_asyncio.fixture
async def tenant(db: AsyncSession) -> AsyncIterator[Tenant]:
    t = Tenant(slug=f"ficha-{uuid.uuid4().hex[:8]}", name="Negocio de prueba")
    db.add(t)
    await db.commit()
    await db.refresh(t)

    yield t

    await db.execute(delete(Tenant).where(Tenant.id == t.id))
    await db.commit()


async def test_un_cliente_nuevo_tiene_la_ficha_vacia(tenant: Tenant) -> None:
    """Sin esto habria un tercer estado -sin ficha- ademas de vacia y cargada."""
    assert tenant.business_profile == {}
    assert servicio.leer(tenant).esta_vacia()


async def test_lo_que_se_guarda_se_lee_igual(db: AsyncSession, tenant: Tenant) -> None:
    guardada = await servicio.guardar(db, tenant, FichaNegocio.model_validate(FICHA_COMPLETA))
    assert guardada == servicio.leer(tenant)
    assert guardada.direccion == "Av. Siempreviva 742"
    assert guardada.extras[0].titulo == "Estacionamiento"


async def test_las_horas_sobreviven_al_viaje(db: AsyncSession, tenant: Tenant) -> None:
    """El unico tipo de la ficha que no es JSON de por si.

    Incluye el tramo que cruza la medianoche, que es el que mas facil se rompe
    si alguien "arregla" la serializacion por su cuenta.
    """
    await servicio.guardar(db, tenant, FichaNegocio.model_validate(FICHA_COMPLETA))

    nocturno = servicio.leer(tenant).horarios[-1]
    assert (nocturno.dia, nocturno.desde.hour, nocturno.hasta.hour) == (5, 20, 0)
    assert nocturno.hasta.minute == 30


async def test_guardar_reemplaza_la_ficha_entera(db: AsyncSession, tenant: Tenant) -> None:
    """Es lo que permite BORRAR algo: no hay merge parcial."""
    await servicio.guardar(db, tenant, FichaNegocio.model_validate(FICHA_COMPLETA))

    quedo = await servicio.guardar(db, tenant, FichaNegocio(direccion="Corrientes 1234"))
    assert quedo.direccion == "Corrientes 1234"
    assert quedo.horarios == []
    assert quedo.envios is None


async def test_vaciar_la_ficha_la_deja_vacia_de_verdad(db: AsyncSession, tenant: Tenant) -> None:
    await servicio.guardar(db, tenant, FichaNegocio.model_validate(FICHA_COMPLETA))

    quedo = await servicio.guardar(db, tenant, FichaNegocio())
    assert quedo.esta_vacia()
    # Y no queda basura guardada: `exclude_defaults` deja el json en {}, que es
    # lo que hace que la ficha vaciada sea indistinguible de la de un cliente
    # que nunca la toco. Con `exclude_none` quedaban las listas vacias adentro.
    assert tenant.business_profile == {}


async def test_dos_guardados_iguales_dejan_el_mismo_json(db: AsyncSession, tenant: Tenant) -> None:
    """★ Esto es lo que protege el cache del prompt.

    Se guarda la misma ficha dos veces, la segunda con los horarios cargados al
    reves. Si el json guardado saliera distinto, apretar "Guardar" sin cambiar
    nada le costaria al cliente una invalidacion de cache.
    """
    await servicio.guardar(db, tenant, FichaNegocio.model_validate(FICHA_COMPLETA))
    primero = tenant.business_profile

    al_reves = {**FICHA_COMPLETA, "horarios": list(reversed(FICHA_COMPLETA["horarios"]))}
    await servicio.guardar(db, tenant, FichaNegocio.model_validate(al_reves))

    assert tenant.business_profile == primero


async def test_una_ficha_guardada_por_una_version_anterior_se_lee(
    db: AsyncSession, tenant: Tenant
) -> None:
    """Un campo que el schema ya no conoce no puede romper la lectura.

    Es el escenario de retirar un campo alguna vez: las fichas viejas siguen en
    la base con el campo adentro.
    """
    tenant.business_profile = {"direccion": "Corrientes 1234", "rubro_viejo": "kiosco"}
    await db.commit()

    assert servicio.leer(tenant).direccion == "Corrientes 1234"
