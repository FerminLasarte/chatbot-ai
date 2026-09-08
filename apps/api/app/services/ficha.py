"""Leer y guardar la ficha del negocio, sin saber quien esta preguntando.

POR QUE ESTO NO VIVE EN LA RUTA
-------------------------------
Mismo motivo que `services/conversaciones.py`: hay dos puertas hacia la misma
ficha y tienen autenticaciones distintas. La agencia entra por
`routes/tenants.py` con clave admin, diciendo sobre que cliente opera; el duenio
del negocio entra por `routes/portal.py` con una clave que YA trae su tenant. Si
cada ruta tuviera su copia, el dia que se corrija algo en una, el otro camino se
queda con la version vieja —y uno de los dos es el que ve el cliente final—.

Aca el `tenant` llega ya resuelto: este modulo no decide de quien es la
peticion. Quien lo llama es el responsable de que ese tenant salga de la
credencial y no de algo que mando el navegador.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.schemas.negocio import FichaNegocio


def leer(tenant: Tenant) -> FichaNegocio:
    """La ficha del cliente. Si nunca cargo nada, una ficha vacia.

    No es `async` ni recibe la sesion a proposito: el dato ya viaja en la fila
    del tenant, que quien llama tiene cargada. Es lo que hace que componer el
    prompt no cueste una consulta mas por mensaje.

    Un campo que el schema ya no conoce se ignora al validar, asi que una ficha
    guardada por una version anterior se sigue leyendo (ver `FichaNegocio`).
    """
    return FichaNegocio.model_validate(tenant.business_profile or {})


async def guardar(db: AsyncSession, tenant: Tenant, ficha: FichaNegocio) -> FichaNegocio:
    """Reemplaza la ficha entera y devuelve como quedo guardada.

    ★ Se ASIGNA un dict nuevo, nunca se muta el que ya estaba. SQLAlchemy
    detecta cambios por identidad: un `tenant.business_profile["direccion"] =
    ...` no marca la fila como sucia y el commit se va sin escribir nada, en
    silencio y sin error.

    `mode="json"` no es opcional: sin el, las horas viajan como objetos `time`
    de Python y psycopg no las sabe serializar a JSONB.

    `exclude_defaults` deja guardado solo lo que el negocio cargo de verdad, y
    con eso vaciar la ficha la deja igual que la de un cliente que nunca la
    toco. No alcanza `exclude_none`: las listas vacias de horarios y extras no
    son `None` y quedarian escritas.

    ★ Ojo al agregar un campo con un default que NO sea vacio (una zona horaria,
    por ejemplo): no se guardaria, se volveria a derivar del default al leer, y
    cambiar ese default el dia de maniana le cambiaria la ficha a todos los
    clientes de una. Un campo asi tiene que guardarse explicito.
    """
    tenant.business_profile = ficha.model_dump(mode="json", exclude_defaults=True)
    await db.commit()
    await db.refresh(tenant)
    return leer(tenant)
