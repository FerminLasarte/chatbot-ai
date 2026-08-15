"""El portal del duenio del negocio: ver sus conversaciones y pausar su bot.

QUE ES ESTO
-----------
El cliente de la agencia no tiene usuario en el panel —el panel es de la
agencia, con una contrasena compartida que ve a TODOS los clientes—. Pero
necesita poder hacer dos cosas por su cuenta, sin llamar a nadie: mirar quien le
escribio y callar al bot en una conversacion para atenderla el mismo.

Estas rutas son exactamente esas dos cosas y ninguna mas.

★ POR QUE NO HAY `tenant_id` EN NINGUNA URL DE ESTE ARCHIVO
-----------------------------------------------------------
Las rutas de la agencia (routes/conversations.py) dicen sobre que cliente operan
en el path, porque una clave admin no tiene cliente propio. Aca seria un agujero:
el cliente final es quien manda la peticion, asi que un `tenant_id` en la URL es
un dato que el elige. Bastaria con cambiar el UUID para leerle las
conversaciones al negocio de al lado.

En cambio el tenant sale de `CurrentTenant`, que lo saca de la fila de la clave
en la base (ver deps.py). No hay parametro que cruzar: para ver los datos de
otro cliente habria que tener la clave de otro cliente.

QUE PUEDE HACER EL QUE TENGA LA CLAVE
-------------------------------------
Listar las conversaciones de SU negocio y correr la fecha de `pausada_hasta` de
una de ellas. No lee documentos, no toca el prompt, no ve el consumo ni el tope,
no puede borrar nada y no puede emitir ni revocar claves. El peor caso de una
clave filtrada es que un tercero vea los numeros de telefono y los adelantos de
mensajes de ese negocio, y le pause el bot unas horas —molesto y reversible—.
Si pasa, la agencia revoca la clave desde el panel y emite otra.
"""

import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.api.v1.deps import CurrentTenant, DbSession, PortalKey
from app.core.config import settings
from app.schemas.chat import ConversationRead, ManualModeStart, PortalTenant
from app.services import conversaciones

router = APIRouter(prefix="/portal", tags=["portal"])


def _no_encontrada() -> HTTPException:
    """404 tambien cuando la conversacion existe pero es de otro cliente.

    Un 403 confirmaria que ese id existe en algun lado, que es justo lo que no
    hace falta que sepa quien esta probando ids.
    """
    return HTTPException(status.HTTP_404_NOT_FOUND, "conversacion no encontrada")


@router.get("/me", response_model=PortalTenant)
async def mi_negocio(tenant: CurrentTenant, _: PortalKey) -> PortalTenant:
    """El nombre del negocio, para encabezar la pagina y confirmar el link.

    Tambien es la ruta que usa el frontend para validar la clave al canjearla
    por una cookie de sesion: si esto responde 200, el link sirve.
    """
    return PortalTenant(nombre=tenant.name)


@router.get("/conversations", response_model=list[ConversationRead])
async def mis_conversaciones(
    tenant: CurrentTenant,
    db: DbSession,
    _: PortalKey,
    limite: int = Query(default=50, ge=1, le=200),
) -> list[ConversationRead]:
    """Las conversaciones del propio negocio, la ultima primero."""
    return await conversaciones.listar(db, tenant.id, limite=limite)


@router.post("/conversations/{conversation_id}/manual", response_model=ConversationRead)
async def pausar_mi_bot(
    conversation_id: uuid.UUID,
    payload: ManualModeStart,
    tenant: CurrentTenant,
    db: DbSession,
    _: PortalKey,
) -> ConversationRead:
    """Silencia al bot en esa conversacion para atenderla a mano.

    El tope de una semana lo valida el schema, igual que para la agencia: no
    existe la pausa indefinida (ver `Conversation.pausada_hasta`).
    """
    horas = payload.horas if payload.horas is not None else settings.manual_mode_hours
    try:
        return await conversaciones.pausar(db, tenant.id, conversation_id, horas=horas)
    except conversaciones.ConversacionNoEncontrada as exc:
        raise _no_encontrada() from exc


@router.delete("/conversations/{conversation_id}/manual", response_model=ConversationRead)
async def reanudar_mi_bot(
    conversation_id: uuid.UUID,
    tenant: CurrentTenant,
    db: DbSession,
    _: PortalKey,
) -> ConversationRead:
    """Devuelve la conversacion al bot antes de que venza la pausa."""
    try:
        return await conversaciones.reanudar(db, tenant.id, conversation_id)
    except conversaciones.ConversacionNoEncontrada as exc:
        raise _no_encontrada() from exc
